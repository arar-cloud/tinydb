import os.path
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

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


@pytest.fixture
def storage():
    return CachingMiddleware(MemoryStorage)()


# Backend-specific fixtures
@pytest.fixture
def backend_db(tmp_path: Path):
    """Backend database with JSON storage for persistent operations."""
    db_ = TinyDB(tmp_path / 'backend_test.db', storage=JSONStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def backend_memory_db():
    """Backend database with memory storage for fast backend unit tests."""
    db_ = TinyDB(storage=MemoryStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def mock_storage():
    """Mock storage for backend operations testing."""
    return Mock(spec=MemoryStorage)


# Mobile-specific fixtures
@pytest.fixture
def mobile_db():
    """Mobile-optimized in-memory database for mobile scenarios."""
    db_ = TinyDB(storage=MemoryStorage)
    db_.drop_tables()
    yield db_
    db_.close()


@pytest.fixture
def constrained_db():
    """Database fixture simulating mobile memory constraints."""
    db_ = TinyDB(storage=MemoryStorage)
    db_.drop_tables()
    # Simulate memory-constrained environment
    db_._memory_limit = 10 * 1024 * 1024  # 10MB limit
    yield db_


@pytest.fixture
def mock_network():
    """Mock network operations for mobile offline scenarios."""
    mock = MagicMock()
    mock.is_connected = True
    mock.connect = MagicMock(return_value=True)
    mock.disconnect = MagicMock(return_value=None)
    mock.send = MagicMock(return_value={'status': 'ok'})
    return mock
