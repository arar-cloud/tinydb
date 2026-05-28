"""Performance regression tests for TinyDB query execution.

Tests measure execution time and memory allocation for:
- Simple filtering operations
- Complex multi-condition queries
- Sorting operations
- Performance scaling with dataset size
"""

import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
from tests.benchmarks import (
    BenchmarkResult,
    PerformanceBaseline,
    measure_execution_time,
    measure_memory_usage,
)


class TestQueryPerformance:
    """Regression tests for query performance."""
    
    def setup_method(self):
        """Setup test database and baseline tracker."""
        self.db = TinyDB(storage=MemoryStorage())
        self.baseline = PerformanceBaseline('.query_performance_baseline.json')
    
    def teardown_method(self):
        """Cleanup."""
        if self.db:
            self.db.close()
    
    def test_simple_filter_small_dataset_performance(self):
        """Measure performance of simple equality filter on 100 items."""
        # Setup: insert 100 documents
        for i in range(100):
            self.db.insert({'id': i, 'name': f'item_{i}', 'category': 'A' if i % 2 == 0 else 'B'})
        
        Query_obj = Query()
        
        # Measure: simple equality filter
        def filter_operation():
            return self.db.search(Query_obj.category == 'A')
        
        results, exec_time = measure_execution_time(filter_operation)
        _, memory_alloc, _ = measure_memory_usage(filter_operation)
        
        # Verify: query returns expected results
        assert len(results) == 50
        
        # Record benchmark
        benchmark = BenchmarkResult(
            name='simple_filter_100_items',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=15.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_simple_filter_large_dataset_performance(self):
        """Measure performance of simple filter on 10k items (scaling test)."""
        # Setup: insert 10,000 documents
        for i in range(10000):
            self.db.insert({
                'id': i,
                'value': i * 2,
                'status': 'active' if i % 3 == 0 else 'inactive'
            })
        
        Query_obj = Query()
        
        # Measure: filter on large dataset
        def large_filter():
            return self.db.search(Query_obj.status == 'active')
        
        results, exec_time = measure_execution_time(large_filter)
        _, memory_alloc, _ = measure_memory_usage(large_filter)
        
        # Verify: query returns expected count (~3333)
        assert len(results) > 3000
        
        benchmark = BenchmarkResult(
            name='simple_filter_10k_items',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_complex_multi_condition_query_performance(self):
        """Measure performance of multi-condition query with AND logic."""
        # Setup: insert 500 documents with multiple fields
        for i in range(500):
            self.db.insert({
                'id': i,
                'age': 20 + (i % 60),
                'department': ['sales', 'engineering', 'hr'][i % 3],
                'active': i % 5 != 0,
                'score': (i * 7) % 100
            })
        
        Query_obj = Query()
        
        # Measure: complex AND query
        def complex_query():
            return self.db.search(
                (Query_obj.age > 30) &
                (Query_obj.department == 'engineering') &
                (Query_obj.active == True)
            )
        
        results, exec_time = measure_execution_time(complex_query)
        _, memory_alloc, _ = measure_memory_usage(complex_query)
        
        # Verify: query succeeds and returns results
        assert isinstance(results, list)
        
        benchmark = BenchmarkResult(
            name='complex_multi_condition_query_500_items',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_query_with_multiple_iterations_performance(self):
        """Measure performance when running same query multiple times (caching/optimization test)."""
        # Setup: insert 200 documents
        for i in range(200):
            self.db.insert({'id': i, 'type': 'A' if i < 100 else 'B', 'value': i})
        
        Query_obj = Query()
        
        # Measure: run same query 100 times
        def repeated_query():
            results = []
            for _ in range(100):
                results.extend(self.db.search(Query_obj.type == 'A'))
            return results
        
        results, exec_time = measure_execution_time(repeated_query)
        _, memory_alloc, _ = measure_memory_usage(repeated_query)
        
        # Verify: all queries executed successfully
        assert len(results) == 10000  # 100 items * 100 iterations
        
        benchmark = BenchmarkResult(
            name='repeated_query_100_iterations',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc,
            metadata={'iterations': 100, 'dataset_size': 200}
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=25.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_update_with_query_performance(self):
        """Measure performance of update operations filtered by query."""
        # Setup: insert 300 documents
        for i in range(300):
            self.db.insert({
                'id': i,
                'status': 'pending',
                'priority': i % 5
            })
        
        Query_obj = Query()
        
        # Measure: update all pending items with priority > 2
        def update_filtered():
            return self.db.update(
                {'status': 'processed'},
                (Query_obj.status == 'pending') & (Query_obj.priority > 2)
            )
        
        count, exec_time = measure_execution_time(update_filtered)
        _, memory_alloc, _ = measure_memory_usage(update_filtered)
        
        # Verify: correct number of items updated
        assert count > 0
        
        benchmark = BenchmarkResult(
            name='update_with_query_300_items',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
