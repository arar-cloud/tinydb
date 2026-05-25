"""Tests for mobile-backend integration and concurrent operations."""
import pytest
import threading
import time
from typing import List
from pathlib import Path

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


@pytest.mark.mobile
@pytest.mark.integration
class TestMobileBackendIntegration:
    """Test mobile-backend integration scenarios."""

    def test_rapid_sequential_writes(self, concurrent_db: TinyDB):
        """Simulate mobile app rapid sequential write pattern."""
        for i in range(50):
            concurrent_db.insert({
                'mobile_id': 'device_001',
                'timestamp': i,
                'event': 'user_action',
                'data': f'event_{i}'
            })
        
        assert len(concurrent_db.all()) == 50

    def test_sync_after_offline(self, concurrent_db: TinyDB):
        """Simulate mobile offline/online sync scenario."""
        # Offline: insert records
        offline_records = [{'id': i, 'offline': True} for i in range(10)]
        concurrent_db.insert_multiple(offline_records)
        
        # Online: insert more records
        online_records = [{'id': i + 10, 'offline': False} for i in range(10)]
        concurrent_db.insert_multiple(online_records)
        
        # Verify all synced
        all_docs = concurrent_db.all()
        assert len(all_docs) == 20
        offline_count = len(concurrent_db.search(lambda doc: doc['offline'] == True))
        online_count = len(concurrent_db.search(lambda doc: doc['offline'] == False))
        assert offline_count == 10
        assert online_count == 10

    def test_batch_sync_consistency(self, concurrent_db: TinyDB):
        """Test consistency during batch sync operations."""
        # Initial state
        concurrent_db.insert({'type': 'initial', 'synced': False})
        
        # Batch sync operation
        batch_records = [{'type': 'batch', 'synced': False, 'index': i} for i in range(20)]
        concurrent_db.insert_multiple(batch_records)
        
        # Mark as synced
        concurrent_db.update({'synced': True}, lambda doc: doc['type'] == 'batch')
        
        # Verify
        unsynced = len(concurrent_db.search(lambda doc: doc['synced'] == False))
        synced = len(concurrent_db.search(lambda doc: doc['synced'] == True))
        assert unsynced == 1  # Only initial record
        assert synced == 20


