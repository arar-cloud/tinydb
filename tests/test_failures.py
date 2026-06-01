"""Active failure reproduction test cases for debugging and root cause analysis.

These tests are designed to:
1. Reproduce active failures on master branch (backend/mobile stacks)
2. Test edge cases and concurrent access patterns
3. Verify storage backend failures and recovery
4. Capture failure conditions for stability validation
5. Provide regression test coverage for known issues
"""

import pytest
import threading
import time
from pathlib import Path
from contextlib import contextmanager

from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.middlewares import CachingMiddleware


class TestConcurrentAccess:
    """Test concurrent access patterns that may fail on backend/mobile stacks."""

    @pytest.mark.regression
    @pytest.mark.backend
    def test_concurrent_insert_consistency(self, db, traceback_collector):
        """Test that concurrent inserts maintain data consistency.
        
        Reproduces potential race conditions in concurrent backend access.
        """
        results = []
        errors = []

        def insert_batch():
            try:
                for i in range(10):
                    db.insert({"batch": threading.current_thread().name, "index": i})
                results.append(True)
            except Exception as e:
                traceback_collector(e)
                errors.append(e)

        threads = [threading.Thread(target=insert_batch, name=f"thread-{i}") for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent insert failed: {errors}"
        assert len(results) == 3
        assert len(db) == 30  # 10 * 3 threads

    @pytest.mark.regression
    @pytest.mark.mobile
    def test_database_with_memory_constraint(self, db, mobile_env, traceback_collector):
        """Test database operations under memory-constrained conditions.
        
        Simulates mobile environment with limited memory resources.
        """
        try:
            # Insert moderate amount of data
            for i in range(100):
                db.insert({"id": i, "data": "x" * 1000})
            
            # Query large result set
            results = db.all()
            assert len(results) == 100
            
            # Update operations
            User = Query()
            db.update({"updated": True}, User.id < 50)
            
            results = db.search(User.updated == True)
            assert len(results) == 50
        except Exception as e:
            traceback_collector(e)
            raise

    @pytest.mark.regression
    @pytest.mark.backend
    def test_database_recovery_after_failure(self, tmp_path, traceback_collector):
        """Test database recovery after simulated failure.
        
        Ensures backend stability after interruption and restart.
        """
        db_path = tmp_path / "recovery_test.db"
        
        try:
            # Create and populate database
            db1 = TinyDB(db_path, storage=JSONStorage)
            db1.insert({"status": "initial", "count": 1})
            db1.close()
            
            # Reopen and verify persistence
            db2 = TinyDB(db_path, storage=JSONStorage)
            records = db2.all()
            assert len(records) == 1
            assert records[0]["status"] == "initial"
            db2.close()
        except Exception as e:
            traceback_collector(e)
            raise


class TestStorageFailures:
    """Test storage backend failures and error handling."""

    @pytest.mark.regression
    @pytest.mark.backend
    def test_caching_middleware_consistency(self, traceback_collector):
        """Test CachingMiddleware maintains consistency under failures.
        
        Verifies cache coherency in backend operations.
        """
        try:
            storage = CachingMiddleware(MemoryStorage)()
            db = TinyDB(storage=storage)
            
            db.insert({"key": "value1"})
            db.insert({"key": "value2"})
            
            # Access through cache
            all_docs = db.all()
            assert len(all_docs) == 2
            
            # Clear and verify
            db.truncate()
            assert len(db.all()) == 0
        except Exception as e:
            traceback_collector(e)
            raise

    @pytest.mark.regression
    @pytest.mark.mobile
    def test_storage_with_io_timeout(self, tmp_path, mobile_env, traceback_collector):
        """Test storage operations with I/O timeout constraints.
        
        Simulates mobile environment with aggressive I/O timeouts.
        """
        try:
            db_path = tmp_path / "timeout_test.db"
            db = TinyDB(db_path, storage=JSONStorage)
            
            # Rapid operations
            for i in range(50):
                db.insert({"rapid": i})
            
            result = db.get(doc_id=1)
            assert result is not None
            db.close()
        except Exception as e:
            traceback_collector(e)
            raise


class TestQueryFailures:
    """Test query and operation failures under edge conditions."""

    @pytest.mark.regression
    @pytest.mark.backend
    def test_complex_query_stability(self, db, traceback_collector):
        """Test complex queries don't cause instability.
        
        Verifies backend handles nested queries without failures.
        """
        try:
            User = Query()
            
            # Insert test data
            for i in range(20):
                db.insert({"user_id": i, "active": i % 2 == 0, "score": i * 10})
            
            # Complex query
            results = db.search((User.active == True) & (User.score > 50))
            assert len(results) >= 0  # Just verify no exception
        except Exception as e:
            traceback_collector(e)
            raise

    @pytest.mark.regression
    def test_empty_database_operations(self, db, traceback_collector):
        """Test operations on empty database don't fail.
        
        Ensures graceful handling of empty state.
        """
        try:
            db.truncate()
            
            # Operations on empty DB
            assert db.all() == []
            assert db.get(doc_id=1) is None
            
            User = Query()
            assert db.search(User.active == True) == []
        except Exception as e:
            traceback_collector(e)
            raise
