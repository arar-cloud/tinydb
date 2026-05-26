"""Test module for TinyDB.

Provides fixtures, utilities, and infrastructure for testing, including:
- Database fixtures (memory and JSON storage)
- Backend mocking utilities for mobile/backend integration testing
- Request/response simulation for debugging active failures
- Async context managers for asynchronous operations
"""

from typing import Any, Dict, List
from unittest.mock import MagicMock
import asyncio


class BackendMockHelper:
    """Helper class for mocking backend operations in tests."""

    def __init__(self):
        self.requests: List[Dict[str, Any]] = []
        self.responses: Dict[str, Any] = {}
        self.failures: List[Dict[str, Any]] = []

    def record_request(self, method: str, endpoint: str, data: Dict = None) -> None:
        """Record a backend request for inspection."""
        self.requests.append({
            'method': method,
            'endpoint': endpoint,
            'data': data or {},
        })

    def set_response(self, endpoint: str, response: Dict) -> None:
        """Set mock response for an endpoint."""
        self.responses[endpoint] = response

    def get_response(self, endpoint: str) -> Dict:
        """Get mock response for an endpoint."""
        return self.responses.get(endpoint, {'success': True, 'data': []})

    def record_failure(self, endpoint: str, error: str) -> None:
        """Record a backend failure."""
        self.failures.append({'endpoint': endpoint, 'error': error})

    def clear(self) -> None:
        """Clear all recorded requests and failures."""
        self.requests.clear()
        self.failures.clear()
        self.responses.clear()


class AsyncOperationTracker:
    """Tracker for asynchronous operations in tests."""

    def __init__(self):
        self.tasks: List[asyncio.Task] = []
        self.completed = 0
        self.failed = 0

    async def track_operation(self, coro):
        """Track an asynchronous operation."""
        try:
            result = await coro
            self.completed += 1
            return result
        except Exception as e:
            self.failed += 1
            raise e

    def cleanup(self) -> None:
        """Cancel pending tasks."""
        for task in self.tasks:
            if not task.done():
                task.cancel()

    def reset(self) -> None:
        """Reset tracking counters."""
        self.completed = 0
        self.failed = 0
        self.tasks.clear()


class RequestMockFactory:
    """Factory for creating mock HTTP requests."""

    @staticmethod
    def create_request(
        method: str = 'GET',
        url: str = 'http://localhost:8000/api',
        headers: Dict = None,
        data: Dict = None,
    ) -> MagicMock:
        """Create a mock HTTP request."""
        mock = MagicMock()
        mock.method = method
        mock.url = url
        mock.headers = headers or {'Content-Type': 'application/json'}
        mock.data = data or {}
        return mock

    @staticmethod
    def create_response(
        status_code: int = 200,
        data: Dict = None,
        headers: Dict = None,
    ) -> MagicMock:
        """Create a mock HTTP response."""
        mock = MagicMock()
        mock.status_code = status_code
        mock.headers = headers or {'Content-Type': 'application/json'}
        mock.json.return_value = data or {'success': True}
        mock.text = str(data or {'success': True})
        return mock


__all__ = [
    'BackendMockHelper',
    'AsyncOperationTracker',
    'RequestMockFactory',
]
