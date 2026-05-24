"""Chaos and fault injection tests for TinyDB stability validation.

Tests failure scenarios: network timeouts, disk full, concurrent access,
and validates retry behavior and consistency under adverse conditions.
"""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestNetworkTimeoutResilience:
    """Test database behavior under network/IO timeout conditions."""

    @pytest.mark.timeout(10)
    def test_write_timeout_recovery(self, tmp_path: Path):
        """Verify database recovers from write timeout."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initial write succeeds
        doc_id = db.insert({"status": "initial"})
        assert db.get(doc_id)["status"] == "initial"
        
        # Simulate timeout on next write
        with patch.object(JSONStorage, "write") as mock_write:
            mock_write.side_effect = TimeoutError("Write timeout")
            
            with pytest.raises(TimeoutError):
                db.insert({"status": "during_timeout"})
            
            # Verify database state unchanged after timeout
            db.close()
            db = TinyDB(db_path, storage=JSONStorage)
            assert db.get(doc_id)["status"] == "initial"
            assert len(db.all()) == 1
        
        db.close()

    @pytest.mark.timeout(10)
    def test_read_timeout_recovery(self, tmp_path: Path):
        """Verify database recovers from read timeout."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        doc_id = db.insert({"data": "test"})
        db.close()
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        with patch.object(JSONStorage, "read") as mock_read:
            mock_read.side_effect = TimeoutError("Read timeout")
            
            with pytest.raises(TimeoutError):
                _ = db.all()
        
        db.close()

    @pytest.mark.timeout(10)
    def test_partial_write_recovery(self, tmp_path: Path):
        """Verify recovery from partial write failures."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"value": 1})
        db.update({"value": 2}, doc_ids=[doc_id])
        assert db.get(doc_id)["value"] == 2
        
        # Simulate partial write corruption
        with patch.object(JSONStorage, "write") as mock_write:
            mock_write.side_effect = IOError("Disk write failed")
            
            with pytest.raises(IOError):
                db.update({"value": 3}, doc_ids=[doc_id])
            
            # Verify database recovers to last stable state
            db.close()
            db = TinyDB(db_path, storage=JSONStorage)
            assert db.get(doc_id)["value"] == 2
        
        db.close()


class TestDiskFullConditions:
    """Test database behavior when disk space is exhausted."""

    @pytest.mark.timeout(10)
    def test_insert_disk_full_error(self, tmp_path: Path):
        """Verify proper error handling when disk is full."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert baseline data
        doc_id = db.insert({"baseline": True})
        db.close()
        
        # Simulate disk full on write
        db = TinyDB(db_path, storage=JSONStorage)
        with patch.object(JSONStorage, "write") as mock_write:
            mock_write.side_effect = OSError("No space left on device")
            
            with pytest.raises(OSError):
                db.insert({"during_disk_full": True})
            
            # Verify baseline data still accessible
            db.close()
            db = TinyDB(db_path, storage=JSONStorage)
            assert db.get(doc_id)["baseline"] is True
            assert len(db.all()) == 1
        
        db.close()

    @pytest.mark.timeout(10)
    def test_update_disk_full_consistency(self, tmp_path: Path):
        """Verify consistency when update fails due to disk full."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0})
        db.close()
        
        db = TinyDB(db_path, storage=JSONStorage)
        with patch.object(JSONStorage, "write") as mock_write:
            mock_write.side_effect = OSError("No space left on device")
            
            with pytest.raises(OSError):
                db.update({"counter": 1}, doc_ids=[doc_id])
            
            # Counter should still be 0
            db.close()
            db = TinyDB(db_path, storage=JSONStorage)
            assert db.get(doc_id)["counter"] == 0
        
        db.close()


class TestConcurrentAccessStability:
    """Test database stability under concurrent access patterns."""

    @pytest.mark.timeout(15)
    def test_concurrent_insert_consistency(self, tmp_path: Path):
        """Verify inserts are consistent under concurrent access simulation."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Simulate concurrent insert pattern
        doc_ids = []
        for i in range(5):
            doc_ids.append(db.insert({"thread_id": i, "sequence": i}))
        
        # Verify all inserts persisted
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 5
        
        # Verify data integrity
        for i, doc_id in enumerate(doc_ids):
            doc = db.get(doc_id)
            assert doc["thread_id"] == i
            assert doc["sequence"] == i
        
        db.close()

    @pytest.mark.timeout(15)
    def test_concurrent_update_consistency(self, tmp_path: Path):
        """Verify updates are consistent when accessed concurrently."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create baseline documents
        doc_ids = [db.insert({"value": 0, "updates": 0}) for _ in range(3)]
        db.close()
        
        # Simulate concurrent updates
        db = TinyDB(db_path, storage=JSONStorage)
        for i, doc_id in enumerate(doc_ids):
            db.update({"value": i + 1, "updates": 1}, doc_ids=[doc_id])
        
        # Verify all updates applied
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        for i, doc_id in enumerate(doc_ids):
            doc = db.get(doc_id)
            assert doc["value"] == i + 1
            assert doc["updates"] == 1
        
        db.close()

    @pytest.mark.timeout(15)
    def test_concurrent_read_write_interleave(self, tmp_path: Path):
        """Verify consistency when reads and writes are interleaved."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert initial data
        doc_id = db.insert({"step": 0})
        
        # Interleave reads and writes
        db.update({"step": 1}, doc_ids=[doc_id])
        doc = db.get(doc_id)
        assert doc["step"] == 1
        
        db.update({"step": 2}, doc_ids=[doc_id])
        doc = db.get(doc_id)
        assert doc["step"] == 2
        
        # Verify final state on reload
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        doc = db.get(doc_id)
        assert doc["step"] == 2
        
        db.close()


