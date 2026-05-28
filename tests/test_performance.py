"""Performance regression tests for TinyDB critical paths.

These benchmarks measure insert, query, and update operations across
memory and JSON storage backends to catch performance regressions.
"""

import tempfile
from pathlib import Path

import pytest

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage
from tinydb.middlewares import CachingMiddleware


class TestInsertPerformance:
    """Benchmark insert operations across storage backends."""

    @pytest.fixture
    def memory_db(self):
        """Fresh in-memory database for each test."""
        db = TinyDB(storage=MemoryStorage)
        yield db
        db.close()

    @pytest.fixture
    def json_db(self, tmp_path):
        """Fresh JSON file-based database for each test."""
        db = TinyDB(tmp_path / "test.db", storage=JSONStorage)
        yield db
        db.close()

    def test_insert_single_memory(self, benchmark, memory_db):
        """Benchmark single document insert into memory storage."""
        def insert():
            memory_db.insert({"key": "value", "number": 42})
        benchmark(insert)

    def test_insert_single_json(self, benchmark, json_db):
        """Benchmark single document insert into JSON storage."""
        def insert():
            json_db.insert({"key": "value", "number": 42})
        benchmark(insert)

    def test_insert_batch_100_memory(self, benchmark, memory_db):
        """Benchmark bulk insert of 100 documents into memory storage."""
        def insert_batch():
            memory_db.insert_multiple(
                {"id": i, "data": f"doc_{i}"} for i in range(100)
            )
        benchmark(insert_batch)

    def test_insert_batch_100_json(self, benchmark, json_db):
        """Benchmark bulk insert of 100 documents into JSON storage."""
        def insert_batch():
            json_db.insert_multiple(
                {"id": i, "data": f"doc_{i}"} for i in range(100)
            )
        benchmark(insert_batch)


class TestQueryPerformance:
    """Benchmark query operations across storage backends."""

    @pytest.fixture
    def populated_memory_db(self):
        """In-memory database pre-populated with test data."""
        db = TinyDB(storage=MemoryStorage)
        db.insert_multiple(
            {"id": i, "category": "A" if i % 2 == 0 else "B", "value": i * 10}
            for i in range(1000)
        )
        yield db
        db.close()

    @pytest.fixture
    def populated_json_db(self, tmp_path):
        """JSON database pre-populated with test data."""
        db = TinyDB(tmp_path / "test.db", storage=JSONStorage)
        db.insert_multiple(
            {"id": i, "category": "A" if i % 2 == 0 else "B", "value": i * 10}
            for i in range(1000)
        )
        yield db
        db.close()

    def test_query_all_memory(self, benchmark, populated_memory_db):
        """Benchmark retrieving all documents from memory storage."""
        def query_all():
            return populated_memory_db.all()
        benchmark(query_all)

    def test_query_all_json(self, benchmark, populated_json_db):
        """Benchmark retrieving all documents from JSON storage."""
        def query_all():
            return populated_json_db.all()
        benchmark(query_all)

    def test_query_search_memory(self, benchmark, populated_memory_db):
        """Benchmark search query on memory storage."""
        from tinydb import Query
        q = Query()

        def query_search():
            return populated_memory_db.search(q.category == "A")
        benchmark(query_search)

    def test_query_search_json(self, benchmark, populated_json_db):
        """Benchmark search query on JSON storage."""
        from tinydb import Query
        q = Query()

        def query_search():
            return populated_json_db.search(q.category == "A")
        benchmark(query_search)

    def test_query_get_memory(self, benchmark, populated_memory_db):
        """Benchmark get_by_id on memory storage."""
        def query_get():
            return populated_memory_db.get_by_id(500)
        benchmark(query_get)

    def test_query_get_json(self, benchmark, populated_json_db):
        """Benchmark get_by_id on JSON storage."""
        def query_get():
            return populated_json_db.get_by_id(500)
        benchmark(query_get)


class TestUpdatePerformance:
    """Benchmark update operations across storage backends."""

    @pytest.fixture
    def populated_memory_db(self):
        """In-memory database pre-populated with test data."""
        db = TinyDB(storage=MemoryStorage)
        db.insert_multiple(
            {"id": i, "status": "pending", "count": 0}
            for i in range(500)
        )
        yield db
        db.close()

    @pytest.fixture
    def populated_json_db(self, tmp_path):
        """JSON database pre-populated with test data."""
        db = TinyDB(tmp_path / "test.db", storage=JSONStorage)
        db.insert_multiple(
            {"id": i, "status": "pending", "count": 0}
            for i in range(500)
        )
        yield db
        db.close()

    def test_update_single_memory(self, benchmark, populated_memory_db):
        """Benchmark updating a single document in memory storage."""
        counter = [0]

        def update():
            counter[0] += 1
            populated_memory_db.update({"status": "completed"}, doc_ids=[counter[0]])
        benchmark(update)

    def test_update_single_json(self, benchmark, populated_json_db):
        """Benchmark updating a single document in JSON storage."""
        counter = [0]

        def update():
            counter[0] += 1
            populated_json_db.update({"status": "completed"}, doc_ids=[counter[0]])
        benchmark(update)

    def test_update_batch_memory(self, benchmark, populated_memory_db):
        """Benchmark bulk update in memory storage."""
        from tinydb import Query
        q = Query()

        def update_batch():
            populated_memory_db.update({"status": "processed"}, q.status == "pending")
        benchmark(update_batch)

    def test_update_batch_json(self, benchmark, populated_json_db):
        """Benchmark bulk update in JSON storage."""
        from tinydb import Query
        q = Query()

        def update_batch():
            populated_json_db.update({"status": "processed"}, q.status == "pending")
        benchmark(update_batch)
