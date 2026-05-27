import os.path
import tempfile
import threading
import json
from pathlib import Path
from typing import Generator, Any, Dict

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage, Query


@pytest.fixture(params=['memory', 'json'])
def db(request, tmp_path: Path):
    if request.param == 'json':
        db_ = TinyDB(tmp_path / 'test.db', storage=JSONStorage)
    else:
        db_ = TinyDB(storage=MemoryStorage)

    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    yield db_


@pytest.fixture
def storage():
    """Fixture for caching middleware with memory storage."""
    return CachingMiddleware(MemoryStorage)()


@pytest.fixture
def empty_db(tmp_path: Path) -> Generator[TinyDB, None, None]:
    """Fixture for empty database for testing initialization."""
    db_path = tmp_path / 'empty.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def sample_data_db(tmp_path: Path) -> Generator[TinyDB, None, None]:
    """Fixture for database with sample data for query testing."""
    db_path = tmp_path / 'sample.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    
    # Insert diverse sample data for query validation
    sample_docs = [
        {'id': 1, 'name': 'Alice', 'age': 30, 'status': 'active'},
        {'id': 2, 'name': 'Bob', 'age': 25, 'status': 'inactive'},
        {'id': 3, 'name': 'Charlie', 'age': 35, 'status': 'active'},
        {'id': 4, 'name': 'David', 'age': 28, 'status': 'active'},
    ]
    db_.insert_multiple(sample_docs)
    yield db_
    db_.close()


@pytest.fixture
def memory_db() -> Generator[TinyDB, None, None]:
    """Fixture for in-memory database for fast unit tests."""
    db_ = TinyDB(storage=MemoryStorage)
    db_.drop_tables()
    db_.insert_multiple(
        {'int': i, 'char': c, 'float': i * 1.5}
        for i, c in enumerate('abcdef', 1)
    )
    yield db_


@pytest.fixture
def concurrent_access_db(tmp_path: Path) -> Generator[Dict[str, Any], None, None]:
    """Fixture for testing concurrent database access scenarios."""
    db_path = tmp_path / 'concurrent.db'
    results = {'errors': [], 'lock': threading.Lock()}
    
    def _access_db():
        """Worker function for concurrent access testing."""
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({'thread_id': threading.current_thread().ident})
            db.close()
        except Exception as e:
            with results['lock']:
                results['errors'].append(str(e))
    
    # Initialize database
    db_init = TinyDB(db_path, storage=JSONStorage)
    db_init.drop_tables()
    db_init.close()
    
    results['db_path'] = db_path
    results['access_worker'] = _access_db
    
    yield results


@pytest.fixture
def serialization_validator():
    """Fixture for validating JSON serialization/deserialization of database records."""
    def _validate(data: Dict[str, Any]) -> bool:
        """Validate that data can be serialized and deserialized without loss."""
        try:
            serialized = json.dumps(data)
            deserialized = json.loads(serialized)
            return deserialized == data
        except (TypeError, ValueError):
            return False
    
    return _validate