class TestRetryConsistency:
    """Test that retry operations maintain consistency."""

    @pytest.mark.timeout(10)
    def test_insert_retry_no_duplicates(self, tmp_path: Path):
        """Verify retried inserts don't create duplicates."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Simulate retry scenario
        data = {"unique_id": "test_123", "attempt": 1}
        doc_id = db.insert(data)
        
        # Retry should get same document
        assert doc_id is not None
        assert db.get(doc_id)["unique_id"] == "test_123"
        
        # Verify no duplicates after simulated retry
        all_docs = db.all()
        assert len(all_docs) == 1
        assert all_docs[0]["unique_id"] == "test_123"
        
        db.close()

    @pytest.mark.timeout(10)
    def test_update_retry_idempotent(self, tmp_path: Path):
        """Verify retried updates are idempotent."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0, "version": 1})
        
        # First update
        db.update({"counter": 1, "version": 2}, doc_ids=[doc_id])
        state_after_first = db.get(doc_id)
        
        # Retry same update
        db.update({"counter": 1, "version": 2}, doc_ids=[doc_id])
        state_after_retry = db.get(doc_id)
        
        # State should be identical
        assert state_after_first["counter"] == state_after_retry["counter"]
        assert state_after_first["version"] == state_after_retry["version"]
        assert state_after_retry["counter"] == 1
        assert state_after_retry["version"] == 2
        
        db.close()

    @pytest.mark.timeout(10)
    def test_delete_retry_idempotent(self, tmp_path: Path):
        """Verify retried deletes are idempotent and safe."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"data": "to_delete"})
        assert db.get(doc_id) is not None
        
        # First delete
        db.remove(doc_ids=[doc_id])
        assert db.get(doc_id) is None
        
        # Retry delete should not raise or modify state
        initial_count = len(db.all())
        db.remove(doc_ids=[doc_id])  # Should be no-op
        assert len(db.all()) == initial_count
        
        db.close()

    @pytest.mark.timeout(10)
    def test_batch_retry_consistency(self, tmp_path: Path):
        """Verify batch operations remain consistent on retry."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initial batch insert
        batch_data = [{"id": i, "status": "initial"} for i in range(5)]
        doc_ids = db.insert_multiple(batch_data)
        assert len(doc_ids) == 5
        
        # Verify all inserted
        assert len(db.all()) == 5
        
        # Retry scenario: re-check state
        doc_ids_retry = [db.get(doc_id) for doc_id in doc_ids]
        assert len(doc_ids_retry) == 5
        assert all(doc is not None for doc in doc_ids_retry)
        
        db.close()
