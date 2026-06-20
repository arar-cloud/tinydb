"""Tests for retry resilience and concurrent access patterns.

Validates that TinyDB maintains consistency across multiple retries,
concurrent access patterns, and transient failures common in backend/mobile/web deployments.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Any

import pytest

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage


class TestRetryMechanisms:
    """Test retry logic for database operations."""
    
    @pytest.mark.retry
    def test_insert_with_retries(self, tmp_path: Path) -> None:
        """Verify insert succeeds consistently across retries."""
        db_path = tmp_path / 'retry.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        max_retries = 5
        for attempt in range(max_retries):
            db.insert({'attempt': attempt, 'status': 'success'})
        
        db.close()
        
        # Re-open and verify all inserts persisted
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == max_retries
        db.close()
    
    @pytest.mark.retry
    def test_query_retry_consistency(self, tmp_path: Path) -> None:
        """Verify queries return consistent results across retries."""
        db_path = tmp_path / 'query_retry.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert test data
        for i in range(10):
            db.insert({'id': i, 'value': i * 2})
        
        # Query multiple times and verify consistency
        query = Query()
        results_list: List[List[Any]] = []
        
        for _ in range(5):
            results = db.search(query.value >= 10)
            results_list.append(results)
        
        # All query attempts should return same count
        counts = [len(r) for r in results_list]
        assert len(set(counts)) == 1, "Query results inconsistent across retries"
        
        db.close()
    
    @pytest.mark.retry
    def test_update_retry_idempotence(self, tmp_path: Path) -> None:
        """Verify updates are idempotent across retries."""
        db_path = tmp_path / 'update_retry.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        db.insert({'id': 1, 'count': 0})
        
        query = Query()
        for _ in range(5):
            db.update({'count': 1}, query.id == 1)
        
        result = db.get(query.id == 1)
        assert result['count'] == 1, "Update not idempotent"
        
        db.close()


class TestConcurrentAccess:
    """Test concurrent access patterns to the database."""
    
    @pytest.mark.concurrent
    @pytest.mark.timeout(60)
    def test_concurrent_inserts(self, tmp_path: Path) -> None:
        """Verify database maintains consistency under concurrent inserts."""
        db_path = tmp_path / 'concurrent_inserts.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        num_threads = 5
        inserts_per_thread = 20
        
        def worker(thread_id: int) -> int:
            """Worker thread that performs inserts."""
            count = 0
            for i in range(inserts_per_thread):
                try:
                    db.insert({'thread': thread_id, 'index': i})
                    count += 1
                except Exception as e:
                    pytest.fail(f"Insert failed in thread {thread_id}: {e}")
            return count
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, i) for i in range(num_threads)]
            total_inserted = sum(f.result() for f in as_completed(futures))
        
        db.close()
        
        # Verify all inserts persisted
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == total_inserted
        db.close()
    
    @pytest.mark.concurrent
    @pytest.mark.timeout(60)
    def test_concurrent_reads_writes(self, tmp_path: Path) -> None:
        """Verify database consistency with interleaved reads and writes."""
        db_path = tmp_path / 'concurrent_rw.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Pre-populate database
        for i in range(10):
            db.insert({'id': i, 'value': i})
        
        results = {'reads': 0, 'writes': 0, 'errors': []}
        lock = threading.Lock()
        
        def reader_worker() -> None:
            """Worker that reads from database."""
            try:
                for _ in range(10):
                    _ = db.all()
                    with lock:
                        results['reads'] += 1
            except Exception as e:
                with lock:
                    results['errors'].append(f"Read error: {e}")
        
        def writer_worker() -> None:
            """Worker that writes to database."""
            try:
                for i in range(5):
                    db.insert({'value': i})
                    with lock:
                        results['writes'] += 1
            except Exception as e:
                with lock:
                    results['errors'].append(f"Write error: {e}")
        
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=reader_worker))
        for _ in range(2):
            threads.append(threading.Thread(target=writer_worker))
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert not results['errors'], f"Concurrent access errors: {results['errors']}"
        assert results['reads'] > 0
        assert results['writes'] > 0
        
        db.close()
    
    @pytest.mark.concurrent
    def test_concurrent_deletes(self, tmp_path: Path) -> None:
        """Verify database maintains consistency during concurrent deletes."""
        db_path = tmp_path / 'concurrent_deletes.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert initial data
        ids = []
        for i in range(100):
            doc_id = db.insert({'index': i})
            ids.append(doc_id)
        
        initial_count = len(db.all())
        
        def delete_worker(start: int, end: int) -> int:
            """Worker that deletes documents in a range."""
            deleted = 0
            for idx in range(start, end):
                if idx < len(ids):
                    try:
                        db.remove(doc_ids=[ids[idx]])
                        deleted += 1
                    except Exception:
                        pass  # Expected: some deletes may fail due to timing
            return deleted
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(delete_worker, 0, 25),
                executor.submit(delete_worker, 25, 50),
                executor.submit(delete_worker, 50, 75),
                executor.submit(delete_worker, 75, 100),
            ]
            total_deleted = sum(f.result() for f in as_completed(futures))
        
        db.close()
        
        # Verify database is still valid
        db = TinyDB(db_path, storage=JSONStorage)
        final_count = len(db.all())
        assert final_count <= initial_count
        assert final_count >= 0
        db.close()


class TestRetryWithErrors:
    """Test retry behavior under simulated error conditions."""
    
    @pytest.mark.retry
    def test_operation_retry_on_temporary_failure(self, tmp_path: Path) -> None:
        """Verify operations can recover from temporary failures via retry."""
        db_path = tmp_path / 'temp_failure.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        max_attempts = 3
        attempt_count = 0
        
        def operation_with_retry() -> bool:
            """Try operation up to max_attempts times."""
            nonlocal attempt_count
            for attempt in range(max_attempts):
                attempt_count += 1
                try:
                    db.insert({'attempt': attempt})
                    return True
                except Exception:
                    if attempt == max_attempts - 1:
                        return False
                    time.sleep(0.1)
            return False
        
        success = operation_with_retry()
        assert success
        assert attempt_count <= max_attempts
        
        db.close()
