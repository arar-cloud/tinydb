import os.path
import tempfile
import time
import psutil
from pathlib import Path
from typing import Dict, Any, Callable

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


@pytest.fixture()
def performance_timer():
    """Fixture providing a high-resolution timer for performance measurements."""
    class PerformanceTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, *args):
            self.end_time = time.perf_counter()

        @property
        def elapsed_ms(self) -> float:
            """Return elapsed time in milliseconds."""
            if self.start_time is None or self.end_time is None:
                return 0.0
            return (self.end_time - self.start_time) * 1000

        @property
        def elapsed_us(self) -> float:
            """Return elapsed time in microseconds."""
            if self.start_time is None or self.end_time is None:
                return 0.0
            return (self.end_time - self.start_time) * 1_000_000

    return PerformanceTimer


@pytest.fixture()
def memory_snapshot():
    """Fixture providing memory profiling utilities."""
    class MemorySnapshot:
        def __init__(self):
            self.process = psutil.Process(os.getpid())
            self.start_mem = None
            self.end_mem = None

        def take_snapshot(self) -> float:
            """Take current memory snapshot in MB."""
            return self.process.memory_info().rss / (1024 * 1024)

        def __enter__(self):
            self.start_mem = self.take_snapshot()
            return self

        def __exit__(self, *args):
            self.end_mem = self.take_snapshot()

        @property
        def delta_mb(self) -> float:
            """Return memory delta in MB."""
            if self.start_mem is None or self.end_mem is None:
                return 0.0
            return self.end_mem - self.start_mem

    return MemorySnapshot


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
