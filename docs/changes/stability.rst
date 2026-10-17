Stability and Debugging Guide
=============================

This guide documents known stability issues, debugging procedures, and best practices for mobile and backend integration with TinyDB.

Known Issues
------------

Mobile/Backend Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following issues have been identified in mobile-backend integration scenarios:

1. **Test Infrastructure Gaps**: Test infrastructure for mobile/backend failures is incomplete (Issue #ab91fec693)
   - Missing test cases for mobile client integration
   - Incomplete async operation testing
   - No dedicated mobile-backend synchronization tests

2. **Async Operation Stability**: Backend async operations may not properly isolate concurrent database access (Issue #d671b48881)
   - Concurrent insert/update operations need verification
   - Async fixture setup requires proper event loop management

3. **Mobile Client State Sync**: Mobile client state synchronization with backend may encounter conflicts (Issue #3fb6fd2b7b)
   - Pending operation queues require proper handling
   - Conflict detection and resolution mechanisms needed

Debugging Procedures
--------------------

Running Mobile/Backend Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To debug mobile/backend failures:

1. **Run Mobile-Specific Tests**::

    pytest -m mobile -v

2. **Run Backend-Specific Tests**::

    pytest -m backend -v

3. **Run Integration Tests**::

    pytest -m integration -v

4. **Run All Async Tests**::

    pytest -m async -v

5. **Run Full Test Suite with Coverage**::

    pytest --cov=tinydb --cov-report=html

Test Markers
~~~~~~~~~~~~

The following markers are available for organizing and isolating tests:

- ``@pytest.mark.mobile``: Tests for mobile client integration
- ``@pytest.mark.backend``: Tests for backend/server stability
- ``@pytest.mark.integration``: Tests for mobile-backend integration
- ``@pytest.mark.async``: Tests requiring async support
- ``@pytest.mark.slow``: Slow running tests (may be skipped in CI)

Common Debugging Scenarios
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario 1: Database Consistency Issues**

If you encounter database consistency issues:

1. Check test logs for transaction failures
2. Verify caching middleware is not corrupting state (test_db_caching_middleware_stability)
3. Review concurrent insert safety tests (test_concurrent_insert_safety)
4. Check storage layer integrity tests (test_db_storage_persistence)

**Scenario 2: Mobile Client Sync Failures**

If mobile client synchronization fails:

1. Verify mobile state initialization (test_mobile_db_state_initialization)
2. Check pending operations queue handling (test_mobile_pending_operations_queue)
3. Review conflict detection logs (test_mobile_conflict_logging)
4. Verify state consistency with backend (test_mobile_state_consistency)

**Scenario 3: Async Operation Hangs**

If async operations hang or timeout:

1. Verify event loop fixture is properly configured (event_loop fixture)
2. Check async database fixture initialization (test_async_db_fixture_available)
3. Review pytest-asyncio configuration in pytest.ini
4. Enable asyncio debug mode for detailed logs

Test Fixtures
~~~~~~~~~~~~~~

**db**: Standard database fixture (memory or JSON storage)

**async_db**: Async-compatible database fixture for backend testing

**mobile_db_state**: Simulated mobile client state dictionary

**mobile_backend_context**: Full integration context with backend and mobile state

**storage**: Caching middleware with memory storage

**event_loop**: Asyncio event loop for async test support

Best Practices
---------------

1. **Always Use Appropriate Markers**: Tag tests with ``@pytest.mark.mobile``, ``@pytest.mark.backend``, or ``@pytest.mark.integration``

2. **Test Isolation**: Use fixtures to ensure each test starts with a clean state

3. **Error Logging**: Enable verbose logging when debugging failures

4. **Concurrent Safety**: Test concurrent operations separately from single-threaded operations

5. **State Verification**: Always verify both backend and mobile state after operations

Contributing Stability Fixes
-----------------------------

When contributing fixes for stability issues:

1. Create a test case that reproduces the issue
2. Mark the test with appropriate markers (mobile, backend, integration, async)
3. Implement the fix in the source code
4. Verify all related tests pass
5. Add documentation to this guide if the issue is systemic
