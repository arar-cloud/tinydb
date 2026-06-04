import os.path
import tempfile
from pathlib import Path
from functools import wraps
import time

import pytest  # type: ignore
from tenacity import retry, stop_after_attempt, wait_exponential

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


def retry_on_transient(func):
    """Decorator for test functions to retry on transient failures."""
    @wraps(func)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
        reraise=True
    )
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


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
def db_with_recovery(tmp_path: Path):
    """Fixture providing database with state recovery capability for testing resilience."""
    db_path = tmp_path / 'recovery_test.db'
    
    def _create_db():
        db = TinyDB(db_path, storage=JSONStorage)
        db.drop_tables()
        return db
    
    db = _create_db()
    
    def _assert_recovery():
        """Validate database state consistency after recovery."""
        recovered_db = _create_db()
        assert len(recovered_db) == len(db), "Database state inconsistency detected"
        recovered_db.close()
    
    yield db, _assert_recovery
    db.close()


@pytest.fixture
def transient_failure_simulator():
    """Fixture for simulating transient failures in database operations."""
    class TransientFailureSimulator:
        def __init__(self):
            self.fail_count = 0
            self.max_failures = 0
        
        def should_fail(self) -> bool:
            if self.fail_count < self.max_failures:
                self.fail_count += 1
                return True
            return False
        
        def set_failure_count(self, count: int) -> None:
            self.max_failures = count
            self.fail_count = 0
        
        def reset(self) -> None:
            self.fail_count = 0
            self.max_failures = 0
    
    return TransientFailureSimulator()


@pytest.fixture
def chaos_injection():
    """Fixture for fault injection testing (connection drops, timeouts, partial writes)."""
    class ChaosInjection:
        def __init__(self):
            self.connection_drop_enabled = False
            self.timeout_enabled = False
            self.partial_write_enabled = False
            self.delay_ms = 0
        
        def enable_connection_drop(self) -> None:
            """Simulate connection drop."""
            self.connection_drop_enabled = True
        
        def enable_timeout(self, delay_ms: int = 100) -> None:
            """Simulate operation timeout."""
            self.timeout_enabled = True
            self.delay_ms = delay_ms
        
        def enable_partial_write(self) -> None:
            """Simulate partial write failure."""
            self.partial_write_enabled = True
        
        def inject_delay(self) -> None:
            """Apply injected delay."""
            if self.delay_ms > 0:
                time.sleep(self.delay_ms / 1000.0)
        
        def reset(self) -> None:
            """Reset all chaos conditions."""
            self.connection_drop_enabled = False
            self.timeout_enabled = False
            self.partial_write_enabled = False
            self.delay_ms = 0
    
    return ChaosInjection()
