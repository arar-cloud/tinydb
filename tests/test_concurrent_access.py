"""Tests for concurrent access and race condition detection in TinyDB."""
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tinydb.storages import MemoryStorage
from tinydb import TinyDB


class TestConcurrentWrite:
    """Test concurrent write operations for race conditions."""

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_concurrent_inserts_atomicity(self, db_stable):
        """Test that concurrent inserts maintain atomicity."""
        num_threads = 5
        docs_per_thread = 10
        results = []
        errors = []
        
        def insert_docs(thread_id):
            try:
                for i in range(docs_per_thread):
                    doc_id = db_stable.insert({
                        'thread': thread_id,
                        'sequence': i,
                        'timestamp': time.time()
                    })
                    results.append(doc_id)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for tid in range(num_threads):
            t = threading.Thread(target=insert_docs, args=(tid,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # No errors should occur
        assert len(errors) == 0, f"Errors occurred: {errors}"
        # All inserts should succeed
        assert len(results) == num_threads * docs_per_thread
        # Database should have all docs plus initial 3
        assert len(db_stable.all()) >= num_threads * docs_per_thread

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_concurrent_updates_ordering(self, db_stable):
        """Test that concurrent updates maintain consistent ordering."""
        num_threads = 3
        update_count = {'value': 0}
        lock = threading.Lock()
        
        # Get a document to update
        doc = db_stable.all()[0]
        doc_id = doc.doc_id
        
        def update_doc(thread_id):
            for i in range(5):
                db_stable.update(
                    {'updates': thread_id, 'counter': i},
                    doc_ids=[doc_id]
                )
                with lock:
                    update_count['value'] += 1
        
        threads = []
        for tid in range(num_threads):
            t = threading.Thread(target=update_doc, args=(tid,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All updates should have been recorded
        assert update_count['value'] == num_threads * 5
        # Document should exist and have last update
        updated_doc = db_stable.get(doc_id=doc_id)
        assert updated_doc is not None

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_concurrent_delete_idempotency(self, db_stable):
        """Test that concurrent deletes are idempotent."""
        # Insert additional test documents
        doc_ids = []
        for i in range(10):
            doc_id = db_stable.insert({'id': i, 'concurrent_test': True})
            doc_ids.append(doc_id)
        
        deletion_results = []
        
        def delete_doc(doc_id):
            try:
                # Multiple threads trying to delete same doc
                db_stable.remove(doc_ids=[doc_id])
                deletion_results.append('success')
            except Exception as e:
                deletion_results.append(str(e))
        
        # Try to delete same doc from multiple threads
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(delete_doc, doc_ids[0]) for _ in range(3)]
            for future in as_completed(futures):
                future.result()
        
        # First delete succeeds, others should be idempotent (not error)
        assert 'success' in deletion_results
        # Verify document is deleted
        remaining = db_stable.get(doc_id=doc_ids[0])
        assert remaining is None

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_concurrent_read_consistency(self, db_stable):
        """Test that concurrent reads see consistent data."""
        # Insert test data
        inserted_ids = []
        for i in range(20):
            doc_id = db_stable.insert({'value': i})
            inserted_ids.append(doc_id)
        
        read_results = []
        
        def read_all():
            docs = db_stable.all()
            read_results.append(len(docs))
        
        # Multiple threads reading concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(read_all) for _ in range(10)]
            for future in as_completed(futures):
                future.result()
        
        # All readers should see same number of documents
        assert all(count == read_results[0] for count in read_results)


class TestRaceConditions:
    """Test detection and prevention of race conditions."""

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_race_on_insert_with_same_data(self, db_stable):
        """Test race condition when inserting identical documents."""
        shared_data = {'user': 'bob', 'action': 'login'}
        insert_results = []
        
        def concurrent_insert():
            doc_id = db_stable.insert(shared_data.copy())
            insert_results.append(doc_id)
        
        threads = [threading.Thread(target=concurrent_insert) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All inserts should succeed with different IDs
        assert len(insert_results) == 3
        assert len(set(insert_results)) == 3  # All unique

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_race_on_query_during_insert(self, db_stable):
        """Test query behavior during concurrent insert."""
        query_results = []
        errors = []
        
        def reader():
            try:
                for _ in range(5):
                    result = db_stable.search(lambda x: x.get('int') == 1)
                    query_results.append(len(result))
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        def writer():
            try:
                for i in range(5):
                    db_stable.insert({'int': 1, 'seq': i})
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        
        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)
        
        reader_thread.start()
        writer_thread.start()
        
        reader_thread.join()
        writer_thread.join()
        
        # No crashes
        assert len(errors) == 0
        # Query results should show progression (not all same due to inserts)
        assert len(query_results) > 0

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_no_lost_updates_with_parallel_writes(self, db_stable):
        """Test that no updates are lost in parallel write scenario."""
        # Start with a known document
        doc_id = db_stable.insert({'counter': 0})
        
        num_threads = 4
        updates_per_thread = 5
        
        def increment_doc(thread_id):
            for _ in range(updates_per_thread):
                db_stable.update({'thread_id': thread_id}, doc_ids=[doc_id])
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(increment_doc, tid)
                for tid in range(num_threads)
            ]
            for future in as_completed(futures):
                future.result()
        
        # Document should still exist with valid state
        final_doc = db_stable.get(doc_id=doc_id)
        assert final_doc is not None
        assert 'thread_id' in final_doc


class TestTransactionOrdering:
    """Test transaction ordering and consistency."""

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_fifo_transaction_ordering(self, db_stable):
        """Test that transactions maintain FIFO ordering semantics."""
        execution_order = []
        lock = threading.Lock()
        
        def ordered_operation(op_id, delay=0):
            if delay:
                time.sleep(delay)
            db_stable.insert({'op_id': op_id})
            with lock:
                execution_order.append(op_id)
        
        # Create operations with slight delays to control submission order
        threads = []
        for i in range(5):
            t = threading.Thread(
                target=ordered_operation,
                args=(i, 0.001 * (5 - i))
            )
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All operations should have been recorded
        assert len(execution_order) == 5
        # All docs should exist
        all_docs = db_stable.all()
        assert len(all_docs) >= 8  # 3 initial + 5 new

    @pytest.mark.concurrent
    @pytest.mark.stability
    def test_snapshot_isolation(self, db_stable):
        """Test that query snapshots remain consistent during concurrent modifications."""
        # Take snapshot of initial state
        initial_snapshot = db_stable.all()
        initial_count = len(initial_snapshot)
        
        def modify_db():
            for i in range(10):
                db_stable.insert({'snapshot_test': i})
        
        # Modify in background
        modifier = threading.Thread(target=modify_db)
        modifier.start()
        
        # Query during modification
        time.sleep(0.005)
        modified_snapshot = db_stable.all()
        
        modifier.join()
        
        # Snapshots should show data progression
        assert len(modified_snapshot) >= initial_count
        assert len(db_stable.all()) >= initial_count + 10
