import os.path
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator, List

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


@pytest.fixture(params=['memory', 'json'])
def db(request, tmp_path: Path):
    if request.param == 'json':
        db_ = TinyDB(tmp_path / 'test.db', storage=JSONStorage)
    else:
        db_ = TinyDB(storage=MemoryStorage)

    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    yield db_
    db_.close()


@pytest.fixture
def storage():
    return CachingMiddleware(MemoryStorage)()


@pytest.fixture
def persistent_db(tmp_path: Path) -> Generator[TinyDB, None, None]:
    """Fixture for testing data persistence with JSONStorage."""
    db_path = tmp_path / 'persistent.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def isolated_storage(tmp_path: Path) -> MemoryStorage:
    """Fixture providing isolated MemoryStorage for each test."""
    return MemoryStorage()


@pytest.fixture
def concurrent_db(tmp_path: Path) -> Generator[TinyDB, None, None]:
    """Fixture for testing concurrent access patterns."""
    db_path = tmp_path / 'concurrent.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def stress_test_helper() -> dict:
    """Helper fixture for stress testing with concurrent operations."""
    return {
        'operations': [],
        'errors': [],
        'lock': threading.Lock()
    }
