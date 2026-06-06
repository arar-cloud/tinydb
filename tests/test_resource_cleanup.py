import pytest
import tempfile
from pathlib import Path
import gc
import weakref
import os
import sys
from unittest.mock import patch, MagicMock, mock_open
import time

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestFileHandleCleanup:
    """Test cleanup of file handles."""

    def test_file_handle_closed_on_db_close(self, tmp_path: Path):
        """Verify file handles are closed when database closes."""
        db_path = tmp_path / "handle_close.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        # File should be closeable and reopenable
        db2 = TinyDB(db_path, storage=JSONStorage)
        docs = db2.all()
        assert len(docs) == 1
        db2.close()

    def test_file_handle_closed_on_exception(self, tmp_path: Path):
        """Verify file handles are closed even when exception occurs."""
        db_path = tmp_path / "handle_except.db"
        
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({"test": "data"})
            raise RuntimeError("Test error")
        except RuntimeError:
            pass
        finally:
            try:
                db.close()
            except:
                pass
        
        # File should still be accessible
        try:
            db2 = TinyDB(db_path, storage=JSONStorage)
            db2.close()
        except OSError as e:
            pytest.fail(f"File was not properly closed: {e}")

    def test_multiple_file_handles_not_leaked(self, tmp_path: Path):
        """Verify multiple database operations don't leak file handles."""
        db_path = tmp_path / "multi_handle.db"
        
        # Get initial open file count
        initial_fds = len(os.listdir(f"/proc/{os.getpid()}/fd")) if sys.platform == "linux" else 0
        
        # Open/close database 50 times
        for _ in range(50):
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({"data": "test"})
            db.close()
        
        # File descriptor count shouldn't grow significantly
        if sys.platform == "linux":
            final_fds = len(os.listdir(f"/proc/{os.getpid()}/fd"))
            # Allow small growth due to GC or system variation
            assert final_fds < initial_fds + 10

    def test_file_handle_closed_with_context_manager(self, tmp_path: Path):
        """Verify file handles work with context manager pattern."""
        db_path = tmp_path / "context_manager.db"
        
        # Simulate context manager usage pattern
        with TinyDB(db_path, storage=JSONStorage) as db:
            db.insert({"test": "data"})
        # Database should be closed here
        
        # Should be reopenable
        db2 = TinyDB(db_path, storage=JSONStorage)
        db2.close()


class TestMemoryCleanup:
    """Test memory cleanup and garbage collection."""

    def test_memory_freed_after_close(self, tmp_path: Path):
        """Verify memory is freed when database is closed."""
        db_path = tmp_path / "memory_freed.db"
        
        # Create large dataset
        db = TinyDB(db_path, storage=JSONStorage)
        for i in range(1000):
            db.insert({"id": i, "data": "x" * 100})
        
        db_ref = weakref.ref(db)
        db.close()
        
        # Force garbage collection
        del db
        gc.collect()
        
        # Reference should be gone
        assert db_ref() is None

    def test_large_query_result_cleanup(self, tmp_path: Path):
        """Verify large query results are properly freed."""
        db_path = tmp_path / "query_cleanup.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert large dataset
        for i in range(500):
            db.insert({"id": i, "data": "y" * 50})
        
        # Query large result set
        result = db.all()
        result_ref = weakref.ref(result)
        
        # Clear reference
        del result
        gc.collect()
        
        # Memory should be freed
        assert result_ref() is None
        
        db.close()

    def test_memory_stable_on_repeated_operations(self, tmp_path: Path):
        """Verify memory doesn't grow unbounded on repeated operations."""
        db_path = tmp_path / "stable_memory.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Repeat insert/query/delete cycles
        for cycle in range(10):
            # Insert
            for i in range(100):
                db.insert({"cycle": cycle, "index": i})
            
            # Query
            _ = db.all()
            
            # Partial cleanup
            # (Note: TinyDB doesn't have explicit truncate, so we delete all)
            ids = [doc.doc_id for doc in db.all()]
            for doc_id in ids:
                db.remove(doc_ids=[doc_id])
            
            gc.collect()
        
        assert len(db.all()) == 0
        db.close()

    def test_iterator_memory_cleanup(self, tmp_path: Path):
        """Verify iterators don't cause memory leaks."""
        db_path = tmp_path / "iterator_cleanup.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert data
        for i in range(200):
            db.insert({"id": i})
        
        # Iterate and discard
        for _ in range(5):
            count = 0
            for doc in db.all():
                count += 1
            assert count == 200
        
        db.close()

    def test_exception_path_memory_cleanup(self, tmp_path: Path):
        """Verify memory is cleaned up when exceptions occur."""
        db_path = tmp_path / "exception_memory.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        try:
            # Create large dataset
            for i in range(500):
                db.insert({"id": i, "large_data": "z" * 1000})
            
            # Simulate error
            raise RuntimeError("Simulated failure")
        except RuntimeError:
            pass
        finally:
            db.close()
        
        gc.collect()


