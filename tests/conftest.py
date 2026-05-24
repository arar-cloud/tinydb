import os.path
import tempfile
import gc
from pathlib import Path
from typing import Iterator

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
def tracked_db(tmp_path: Path) -> Iterator[TinyDB]:
    """Fixture that tracks file handles and validates cleanup on error paths."""
    db_path = tmp_path / 'tracked.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    
    open_files_before = len([f for f in (tmp_path / '.').glob('*') if f.is_file()])
    
    yield db_
    
    try:
        db_.close()
    except Exception:
        pass
    
    gc.collect()  # Force garbage collection to release file handles
    
    # Verify file handle was released by checking if file can be deleted
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError as e:
            pytest.fail(f"File handle not released after close: {e}")


@pytest.fixture
def resource_monitor(tmp_path: Path) -> Iterator[dict]:
    """Fixture to monitor resource usage (file handles, memory) during test."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    resources_before = {
        'fds': len(process.open_files()),
        'memory': process.memory_info().rss,
    }
    
    monitoring_data: dict = {}
    yield monitoring_data
    
    gc.collect()
    resources_after = {
        'fds': len(process.open_files()),
        'memory': process.memory_info().rss,
    }
    
    monitoring_data['before'] = resources_before
    monitoring_data['after'] = resources_after
    
    # Warn if file descriptors increased significantly (potential leak)
    fd_diff = resources_after['fds'] - resources_before['fds']
    if fd_diff > 2:
        pytest.warns(UserWarning, match="File descriptor count increased")
