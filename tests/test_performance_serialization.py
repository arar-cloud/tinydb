"""Performance regression tests for TinyDB serialization and storage operations.

Tests measure execution time and memory allocation for:
- JSON serialization of various data structures
- Database write operations
- Database read operations
- Large payload handling
"""

import pytest
import json
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
from tests.benchmarks import (
    BenchmarkResult,
    PerformanceBaseline,
    measure_execution_time,
    measure_memory_usage,
)


class TestSerializationPerformance:
    """Regression tests for serialization performance."""
    
    def setup_method(self):
        """Setup test database and baseline tracker."""
        self.db = TinyDB(storage=MemoryStorage())
        self.baseline = PerformanceBaseline('.serialization_performance_baseline.json')
    
    def teardown_method(self):
        """Cleanup."""
        if self.db:
            self.db.close()
    
    def test_insert_small_documents_performance(self):
        """Measure performance of inserting 500 small documents (simple fields)."""
        # Prepare: 500 simple documents
        documents = [
            {'id': i, 'name': f'user_{i}', 'active': True}
            for i in range(500)
        ]
        
        # Measure: bulk insert operation
        def bulk_insert():
            for doc in documents:
                self.db.insert(doc)
            return len(self.db)
        
        count, exec_time = measure_execution_time(bulk_insert)
        _, memory_alloc, _ = measure_memory_usage(bulk_insert)
        
        # Verify: all inserted
        assert count == 500
        
        benchmark = BenchmarkResult(
            name='insert_500_small_documents',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc,
            metadata={'document_count': 500, 'avg_size': 'small'}
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_insert_large_documents_performance(self):
        """Measure performance of inserting 100 large documents (complex nested structures)."""
        # Prepare: 100 large nested documents (~2KB each)
        documents = [
            {
                'id': i,
                'user_id': f'user_{i}',
                'metadata': {
                    'tags': [f'tag_{j}' for j in range(50)],
                    'scores': [j * 1.5 for j in range(50)],
                    'nested': {
                        'level2': {
                            'level3': {
                                'data': f'value_{i}_{j}' * 10
                            } for j in range(5)
                        }
                    }
                },
                'content': 'x' * 1000  # ~1KB of text
            }
            for i in range(100)
        ]
        
        # Measure: bulk insert of large documents
        def insert_large_docs():
            for doc in documents:
                self.db.insert(doc)
            return len(self.db)
        
        count, exec_time = measure_execution_time(insert_large_docs)
        _, memory_alloc, _ = measure_memory_usage(insert_large_docs)
        
        # Verify: all inserted
        assert count == 100
        
        benchmark = BenchmarkResult(
            name='insert_100_large_documents',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc,
            metadata={'document_count': 100, 'avg_size': 'large (~2KB)'}
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=25.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_read_all_documents_performance(self):
        """Measure performance of reading/deserializing 1000 documents."""
        # Setup: insert 1000 documents
        for i in range(1000):
            self.db.insert({
                'id': i,
                'data': f'item_{i}',
                'value': i * 1.5,
                'active': i % 2 == 0
            })
        
        # Measure: read all documents
        def read_all():
            return self.db.all()
        
        results, exec_time = measure_execution_time(read_all)
        _, memory_alloc, _ = measure_memory_usage(read_all)
        
        # Verify: all documents retrieved
        assert len(results) == 1000
        
        benchmark = BenchmarkResult(
            name='read_1000_documents',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_json_serialization_performance(self):
        """Measure raw JSON serialization performance (not TinyDB-specific)."""
        # Prepare: large data structure to serialize
        data = {
            'users': [
                {
                    'id': i,
                    'name': f'User_{i}',
                    'email': f'user_{i}@example.com',
                    'metadata': {
                        'tags': [f'tag_{j}' for j in range(10)],
                        'scores': [j * 1.1 for j in range(20)]
                    }
                }
                for i in range(1000)
            ]
        }
        
        # Measure: JSON serialization
        def serialize():
            return json.dumps(data)
        
        result, exec_time = measure_execution_time(serialize)
        _, memory_alloc, _ = measure_memory_usage(serialize)
        
        # Verify: serialization succeeded
        assert len(result) > 0
        
        benchmark = BenchmarkResult(
            name='json_serialize_1000_objects',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc,
            metadata={'object_count': 1000}
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=25.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_json_deserialization_performance(self):
        """Measure raw JSON deserialization performance."""
        # Prepare: JSON string of large data structure
        data = {
            'records': [
                {
                    'id': i,
                    'value': f'item_{i}',
                    'nested': {
                        'field1': i * 2,
                        'field2': f'data_{i}' * 5,
                        'field3': [j for j in range(5)]
                    }
                }
                for i in range(2000)
            ]
        }
        json_str = json.dumps(data)
        
        # Measure: JSON deserialization
        def deserialize():
            return json.loads(json_str)
        
        result, exec_time = measure_execution_time(deserialize)
        _, memory_alloc, _ = measure_memory_usage(deserialize)
        
        # Verify: deserialization succeeded
        assert len(result['records']) == 2000
        
        benchmark = BenchmarkResult(
            name='json_deserialize_2000_objects',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc,
            metadata={'object_count': 2000}
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=25.0)
        assert passed, f"Regression detected: {msg}"
    
    def test_update_document_serialization_performance(self):
        """Measure performance of updating documents (requires serialization)."""
        # Setup: insert 200 documents
        for i in range(200):
            self.db.insert({
                'id': i,
                'status': 'initial',
                'count': 0,
                'data': f'content_{i}'
            })
        
        Query_obj = Query()
        
        # Measure: update all documents
        def update_all():
            return self.db.update(
                {'status': 'updated', 'count': 1},
                Query_obj.count == 0
            )
        
        count, exec_time = measure_execution_time(update_all)
        _, memory_alloc, _ = measure_memory_usage(update_all)
        
        # Verify: correct number of documents updated
        assert count == 200
        
        benchmark = BenchmarkResult(
            name='update_200_documents_serialization',
            execution_time_ms=exec_time,
            memory_allocated_bytes=memory_alloc,
            peak_memory_bytes=memory_alloc
        )
        
        passed, msg = self.baseline.check_regression(benchmark, tolerance_percent=20.0)
        assert passed, f"Regression detected: {msg}"
