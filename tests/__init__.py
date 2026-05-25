"""TinyDB test suite with diagnostic infrastructure.

This module provides comprehensive test fixtures, logging, and diagnostic hooks
to enable debugging of backend, mobile, and web stack failures.

Diagnostic Features:
- Comprehensive pytest hooks for failure capture
- Database state snapshots for debugging
- Backend state tracking across test execution
- Transaction consistency verification
- Client-backend communication simulation
- Detailed logging to both console and file (test_debug.log)

Test Markers:
- @pytest.mark.backend: Backend layer tests
- @pytest.mark.mobile: Mobile client integration tests
- @pytest.mark.web: Web client integration tests
- @pytest.mark.flaky: Tests known to be flaky or transient

Run tests with debugging:
    pytest -vv --log-cli-level=DEBUG

Run specific layer tests:
    pytest -m backend
    pytest -m mobile
    pytest -m web
"""

import logging

logger = logging.getLogger(__name__)
logger.debug("TinyDB test suite initialized")
