import os.path
import tempfile
import time
import tracemalloc
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Dict, Any

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


class PerformanceMetrics:
    """Container for performance measurement results."""
    def __init__(self):
        self.execution_time: float = 0.0
        self.peak_memory: float = 0.0
        self.memory_delta: float = 0.0
        self.iterations: int = 0


@contextmanager
def measure_performance() -> Generator[PerformanceMetrics, None, None]:
    """Context manager for measuring execution time and memory usage.
    
    Yields:
        PerformanceMetrics object with timing and memory data.
    """
    metrics = PerformanceMetrics()
    tracemalloc.start()
    start_memory = tracemalloc.get_traced_memory()[0]
    
    start_time = time.perf_counter()
    try:
        yield metrics
    finally:
        metrics.execution_time = time.perf_counter() - start_time
        current_memory, peak_memory = tracemalloc.get_traced_memory()
        metrics.peak_memory = peak_memory / 1024 / 1024  # Convert to MB
        metrics.memory_delta = (current_memory - start_memory) / 1024 / 1024  # MB
        tracemalloc.stop()


@pytest.fixture
def performance_baseline() -> Dict[str, Any]:
    """Provide baseline performance thresholds for common database operations.
    
    Returns:
        Dictionary with operation names and their acceptable time/memory limits.
    """
    return {
        "insert_single": {"time_ms": 10.0, "memory_mb": 2.0},
        "insert_bulk": {"time_ms": 50.0, "memory_mb": 5.0},
        "search_simple": {"time_ms": 5.0, "memory_mb": 1.0},
        "update_record": {"time_ms": 8.0, "memory_mb": 1.5},
        "delete_record": {"time_ms": 5.0, "memory_mb": 1.0},
    }


@pytest.fixture
def perf_tracker() -> Generator[Dict[str, PerformanceMetrics], None, None]:
    """Track performance metrics across multiple operations in a test.
    
    Yields:
        Dictionary to store named PerformanceMetrics results.
    """
    yield {}
