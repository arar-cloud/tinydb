import os.path
import tempfile
import time
from pathlib import Path
from typing import Callable, Tuple

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
def assert_performance():
    """Fixture for asserting operation latency constraints.
    
    Returns a function that measures operation execution time and asserts
    it meets the specified maximum latency constraint.
    
    Usage:
        def test_operation(assert_performance):
            elapsed = assert_performance(
                lambda: db.insert(doc),
                max_latency_ms=1.0,
                description="single insert"
            )
    """
    def _assert_performance(
        operation: Callable,
        max_latency_ms: float,
        description: str = "operation",
        iterations: int = 1
    ) -> float:
        """Measure operation latency and assert it meets constraint.
        
        Args:
            operation: Callable that performs the operation to measure
            max_latency_ms: Maximum allowed latency in milliseconds
            description: Human-readable description of the operation
            iterations: Number of times to execute operation
        
        Returns:
            Mean execution time in seconds
        """
        start = time.perf_counter()
        for _ in range(iterations):
            operation()
        elapsed = time.perf_counter() - start
        mean_ms = (elapsed / iterations) * 1000
        
        assert mean_ms <= max_latency_ms, (
            f"{description} took {mean_ms:.3f}ms, "
            f"expected <={max_latency_ms:.3f}ms"
        )
        return elapsed / iterations
    
    return _assert_performance
