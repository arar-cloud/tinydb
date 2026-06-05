import os.path
import tempfile
from pathlib import Path
import platform
from unittest.mock import patch, MagicMock
from contextlib import contextmanager
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


@contextmanager
def inject_io_failure(exception_type=OSError, error_code=errno.EIO, call_count=1):
    """Context manager to inject transient I/O failures.
    
    Args:
        exception_type: Exception class to raise (OSError, PermissionError, etc.)
        error_code: errno code for the exception
        call_count: Number of times to raise before allowing normal operation
    """
    call_counter = {'count': 0}
    original_open = open
    
    def failing_open(*args, **kwargs):
        call_counter['count'] += 1
        if call_counter['count'] <= call_count:
            raise exception_type(error_code, f"Injected I/O failure (attempt {call_counter['count']})")
        return original_open(*args, **kwargs)
    
    with patch('builtins.open', failing_open):
        yield


@pytest.fixture
def io_failure_injector():
    """Fixture providing I/O failure injection utility."""
    return inject_io_failure


@pytest.fixture
def permission_error_injector():
    """Fixture for injecting permission errors on file operations."""
    @contextmanager
    def inject_permission_error(call_count=1):
        call_counter = {'count': 0}
        original_open = open
        
        def failing_open(*args, **kwargs):
            call_counter['count'] += 1
            if call_counter['count'] <= call_count:
                raise PermissionError(errno.EACCES, "Permission denied")
            return original_open(*args, **kwargs)
        
        with patch('builtins.open', failing_open):
            yield
    
    return inject_permission_error


@pytest.fixture
def concurrent_access_simulator():
    """Fixture for simulating concurrent file access races."""
    @contextmanager
    def simulate_concurrent_access():
        original_open = open
        access_log = []
        
        def tracked_open(*args, **kwargs):
            mode = kwargs.get('mode', args[1] if len(args) > 1 else 'r')
            access_log.append({'mode': mode, 'args': args})
            # Simulate race condition: fail if multiple writes detected
            write_count = sum(1 for a in access_log if 'w' in a['mode'])
            if write_count > 1:
                raise OSError(errno.EAGAIN, "Resource temporarily unavailable")
            return original_open(*args, **kwargs)
        
        with patch('builtins.open', tracked_open):
            yield access_log
    
    return simulate_concurrent_access
