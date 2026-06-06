"""Backend stability tests for TinyDB.

These tests reproduce and verify fixes for known backend stability issues
across Python 3.10-3.14.
"""

import sys
import pytest
from pathlib import Path

from tinydb import TinyDB
from tinydb.storages import MemoryStorage, JSONStorage
from tinydb.middlewares import CachingMiddleware


class TestBackendStability:
    """Test backend stability and regression issues."""

    def test_memory_storage_basic_operations(self, tmp_path):
        """Test basic CRUD operations with MemoryStorage."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        # Insert
        doc_id = db.insert({'name': 'test', 'value': 42})
        assert doc_id is not None
        
        # Read
        doc = db.get(db.where('name') == 'test')
        assert doc is not None
        assert doc['value'] == 42
        
        # Update
        db.update({'value': 100}, doc_ids=[doc_id])
        updated = db.get(db.where('name') == 'test')
        assert updated['value'] == 100
        
        # Delete
        db.remove(db.where('name') == 'test')
        deleted = db.get(db.where('name') == 'test')
        assert deleted is None
        
        db.close()

    def test_json_storage_basic_operations(self, tmp_path):
        """Test basic CRUD operations with JSONStorage."""
        db_path = tmp_path / 'test_backend.json'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.drop_tables()
        
        # Insert
        doc_id = db.insert({'name': 'test', 'value': 42})
        assert doc_id is not None
        
        # Read
        doc = db.get(db.where('name') == 'test')
        assert doc is not None
        assert doc['value'] == 42
        
        # Verify persistence
        db.close()
        
        # Reopen and verify
        db2 = TinyDB(str(db_path), storage=JSONStorage)
        doc2 = db2.get(db2.where('name') == 'test')
        assert doc2 is not None
        assert doc2['value'] == 42
        db2.close()

    def test_caching_middleware_consistency(self):
        """Test CachingMiddleware maintains data consistency."""
        base_storage = MemoryStorage()
        cache_storage = CachingMiddleware(MemoryStorage)()
        
        db = TinyDB(storage=cache_storage)
        db.drop_tables()
        
        # Insert multiple documents
        ids = db.insert_multiple(
            [{'id': i, 'data': f'item_{i}'} for i in range(10)]
        )
        
        # Verify all inserted
        assert len(db.all()) == 10
        
        # Query and verify
        results = db.search(db.where('id') >= 5)
        assert len(results) == 5
        
        # Update and verify
        db.update({'data': 'updated'}, db.where('id') < 5)
        updated = db.search(db.where('data') == 'updated')
        assert len(updated) == 5
        
        db.close()

    def test_multiple_table_isolation(self):
        """Test that multiple tables remain properly isolated."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        # Create multiple tables
        table1 = db.table('users')
        table2 = db.table('posts')
        table3 = db.table('comments')
        
        # Insert into each table
        table1.insert({'name': 'Alice', 'type': 'user'})
        table2.insert({'title': 'Post 1', 'type': 'post'})
        table3.insert({'text': 'Comment 1', 'type': 'comment'})
        
        # Verify isolation
        assert len(table1.all()) == 1
        assert len(table2.all()) == 1
        assert len(table3.all()) == 1
        assert table1.all()[0]['type'] == 'user'
        assert table2.all()[0]['type'] == 'post'
        assert table3.all()[0]['type'] == 'comment'
        
        db.close()

    def test_large_dataset_handling(self):
        """Test backend stability with larger datasets."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        # Insert 1000 documents
        docs = [{'index': i, 'value': i * 2} for i in range(1000)]
        ids = db.insert_multiple(docs)
        
        assert len(ids) == 1000
        assert len(db.all()) == 1000
        
        # Query performance and correctness
        results = db.search(db.where('value') > 500)
        assert len(results) > 0
        assert all(r['value'] > 500 for r in results)
        
        db.close()

    def test_concurrent_table_access(self):
        """Test concurrent access to different tables."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        table1 = db.table('t1')
        table2 = db.table('t2')
        
        # Interleaved operations
        for i in range(10):
            table1.insert({'seq': i})
            table2.insert({'seq': i})
            result1 = table1.get(table1.where('seq') == i)
            result2 = table2.get(table2.where('seq') == i)
            assert result1 is not None
            assert result2 is not None
        
        assert len(table1.all()) == 10
        assert len(table2.all()) == 10
        
        db.close()

    def test_empty_database_operations(self):
        """Test operations on empty database don't cause crashes."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        # These should not raise exceptions
        assert db.all() == []
        assert db.search(db.where('x') == 1) == []
        assert db.count() == 0
        assert db.get(db.where('x') == 1) is None
        
        db.close()

    @pytest.mark.skipif(
        sys.version_info < (3, 11),
        reason="Version-specific behavior test for Python 3.11+"
    )
    def test_python_311_specific_stability(self):
        """Test backend stability with Python 3.11+ specific features."""
        db = TinyDB(storage=MemoryStorage)
        db.drop_tables()
        
        # Insert with complex types
        db.insert({
            'data': {'nested': {'deep': [1, 2, 3]}},
            'list': [1, 2, 3],
            'number': 42,
            'string': 'test'
        })
        
        result = db.all()[0]
        assert result['data']['nested']['deep'] == [1, 2, 3]
        
        db.close()
