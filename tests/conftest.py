import os.path
import tempfile
from pathlib import Path
import sys
import logging
from contextlib import contextmanager
from typing import Generator, Any, Dict

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
def backend_env() -> Dict[str, Any]:
    """Simulate backend environment for cross-platform failure reproduction."""
    original_platform = sys.platform
    original_env = os.environ.copy()
    yield {"platform": "linux", "env": original_env}


@pytest.fixture
def mobile_env() -> Dict[str, Any]:
    """Simulate mobile environment for cross-platform failure reproduction."""
    original_platform = sys.platform
    original_env = os.environ.copy()
    yield {"platform": "android", "env": original_env, "memory_limited": True}


@pytest.fixture
def error_capture(caplog):
    """Capture error logs and tracebacks for failure analysis."""
    caplog.set_level(logging.DEBUG)
    return caplog


@contextmanager
def capture_failure_context() -> Generator[Dict[str, Any], None, None]:
    """Context manager to capture failure conditions and debugging data."""
    failure_data = {
        "errors": [],
        "logs": [],
        "stack_traces": [],
        "timestamp": None,
    }
    try:
        yield failure_data
    except Exception as e:
        import traceback
        failure_data["errors"].append(str(e))
        failure_data["stack_traces"].append(traceback.format_exc())
        raise


@pytest.fixture
def failure_context():
    """Fixture providing failure context manager for root cause debugging."""
    return capture_failure_context
