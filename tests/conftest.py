import os
import os.path
import sys
import tempfile
from pathlib import Path

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


def pytest_configure(config):
    """Configure pytest with custom markers for platform-specific tests."""
    config.addinivalue_line(
        "markers", "backend: mark test as backend-specific"
    )
    config.addinivalue_line(
        "markers", "mobile: mark test as mobile-specific"
    )
    config.addinivalue_line(
        "markers", "web: mark test as web-specific"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


def pytest_collection_modifyitems(config, items):
    """Validate test environment and skip platform-specific tests as needed."""
    for item in items:
        # Add default marker for unmarked tests
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.backend)


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment and verify dependencies."""
    # Ensure temp directory is usable
    temp_dir = tempfile.gettempdir()
    if not os.access(temp_dir, os.W_OK):
        pytest.skip(f"Temp directory not writable: {temp_dir}")
    yield


@pytest.fixture(params=['memory', 'json'])
def db(request, tmp_path: Path):
    """Parameterized database fixture with proper cleanup."""
    if request.param == 'json':
        db_ = TinyDB(tmp_path / 'test.db', storage=JSONStorage)
    else:
        db_ = TinyDB(storage=MemoryStorage)

    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    yield db_
    
    # Cleanup: close database and clear tables
    try:
        db_.drop_tables()
        db_.close()
    except Exception:
        pass


@pytest.fixture
def storage():
    """Storage fixture with proper initialization and cleanup."""
    middleware = CachingMiddleware(MemoryStorage)()
    yield middleware
    # Cleanup if needed
    try:
        if hasattr(middleware, 'close'):
            middleware.close()
    except Exception:
        pass
