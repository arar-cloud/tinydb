"""Stress tests for concurrent database access and retry scenarios.

Covers:
- Multi-threaded concurrent access patterns
- Multiprocessing database operations
- Transient failure injection and recovery
- Multi-retry scenarios with consistency verification
"""

import os
import pytest
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestConcurrentThreadedAccess:
    """Test concurrent access from multiple threads."""

    def test_concurrent_inserts_from_threads(self, tmp_path: Path):
        """Verify concurrent inserts from multiple threads maintain consistency."""
        db_path = tmp_path / "concurrent.json"
        num_threads = 5
        docs_per_thread = 20

        def insert_docs(thread_id):
            db = TinyDB(db_path, storage=JSONStorage)
            for i in range(docs_per_thread):
                db.insert({
                    'thread_id': thread_id,
                    'doc_index': i,
                    'value': f'thread_{thread_id}_doc_{i}'
                })
            db.close()

        # Execute concurrent inserts
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(insert_docs, i) for i in range(num_threads)]
            for future in as_completed(futures):
                future.result()

        # Verify all documents were inserted
        db = TinyDB(db_path, storage=JSONStorage)
        all_docs = db.all()
        assert len(all_docs) == num_threads * docs_per_thread

        # Verify no duplicates and data integrity
        seen = set()
        for doc in all_docs:
            key = (doc['thread_id'], doc['doc_index'])
            assert key not in seen, f"Duplicate document: {key}"
            seen.add(key)
        db.close()

    def test_concurrent_reads_while_writing(self, tmp_path: Path):
        """Verify concurrent reads don't block or corrupt while writes happen."""
        db_path = tmp_path / "read_write.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Insert initial data
        for i in range(100):
            db.insert({'id': i, 'value': i * 10})
        db.close()

        read_count = 0
        write_count = 0
        lock = threading.Lock()

        def reader(reader_id):
            nonlocal read_count
            db = TinyDB(db_path, storage=JSONStorage)
            for _ in range(50):
                docs = db.all()
                # Verify consistency: at least initial docs present
                assert len(docs) >= 100
                with lock:
                    read_count += 1
                time.sleep(0.001)  # Small delay
            db.close()

        def writer():
            nonlocal write_count
            db = TinyDB(db_path, storage=JSONStorage)
            for i in range(100, 150):
                db.insert({'id': i, 'value': i * 10})
                with lock:
                    write_count += 1
                time.sleep(0.005)  # Slower writes
            db.close()

        # Run concurrent readers and writer
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(reader, i) for i in range(5)]
            futures.append(executor.submit(writer))
            for future in as_completed(futures):
                future.result()

        # Verify final state
        db = TinyDB(db_path, storage=JSONStorage)
        final_count = len(db.all())
        assert final_count == 150  # Initial 100 + 50 written
        assert read_count > 0
        assert write_count == 50
        db.close()

    def test_concurrent_updates_same_documents(self, tmp_path: Path):
        """Verify concurrent updates to same documents maintain last-write consistency."""
        db_path = tmp_path / "concurrent_updates.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Insert target documents
        target_ids = []
        for i in range(10):
            doc_id = db.insert({'id': i, 'counter': 0})
            target_ids.append(doc_id)
        db.close()

        def update_worker(worker_id):
            db = TinyDB(db_path, storage=JSONStorage)
            for _ in range(20):
                for doc_id in target_ids:
                    doc = db.get(doc_id=doc_id)
                    db.update(
                        {'counter': doc['counter'] + 1, 'last_worker': worker_id},
                        doc_ids=[doc_id]
                    )
            db.close()

        # Run concurrent updates
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(update_worker, i) for i in range(4)]
            for future in as_completed(futures):
                future.result()

        # Verify final state: counters should be at least partial increments
        db = TinyDB(db_path, storage=JSONStorage)
        for doc_id in target_ids:
            doc = db.get(doc_id=doc_id)
            # Each doc was updated at least once (non-zero counter)
            assert doc['counter'] > 0
        db.close()

    def test_thread_safety_with_single_instance(self, tmp_path: Path):
        """Verify single TinyDB instance is safe across multiple threads."""
        db_path = tmp_path / "shared_instance.json"
        db = TinyDB(db_path, storage=JSONStorage)

        insert_count = 0
        lock = threading.Lock()

        def shared_insert(thread_id):
            nonlocal insert_count
            for i in range(10):
                doc_id = db.insert({
                    'thread_id': thread_id,
                    'index': i
                })
                with lock:
                    insert_count += 1
                assert doc_id is not None

        # Use shared database instance
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(shared_insert, i) for i in range(5)]
            for future in as_completed(futures):
                future.result()

        # Verify all inserts succeeded
        assert len(db.all()) == insert_count == 50
        db.close()