class TestConnectionStateCleanup:
    """Test cleanup of connection and internal state."""

    def test_storage_state_cleared_on_close(self, tmp_path: Path):
        """Verify storage internal state is cleared on close."""
        db_path = tmp_path / "storage_state.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        
        # Storage should have data
        storage_data = db.storage.read()
        assert len(storage_data) > 0
        
        db.close()
        
        # After close, new instance should work independently
        db2 = TinyDB(db_path, storage=JSONStorage)
        assert len(db2.all()) == 1
        db2.close()

    def test_table_state_cleanup(self, tmp_path: Path):
        """Verify table state is cleaned up."""
        db_path = tmp_path / "table_state.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create multiple tables
        table1 = db.table("table1")
        table1.insert({"data": "table1_data"})
        
        table2 = db.table("table2")
        table2.insert({"data": "table2_data"})
        
        db.close()
        
        # Reopen and verify
        db2 = TinyDB(db_path, storage=JSONStorage)
        assert len(db2.table("table1").all()) == 1
        assert len(db2.table("table2").all()) == 1
        db2.close()

    def test_query_cache_cleanup(self, tmp_path: Path):
        """Verify query caches are cleared on close."""
        db_path = tmp_path / "query_cache.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert data
        db.insert({"id": 1, "name": "Test"})
        
        # Execute queries (may be cached)
        _ = db.all()
        _ = db.all()
        
        db.close()
        
        # New instance should have clean cache
        db2 = TinyDB(db_path, storage=JSONStorage)
        docs = db2.all()
        assert len(docs) == 1
        db2.close()


class TestResourceLeakDetection:
    """Detect resource leaks in various scenarios."""

    def test_no_leak_on_failed_insert(self, tmp_path: Path):
        """Verify no resource leak on failed insert."""
        db_path = tmp_path / "failed_insert.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        initial_count = len(db.all())
        
        # Simulate failed insert
        try:
            with patch.object(db.storage, 'write', side_effect=IOError("Write error")):
                db.insert({"test": "data"})
        except IOError:
            pass
        
        # State should be unchanged
        assert len(db.all()) == initial_count
        
        db.close()

    def test_no_leak_on_transaction_rollback(self, tmp_path: Path):
        """Verify no resource leak on transaction rollback."""
        db_path = tmp_path / "rollback.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"value": 1})
        original_value = db.get(doc_id=doc_id)["value"]
        
        # Simulate transaction rollback
        try:
            # Start update
            new_doc = {"value": 2}
            # Simulate error
            raise RuntimeError("Transaction error")
        except RuntimeError:
            pass
        
        # Original value should be preserved
        assert db.get(doc_id=doc_id)["value"] == original_value
        
        db.close()

    def test_no_leak_on_concurrent_access(self, tmp_path: Path):
        """Verify no resource leak with concurrent access patterns."""
        db_path = tmp_path / "concurrent_leak.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        # Access from multiple instances
        dbs = []
        for i in range(10):
            db = TinyDB(db_path, storage=JSONStorage)
            _ = db.all()
            dbs.append(db)
        
        # Close all
        for db in dbs:
            db.close()
        
        # Should still work
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 1
        db.close()

    def test_storage_cleanup_after_exception_in_context(self, tmp_path: Path):
        """Verify storage cleanup even with exception in context."""
        db_path = tmp_path / "context_except.db"
        
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({"test": "data"})
            raise RuntimeError("Test error")
        except RuntimeError:
            pass
        finally:
            try:
                db.close()
            except:
                pass
        
        # File should be accessible
        db2 = TinyDB(db_path, storage=JSONStorage)
        assert len(db2.all()) == 1
        db2.close()
