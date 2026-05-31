import os.path
import tempfile
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


@pytest.fixture
def storage():
    return CachingMiddleware(MemoryStorage)()


@pytest.fixture
def large_dataset(request):
    """
    Generate a large dataset for stress testing.
    Parametrize with request.config.getoption("--dataset-size", default=1000).
    Returns list of document dicts with varying structures.
    """
    dataset_size = getattr(request.config.option, 'dataset_size', 1000)
    return [
        {
            'id': i,
            'int': i % 100,
            'char': chr(65 + (i % 26)),
            'float': float(i) / 10.0,
            'nested': {'value': i * 2, 'tag': f'doc_{i}'}
        }
        for i in range(dataset_size)
    ]


@pytest.fixture
def benchmark_timer():
    """
    Provide high-resolution timing context for measuring operation latencies.
    Usage: with benchmark_timer() as timer:
               # operation
           elapsed = timer.elapsed()
    """
    import time
    
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
        
        def __enter__(self):
            self.start_time = time.perf_counter()
            return self
        
        def __exit__(self, *args):
            self.end_time = time.perf_counter()
        
        def elapsed(self):
            if self.start_time is None or self.end_time is None:
                return 0
            return (self.end_time - self.start_time) * 1000  # milliseconds
    
    return Timer


@pytest.fixture
def performance_context(db, large_dataset, benchmark_timer):
    """
    Combined fixture for database performance testing under realistic load.
    Provides pre-populated database with large_dataset and timer for measuring operations.
    Returns dict: {'db': db_instance, 'dataset_size': int, 'timer': Timer class, 'measure': callable}
    """
    def measure(operation_name, operation_func):
        """
        Measure operation latency and log results.
        Returns {'operation': str, 'latency_ms': float, 'success': bool}
        """
        try:
            timer_instance = benchmark_timer()
            with timer_instance as t:
                result = operation_func()
            return {
                'operation': operation_name,
                'latency_ms': t.elapsed(),
                'success': True,
                'result': result
            }
        except Exception as e:
            return {
                'operation': operation_name,
                'latency_ms': 0,
                'success': False,
                'error': str(e)
            }
    
    # Pre-populate database with large dataset
    db.insert_multiple(large_dataset)
    
    return {
        'db': db,
        'dataset_size': len(large_dataset),
        'timer': benchmark_timer,
        'measure': measure
    }
