import os.path
import tempfile
from pathlib import Path
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock, patch

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
def mock_backend_request():
    """Mock HTTP backend request for mobile/backend integration testing."""
    mock_request = MagicMock()
    mock_request.method = 'GET'
    mock_request.url = 'http://localhost:8000/api/db'
    mock_request.headers = {'Content-Type': 'application/json'}
    mock_request.timeout = 30
    return mock_request


@pytest.fixture
def mock_backend_response():
    """Mock HTTP backend response for mobile/backend integration testing."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {'success': True, 'data': []}
    mock_response.text = '{"success": true, "data": []}'
    return mock_response


@pytest.fixture
def backend_context():
    """Context manager for backend operations with timeout and error handling."""
    class BackendContext:
        def __init__(self, timeout: int = 30):
            self.timeout = timeout
            self.active = False
            self.requests = []

        def __enter__(self):
            self.active = True
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self.active = False
            if exc_type is not None:
                raise exc_type(f"Backend operation failed: {exc_val}")
            return False

        def record_request(self, method: str, endpoint: str, data: dict = None):
            self.requests.append({
                'method': method,
                'endpoint': endpoint,
                'data': data or {},
                'timestamp': __import__('time').time()
            })

    return BackendContext()


@pytest.fixture
def mobile_backend_mock():
    """Mock mobile backend client with request/response simulation."""
    class MobileBackendMock:
        def __init__(self):
            self.call_count = 0
            self.last_request = None
            self.responses = {}
            self.failures = []

        def request(self, method: str, endpoint: str, data: dict = None, timeout: int = 30):
            self.call_count += 1
            self.last_request = {
                'method': method,
                'endpoint': endpoint,
                'data': data,
                'timeout': timeout
            }
            if endpoint in self.responses:
                return self.responses[endpoint]
            return {'success': True, 'data': []}

        def async_request(self, method: str, endpoint: str, data: dict = None):
            """Async variant for mobile backend calls."""
            self.request(method, endpoint, data)
            return asyncio.sleep(0)

        def set_response(self, endpoint: str, response: dict):
            self.responses[endpoint] = response

        def set_failure(self, endpoint: str, error: str):
            self.failures.append({'endpoint': endpoint, 'error': error})

    return MobileBackendMock()


@pytest.fixture
def async_test_context():
    """Async context fixture for asynchronous backend/mobile operations."""
    class AsyncTestContext:
        def __init__(self):
            self.loop = None
            self.tasks = []

        async def run_async_operation(self, coro):
            """Execute asynchronous operation with tracking."""
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return await task

        def cleanup(self):
            """Cancel pending tasks."""
            for task in self.tasks:
                if not task.done():
                    task.cancel()

    return AsyncTestContext()
