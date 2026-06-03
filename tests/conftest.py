import os.path
import tempfile
from pathlib import Path
import asyncio
from typing import AsyncGenerator, Dict, Any

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


@pytest.fixture
@pytest.mark.backend
async def async_db(tmp_path: Path):
    """Async database fixture for backend testing."""
    db_ = TinyDB(tmp_path / 'async_test.db', storage=JSONStorage)
    db_.drop_tables()
    db_.insert_multiple({'int': i, 'async': True} for i in range(3))
    yield db_
    db_.close()


@pytest.fixture
@pytest.mark.mobile
def mobile_db_state() -> Dict[str, Any]:
    """Simulated mobile client database state for integration testing."""
    return {
        'tables': {},
        'pending_ops': [],
        'sync_state': 'idle',
        'connection_status': 'connected',
    }


@pytest.fixture
@pytest.mark.integration
def mobile_backend_context(db, mobile_db_state):
    """Integration fixture simulating mobile-backend sync context."""
    return {
        'backend_db': db,
        'mobile_state': mobile_db_state,
        'sync_queue': [],
        'conflict_log': [],
    }


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
