import pytest
from tinydb import TinyDB, where
from tinydb.storages import MemoryStorage


class TestBatchInsert:
    def test_batch_insert_basic(self):
        """Test basic batch insertion."""
        db = TinyDB(storage=MemoryStorage())
        elements = [{'data': i} for i in range(10)]
        ids = db.batch_insert(elements)
        
        assert len(ids) == 10
        assert all(isinstance(id, int) for id in ids)
        assert db.all() == [{'data': i, '_id': i+1} for i in range(10)]

    def test_batch_insert_empty(self):
        """Test batch insertion with empty list."""
        db = TinyDB(storage=MemoryStorage())
        ids = db.batch_insert([])
        
        assert ids == []
        assert db.all() == []

    def test_batch_insert_multiple_calls(self):
        """Test multiple batch insertions maintain correct IDs."""
        db = TinyDB(storage=MemoryStorage())
        ids1 = db.batch_insert([{'batch': 1, 'idx': i} for i in range(5)])
        ids2 = db.batch_insert([{'batch': 2, 'idx': i} for i in range(3)])
        
        assert ids1 == [1, 2, 3, 4, 5]
        assert ids2 == [6, 7, 8]
        assert len(db.all()) == 8

    def test_batch_insert_preserves_data(self):
        """Test that batch insertion preserves all data accurately."""
        db = TinyDB(storage=MemoryStorage())
        elements = [
            {'name': 'alice', 'age': 30},
            {'name': 'bob', 'age': 25},
            {'name': 'charlie', 'age': 35},
        ]
        ids = db.batch_insert(elements)
        
        for i, el in enumerate(elements):
            retrieved = db.get(doc_id=ids[i])
            assert retrieved['name'] == el['name']
            assert retrieved['age'] == el['age']


class TestBootstrap:
    def test_bootstrap_basic(self):
        """Test basic bootstrap with generator."""
        db = TinyDB(storage=MemoryStorage())
        ids = db.bootstrap(5, lambda i: {'index': i, 'value': i*2})
        
        assert len(ids) == 5
        docs = db.all()
        assert docs[0]['index'] == 0
        assert docs[4]['index'] == 4
        assert docs[2]['value'] == 4

    def test_bootstrap_zero_count(self):
        """Test bootstrap with zero count."""
        db = TinyDB(storage=MemoryStorage())
        ids = db.bootstrap(0, lambda i: {'data': i})
        
        assert ids == []
        assert db.all() == []

    def test_bootstrap_sequential_calls(self):
        """Test that bootstrap maintains ID sequence across calls."""
        db = TinyDB(storage=MemoryStorage())
        ids1 = db.bootstrap(3, lambda i: {'gen': 1, 'idx': i})
        ids2 = db.bootstrap(2, lambda i: {'gen': 2, 'idx': i})
        
        assert ids1 == [1, 2, 3]
        assert ids2 == [4, 5]

    def test_bootstrap_complex_generator(self):
        """Test bootstrap with complex data generation."""
        db = TinyDB(storage=MemoryStorage())
        
        def complex_gen(i):
            return {
                'id': i,
                'nested': {'level': i % 3},
                'list': [i, i+1, i+2],
                'text': f'doc_{i}'
            }
        
        ids = db.bootstrap(10, complex_gen)
        assert len(ids) == 10
        
        doc = db.get(doc_id=ids[5])
        assert doc['nested']['level'] == 2
        assert doc['list'] == [5, 6, 7]