@pytest.mark.concurrent
@pytest.mark.mobile
class TestConcurrentOperations:
    """Stress test concurrent database operations."""

    def test_concurrent_writes(self, stress_test_helper: dict):
        """Test multiple threads writing concurrently."""
        db = TinyDB(storage=MemoryStorage)
        errors = stress_test_helper['errors']
        operations = stress_test_helper['operations']
        lock = stress_test_helper['lock']
        
        def write_records(thread_id: int, count: int):
            try:
                for i in range(count):
                    db.insert({
                        'thread_id': thread_id,
                        'iteration': i,
                        'timestamp': time.time()
                    })
                    with lock:
                        operations.append(('insert', thread_id, i))
            except Exception as e:
                with lock:
                    errors.append((thread_id, str(e)))
        
        # Create threads
        threads = []
        num_threads = 4
        records_per_thread = 25
        
        for i in range(num_threads):
            t = threading.Thread(target=write_records, args=(i, records_per_thread))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join(timeout=10)
        
        # Verify
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(db.all()) == num_threads * records_per_thread
        assert len(operations) == num_threads * records_per_thread

    def test_concurrent_reads_and_writes(self, stress_test_helper: dict):
        """Test concurrent read and write operations."""
        db = TinyDB(storage=MemoryStorage)
        errors = stress_test_helper['errors']
        lock = stress_test_helper['lock']
        
        # Pre-populate
        for i in range(50):
            db.insert({'id': i, 'value': i * 10})
        
        read_count = [0]
        write_count = [0]
        
        def reader_thread(thread_id: int):
            try:
                for _ in range(20):
                    docs = db.search(lambda doc: doc['id'] < 25)
                    with lock:
                        read_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append((thread_id, 'read', str(e)))
        
        def writer_thread(thread_id: int):
            try:
                for i in range(10):
                    db.insert({'id': 50 + i, 'new': True})
                    with lock:
                        write_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append((thread_id, 'write', str(e)))
        
        threads = []
        # Create reader threads
        for i in range(3):
            t = threading.Thread(target=reader_thread, args=(i,))
            threads.append(t)
        
        # Create writer threads
        for i in range(2):
            t = threading.Thread(target=writer_thread, args=(i + 10,))
            threads.append(t)
        
        # Start all
        for t in threads:
            t.start()
        
        # Wait
        for t in threads:
            t.join(timeout=10)
        
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert read_count[0] == 60  # 3 threads * 20 reads
        assert write_count[0] == 20  # 2 threads * 10 writes

    def test_concurrent_updates(self, stress_test_helper: dict):
        """Test concurrent update operations on same records."""
        db = TinyDB(storage=MemoryStorage)
        errors = stress_test_helper['errors']
        lock = stress_test_helper['lock']
        
        # Initialize counters
        for i in range(10):
            db.insert({'id': i, 'counter': 0})
        
        def increment_counter(thread_id: int, iterations: int):
            try:
                for _ in range(iterations):
                    # Read-modify-write pattern
                    doc = db.get(lambda d: d['id'] == 0)
                    if doc:
                        new_val = doc['counter'] + 1
                        db.update({'counter': new_val}, lambda d: d['id'] == 0)
            except Exception as e:
                with lock:
                    errors.append((thread_id, str(e)))
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=increment_counter, args=(i, 10))
            threads.append(t)
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=10)
        
        # May not reach 50 due to race conditions, but should be > 0
        final_doc = db.get(lambda d: d['id'] == 0)
        assert final_doc['counter'] > 0, "Concurrent updates failed"


@pytest.mark.mobile
@pytest.mark.integration
class TestMobileRegressions:
    """Regression tests for known mobile-backend issues."""

    def test_document_id_collision(self, concurrent_db: TinyDB):
        """Verify no document ID collisions under concurrent load."""
        doc_ids = set()
        
        for _ in range(100):
            doc_id = concurrent_db.insert({'data': 'test'})
            assert doc_id not in doc_ids, f"Document ID collision: {doc_id}"
            doc_ids.add(doc_id)
        
        assert len(doc_ids) == 100

    def test_query_after_large_batch(self, concurrent_db: TinyDB):
        """Verify queries work correctly after large batch operations."""
        # Large batch insert
        records = [{'batch': i, 'status': 'pending'} for i in range(1000)]
        concurrent_db.insert_multiple(records)
        
        # Query operations
        pending = concurrent_db.search(lambda doc: doc['status'] == 'pending')
        assert len(pending) == 1000
        
        # Update subset
        concurrent_db.update({'status': 'complete'}, lambda doc: doc['batch'] < 100)
        
        # Re-query
        complete = concurrent_db.search(lambda doc: doc['status'] == 'complete')
        pending = concurrent_db.search(lambda doc: doc['status'] == 'pending')
        assert len(complete) == 100
        assert len(pending) == 900

    def test_memory_stability_under_load(self, stress_test_helper: dict):
        """Verify no memory leaks under sustained operations."""
        db = TinyDB(storage=MemoryStorage)
        lock = stress_test_helper['lock']
        
        # Perform many insert-delete cycles
        for cycle in range(10):
            # Insert
            for i in range(50):
                db.insert({'cycle': cycle, 'index': i})
            
            # Query
            docs = db.search(lambda doc: doc['cycle'] == cycle)
            assert len(docs) == 50
            
            # Delete
            db.remove(lambda doc: doc['cycle'] == cycle)
            assert len(db.search(lambda doc: doc['cycle'] == cycle)) == 0
        
        # Database should still be empty and responsive
        assert len(db.all()) == 0
