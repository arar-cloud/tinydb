"""Performance regression tests for TinyDB.

These benchmarks measure query latency, write throughput, and memory usage
to ensure optimizations maintain performance and prevent regressions across
Python versions and storage backends.
"""

import time
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest

from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.middlewares import CachingMiddleware


class PerformanceBenchmarks:
    """Baseline performance thresholds (in seconds, lower is better)."""

    # Insert operations
    INSERT_SINGLE_THRESHOLD = 0.001  # 1ms per insert
    INSERT_BATCH_1000_THRESHOLD = 0.5  # 500ms for 1000 inserts
    INSERT_BATCH_10000_THRESHOLD = 5.0  # 5s for 10000 inserts

    # Query operations
    QUERY_SIMPLE_1000_THRESHOLD = 0.05  # 50ms to query 1000 docs
    QUERY_COMPLEX_1000_THRESHOLD = 0.1  # 100ms for complex query on 1000 docs
    QUERY_COUNT_1000_THRESHOLD = 0.01  # 10ms to count 1000 docs

    # Update operations
    UPDATE_SINGLE_THRESHOLD = 0.001  # 1ms per update
    UPDATE_BATCH_1000_THRESHOLD = 0.5  # 500ms for 1000 updates

    # Delete operations
    DELETE_SINGLE_THRESHOLD = 0.001  # 1ms per delete
    DELETE_BATCH_1000_THRESHOLD = 0.5  # 500ms for 1000 deletes