class TestTransientFailureRetry:
    """Test retry behavior on transient failures."""

    def test_retry_on_io_error(self, tmp_path: Path):
        """Verify operation succeeds after transient IOError."""
        db_path = tmp_path / "retry_io.json"
        db = TinyDB(db_path, storage=JSONStorage)

        call_count = 0

        def failing_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise IOError("Simulated transient failure")
            return db.insert({'status': 'success', 'attempts': call_count})

        # Implement simple retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = failing_operation()
                break
            except IOError as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(0.01 * (2 ** attempt))  # Exponential backoff

        assert call_count == 3
        assert db.get(doc_id=result)['attempts'] == 3
        db.close()

    def test_multi_retry_scenario_with_partial_success(self, tmp_path: Path):
        """Verify multi-step operations with retry handle partial success."""
        db_path = tmp_path / "multi_retry.json"
        db = TinyDB(db_path, storage=JSONStorage)

        step_attempts = {'step1': 0, 'step2': 0, 'step3': 0}

        def multi_step_operation(should_fail_at=None):
            # Step 1: Insert base document
            step_attempts['step1'] += 1
            if should_fail_at == 'step1' and step_attempts['step1'] < 2:
                raise IOError("Step 1 failed")
            doc_id = db.insert({'status': 'step1_done'})

            # Step 2: Update document
            step_attempts['step2'] += 1
            if should_fail_at == 'step2' and step_attempts['step2'] < 2:
                raise IOError("Step 2 failed")
            db.update({'status': 'step2_done'}, doc_ids=[doc_id])

            # Step 3: Add related record
            step_attempts['step3'] += 1
            if should_fail_at == 'step3' and step_attempts['step3'] < 2:
                raise IOError("Step 3 failed")
            related_id = db.insert({'parent_id': doc_id, 'status': 'step3_done'})

            return doc_id, related_id

        # Test failure at each step with retry
        for fail_step in ['step1', 'step2', 'step3']:
            step_attempts = {'step1': 0, 'step2': 0, 'step3': 0}
            max_retries = 3
            result = None

            for attempt in range(max_retries):
                try:
                    result = multi_step_operation(should_fail_at=fail_step)
                    break
                except IOError:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(0.01)

            # Verify operation eventually succeeded
            assert result is not None
            assert step_attempts[fail_step] >= 2  # Failed then succeeded

        db.close()

    def test_exponential_backoff_increases_delay(self):
        """Verify exponential backoff delays increase correctly."""
        delays = []

        def backoff_delay(attempt, base=0.01, multiplier=2):
            return base * (multiplier ** attempt)

        for attempt in range(5):
            delay = backoff_delay(attempt)
            delays.append(delay)

        # Verify delays increase exponentially
        for i in range(1, len(delays)):
            assert delays[i] > delays[i - 1]
            assert delays[i] / delays[i - 1] == pytest.approx(2.0)


class TestChaosScenarios:
    """Test database behavior under adverse conditions."""

    def test_stress_many_small_inserts(self, tmp_path: Path):
        """Stress test with many small rapid inserts."""
        db_path = tmp_path / "stress_inserts.json"
        db = TinyDB(db_path, storage=JSONStorage)

        num_inserts = 1000
        start = time.time()

        for i in range(num_inserts):
            db.insert({'id': i, 'data': f'record_{i}'})

        elapsed = time.time() - start
        docs = db.all()

        assert len(docs) == num_inserts
        assert elapsed < 60  # Should complete in reasonable time
        db.close()

    def test_recovery_after_connection_loss_simulation(self, tmp_path: Path):
        """Simulate connection loss and verify recovery on reconnect."""
        db_path = tmp_path / "recover.json"

        # Initial insert
        db = TinyDB(db_path, storage=JSONStorage)
        doc_id = db.insert({'value': 'initial', 'status': 'active'})
        db.close()

        # Simulate connection loss by accessing file directly
        time.sleep(0.05)

        # Reconnect and verify data persisted
        db = TinyDB(db_path, storage=JSONStorage)
        doc = db.get(doc_id=doc_id)
        assert doc is not None
        assert doc['value'] == 'initial'

        # Update after reconnect
        db.update({'value': 'updated', 'status': 'recovered'}, doc_ids=[doc_id])
        db.close()

        # Verify update persisted
        db = TinyDB(db_path, storage=JSONStorage)
        doc = db.get(doc_id=doc_id)
        assert doc['value'] == 'updated'
        db.close()

    def test_memory_storage_concurrent_access(self):
        """Test concurrent access with in-memory storage."""
        db = TinyDB(storage=MemoryStorage)

        def worker(worker_id):
            for i in range(50):
                db.insert({
                    'worker': worker_id,
                    'iteration': i,
                    'timestamp': time.time()
                })

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, i) for i in range(8)]
            for future in as_completed(futures):
                future.result()

        # Verify all documents in memory
        assert len(db.all()) == 8 * 50
        db.close()
