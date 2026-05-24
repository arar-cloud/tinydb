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

    logger.debug(f"Database fixture created: {request.param}")
    yield db_
    logger.debug(f"Database fixture teardown: {request.param}")
    if hasattr(db_, 'close'):
        db_.close()


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


@pytest.fixture
def db_with_snapshot(db: TinyDB) -> Dict[str, Any]:
    """Capture database state snapshot for debugging."""
    snapshot: Dict[str, Any] = {
        'tables': {},
        'timestamp': datetime.now().isoformat(),
        'storage_type': type(db.storage).__name__
    }
    for table_name in db.tables():
        table = db.table(table_name)
        snapshot['tables'][table_name] = list(table.all())
    logger.debug(f"Database snapshot captured: {snapshot}")
    yield snapshot


@pytest.fixture
def backend_state_fixture() -> Dict[str, Any]:
    """Fixture for capturing backend state during cross-layer tests."""
    state: Dict[str, Any] = {
        'operations': [],
        'errors': [],
        'start_time': datetime.now().isoformat()
    }
    logger.debug("Backend state fixture initialized")
    yield state
    logger.debug(f"Backend state at teardown: {state}")


@pytest.fixture
def transaction_fixture(db: TinyDB) -> Dict[str, Any]:
    """Fixture for testing database transactions and consistency."""
    transaction_context: Dict[str, Any] = {
        'initial_count': len(db.all()),
        'operations': [],
        'rollback_data': None
    }
    logger.debug(f"Transaction fixture initialized with {transaction_context['initial_count']} records")
    yield transaction_context
    logger.debug(f"Transaction fixture teardown: {transaction_context}")


@pytest.fixture
def communication_channel_fixture() -> Dict[str, Any]:
    """Fixture for simulating mobile/web client communication with backend."""
    channel: Dict[str, Any] = {
        'messages': [],
        'errors': [],
        'latency_ms': 0
    }
    logger.debug("Communication channel fixture initialized for client-backend testing")
    yield channel
    logger.debug(f"Communication channel fixture teardown: {len(channel['messages'])} messages, {len(channel['errors'])} errors")
