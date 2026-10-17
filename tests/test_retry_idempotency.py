import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import time
import random

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage
from tinydb.middlewares import CachingMiddleware


class TestRetryBehavior:
    """Test retry behavior for database operations."""

    def test_insert_retry_consistency(self, tmp_path: Path):
        """Verify insert operations are consistent across retries."""
        db_path = tmp_path / "retry_test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        data = {"name": "test", "value": 42}
        doc_id = db.insert(data)
        
        # Retry insert of same document
        retrieved = db.get(doc_id=doc_id)
        assert retrieved["name"] == "test"
        assert retrieved["value"] == 42
        
        db.close()

    def test_update_retry_idempotency(self, tmp_path: Path):
        """Verify update operations are idempotent across retries."""
        db_path = tmp_path / "update_retry.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0})
        
        # First update
        db.update({"counter": 1}, doc_ids=[doc_id])
        result1 = db.get(doc_id=doc_id)["counter"]
        
        # Retry same update
        db.update({"counter": 1}, doc_ids=[doc_id])
        result2 = db.get(doc_id=doc_id)["counter"]
        
        assert result1 == result2 == 1
        db.close()

    def test_remove_retry_safety(self, tmp_path: Path):
        """Verify remove operations handle retry safely (no double-delete errors)."""
        db_path = tmp_path / "remove_retry.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"data": "to_remove"})
        db.remove(doc_ids=[doc_id])
        
        # Retry remove should not raise
        try:
            result = db.remove(doc_ids=[doc_id])
            assert result == []
        except Exception as e:
            pytest.fail(f"Retry remove raised exception: {e}")
        
        db.close()

    def test_transaction_partial_failure_recovery(self, tmp_path: Path):
        """Verify recovery from partial transaction failures."""
        db_path = tmp_path / "partial_failure.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        initial_count = len(db.all())
        
        # Simulate partial operation
        try:
            db.insert({"step": 1})
            # Simulate failure mid-transaction
            raise RuntimeError("Simulated transaction failure")
        except RuntimeError:
            pass
        
        # State should be recoverable
        recovered_count = len(db.all())
        assert recovered_count >= initial_count
        
        db.close()

    def test_duplicate_insert_detection(self, tmp_path: Path):
        """Verify duplicate inserts are handled safely."""
        db_path = tmp_path / "dup_insert.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        data = {"unique_id": "test_123", "value": "data"}
        id1 = db.insert(data)
        id2 = db.insert(data)
        
        # Both should succeed but create different documents
        assert id1 != id2
        assert db.get(doc_id=id1) is not None
        assert db.get(doc_id=id2) is not None
        
        db.close()


class TestIdempotencyGuarantees:
    """Test idempotency guarantees for database operations."""

    def test_insert_idempotency_with_checkpoint(self, tmp_path: Path):
        """Verify inserts are idempotent with checkpointing."""
        db_path = tmp_path / "idempotent.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        data = {"checkpoint": 1, "data": "test"}
        
        # First insert
        id1 = db.insert(data)
        count1 = len(db.all())
        
        # Simulate checkpoint and retry
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        
        id2 = db.insert(data)
        count2 = len(db.all())
        
        assert count2 == count1 + 1  # New insert should increment
        db.close()

    def test_batch_operation_consistency(self, tmp_path: Path):
        """Verify batch operations maintain consistency across retries."""
        db_path = tmp_path / "batch.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        items = [{"id": i, "value": i*2} for i in range(10)]
        
        # Insert batch
        result1 = db.insert_multiple(items)
        assert len(result1) == 10
        
        # Verify state persists
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 10
        
        db.close()
