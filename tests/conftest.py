import os.path
import tempfile
from pathlib import Path
import threading
import time
from unittest.mock import MagicMock, patch
from typing import Callable, Any

import pytest  # type: ignore
from tenacity import retry, stop_after_attempt, wait_fixed

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


class TransientFailureSimulator:
    """Simulates transient failures for chaos testing."""
    def __init__(self, fail_count: int = 1):
        self.fail_count = fail_count
        self.attempt_count = 0
        self.lock = threading.Lock()
    
    def should_fail(self) -> bool:
        with self.lock:
            if self.attempt_count < self.fail_count:
                self.attempt_count += 1
                return True
            return False
    
    def reset(self):
        with self.lock:
            self.attempt_count = 0


@pytest.fixture
def transient_failure_simulator():
    """Fixture providing transient failure injection for chaos testing."""
    return TransientFailureSimulator()


@pytest.fixture
def io_delay_injector():
    """Fixture for simulating I/O delays and timeout scenarios."""
    class IODelayInjector:
        def __init__(self):
            self.delay_ms = 0
        
        def apply(self, delay_ms: int = 100):
            self.delay_ms = delay_ms
            return self
        
        def sleep(self):
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000.0)
    
    return IODelayInjector()


@pytest.fixture
def retry_backoff_tracker():
    """Fixture tracking retry backoff timing and attempt sequences."""
    class RetryBackoffTracker:
        def __init__(self):
            self.attempts = []
            self.backoff_times = []
            self.lock = threading.Lock()
        
        def record_attempt(self, attempt_num: int, delay_ms: int = 0):
            with self.lock:
                self.attempts.append({
                    'number': attempt_num,
                    'timestamp': time.time(),
                    'delay_ms': delay_ms
                })
        
        def get_attempt_count(self) -> int:
            with self.lock:
                return len(self.attempts)
        
        def get_backoff_sequence(self) -> list:
            with self.lock:
                return [a['delay_ms'] for a in self.attempts]
        
        def reset(self):
            with self.lock:
                self.attempts = []
                self.backoff_times = []
    
    return RetryBackoffTracker()


@pytest.fixture
def file_io_error_injector(tmp_path: Path):
    """Fixture for injecting file I/O errors and permission failures."""
    class FileIOErrorInjector:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.fail_write = False
            self.fail_read = False
            self.fail_permission = False
        
        def inject_write_failure(self):
            self.fail_write = True
        
        def inject_read_failure(self):
            self.fail_read = True
        
        def inject_permission_error(self):
            self.fail_permission = True
        
        def clear(self):
            self.fail_write = False
            self.fail_read = False
            self.fail_permission = False
    
    return FileIOErrorInjector(tmp_path)


@pytest.fixture
def concurrent_access_lock():
    """Fixture providing thread-safe lock for concurrent access testing."""
    return threading.RLock()
