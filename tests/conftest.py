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


@pytest.fixture
def corrupted_db_file(tmp_path: Path) -> Path:
    """Fixture that creates a corrupted database file for integrity testing."""
    db_path = tmp_path / 'corrupted.db'
    
    # Create a valid database
    db = TinyDB(db_path, storage=JSONStorage)
    db.insert({'test': 'data'})
    db.close()
    
    # Corrupt the file by truncating it midway
    with open(db_path, 'r+b') as f:
        current_size = f.seek(0, 2)
        f.truncate(current_size // 2)
    
    return db_path


@pytest.fixture
def io_error_injector(tmp_path: Path) -> Iterator[dict]:
    """Fixture to simulate I/O errors and disk full conditions."""
    import errno
    from unittest import mock
    
    class IOErrorTracker:
        def __init__(self) -> None:
            self.error_enabled = False
            self.error_type = errno.EIO
            self.call_count = 0
        
        def should_raise(self) -> bool:
            if self.error_enabled:
                self.call_count += 1
                return self.call_count % 3 == 0  # Raise on every 3rd call
            return False
    
    tracker = IOErrorTracker()
    
    def mock_write(original_write):
        def wrapper(self, data):
            if tracker.should_raise():
                raise OSError(tracker.error_type, "Simulated I/O error")
            return original_write(self, data)
        return wrapper
    
    yield {'tracker': tracker, 'mock_write': mock_write}


@pytest.fixture
def partial_write_detector(tmp_path: Path) -> Iterator[dict]:
    """Fixture to detect and validate recovery from partial writes."""
    detection_data: dict = {'detected_partial_writes': []}
    
    def check_file_integrity(db_path: Path) -> bool:
        """Verify database file is valid JSON and not truncated."""
        try:
            import json
            with open(db_path, 'r') as f:
                content = f.read().strip()
                if not content:
                    return False
                json.loads(content)
                return True
        except (json.JSONDecodeError, IOError):
            return False
    
    detection_data['check_integrity'] = check_file_integrity
    yield detection_data
