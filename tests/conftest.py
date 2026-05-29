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


def assert_performance_baseline(
    metrics: PerformanceMetrics,
    baseline: Dict[str, Any],
    operation_name: str,
    time_tolerance: float = 1.2,
    memory_tolerance: float = 1.3,
) -> None:
    """Assert that measured performance is within acceptable baselines.
    
    Args:
        metrics: PerformanceMetrics object with measured values
        baseline: Baseline thresholds dictionary
        operation_name: Name of the operation being tested
        time_tolerance: Multiplier for time threshold (e.g., 1.2 = 20% slower acceptable)
        memory_tolerance: Multiplier for memory threshold (e.g., 1.3 = 30% more acceptable)
        
    Raises:
        AssertionError if performance exceeds baseline * tolerance
    """
    if operation_name not in baseline:
        return  # Skip if baseline not defined
    
    thresholds = baseline[operation_name]
    execution_ms = metrics.execution_time * 1000
    max_time_ms = thresholds["time_ms"] * time_tolerance
    max_memory_mb = thresholds["memory_mb"] * memory_tolerance
    
    assert (
        execution_ms <= max_time_ms
    ), f"{operation_name} took {execution_ms:.2f}ms (limit: {max_time_ms:.2f}ms)"
    
    assert (
        metrics.memory_delta <= max_memory_mb
    ), f"{operation_name} used {metrics.memory_delta:.2f}MB (limit: {max_memory_mb:.2f}MB)"
