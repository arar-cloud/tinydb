import os.path
import tempfile
import time
import random
from pathlib import Path
from typing import Callable, TypeVar, Any
from functools import wraps
from contextlib import contextmanager

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage

T = TypeVar('T')


@pytest.fixture(params=['memory', 'json'])
def db(request, tmp_path: Path):
    """Parametrized database fixture supporting both memory and file storage."""
    if request.param == 'json':
        db_ = TinyDB(tmp_path / 'test.db', storage=JSONStorage)
    else:
        db_ = TinyDB(storage=MemoryStorage)

    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')

    yield db_


@pytest.fixture
def db_stable(tmp_path: Path):
    """Stable in-memory database fixture for deterministic tests."""
    db_ = TinyDB(storage=MemoryStorage)
    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')
    yield db_
    db_.close()


@pytest.fixture
def db_with_file(tmp_path: Path):
    """File-based database fixture for persistence tests."""
    db_path = tmp_path / 'test_stable.db'
    db_ = TinyDB(db_path, storage=JSONStorage)
    db_.drop_tables()
    db_.insert_multiple({'int': 1, 'char': c} for c in 'abc')
    yield db_, db_path
    db_.close()


@pytest.fixture
def storage():
    """Cached in-memory storage fixture."""
    return CachingMiddleware(MemoryStorage)()


def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 5.0
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for exponential backoff retry logic with jitter.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        raise
                    delay = min(
                        base_delay * (2 ** attempt) + random.uniform(0, 0.1),
                        max_delay
                    )
                    time.sleep(delay)
            raise last_exception or Exception("Unknown retry failure")
        return wrapper
    return decorator


@contextmanager
def transactional_scope(db_: TinyDB):
    """Context manager for transactional scope with automatic rollback on error.
    
    Ensures consistent state even if operations fail mid-transaction.
    """
    initial_state = {table: list(db_.table(table).all()) for table in db_.tables()}
    try:
        yield db_
    except Exception:
        # Rollback: restore initial state
        for table_name, docs in initial_state.items():
            table = db_.table(table_name)
            table.truncate()
            if docs:
                table.insert_multiple(docs)
        raise


def assert_idempotent(
    operation: Callable[[], Any],
    max_runs: int = 3
) -> None:
    """Assert that an operation produces identical results across multiple runs.
    
    Args:
        operation: Callable that performs database operation
        max_runs: Number of times to execute the operation
    """
    results = []
    for _ in range(max_runs):
        try:
            result = operation()
            results.append(result)
        except Exception as e:
            results.append(type(e).__name__)
    
    # All results should be identical
    if results:
        expected = results[0]
        for i, result in enumerate(results[1:], 1):
            assert result == expected, (
                f"Idempotency violation: run 1 returned {expected}, "
                f"run {i+1} returned {result}"
            )


@pytest.fixture
def assert_consistent_retry():
    """Fixture providing idempotency assertion helper."""
    return assert_idempotent