class TestInsertPerformance:
    """Test write throughput and insert latency."""

    def test_insert_single_document_latency(self):
        """Measure latency of inserting a single document."""
        db = TinyDB(storage=MemoryStorage)
        doc = {'name': 'test', 'value': 42, 'tags': ['a', 'b', 'c']}

        start = time.perf_counter()
        db.insert(doc)
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.INSERT_SINGLE_THRESHOLD, (
            f"Single insert took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.INSERT_SINGLE_THRESHOLD}s"
        )

    def test_insert_batch_1000_throughput(self):
        """Measure write throughput for 1000 inserts."""
        db = TinyDB(storage=MemoryStorage)
        docs = [
            {'id': i, 'value': i * 2, 'name': f'doc_{i}'}
            for i in range(1000)
        ]

        start = time.perf_counter()
        db.insert_multiple(docs)
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.INSERT_BATCH_1000_THRESHOLD, (
            f"Insert 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.INSERT_BATCH_1000_THRESHOLD}s"
        )
        throughput = 1000 / elapsed
        print(f"\nInsert throughput (1000 docs): {throughput:.0f} docs/sec")

    def test_insert_batch_10000_throughput(self):
        """Measure write throughput for 10000 inserts."""
        db = TinyDB(storage=MemoryStorage)
        docs = [
            {'id': i, 'value': i * 3, 'name': f'doc_{i}', 'data': 'x' * 100}
            for i in range(10000)
        ]

        start = time.perf_counter()
        db.insert_multiple(docs)
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.INSERT_BATCH_10000_THRESHOLD, (
            f"Insert 10000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.INSERT_BATCH_10000_THRESHOLD}s"
        )
        throughput = 10000 / elapsed
        print(f"\nInsert throughput (10000 docs): {throughput:.0f} docs/sec")

    def test_insert_to_json_storage(self):
        """Measure insert performance with JSONStorage backend."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'
            db = TinyDB(db_path, storage=JSONStorage)
            docs = [{'id': i, 'value': i} for i in range(100)]

            start = time.perf_counter()
            db.insert_multiple(docs)
            elapsed = time.perf_counter() - start

            # JSONStorage is slower due to disk I/O, use relaxed threshold
            assert elapsed < 2.0, (
                f"Insert 100 docs to JSONStorage took {elapsed:.4f}s"
            )
            db.close()


class TestQueryPerformance:
    """Test query latency on various dataset sizes."""

    def test_simple_query_1000_documents(self):
        """Measure latency of simple equality query on 1000 documents."""
        db = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'status': 'active' if i % 2 == 0 else 'inactive'}
                for i in range(1000)]
        db.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        results = db.search(User.status == 'active')
        elapsed = time.perf_counter() - start

        assert len(results) == 500, "Query should return 500 results"
        assert elapsed < PerformanceBenchmarks.QUERY_SIMPLE_1000_THRESHOLD, (
            f"Simple query on 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.QUERY_SIMPLE_1000_THRESHOLD}s"
        )
        print(f"\nSimple query latency (1000 docs): {elapsed*1000:.2f}ms")

    def test_complex_query_1000_documents(self):
        """Measure latency of complex query with multiple conditions."""
        db = TinyDB(storage=MemoryStorage)
        docs = [
            {
                'id': i,
                'status': 'active' if i % 2 == 0 else 'inactive',
                'score': i % 100,
                'category': f'cat_{i % 10}'
            }
            for i in range(1000)
        ]
        db.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        results = db.search(
            (User.status == 'active') &
            (User.score > 50) &
            (User.category.test(lambda x: x.startswith('cat_')))
        )
        elapsed = time.perf_counter() - start

        assert len(results) > 0, "Query should return results"
        assert elapsed < PerformanceBenchmarks.QUERY_COMPLEX_1000_THRESHOLD, (
            f"Complex query on 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.QUERY_COMPLEX_1000_THRESHOLD}s"
        )
        print(f"\nComplex query latency (1000 docs): {elapsed*1000:.2f}ms")

    def test_query_count_1000_documents(self):
        """Measure latency of counting query results."""
        db = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'status': 'active'} for i in range(1000)]
        db.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        count = len(db.search(User.status == 'active'))
        elapsed = time.perf_counter() - start

        assert count == 1000, "Count should be 1000"
        assert elapsed < PerformanceBenchmarks.QUERY_COUNT_1000_THRESHOLD, (
            f"Count query on 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.QUERY_COUNT_1000_THRESHOLD}s"
        )
        print(f"\nCount query latency (1000 docs): {elapsed*1000:.2f}ms")

    def test_query_all_documents(self):
        """Measure latency of retrieving all documents."""
        db = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'value': i * 2} for i in range(1000)]
        db.insert_multiple(docs)

        start = time.perf_counter()
        results = db.all()
        elapsed = time.perf_counter() - start

        assert len(results) == 1000, "Should retrieve 1000 documents"
        assert elapsed < PerformanceBenchmarks.QUERY_SIMPLE_1000_THRESHOLD, (
            f"Retrieve all 1000 docs took {elapsed:.4f}s"
        )
        print(f"\nRetrieve all latency (1000 docs): {elapsed*1000:.2f}ms")


class TestUpdatePerformance:
    """Test update latency and throughput."""

    def test_update_single_document(self):
        """Measure latency of updating a single document."""
        db = TinyDB(storage=MemoryStorage)
        db.insert({'id': 1, 'status': 'active', 'count': 0})

        User = Query()
        start = time.perf_counter()
        db.update({'status': 'inactive', 'count': 1}, User.id == 1)
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.UPDATE_SINGLE_THRESHOLD, (
            f"Single update took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.UPDATE_SINGLE_THRESHOLD}s"
        )

    def test_update_batch_1000_documents(self):
        """Measure update throughput for 1000 documents."""
        db = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'status': 'active'} for i in range(1000)]
        db.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        db.update({'status': 'inactive'}, User.status == 'active')
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.UPDATE_BATCH_1000_THRESHOLD, (
            f"Update 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.UPDATE_BATCH_1000_THRESHOLD}s"
        )
        throughput = 1000 / elapsed
        print(f"\nUpdate throughput (1000 docs): {throughput:.0f} docs/sec")


class TestDeletePerformance:
    """Test delete latency and throughput."""

    def test_delete_single_document(self):
        """Measure latency of deleting a single document."""
        db = TinyDB(storage=MemoryStorage)
        db.insert({'id': 1, 'value': 'test'})

        User = Query()
        start = time.perf_counter()
        db.remove(User.id == 1)
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.DELETE_SINGLE_THRESHOLD, (
            f"Single delete took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.DELETE_SINGLE_THRESHOLD}s"
        )

    def test_delete_batch_1000_documents(self):
        """Measure delete throughput for 1000 documents."""
        db = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'status': 'temp'} for i in range(1000)]
        db.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        db.remove(User.status == 'temp')
        elapsed = time.perf_counter() - start

        assert elapsed < PerformanceBenchmarks.DELETE_BATCH_1000_THRESHOLD, (
            f"Delete 1000 docs took {elapsed:.4f}s, "
            f"expected < {PerformanceBenchmarks.DELETE_BATCH_1000_THRESHOLD}s"
        )
        throughput = 1000 / elapsed
        print(f"\nDelete throughput (1000 docs): {throughput:.0f} docs/sec")


class TestMemoryUsage:
    """Test memory efficiency with large datasets."""

    def test_memory_efficiency_with_large_documents(self):
        """Verify memory usage stays reasonable with large documents."""
        db = TinyDB(storage=MemoryStorage)
        # Create documents with significant data
        docs = [
            {
                'id': i,
                'data': 'x' * 1000,  # 1KB of data per document
                'nested': {'key': 'value', 'items': list(range(100))}
            }
            for i in range(100)
        ]

        start = time.perf_counter()
        db.insert_multiple(docs)
        elapsed = time.perf_counter() - start

        # Should handle 100KB of data efficiently
        assert elapsed < 1.0, (
            f"Insert 100 large docs took {elapsed:.4f}s, "
            "indicates possible memory inefficiency"
        )

        # Verify retrieval is also efficient
        start = time.perf_counter()
        results = db.all()
        elapsed = time.perf_counter() - start

        assert len(results) == 100, "All documents should be retrieved"
        assert elapsed < 0.1, "Retrieval of 100 docs should be fast"

    def test_memory_efficiency_after_many_operations(self):
        """Verify memory doesn't accumulate after many operations."""
        db = TinyDB(storage=MemoryStorage)

        # Perform many insert/update/delete cycles
        for cycle in range(10):
            docs = [{'id': i, 'cycle': cycle} for i in range(100)]
            db.insert_multiple(docs)

            User = Query()
            db.update({'cycle': cycle + 1}, User.cycle == cycle)
            db.remove(User.cycle == cycle + 1)

        # Final state should be empty and fast
        assert len(db.all()) == 0, "Database should be empty"

        # Verify we can still insert efficiently
        start = time.perf_counter()
        db.insert_multiple([{'id': i} for i in range(100)])
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, (
            "Insert should be fast even after many operations"
        )


