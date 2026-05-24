import os.path
import tempfile
from pathlib import Path
import logging
import sys
import json
from typing import Any, Dict
from datetime import datetime

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage

# Configure logging for diagnostic capture
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] [%(name)s:%(filename)s:%(lineno)d] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_debug.log')
    ]
)

logger = logging.getLogger(__name__)


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


def pytest_configure(config: Any) -> None:
    """Initialize pytest with diagnostic markers and logging."""
    config.addinivalue_line(
        "markers", "backend: marks tests as backend layer tests"
    )
    config.addinivalue_line(
        "markers", "mobile: marks tests as mobile client integration tests"
    )
    config.addinivalue_line(
        "markers", "web: marks tests as web client integration tests"
    )
    config.addinivalue_line(
        "markers", "flaky: marks tests known to be flaky"
    )
    logger.info("Pytest configured with diagnostic markers and logging")


def pytest_runtest_setup(item: Any) -> None:
    """Capture setup phase for each test."""
    logger.info(f"Setup: {item.name} from {item.fspath}")
    logger.debug(f"Test markers: {[m.name for m in item.iter_markers()]}")


def pytest_runtest_makereport(item: Any, call: Any) -> None:
    """Capture detailed test execution context and failures."""
    if call.when == "call":
        logger.debug(f"Executing: {item.name}")
    elif call.when == "teardown":
        logger.debug(f"Teardown: {item.name}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_protocol(item: Any, nextitem: Any) -> Any:
    """Wrap test execution to capture failure context."""
    outcome = yield
    if outcome.excinfo is not None:
        exc_type, exc_value, exc_tb = outcome.excinfo
        logger.error(
            f"Test failed: {item.name}",
            exc_info=(exc_type, exc_value, exc_tb)
        )
        logger.error(f"Exception type: {exc_type.__name__ if exc_type else 'Unknown'}")
        logger.error(f"Exception message: {str(exc_value)}")


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    """Log session summary with diagnostic information."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Test session finished with exit status: {exitstatus}")
    logger.info(f"Session timestamp: {datetime.now().isoformat()}")
    logger.info(f"{'='*60}\n")
