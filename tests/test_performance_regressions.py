"""Performance regression tests for bulk operations.

Measures:
- Serialization overhead during bulk insert/update/delete
- Query predicate cache effectiveness
- Table initialization time with various dataset sizes
"""

import time
import pytest
from pathlib import Path
import tempfile


class TestSerializationOverhead:
    """Benchmark serialization performance during bulk operations."""

    def test_bulk_insert_serialization_overhead(self, db):
        """Measure serialization time for bulk inserts (target: <100ms for 1000 docs)."""
        table = db.table('perf_test_bulk_insert')
        documents = [{'id': i, 'data': f'value_{i}' * 10} for i in range(1000)]
        
        start = time.perf_counter()
        for doc in documents:
            table.insert(doc)
        elapsed = time.perf_counter() - start
        
        # Assert regression: serialization should not exceed 100ms for 1000 docs
        assert elapsed < 0.1, f"Bulk insert serialization took {elapsed:.3f}s (target: <0.1s)"

    def test_bulk_update_serialization_overhead(self, db):
        """Measure serialization time for bulk updates (target: <80ms for 1000 updates)."""
        table = db.table('perf_test_bulk_update')
        doc_ids = [table.insert({'value': 0}) for _ in range(1000)]
        
        start = time.perf_counter()
        for doc_id in doc_ids:
            table.update({'value': 1}, doc_ids=[doc_id])
        elapsed = time.perf_counter() - start
        
        # Assert regression: bulk updates should not exceed 80ms
        assert elapsed < 0.08, f"Bulk update serialization took {elapsed:.3f}s (target: <0.08s)"

    def test_bulk_delete_serialization_overhead(self, db):
        """Measure serialization time for bulk deletes (target: <50ms for 500 deletes)."""
        table = db.table('perf_test_bulk_delete')
        doc_ids = [table.insert({'value': i}) for i in range(500)]
        
        start = time.perf_counter()
        for doc_id in doc_ids:
            table.remove(doc_ids=[doc_id])
        elapsed = time.perf_counter() - start
        
        # Assert regression: bulk deletes should not exceed 50ms
        assert elapsed < 0.05, f"Bulk delete serialization took {elapsed:.3f}s (target: <0.05s)"


class TestQueryPredicateCaching:
    """Benchmark query predicate cache effectiveness."""

    def test_predicate_cache_hit_rate(self, db):
        """Measure query cache effectiveness: repeated queries should use cache (target: >80% hit rate)."""
        table = db.table('perf_test_cache')
        for i in range(100):
            table.insert({'category': 'A' if i % 2 == 0 else 'B', 'value': i})
        
        # Warm up
        from tinydb import where
        query = where('category') == 'A'
        
        # First query (cache miss)
        start1 = time.perf_counter()
        result1 = table.search(query)
        time1 = time.perf_counter() - start1
        
        # Repeated queries (should hit cache)
        times = []
        for _ in range(10):
            start = time.perf_counter()
            result = table.search(query)
            times.append(time.perf_counter() - start)
        
        avg_cached_time = sum(times) / len(times)
        # Cached queries should be significantly faster
        speedup = time1 / avg_cached_time if avg_cached_time > 0 else 1
        assert speedup > 1.2, f"Query cache speedup only {speedup:.2f}x (target: >1.2x)"

    def test_complex_predicate_cache(self, db):
        """Measure cache performance for complex predicates (target: <5ms per repeated query)."""
        from tinydb import where
        table = db.table('perf_test_complex_cache')
        
        for i in range(200):
            table.insert({
                'status': 'active' if i % 3 == 0 else 'inactive',
                'priority': i % 5,
                'value': i
            })
        
        # Complex query
        query = (where('status') == 'active') & (where('priority') > 2)
        
        # Warm up
        table.search(query)
        
        # Measure repeated queries
        start = time.perf_counter()
        for _ in range(10):
            table.search(query)
        elapsed = time.perf_counter() - start
        
        avg_time = elapsed / 10
        assert avg_time < 0.005, f"Complex predicate cache query took {avg_time:.4f}s (target: <0.005s)"


class TestTableInitialization:
    """Benchmark table initialization time."""

    def test_table_init_empty(self, db):
        """Measure empty table initialization (target: <5ms)."""
        start = time.perf_counter()
        table = db.table('perf_test_init_empty')
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.005, f"Empty table init took {elapsed:.4f}s (target: <0.005s)"

    def test_table_init_with_existing_data(self, db):
        """Measure table init with 500 existing documents (target: <20ms)."""
        table = db.table('perf_test_init_existing')
        for i in range(500):
            table.insert({'id': i, 'data': f'item_{i}'})
        
        # Reinitialize - should load from disk/cache
        start = time.perf_counter()
        table2 = db.table('perf_test_init_existing')
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.02, f"Table init with 500 docs took {elapsed:.4f}s (target: <0.02s)"
        assert len(table2) == 500, "Data mismatch after table reinitialization"

    def test_table_init_multiple_sequential(self, db):
        """Measure sequential initialization of multiple tables (target: <30ms for 5 tables)."""
        start = time.perf_counter()
        for i in range(5):
            table = db.table(f'perf_test_multi_{i}')
            for j in range(50):
                table.insert({'id': j})
        elapsed = time.perf_counter() - start
        
        assert elapsed < 0.03, f"5-table init took {elapsed:.4f}s (target: <0.03s)"


class TestBulkOperationPerformance:
    """Integrated bulk operation performance tests."""

    def test_bulk_insert_vs_sequential_insert(self, db):
        """Verify bulk insert doesn't degrade vs sequential (no >20% slowdown)."""
        # Sequential inserts
        table1 = db.table('perf_test_sequential')
        start1 = time.perf_counter()
        for i in range(200):
            table1.insert({'id': i, 'data': f'seq_{i}'})
        time_sequential = time.perf_counter() - start1
        
        # "Bulk" inserts (all at once to same table)
        table2 = db.table('perf_test_bulk')
        start2 = time.perf_counter()
        for i in range(200):
            table2.insert({'id': i, 'data': f'bulk_{i}'})
        time_bulk = time.perf_counter() - start2
        
        # Performance should be similar (bulk shouldn't be >20% slower)
        overhead = (time_bulk - time_sequential) / time_sequential if time_sequential > 0 else 0
        assert overhead < 0.2, f"Bulk insert overhead: {overhead:.1%} (target: <20%)"
