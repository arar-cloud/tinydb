"""Performance regression tests for TinyDB core operations.

Uses pytest-benchmark to track insert, query, update, and delete operation
latencies and verify they stay within target thresholds for mobile/backend
constraints.
"""
import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage
from tinydb.middlewares import CachingMiddleware


@pytest.fixture
def benchmark_db():
    """Create a fresh in-memory database for each benchmark."""
    db = TinyDB(storage=MemoryStorage)
    db.truncate()
    yield db
    db.close()


class TestInsertPerformance:
    """Benchmark insert operation performance."""

    def test_single_insert_latency(self, benchmark, benchmark_db):
        """Single document insert should complete in <1ms.
        
        This is a fundamental operation that should be very fast even on
        constrained mobile devices.
        """
        def insert_single():
            benchmark_db.insert({'id': 1, 'value': 'test', 'number': 42})

        result = benchmark(insert_single)
        # Assert mean latency stays below 1ms
        assert benchmark.stats.mean < 0.001, \
            f"Single insert took {benchmark.stats.mean*1000:.2f}ms, expected <1ms"

    def test_bulk_insert_100_docs(self, benchmark, benchmark_db):
        """Bulk insert of 100 documents should complete in <50ms.
        
        Bulk operations are common for data loading and should maintain
        reasonable performance under typical mobile/backend constraints.
        """
        documents = [
            {'id': i, 'value': f'doc_{i}', 'number': i * 2}
            for i in range(100)
        ]

        def bulk_insert():
            benchmark_db.insert_multiple(documents)

        result = benchmark(bulk_insert)
        # Assert mean latency stays below 50ms
        assert benchmark.stats.mean < 0.050, \
            f"Bulk insert of 100 docs took {benchmark.stats.mean*1000:.2f}ms, expected <50ms"

    def test_bulk_insert_1000_docs(self, benchmark, benchmark_db):
        """Bulk insert of 1000 documents should complete in <500ms.
        
        Large bulk operations should remain efficient for data synchronization
        and initialization scenarios.
        """
        documents = [
            {'id': i, 'value': f'doc_{i}', 'number': i * 2, 'category': i % 10}
            for i in range(1000)
        ]

        def bulk_insert():
            benchmark_db.insert_multiple(documents)

        result = benchmark(bulk_insert)
        # Assert mean latency stays below 500ms
        assert benchmark.stats.mean < 0.500, \
            f"Bulk insert of 1000 docs took {benchmark.stats.mean*1000:.2f}ms, expected <500ms"


class TestQueryPerformance:
    """Benchmark query operation performance."""

    @pytest.fixture
    def populated_db(self, benchmark_db):
        """Populate database with test data for query benchmarks."""
        docs = [{'id': i, 'value': f'doc_{i}', 'number': i, 'category': i % 5}
                for i in range(500)]
        benchmark_db.insert_multiple(docs)
        return benchmark_db

    def test_simple_equality_query(self, benchmark, populated_db):
        """Simple equality query should complete in <5ms for 500 documents.
        
        Basic filtering queries are frequent and must be responsive on
        mobile devices.
        """
        from tinydb import Query
        q = Query()

        def query_by_id():
            return populated_db.search(q.id == 250)

        result = benchmark(query_by_id)
        # Assert mean latency stays below 5ms
        assert benchmark.stats.mean < 0.005, \
            f"Simple query took {benchmark.stats.mean*1000:.2f}ms, expected <5ms"
        # Verify query correctness
        assert len(result) == 1
        assert result[0]['id'] == 250

    def test_range_query(self, benchmark, populated_db):
        """Range query should complete in <10ms for 500 documents.
        
        Range queries are common for filtering and pagination.
        """
        from tinydb import Query
        q = Query()

        def range_query():
            return populated_db.search((q.number >= 100) & (q.number < 200))

        result = benchmark(range_query)
        # Assert mean latency stays below 10ms
        assert benchmark.stats.mean < 0.010, \
            f"Range query took {benchmark.stats.mean*1000:.2f}ms, expected <10ms"
        # Verify query correctness
        assert len(result) == 100

    def test_complex_query(self, benchmark, populated_db):
        """Complex multi-condition query should complete in <15ms for 500 documents.
        
        Complex queries with multiple conditions should remain responsive.
        """
        from tinydb import Query
        q = Query()

        def complex_query():
            return populated_db.search(
                ((q.number > 50) & (q.number < 200)) | (q.category == 0)
            )

        result = benchmark(complex_query)
        # Assert mean latency stays below 15ms
        assert benchmark.stats.mean < 0.015, \
            f"Complex query took {benchmark.stats.mean*1000:.2f}ms, expected <15ms"
        # Verify results exist
        assert len(result) > 0

    def test_get_all_query(self, benchmark, populated_db):
        """Get all documents should complete in <10ms for 500 documents.
        
        Retrieving all documents is a common operation that must scale
        linearly with document count.
        """
        def get_all():
            return populated_db.all()

        result = benchmark(get_all)
        # Assert mean latency stays below 10ms
        assert benchmark.stats.mean < 0.010, \
            f"Get all took {benchmark.stats.mean*1000:.2f}ms, expected <10ms"
        # Verify all documents retrieved
        assert len(result) == 500