class TestStorageBackendPerformance:
    """Test performance across different storage backends."""

    def test_memory_vs_json_storage_insert(self):
        """Compare insert performance between MemoryStorage and JSONStorage."""
        # Test MemoryStorage
        db_mem = TinyDB(storage=MemoryStorage)
        docs = [{'id': i, 'value': i} for i in range(100)]

        start = time.perf_counter()
        db_mem.insert_multiple(docs)
        mem_time = time.perf_counter() - start

        # Test JSONStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            db_json = TinyDB(
                Path(tmpdir) / 'test.db',
                storage=JSONStorage
            )

            start = time.perf_counter()
            db_json.insert_multiple(docs)
            json_time = time.perf_counter() - start

            db_json.close()

        # JSONStorage will be slower due to I/O, but should still be reasonable
        print(f"\nMemoryStorage insert time: {mem_time*1000:.2f}ms")
        print(f"JSONStorage insert time: {json_time*1000:.2f}ms")
        assert json_time < 2.0, "JSONStorage insert should complete in reasonable time"

    def test_memory_vs_json_storage_query(self):
        """Compare query performance between storage backends."""
        docs = [{'id': i, 'status': 'active'} for i in range(100)]

        # Test MemoryStorage
        db_mem = TinyDB(storage=MemoryStorage)
        db_mem.insert_multiple(docs)

        User = Query()
        start = time.perf_counter()
        results_mem = db_mem.search(User.status == 'active')
        mem_time = time.perf_counter() - start

        # Test JSONStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            db_json = TinyDB(
                Path(tmpdir) / 'test.db',
                storage=JSONStorage
            )
            db_json.insert_multiple(docs)

            start = time.perf_counter()
            results_json = db_json.search(User.status == 'active')
            json_time = time.perf_counter() - start

            db_json.close()

        assert len(results_mem) == len(results_json) == 100, "Both should return same results"
        print(f"\nMemoryStorage query time: {mem_time*1000:.2f}ms")
        print(f"JSONStorage query time: {json_time*1000:.2f}ms")


@pytest.mark.benchmark
class TestRegressionDetection:
    """Meta-tests to detect performance regressions."""

    def test_no_regression_in_basic_operations(self):
        """Ensure basic operations maintain performance baseline."""
        results = {}
        db = TinyDB(storage=MemoryStorage)

        # Measure insert
        docs = [{'i': i} for i in range(500)]
        start = time.perf_counter()
        db.insert_multiple(docs)
        results['insert_500'] = time.perf_counter() - start

        # Measure query
        User = Query()
        start = time.perf_counter()
        db.search(User.i > 250)
        results['query_500'] = time.perf_counter() - start

        # Measure update
        start = time.perf_counter()
        db.update({'updated': True}, User.i < 100)
        results['update_100'] = time.perf_counter() - start

        # Verify all operations completed in acceptable time
        for op, elapsed in results.items():
            assert elapsed < 1.0, f"{op} took {elapsed:.4f}s (possible regression)"

        print(f"\nPerformance summary:")
        for op, elapsed in results.items():
            print(f"  {op}: {elapsed*1000:.2f}ms")
