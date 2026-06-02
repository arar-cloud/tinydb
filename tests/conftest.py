import os.path
import tempfile
from pathlib import Path
import sys
import logging
import logging.handlers
from contextlib import contextmanager
from typing import Generator, Any, Dict, List
import traceback
import io
import threading
import time

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage


@pytest.fixture
def error_logger() -> logging.Logger:
    """Fixture that provides a logger to capture errors during tests."""
    logger = logging.getLogger('test_errors')
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture
def recovery_fixture(tmp_path: Path):
    """Fixture for testing database recovery under failure conditions."""
    db_path = tmp_path / "recovery_test.json"
    db = TinyDB(str(db_path))
    yield db
    try:
        db.close()
    except Exception:
        pass


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
def backend_env(monkeypatch) -> Dict[str, Any]:
    """Fixture for backend environment simulation.

    Sets backend-specific environment variables and platform conditions
    to reproduce backend stack failures in test execution.
    """
    env_vars = {
        'TINYDB_BACKEND': 'true',
        'TINYDB_DEBUG': 'true',
        'TINYDB_STRICT_MODE': 'true'
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


@pytest.fixture
def mobile_env(monkeypatch) -> Dict[str, Any]:
    """Fixture for mobile environment simulation.

    Sets mobile-specific environment variables and constrains to reproduce
    mobile stack failures (memory, concurrency, file I/O constraints).
    """
    env_vars = {
        'TINYDB_MOBILE': 'true',
        'TINYDB_MEMORY_CONSTRAINED': 'true',
        'TINYDB_IO_TIMEOUT': '5'
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


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


@pytest.fixture
def log_capture():
    """Fixture for capturing log output during test execution.

    Returns a handler that captures all log messages for debugging and analysis.
    Enables identification of logging patterns leading to failures.
    """
    log_capture_handler = logging.handlers.MemoryHandler(capacity=1000)
    logger = logging.getLogger()
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(log_capture_handler)

    yield log_capture_handler

    logger.removeHandler(log_capture_handler)
    logger.setLevel(original_level)


@pytest.fixture
def error_context():
    """Fixture providing context manager for capturing error details.

    Captures exception tracebacks, error messages, and context information
    for root cause analysis during active failure reproduction.
    """
    errors: List[Dict[str, Any]] = []

    @contextmanager
    def error_capture_ctx():
        try:
            yield errors
        except Exception as e:
            error_info = {
                'message': str(e),
                'type': type(e).__name__,
                'traceback': traceback.format_exc()
            }
            errors.append(error_info)
            raise

    return error_capture_ctx
