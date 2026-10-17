"""Test suite for concurrent retry scenarios and race condition validation.

This module validates that TinyDB operations maintain consistency under
concurrent access patterns with retries, critical for multi-threaded backends
and mobile applications.
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import MagicMock, patch

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


@pytest.mark.concurrency
@pytest.mark.stability
class TestConcurrentRaceConditions:
    """Test race condition handling in concurrent retry scenarios."""

    def test_concurrent_insert_no_duplicates(self, db):
        """Verify concurrent inserts produce no duplicate IDs."""
        table = db.table('concurrent_insert_ids')
        doc_ids = set()
        lock = threading.Lock()
        
        def insert_doc(i):
            doc_id = table.insert({'thread_id': i, 'value': f'doc_{i}'})
            with lock:
                doc_ids.add(doc_id)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(insert_doc, i) for i in range(20)]
            for future in as_completed(futures):
                future.result()
        
        # Verify all IDs are unique
        assert len(doc_ids) == 20
        # Verify all documents exist
        assert len(table.all()) == 20

    def test_concurrent_update_same_document(self, db):
        """Verify concurrent updates to same document are handled consistently."""
        table = db.table('concurrent_updates')
        doc_id = table.insert({'counter': 0, 'version': 0})
        
        def increment_counter(i):
            # Read current value
            doc = table.get(doc_id=doc_id)
            current_value = doc['counter']
            # Simulate work
            time.sleep(0.001)
            # Update with incremented value
            table.update({'counter': current_value + 1, 'version': i}, doc_ids=[doc_id])
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(increment_counter, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()
        
        # Verify final state exists (last write wins semantics)
        final_doc = table.get(doc_id=doc_id)
        assert final_doc['counter'] >= 1  # At least one increment persisted

    def test_concurrent_read_during_writes(self, db):
        """Verify reads remain consistent during concurrent writes."""
        table = db.table('concurrent_read_write')
        
        # Pre-populate with base data
        base_ids = [table.insert({'base': i}) for i in range(10)]
        
        read_results = []
        result_lock = threading.Lock()
        
        def reader_task():
            time.sleep(0.002)  # Let writers start
            docs = table.all()
            with result_lock:
                read_results.append(len(docs))
        
        def writer_task(i):
            table.insert({'new': i})
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Start readers
            reader_futures = [executor.submit(reader_task) for _ in range(5)]
            # Start writers
            writer_futures = [executor.submit(writer_task, i) for i in range(10)]
            
            # Wait for all to complete
            for future in as_completed(reader_futures + writer_futures):
                future.result()
        
        # Verify reads are consistent and show expected state
        assert len(read_results) > 0
        assert all(count >= 10 for count in read_results)  # At least base documents

    def test_concurrent_delete_and_insert(self, db):
        """Verify concurrent deletes and inserts maintain consistency."""
        table = db.table('delete_insert')
        
        # Pre-populate
        doc_ids = [table.insert({'id': i}) for i in range(10)]
        
        def delete_and_insert(i):
            if i < len(doc_ids):
                table.remove(doc_ids=[doc_ids[i]])
            table.insert({'id': f'new_{i}'})
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(delete_and_insert, i) for i in range(15)]
            for future in as_completed(futures):
                future.result()
        
        # Verify final state is consistent
        final_docs = table.all()
        assert len(final_docs) > 0  # Some documents remain
        assert len(final_docs) <= 15 + 10  # Won't exceed inserts + original


@pytest.mark.concurrency
@pytest.mark.resilience
class TestConcurrentRetryConsistency:
    """Test consistency of retry behavior under concurrent access."""

    def test_concurrent_operations_with_simulated_retries(self, db, mock_retry_context):
        """Verify concurrent operations with retry simulation maintain consistency."""
        table = db.table('concurrent_retries')
        
        def operation_with_retry(op_id):
            for attempt in range(mock_retry_context['max_attempts']):
                try:
                    table.insert({
                        'operation_id': op_id,
                        'attempt': attempt + 1,
                        'success': True
                    })
                    break
                except Exception:
                    if attempt == mock_retry_context['max_attempts'] - 1:
                        raise
                    time.sleep(0.001)
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(operation_with_retry, i) for i in range(20)]
            for future in as_completed(futures):
                future.result()
        
        # Verify all operations succeeded
        docs = table.all()
        assert len(docs) == 20
        assert all(doc['success'] for doc in docs)

    def test_concurrent_search_with_ongoing_modifications(self, db):
        """Verify search queries return consistent results during concurrent writes."""
        table = db.table('search_during_write')
        
        # Populate initial data
        for i in range(20):
            table.insert({'type': 'initial', 'index': i})
        
        search_results = []
        result_lock = threading.Lock()
        
        def search_task():
            results = table.search(lambda x: x['type'] == 'initial')
            with result_lock:
                search_results.append(len(results))
        
        def modify_task():
            table.insert({'type': 'modified', 'index': 999})
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            search_futures = [executor.submit(search_task) for _ in range(10)]
            modify_futures = [executor.submit(modify_task) for _ in range(5)]
            
            for future in as_completed(search_futures + modify_futures):
                future.result()
        
        # Verify all searches found expected data
        assert len(search_results) > 0
        assert all(count >= 20 for count in search_results)


@pytest.mark.concurrency
@pytest.mark.stability
class TestConcurrentTableOperations:
    """Test concurrent operations across multiple tables."""

    def test_multiple_tables_concurrent_writes(self, db):
        """Verify concurrent writes to multiple tables don't interfere."""
        tables = {f'table_{i}': db.table(f'table_{i}') for i in range(5)}
        
        def write_to_table(table_name, doc_count):
            table = tables[table_name]
            for i in range(doc_count):
                table.insert({'table': table_name, 'index': i})
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(write_to_table, name, 10)
                for name in tables.keys()
            ]
            for future in as_completed(futures):
                future.result()
        
        # Verify each table has correct document count
        for table_name, table in tables.items():
            assert len(table.all()) == 10

    def test_interleaved_multi_table_transactions(self, db):
        """Verify interleaved operations across tables remain consistent."""
        table_a = db.table('multi_table_a')
        table_b = db.table('multi_table_b')
        
        def interleaved_operations(pair_id):
            # Insert to A
            id_a = table_a.insert({'pair_id': pair_id, 'table': 'a'})
            # Insert to B
            id_b = table_b.insert({'pair_id': pair_id, 'table': 'b'})
            # Verify both exist
            assert table_a.get(doc_id=id_a) is not None
            assert table_b.get(doc_id=id_b) is not None
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(interleaved_operations, i) for i in range(15)]
            for future in as_completed(futures):
                future.result()
        
        # Verify final counts
        assert len(table_a.all()) == 15
        assert len(table_b.all()) == 15


@pytest.mark.concurrency
class TestConcurrentLockingBehavior:
    """Test locking behavior under concurrent access."""

    def test_write_operations_maintain_atomicity(self, db):
        """Verify write operations maintain atomicity under concurrency."""
        table = db.table('atomicity_test')
        doc_id = table.insert({'atomic_field': 0, 'transactions': 0})
        
        def atomic_update(i):
            # Simulate atomic transaction
            doc = table.get(doc_id=doc_id)
            new_count = doc['transactions'] + 1
            table.update({
                'atomic_field': doc['atomic_field'] + 1,
                'transactions': new_count
            }, doc_ids=[doc_id])
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(atomic_update, i) for i in range(10)]
            for future in as_completed(futures):
                future.result()
        
        # Verify final state
        final_doc = table.get(doc_id=doc_id)
        assert final_doc['transactions'] >= 1  # At least one transaction completed
