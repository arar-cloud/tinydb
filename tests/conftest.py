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
