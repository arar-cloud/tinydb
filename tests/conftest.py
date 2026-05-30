import os.path
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Tuple

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


class PerformanceBaseline:
    """Stores and compares performance baseline metrics."""
    def __init__(self):
        self.baselines: Dict[str, Dict[str, float]] = {}

    def record(self, test_name: str, metric_name: str, value: float) -> None:
        """Record a baseline metric."""
        if test_name not in self.baselines:
            self.baselines[test_name] = {}
        self.baselines[test_name][metric_name] = value

    def get(self, test_name: str, metric_name: str) -> float | None:
        """Retrieve a baseline metric."""
        return self.baselines.get(test_name, {}).get(metric_name)

    def compare(self, test_name: str, metric_name: str, current_value: float, threshold_percent: float = 10.0) -> Tuple[bool, float]:
        """Compare current value against baseline. Returns (passed, percent_change)."""
        baseline = self.get(test_name, metric_name)
        if baseline is None:
            return True, 0.0
        percent_change = ((current_value - baseline) / baseline) * 100
        passed = abs(percent_change) <= threshold_percent
        return passed, percent_change


@pytest.fixture
def performance_baseline():
    """Fixture providing baseline storage for performance metrics."""
    return PerformanceBaseline()


@pytest.fixture
def memory_profiler(performance_baseline):
    """Fixture for memory profiling with baseline tracking.
    
    Yields a profiler function that returns peak memory usage in MB.
    """
    class MemoryProfiler:
        def __init__(self, baseline):
            self.baseline = baseline

        def start(self) -> None:
            """Start memory tracing."""
            tracemalloc.start()

        def stop(self, test_name: str) -> float:
            """Stop memory tracing and return peak memory in MB."""
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peak_mb = peak / 1024 / 1024
            self.baseline.record(test_name, 'peak_memory_mb', peak_mb)
            return peak_mb

        def compare(self, test_name: str, current_memory_mb: float, threshold_percent: float = 10.0) -> Tuple[bool, float]:
            """Compare current memory usage against baseline."""
            return self.baseline.compare(test_name, 'peak_memory_mb', current_memory_mb, threshold_percent)

    return MemoryProfiler(performance_baseline)


@pytest.fixture
def cpu_profiler(performance_baseline):
    """Fixture for CPU time profiling with baseline tracking.
    
    Yields a profiler context manager that measures elapsed time in seconds.
    """
    class CPUProfiler:
        def __init__(self, baseline):
            self.baseline = baseline
            self.start_time = None
            self.elapsed = None

        def start(self) -> None:
            """Start CPU timer."""
            self.start_time = time.perf_counter()

        def stop(self, test_name: str) -> float:
            """Stop CPU timer and return elapsed time in seconds."""
            if self.start_time is None:
                raise RuntimeError("Timer not started")
            self.elapsed = time.perf_counter() - self.start_time
            self.baseline.record(test_name, 'cpu_time_seconds', self.elapsed)
            return self.elapsed

        def compare(self, test_name: str, current_time_seconds: float, threshold_percent: float = 10.0) -> Tuple[bool, float]:
            """Compare current CPU time against baseline."""
            return self.baseline.compare(test_name, 'cpu_time_seconds', current_time_seconds, threshold_percent)

    return CPUProfiler(performance_baseline)
