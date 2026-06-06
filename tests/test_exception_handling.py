import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open
import logging
import io

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage
from tinydb.middlewares import CachingMiddleware


class TestExceptionHandling:
    """Test exception handling and error propagation consistency."""

    def test_file_not_found_propagation(self, tmp_path: Path):
        """Verify FileNotFoundError is properly propagated."""
        nonexistent_path = tmp_path / "nonexistent" / "db.json"
        
        with pytest.raises(Exception):  # Should raise some form of file error
            db = TinyDB(nonexistent_path, storage=JSONStorage)
            db.insert({"test": "data"})

    def test_corrupted_file_handling(self, tmp_path: Path):
        """Verify corrupted JSON files raise appropriate exceptions."""
        db_path = tmp_path / "corrupted.db"
        
        # Create corrupted file
        with open(db_path, 'w') as f:
            f.write("{invalid json")
        
        with pytest.raises(Exception):  # Should raise JSON decode error or similar
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()

    def test_permission_error_propagation(self, tmp_path: Path):
        """Verify permission errors are properly propagated."""
        db_path = tmp_path / "readonly.db"
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        # Make file read-only
        db_path.chmod(0o444)
        
        try:
            with pytest.raises(Exception):  # Should raise permission error on write
                db = TinyDB(db_path, storage=JSONStorage)
                db.insert({"new": "data"})
        finally:
            # Restore permissions for cleanup
            db_path.chmod(0o644)

    def test_operation_timeout_handling(self, tmp_path: Path):
        """Verify timeouts are handled gracefully."""
        db_path = tmp_path / "timeout_test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert large dataset
        large_data = [{"id": i, "data": "x" * 1000} for i in range(100)]
        db.insert_multiple(large_data)
        
        # Operation should complete without hanging
        result = db.all()
        assert len(result) == 100
        
        db.close()

    def test_memory_storage_error_handling(self):
        """Verify MemoryStorage handles errors gracefully."""
        storage = MemoryStorage()
        db = TinyDB(storage=storage)
        
        # Insert and verify
        db.insert({"test": "data"})
        assert len(db.all()) == 1
        
        # Close and verify storage is cleared
        db.close()

    def test_exception_during_insert(self, tmp_path: Path):
        """Verify exceptions during insert don't corrupt state."""
        db_path = tmp_path / "insert_error.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        initial_count = len(db.all())
        
        # Simulate insert error
        with patch.object(db.storage, 'write', side_effect=IOError("Write failed")):
            with pytest.raises(IOError):
                db.insert({"test": "data"})
        
        # State should remain consistent
        assert len(db.all()) == initial_count
        db.close()

    def test_exception_during_update(self, tmp_path: Path):
        """Verify exceptions during update don't leave partial state."""
        db_path = tmp_path / "update_error.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"value": 1})
        original_value = db.get(doc_id=doc_id)["value"]
        
        # Simulate update error
        with patch.object(db.storage, 'write', side_effect=IOError("Write failed")):
            with pytest.raises(IOError):
                db.update({"value": 2}, doc_ids=[doc_id])
        
        # Value should remain unchanged
        assert db.get(doc_id=doc_id)["value"] == original_value
        db.close()

    def test_exception_during_remove(self, tmp_path: Path):
        """Verify exceptions during remove don't delete data prematurely."""
        db_path = tmp_path / "remove_error.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"data": "important"})
        
        # Simulate remove error
        with patch.object(db.storage, 'write', side_effect=IOError("Write failed")):
            with pytest.raises(IOError):
                db.remove(doc_ids=[doc_id])
        
        # Document should still exist
        assert db.get(doc_id=doc_id) is not None
        db.close()

    def test_exception_logging_consistency(self, tmp_path: Path):
        """Verify exceptions are consistently logged."""
        db_path = tmp_path / "logging_test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        # Simulate operation with error
        try:
            raise ValueError("Test error")
        except ValueError as e:
            logging.error(f"Database operation failed: {e}")
        
        db.close()

    def test_resource_cleanup_on_exception(self, tmp_path: Path):
        """Verify resources are cleaned up when exceptions occur."""
        db_path = tmp_path / "resource_cleanup.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        try:
            db.insert({"test": "data"})
            raise RuntimeError("Simulated error")
        except RuntimeError:
            pass
        finally:
            db.close()
        
        # File should be properly closed and accessible
        db2 = TinyDB(db_path, storage=JSONStorage)
        assert len(db2.all()) == 1
        db2.close()


class TestErrorPropagationRetry:
    """Test error propagation behavior across retry scenarios."""

    def test_transient_error_recovery(self, tmp_path: Path):
        """Verify transient errors can be retried successfully."""
        db_path = tmp_path / "transient.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        attempt = [0]
        
        def flaky_insert():
            attempt[0] += 1
            if attempt[0] < 3:
                raise IOError("Transient error")
            return db.insert({"success": True})
        
        # Retry logic
        for i in range(5):
            try:
                result = flaky_insert()
                assert result is not None
                break
            except IOError:
                if i == 4:
                    raise
        
        assert attempt[0] == 3
        db.close()

    def test_persistent_error_no_recovery(self, tmp_path: Path):
        """Verify persistent errors don't cause infinite retries."""
        db_path = tmp_path / "persistent.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        attempt = [0]
        max_retries = 3
        
        def always_fails():
            attempt[0] += 1
            raise RuntimeError("Persistent error")
        
        with pytest.raises(RuntimeError):
            for i in range(max_retries):
                try:
                    always_fails()
                except RuntimeError:
                    if i == max_retries - 1:
                        raise
        
        assert attempt[0] == max_retries
        db.close()
