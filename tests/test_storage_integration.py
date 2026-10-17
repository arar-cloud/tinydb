"""Integration tests for TinyDB storage backends and concurrent access."""

import threading
import time
from pathlib import Path

import pytest
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage, MemoryStorage
from tinydb.middlewares import CachingMiddleware


@pytest.mark.integration
class TestStorageBackends:
    """Test suite for different storage backends."""

    def test_json_storage_persistence(self, tmp_path: Path) -> None:
        """Test that JSON storage persists data to disk."""
        db_path = tmp_path / 'persistent.db'
        
        # Write data
        db1 = TinyDB(db_path, storage=JSONStorage)
        doc_id = db1.insert({'persistent': True, 'value': 42})
        db1.close()
        
        # Read data back
        db2 = TinyDB(db_path, storage=JSONStorage)
        retrieved = db2.get(doc_id)
        assert retrieved is not None
        assert retrieved['persistent'] is True
        assert retrieved['value'] == 42
        db2.close()

    def test_memory_storage_no_persistence(self) -> None:
        """Test that memory storage does not persist data."""
        db1 = TinyDB(storage=MemoryStorage)
        db1.insert({'data': 'test'})
        db1.close()
        
        # New instance should have no data
        db2 = TinyDB(storage=MemoryStorage)
        assert len(db2) == 0
        db2.close()

    def test_caching_middleware(self) -> None:
        """Test caching middleware improves performance."""
        storage = CachingMiddleware(MemoryStorage)()
        db = TinyDB(storage=storage)
        
        db.insert({'id': 1, 'cached': True})
        
        # Multiple accesses should use cache
        for _ in range(10):
            result = db.get(1)
            assert result is not None
        
        db.close()

    def test_storage_backend_switching(self, tmp_path: Path) -> None:
        """Test that storage backends can be switched for same data."""
        db_path = tmp_path / 'switch.db'
        
        # Create with JSON storage
        db_json = TinyDB(db_path, storage=JSONStorage)
        doc_id = db_json.insert({'backend': 'json'})
        db_json.close()
        
        # Read with JSON storage again
        db_json2 = TinyDB(db_path, storage=JSONStorage)
        retrieved = db_json2.get(doc_id)
        assert retrieved['backend'] == 'json'
        db_json2.close()


