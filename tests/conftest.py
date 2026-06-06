import os.path
import sys
import tempfile
from pathlib import Path

import pytest  # type: ignore

from tinydb.middlewares import CachingMiddleware
from tinydb.storages import MemoryStorage
from tinydb import TinyDB, JSONStorage

# Platform and Python version detection for stability tests
PYTHON_VERSION = sys.version_info
skip_if_python_lt_311 = pytest.mark.skipif(
    PYTHON_VERSION < (3, 11),
    reason="Test requires Python 3.11+"
)
skip_if_python_lt_312 = pytest.mark.skipif(
    PYTHON_VERSION < (3, 12),
    reason="Test requires Python 3.12+"
)


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


def pytest_configure(config):
    """Configure pytest with custom markers and version info."""
    config.addinivalue_line(
        "markers",
        "stability: mark test as backend stability regression test"
    )
    config.addinivalue_line(
        "markers",
        "python_310_plus: mark test for Python 3.10+"
    )
    config.addinivalue_line(
        "markers",
        "python_311_plus: mark test for Python 3.11+"
    )
    config.addinivalue_line(
        "markers",
        "python_312_plus: mark test for Python 3.12+"
    )


@pytest.fixture(scope="session")
def python_version_info():
    """Provide Python version information to tests."""
    return {
        "version": sys.version_info,
        "version_string": sys.version,
        "is_310": sys.version_info >= (3, 10),
        "is_311": sys.version_info >= (3, 11),
        "is_312": sys.version_info >= (3, 12),
        "is_313": sys.version_info >= (3, 13),
        "is_314": sys.version_info >= (3, 14),
    }
