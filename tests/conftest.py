import os.path
import tempfile
import time
import tracemalloc
from pathlib import Path

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


# Performance baseline thresholds (in seconds for latency, bytes for memory)
PERFORMANCE_BASELINES = {
    'insert_single': {'latency': 0.001, 'memory': 1024},
    'insert_bulk_100': {'latency': 0.01, 'memory': 10240},
    'query_simple': {'latency': 0.0005, 'memory': 512},
    'update_single': {'latency': 0.001, 'memory': 1024},
}


def measure_operation_latency(func, *args, **kwargs):
    """Measure execution time of a database operation in seconds."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    end = time.perf_counter()
    return end - start, result


def measure_operation_memory(func, *args, **kwargs):
    """Measure peak memory usage of a database operation in bytes."""
    tracemalloc.start()
    result = func(*args, **kwargs)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak, result


def assert_latency_within_threshold(operation_name, measured_latency, tolerance=0.1):
    """Assert that measured latency is within threshold + tolerance.
    
    Args:
        operation_name: Key in PERFORMANCE_BASELINES dict
        measured_latency: Measured execution time in seconds
        tolerance: Acceptable deviation factor (default 10%)
    """
    baseline = PERFORMANCE_BASELINES.get(operation_name, {}).get('latency')
    if baseline is None:
        return  # No baseline set, skip assertion
    
    threshold = baseline * (1 + tolerance)
    assert measured_latency <= threshold, (
        f"Operation {operation_name} exceeded latency threshold: "
        f"measured {measured_latency:.6f}s, threshold {threshold:.6f}s"
    )


def assert_memory_within_threshold(operation_name, measured_memory, tolerance=0.1):
    """Assert that measured memory is within threshold + tolerance.
    
    Args:
        operation_name: Key in PERFORMANCE_BASELINES dict
        measured_memory: Measured peak memory in bytes
        tolerance: Acceptable deviation factor (default 10%)
    """
    baseline = PERFORMANCE_BASELINES.get(operation_name, {}).get('memory')
    if baseline is None:
        return  # No baseline set, skip assertion
    
    threshold = baseline * (1 + tolerance)
    assert measured_memory <= threshold, (
        f"Operation {operation_name} exceeded memory threshold: "
        f"measured {measured_memory} bytes, threshold {threshold} bytes"
    )


@pytest.fixture
def performance_tracker():
    """Fixture providing performance measurement utilities."""
    return {
        'measure_latency': measure_operation_latency,
        'measure_memory': measure_operation_memory,
        'assert_latency': assert_latency_within_threshold,
        'assert_memory': assert_memory_within_threshold,
        'baselines': PERFORMANCE_BASELINES,
    }


@pytest.fixture
def perf_db(db, performance_tracker):
    """Database fixture with integrated performance tracking for regression testing.
    
    Yields a database instance alongside performance measurement utilities.
    Use this fixture in tests that require performance baseline verification.
    Example:
        def test_insert_performance(perf_db):
            db, perf = perf_db
            latency, _ = perf['measure_latency'](db.insert, {'test': 1})
            perf['assert_latency']('insert_single', latency)
    """
    yield (db, performance_tracker)


@pytest.fixture
def storage():
    return CachingMiddleware(MemoryStorage)()
