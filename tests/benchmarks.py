"""Performance benchmarking utilities for TinyDB regression testing.

Provides decorators and utilities for measuring query execution time,
serialization performance, and memory allocation patterns.
"""

import time
import functools
import tracemalloc
from typing import Callable, Any, Dict, List, Tuple
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    execution_time_ms: float
    memory_allocated_bytes: int
    peak_memory_bytes: int
    timestamp: str = field(default_factory=lambda: time.strftime('%Y-%m-%d %H:%M:%S'))
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceBaseline:
    """Tracks performance baselines and detects regressions."""
    
    def __init__(self, baseline_file: str = '.performance_baseline.json'):
        self.baseline_file = Path(baseline_file)
        self.baselines: Dict[str, Dict[str, float]] = {}
        self._load_baselines()
    
    def _load_baselines(self) -> None:
        """Load baseline metrics from file if exists."""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, 'r') as f:
                    self.baselines = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.baselines = {}
    
    def save_baselines(self) -> None:
        """Persist baseline metrics to file."""
        with open(self.baseline_file, 'w') as f:
            json.dump(self.baselines, f, indent=2)
    
    def set_baseline(self, name: str, execution_time_ms: float, memory_bytes: int) -> None:
        """Set or update baseline for a benchmark."""
        if name not in self.baselines:
            self.baselines[name] = {}
        self.baselines[name]['execution_time_ms'] = execution_time_ms
        self.baselines[name]['memory_bytes'] = memory_bytes
    
    def check_regression(self, result: BenchmarkResult, tolerance_percent: float = 10.0) -> Tuple[bool, str]:
        """Check if result exceeds baseline by tolerance_percent. Returns (passed, message)."""
        if result.name not in self.baselines:
            return True, f"No baseline for {result.name}, skipping regression check"
        
        baseline = self.baselines[result.name]
        baseline_time = baseline.get('execution_time_ms', 0)
        baseline_memory = baseline.get('memory_bytes', 0)
        
        time_threshold = baseline_time * (1 + tolerance_percent / 100.0)
        memory_threshold = baseline_memory * (1 + tolerance_percent / 100.0)
        
        failures = []
        if result.execution_time_ms > time_threshold:
            pct_over = ((result.execution_time_ms - baseline_time) / baseline_time) * 100
            failures.append(f"Execution time regressed by {pct_over:.1f}% ({result.execution_time_ms:.2f}ms vs {baseline_time:.2f}ms baseline)")
        
        if result.memory_allocated_bytes > memory_threshold:
            pct_over = ((result.memory_allocated_bytes - baseline_memory) / baseline_memory) * 100
            failures.append(f"Memory allocation regressed by {pct_over:.1f}% ({result.memory_allocated_bytes} bytes vs {baseline_memory} bytes baseline)")
        
        if failures:
            return False, "; ".join(failures)
        return True, "Within baseline tolerances"


def benchmark_execution_time(func: Callable) -> Callable:
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Tuple[Any, BenchmarkResult]:
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_ms = (time.time() - start_time) * 1000
        
        benchmark = BenchmarkResult(
            name=func.__name__,
            execution_time_ms=elapsed_ms,
            memory_allocated_bytes=0,
            peak_memory_bytes=0
        )
        return result, benchmark
    return wrapper


def benchmark_with_memory(func: Callable) -> Callable:
    """Decorator to measure function execution time and memory allocation."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Tuple[Any, BenchmarkResult]:
        tracemalloc.start()
        start_time = time.time()
        
        result = func(*args, **kwargs)
        
        elapsed_ms = (time.time() - start_time) * 1000
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        benchmark = BenchmarkResult(
            name=func.__name__,
            execution_time_ms=elapsed_ms,
            memory_allocated_bytes=current,
            peak_memory_bytes=peak
        )
        return result, benchmark
    return wrapper


def measure_execution_time(func: Callable, *args: Any, **kwargs: Any) -> Tuple[Any, float]:
    """Measure execution time of a function call in milliseconds."""
    start_time = time.time()
    result = func(*args, **kwargs)
    elapsed_ms = (time.time() - start_time) * 1000
    return result, elapsed_ms


def measure_memory_usage(func: Callable, *args: Any, **kwargs: Any) -> Tuple[Any, int, int]:
    """Measure memory usage of a function call. Returns (result, allocated_bytes, peak_bytes)."""
    tracemalloc.start()
    result = func(*args, **kwargs)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, current, peak
