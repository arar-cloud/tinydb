import os.path
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from io import IOError
import errno

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
def transient_file_failure(monkeypatch):
    """Fixture that simulates transient file I/O failures for the first N calls, then succeeds."""
    call_count = {'count': 0}
    max_failures = 2
    original_open = open
    
    def failing_open(*args, **kwargs):
        call_count['count'] += 1
        if call_count['count'] <= max_failures:
            raise IOError(errno.EIO, "Input/output error")
        return original_open(*args, **kwargs)
    
    return failing_open


@pytest.fixture
def timeout_simulation(monkeypatch):
    """Fixture that simulates timeout errors on file operations."""
    call_count = {'count': 0}
    max_timeouts = 1
    original_read = bytes.read
    
    def failing_read(self, size=-1):
        call_count['count'] += 1
        if call_count['count'] <= max_timeouts:
            raise TimeoutError("Operation timed out")
        return original_read(self, size)
    
    return failing_read


@pytest.fixture
def permission_denied_simulation():
    """Fixture that simulates permission denied errors on file access."""
    def raise_permission_error(*args, **kwargs):
        raise PermissionError("Permission denied")
    return raise_permission_error


@pytest.fixture
def mock_retry_context():
    """Fixture that provides a mock context for testing retry behavior."""
    return {
        'attempt_count': 0,
        'max_attempts': 3,
        'failures': [],
    }


@pytest.fixture
def transient_lock_failure(monkeypatch):
    """Fixture that simulates lock contention and release failures."""
    call_count = {'count': 0}
    max_lock_failures = 2
    
    def mock_lock_with_failures():
        call_count['count'] += 1
        if call_count['count'] <= max_lock_failures:
            raise BlockingIOError("Resource temporarily unavailable")
        return MagicMock()  # Return a successful lock
    
    return mock_lock_with_failures
