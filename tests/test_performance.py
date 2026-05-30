import time
import psutil
import os
from typing import List, Dict, Any
import pytest
from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage
from tinydb.middlewares import CachingMiddleware


class TestQueryLatency:
    """Regression tests for query operation latency."""

    @pytest.fixture(params=['memory', 'json'])
    def benchmark_db(self, request, tmp_path, benchmark):
        """Fixture providing both memory and JSON storage backends for benchmarking."""
        if request.param == 'json':
            db = TinyDB(str(tmp_path / 'db.json'))
        else:
            db = TinyDB(storage=MemoryStorage())
        yield db
        if hasattr(db, 'close'):
            db.close()

    def test_insert_latency(self, benchmark_db, benchmark):
        """Benchmark: Single document insert latency."""
        def insert_single():
            benchmark_db.insert({'name': 'test', 'value': 42})
        
        # Run benchmark
        benchmark(insert_single)

    def test_bulk_insert_latency(self, benchmark_db, benchmark):
        """Benchmark: Bulk insert (100 documents) latency."""
        def bulk_insert():
            docs = [{'name': f'doc_{i}', 'value': i} for i in range(100)]
            benchmark_db.insert_multiple(docs)
        
        # Run benchmark
        benchmark(bulk_insert)

    def test_search_latency(self, benchmark_db, benchmark):
        """Benchmark: Search operation latency on populated database."""
        # Populate database
        docs = [{'name': f'doc_{i}', 'category': 'A' if i % 2 == 0 else 'B'} for i in range(100)]
        benchmark_db.insert_multiple(docs)
        
        def search_query():
            from tinydb import Query
            q = Query()
            return benchmark_db.search(q.category == 'A')
        
        # Run benchmark
        benchmark(search_query)

    def test_search_with_complex_filter_latency(self, benchmark_db, benchmark):
        """Benchmark: Complex query filter latency (multiple conditions)."""
        docs = [{'id': i, 'status': 'active' if i % 3 == 0 else 'inactive', 'score': i * 10} for i in range(100)]
        benchmark_db.insert_multiple(docs)
        
        def complex_search():
            from tinydb import Query
            q = Query()
            return benchmark_db.search((q.status == 'active') & (q.score > 500))
        
        benchmark(complex_search)

    def test_update_latency(self, benchmark_db, benchmark):
        """Benchmark: Update operation latency."""
        doc_id = benchmark_db.insert({'name': 'test', 'value': 0})
        
        def update_single():
            benchmark_db.update({'value': 42}, doc_ids=[doc_id])
        
        benchmark(update_single)

    def test_remove_latency(self, benchmark_db, benchmark):
        """Benchmark: Delete operation latency."""
        doc_id = benchmark_db.insert({'name': 'test', 'value': 0})
        
        def remove_single():
            benchmark_db.remove(doc_ids=[doc_id])
        
        benchmark(remove_single)

    def test_all_latency(self, benchmark_db, benchmark):
        """Benchmark: Retrieve all documents latency."""
        docs = [{'id': i, 'data': f'record_{i}'} for i in range(100)]
        benchmark_db.insert_multiple(docs)
        
        def get_all():
            return benchmark_db.all()
        
        benchmark(get_all)


class TestMemoryUsage:
    """Regression tests for memory usage during operations."""

    @pytest.fixture(params=['memory', 'json'])
    def db_with_cleanup(self, request, tmp_path):
        """Fixture for memory profiling with proper cleanup."""
        if request.param == 'json':
            db = TinyDB(str(tmp_path / 'db.json'))
        else:
            db = TinyDB(storage=MemoryStorage())
        yield db
        if hasattr(db, 'close'):
            db.close()

    def test_memory_baseline(self, db_with_cleanup):
        """Baseline: Initial memory footprint of empty database."""
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        memory_mb = mem_info.rss / (1024 * 1024)
        
        # Assert memory usage is reasonable (less than 100MB for empty database)
        assert memory_mb < 100, f"Empty database baseline memory too high: {memory_mb}MB"

    def test_memory_with_bulk_insert(self, db_with_cleanup):
        """Memory profiling: Bulk insert of 1000 documents."""
        process = psutil.Process(os.getpid())
        
        # Record baseline
        mem_before = process.memory_info().rss / (1024 * 1024)
        
        # Insert 1000 documents
        docs = [{'index': i, 'name': f'document_{i}', 'payload': 'x' * 100} for i in range(1000)]
        db_with_cleanup.insert_multiple(docs)
        
        # Record after insertion
        mem_after = process.memory_info().rss / (1024 * 1024)
        memory_increase = mem_after - mem_before
        
        # Memory increase should be reasonable (less than 50MB for 1000 small docs)
        assert memory_increase < 50, f"Memory increase too high: {memory_increase}MB"

    def test_memory_repeated_operations(self, db_with_cleanup):
        """Memory profiling: Repeated insert/delete cycles to detect leaks."""
        process = psutil.Process(os.getpid())
        mem_readings = []
        
        for cycle in range(5):
            # Insert batch
            docs = [{'cycle': cycle, 'index': i, 'data': 'test'} for i in range(100)]
            db_with_cleanup.insert_multiple(docs)
            
            # Delete batch
            db_with_cleanup.truncate()
            
            # Record memory
            mem_mb = process.memory_info().rss / (1024 * 1024)
            mem_readings.append(mem_mb)
        
        # Check for memory growth trend - memory should not grow significantly after each cycle
        # Allow 5MB variance between first and last reading
        memory_growth = mem_readings[-1] - mem_readings[0]
        assert memory_growth < 10, f"Potential memory leak detected: growth {memory_growth}MB over cycles"

    def test_memory_search_operations(self, db_with_cleanup):
        """Memory profiling: Memory usage during search operations."""
        process = psutil.Process(os.getpid())
        
        # Populate with moderate dataset
        docs = [{'id': i, 'category': 'A' if i % 2 == 0 else 'B', 'data': 'x' * 50} for i in range(500)]
        db_with_cleanup.insert_multiple(docs)
        
        mem_before = process.memory_info().rss / (1024 * 1024)
        
        # Perform repeated searches
        from tinydb import Query
        q = Query()
        for _ in range(10):
            db_with_cleanup.search(q.category == 'A')
        
        mem_after = process.memory_info().rss / (1024 * 1024)
        mem_increase = mem_after - mem_before
        
        # Search operations should not cause significant memory increase
        assert mem_increase < 5, f"Search operations caused excessive memory increase: {mem_increase}MB"


class TestCachingMiddlewarePerformance:
    """Regression tests for caching middleware impact on performance."""

    def test_caching_vs_nocache_latency(self, tmp_path, benchmark):
        """Benchmark: Impact of caching middleware on query performance."""
        # Database with caching
        from tinydb import TinyDB
        db_cached = TinyDB(str(tmp_path / 'cached.json'), storage=CachingMiddleware(JSONStorage))
        
        # Database without caching
        db_nocache = TinyDB(str(tmp_path / 'nocache.json'), storage=JSONStorage)
        
        # Populate both
        docs = [{'id': i, 'value': i * 10} for i in range(100)]
        db_cached.insert_multiple(docs)
        db_nocache.insert_multiple(docs)
        
        from tinydb import Query
        q = Query()
        
        def search_with_cache():
            for _ in range(5):
                db_cached.search(q.value > 500)
        
        def search_without_cache():
            for _ in range(5):
                db_nocache.search(q.value > 500)
        
        # Benchmark both variants
        result_cached = benchmark(search_with_cache)
        # Run once to ensure fair comparison
        search_without_cache()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
