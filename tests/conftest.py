import os.path
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List, Tuple
from contextlib import contextmanager
from dataclasses import dataclass, field
import sys

import pytest  # type: ignore

try:
    import psutil
except ImportError:
    psutil = None

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
def cpu_benchmark(benchmark):
    """Fixture providing benchmark context for CPU-intensive operations."""
    def _benchmark(func, *args, **kwargs):
        return benchmark(func, *args, **kwargs)
    return _benchmark


@pytest.fixture
def memory_profiler():
    """Fixture providing memory profiling utilities with baseline tracking."""
    class MemoryProfiler:
        def __init__(self):
            self.baselines: Dict[str, MemorySnapshot] = {}
            self.measurements: Dict[str, List[MemorySnapshot]] = {}
        
        @contextmanager
        def profile(self, label: str = "default"):
            """Context manager for profiling a code block."""
            with profile_memory() as snapshot:
                yield snapshot
                after = snapshot._after
                
                if label not in self.measurements:
                    self.measurements[label] = []
                self.measurements[label].append(after)
                
                # Set baseline on first measurement
                if label not in self.baselines:
                    self.baselines[label] = snapshot
        
        def get_memory_delta(self, label: str) -> int:
            """Get current memory delta from baseline for label."""
            if label not in self.measurements:
                return 0
            latest = self.measurements[label][-1]
            baseline = self.baselines.get(label)
            if baseline:
                return latest.delta(baseline)
            return 0
        
        def assert_improved(self, label: str, threshold_bytes: int = 0):
            """Assert that memory usage improved from baseline."""
            delta = self.get_memory_delta(label)
            assert delta <= threshold_bytes, f"Memory increased by {delta} bytes (baseline: {self.baselines.get(label)})"
    
    return MemoryProfiler()


@pytest.fixture
def performance_tracker():
    """Fixture for tracking performance metrics across test runs."""
    class PerformanceTracker:
        def __init__(self):
            self.timings: Dict[str, List[float]] = {}
            self.memory_usage: Dict[str, List[int]] = {}
        
        def record_timing(self, label: str, duration: float):
            """Record execution timing for operation."""
            if label not in self.timings:
                self.timings[label] = []
            self.timings[label].append(duration)
        
        def record_memory(self, label: str, bytes_used: int):
            """Record memory usage for operation."""
            if label not in self.memory_usage:
                self.memory_usage[label] = []
            self.memory_usage[label].append(bytes_used)
        
        def get_average_timing(self, label: str) -> float:
            """Get average execution time for label."""
            if label not in self.timings or not self.timings[label]:
                return 0.0
            return sum(self.timings[label]) / len(self.timings[label])
        
        def get_average_memory(self, label: str) -> int:
            """Get average memory usage for label."""
            if label not in self.memory_usage or not self.memory_usage[label]:
                return 0
            return sum(self.memory_usage[label]) // len(self.memory_usage[label])
        
        def assert_timing_improved(self, label: str, previous_avg: float, tolerance: float = 0.1):
            """Assert that average timing improved beyond tolerance threshold."""
            current_avg = self.get_average_timing(label)
            improvement = (previous_avg - current_avg) / previous_avg if previous_avg > 0 else 0
            assert improvement > tolerance, f"Timing did not improve sufficiently: {improvement*100:.1f}% (required: {tolerance*100:.1f}%)"
    
    return PerformanceTracker()


@dataclass
class MemorySnapshot:
    """Captures memory usage at a point in time."""
    current: int
    peak: int
    timestamp: float = field(default_factory=time.time)

    def delta(self, other: 'MemorySnapshot') -> int:
        """Returns memory difference in bytes."""
        return self.current - other.current

    def peak_delta(self, other: 'MemorySnapshot') -> int:
        """Returns peak memory difference in bytes."""
        return self.peak - other.peak


@contextmanager
def profile_memory():
    """Context manager for memory profiling with baseline tracking."""
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()
    current_before, peak_before = tracemalloc.get_traced_memory()
    snapshot_start = MemorySnapshot(current=current_before, peak=peak_before)
    
    try:
        yield snapshot_start
    finally:
        current_after, peak_after = tracemalloc.get_traced_memory()
        snapshot_after = MemorySnapshot(current=current_after, peak=peak_after)
        tracemalloc.stop()
        
        # Store results for assertion
        snapshot_start._after = snapshot_after


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
