import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage


def test_batch_insert_basic():
    """Test basic batch_insert functionality."""
    db = TinyDB(storage=MemoryStorage())
    table = db.table('test')
    
    documents = [
        {'name': 'Alice', 'age': 30},
        {'name': 'Bob', 'age': 25},
        {'name': 'Charlie', 'age': 35},
    ]
    
    ids = table.batch_insert(documents)
    assert len(ids) == 3
    assert ids == [1, 2, 3]
    assert len(table) == 3


def test_batch_insert_bootstrap_mode():
    """Test batch_insert with bootstrap_mode enabled."""
    db = TinyDB(storage=MemoryStorage())
    table = db.table('test')
    
    documents = [
        {'id': i, 'value': f'doc_{i}'}
        for i in range(100)
    ]
    
    ids = table.batch_insert(documents, bootstrap_mode=True)
    assert len(ids) == 100
    assert len(table) == 100


def test_batch_insert_empty_list():
    """Test batch_insert with empty document list."""
    db = TinyDB(storage=MemoryStorage())
    table = db.table('test')
    
    ids = table.batch_insert([])
    assert ids == []
    assert len(table) == 0


def test_batch_insert_invalid_input():
    """Test batch_insert with invalid inputs."""
    db = TinyDB(storage=MemoryStorage())
    table = db.table('test')
    
    # Test non-list input
    with pytest.raises(ValueError, match='Documents must be a list'):
        table.batch_insert({'name': 'Alice'})
    
    # Test non-dict document
    with pytest.raises(ValueError, match='Each document must be a dict'):
        table.batch_insert(['not a dict'])


def test_batch_insert_preserves_order():
    """Test that batch_insert preserves document order."""
    db = TinyDB(storage=MemoryStorage())
    table = db.table('test')
    
    documents = [
        {'seq': i}
        for i in range(10)
    ]
    
    table.batch_insert(documents, bootstrap_mode=True)
    results = table.all()
    for i, doc in enumerate(results):
        assert doc['seq'] == i