class TestUpdatePerformance:
    """Benchmark update operation performance."""

    @pytest.fixture
    def populated_db(self, benchmark_db):
        """Populate database with test data for update benchmarks."""
        docs = [{'id': i, 'value': f'doc_{i}', 'number': i, 'status': 'pending'}
                for i in range(500)]
        benchmark_db.insert_multiple(docs)
        return benchmark_db

    def test_single_document_update(self, benchmark, populated_db):
        """Update single document should complete in <2ms.
        
        Single record updates must be fast for real-time applications.
        """
        from tinydb import Query
        q = Query()

        def update_single():
            populated_db.update({'status': 'updated'}, q.id == 250)

        result = benchmark(update_single)
        # Assert mean latency stays below 2ms
        assert benchmark.stats.mean < 0.002, \
            f"Single update took {benchmark.stats.mean*1000:.2f}ms, expected <2ms"

    def test_bulk_update_100_docs(self, benchmark, populated_db):
        """Update 100 documents should complete in <30ms.
        
        Bulk updates are used for state synchronization and batch processing.
        """
        from tinydb import Query
        q = Query()

        def update_bulk():
            populated_db.update(
                {'status': 'processed'},
                (q.number >= 100) & (q.number < 200)
            )

        result = benchmark(update_bulk)
        # Assert mean latency stays below 30ms
        assert benchmark.stats.mean < 0.030, \
            f"Bulk update of 100 docs took {benchmark.stats.mean*1000:.2f}ms, expected <30ms"

    def test_update_all_documents(self, benchmark, populated_db):
        """Update all documents should complete in <100ms for 500 documents.
        
        Full table updates should maintain reasonable performance.
        """
        def update_all():
            populated_db.update_multiple(
                [{'value': f'updated_{doc.doc_id}'} for doc in populated_db.all()]
            )

        result = benchmark(update_all)
        # Assert mean latency stays below 100ms
        assert benchmark.stats.mean < 0.100, \
            f"Update all took {benchmark.stats.mean*1000:.2f}ms, expected <100ms"


class TestDeletePerformance:
    """Benchmark delete operation performance."""

    @pytest.fixture
    def populated_db(self, benchmark_db):
        """Populate database with test data for delete benchmarks."""
        docs = [{'id': i, 'value': f'doc_{i}', 'number': i}
                for i in range(500)]
        benchmark_db.insert_multiple(docs)
        return benchmark_db

    def test_single_document_delete(self, benchmark, benchmark_db):
        """Delete single document should complete in <1ms.
        
        Single deletions are quick operations essential for CRUD workflows.
        """
        from tinydb import Query
        q = Query()
        
        # Insert a fresh document for each benchmark iteration
        benchmark_db.insert({'id': 999, 'value': 'to_delete'})

        def delete_single():
            benchmark_db.remove(q.id == 999)
            # Re-insert for next iteration
            benchmark_db.insert({'id': 999, 'value': 'to_delete'})

        result = benchmark(delete_single)
        # Assert mean latency stays below 1ms
        assert benchmark.stats.mean < 0.001, \
            f"Single delete took {benchmark.stats.mean*1000:.2f}ms, expected <1ms"

    def test_bulk_delete_100_docs(self, benchmark, benchmark_db):
        """Delete 100 documents should complete in <20ms.
        
        Bulk deletes are used for cleanup and purging operations.
        """
        from tinydb import Query
        q = Query()
        
        # Setup docs for first iteration
        docs = [{'id': i, 'number': i} for i in range(600)]
        benchmark_db.insert_multiple(docs)

        def delete_bulk():
            # Delete 100 docs and re-insert
            count = benchmark_db.remove((q.number >= 0) & (q.number < 100))
            new_docs = [{'id': 1000 + i, 'number': i} for i in range(100)]
            benchmark_db.insert_multiple(new_docs)

        result = benchmark(delete_bulk)
        # Assert mean latency stays below 20ms
        assert benchmark.stats.mean < 0.020, \
            f"Bulk delete of 100 docs took {benchmark.stats.mean*1000:.2f}ms, expected <20ms"


class TestCachedStoragePerformance:
    """Benchmark performance with caching middleware."""

    @pytest.fixture
    def cached_db():
        """Create database with caching middleware enabled."""
        db = TinyDB(storage=CachingMiddleware(MemoryStorage)())
        db.truncate()
        return db

    def test_cached_repeated_queries(self, benchmark, cached_db):
        """Repeated queries should be faster with caching middleware.
        
        Caching should provide significant speedup for repeated queries
        on unchanged data.
        """
        from tinydb import Query
        q = Query()
        
        # Populate with data
        docs = [{'id': i, 'value': f'doc_{i}'} for i in range(200)]
        cached_db.insert_multiple(docs)

        def repeated_query():
            for _ in range(10):
                cached_db.search(q.id == 100)

        result = benchmark(repeated_query)
        # Assert mean latency stays below 10ms for 10 repeated queries
        assert benchmark.stats.mean < 0.010, \
            f"Cached repeated queries took {benchmark.stats.mean*1000:.2f}ms, expected <10ms"