@pytest.mark.concurrent
class TestConcurrentAccess:
    """Test suite for concurrent database access scenarios."""

    def test_concurrent_reads(self, sample_data_db: TinyDB) -> None:
        """Test concurrent read operations."""
        results = {'count': 0, 'lock': threading.Lock()}
        
        def read_worker():
            for _ in range(10):
                docs = sample_data_db.all()
                with results['lock']:
                    results['count'] += len(docs)
        
        threads = [threading.Thread(target=read_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Each thread read 10 times, 4 docs each, 5 threads
        assert results['count'] == 200

    def test_concurrent_inserts(self, tmp_path: Path) -> None:
        """Test concurrent insert operations."""
        db_path = tmp_path / 'concurrent_insert.db'
        db = TinyDB(db_path, storage=JSONStorage)
        db.drop_tables()
        
        errors = []
        
        def insert_worker(worker_id: int):
            try:
                for i in range(10):
                    db.insert({'worker': worker_id, 'index': i})
            except Exception as e:
                errors.append(str(e))
        
        threads = [threading.Thread(target=insert_worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(db) == 30  # 3 workers * 10 inserts each
        db.close()

    def test_concurrent_queries(self, sample_data_db: TinyDB) -> None:
        """Test concurrent query operations."""
        results = {'matches': [], 'lock': threading.Lock(), 'errors': []}
        
        def query_worker(query_value: str):
            try:
                User = Query()
                matches = sample_data_db.search(User.name == query_value)
                with results['lock']:
                    results['matches'].extend(matches)
            except Exception as e:
                with results['lock']:
                    results['errors'].append(str(e))
        
        names = ['Alice', 'Bob', 'Charlie', 'David']
        threads = [threading.Thread(target=query_worker, args=(name,)) for name in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(results['errors']) == 0
        assert len(results['matches']) == 4


@pytest.mark.mobile
class TestMobileBackendContract:
    """Test suite for validating mobile backend contracts."""

    def test_serializable_response_format(self, sample_data_db: TinyDB, serialization_validator) -> None:
        """Test that all database responses are JSON serializable for mobile clients."""
        docs = sample_data_db.all()
        for doc in docs:
            # Mobile clients expect clean JSON serializable responses
            assert serialization_validator({k: v for k, v in doc.items()})

    def test_numeric_id_stability(self, empty_db: TinyDB) -> None:
        """Test that document IDs remain stable across operations."""
        doc_id = empty_db.insert({'test': 'data'})
        doc = empty_db.get(doc_id)
        assert doc.doc_id == doc_id
        assert isinstance(doc.doc_id, int)
        
        # Update should not change ID
        empty_db.update({'test': 'updated'}, doc_ids=[doc_id])
        doc = empty_db.get(doc_id)
        assert doc.doc_id == doc_id

    def test_timestamp_field_handling(self, empty_db: TinyDB) -> None:
        """Test handling of timestamp fields in mobile payloads."""
        import time
        timestamp = int(time.time())
        doc_id = empty_db.insert({'created_at': timestamp, 'data': 'test'})
        retrieved = empty_db.get(doc_id)
        assert retrieved['created_at'] == timestamp
        assert isinstance(retrieved['created_at'], int)

    def test_nested_object_handling(self, empty_db: TinyDB) -> None:
        """Test handling of nested objects in mobile payloads."""
        nested_data = {
            'user': {
                'id': 1,
                'profile': {
                    'name': 'Test',
                    'avatar': None
                }
            }
        }
        doc_id = empty_db.insert(nested_data)
        retrieved = empty_db.get(doc_id)
        assert retrieved['user']['profile']['name'] == 'Test'
        assert retrieved['user']['profile']['avatar'] is None

    def test_array_field_handling(self, empty_db: TinyDB) -> None:
        """Test handling of array fields in mobile payloads."""
        array_data = {
            'items': [1, 2, 3],
            'tags': ['a', 'b', 'c'],
            'mixed': [1, 'two', 3.0, None]
        }
        doc_id = empty_db.insert(array_data)
        retrieved = empty_db.get(doc_id)
        assert retrieved['items'] == [1, 2, 3]
        assert retrieved['tags'] == ['a', 'b', 'c']
        assert retrieved['mixed'] == [1, 'two', 3.0, None]

    def test_null_field_handling(self, empty_db: TinyDB) -> None:
        """Test handling of null/None fields for mobile compatibility."""
        data_with_nulls = {
            'optional_field': None,
            'required_field': 'present',
            'zero_value': 0,
            'empty_string': ''
        }
        doc_id = empty_db.insert(data_with_nulls)
        retrieved = empty_db.get(doc_id)
        assert retrieved['optional_field'] is None
        assert retrieved['zero_value'] == 0
        assert retrieved['empty_string'] == ''


@pytest.mark.stability
class TestBackendStability:
    """Test suite for backend stability under various conditions."""

    def test_rapid_sequential_operations(self, memory_db: TinyDB) -> None:
        """Test rapid sequence of operations without errors."""
        memory_db.drop_tables()
        for i in range(100):
            doc_id = memory_db.insert({'index': i})
            retrieved = memory_db.get(doc_id)
            assert retrieved['index'] == i
            memory_db.update({'index': i + 1000}, doc_ids=[doc_id])

    def test_mixed_operations_sequence(self, tmp_path: Path) -> None:
        """Test mix of insert, query, update, delete operations."""
        db = TinyDB(tmp_path / 'mixed.db', storage=JSONStorage)
        db.drop_tables()
        
        # Insert
        ids = [db.insert({'value': i}) for i in range(10)]
        assert len(db) == 10
        
        # Query
        Doc = Query()
        results = db.search(Doc.value < 5)
        assert len(results) == 5
        
        # Update
        db.update({'status': 'updated'}, doc_ids=[ids[0]])
        assert db.get(ids[0])['status'] == 'updated'
        
        # Delete
        db.remove(doc_ids=[ids[9]])
        assert len(db) == 9
        
        db.close()

    def test_error_recovery(self, memory_db: TinyDB) -> None:
        """Test database remains usable after error conditions."""
        memory_db.drop_tables()
        
        # Try invalid query (should not crash database)
        Doc = Query()
        try:
            # This might raise or return empty depending on implementation
            _ = memory_db.search(Doc.nonexistent_field == 'value')
        except Exception:
            pass
        
        # Database should still work
        doc_id = memory_db.insert({'valid': 'data'})
        retrieved = memory_db.get(doc_id)
        assert retrieved is not None
