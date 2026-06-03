Mobile/Backend Debugging Reference
===================================

This document provides technical reference for debugging mobile and backend failures in TinyDB.

Root Cause Analysis Checklist
-----------------------------

When investigating a mobile/backend failure:

1. **Identify Test Category**
   - [ ] Is this a mobile client issue? (test_mobile_*)
   - [ ] Is this a backend stability issue? (test_backend_*)
   - [ ] Is this an integration/sync issue? (test_mobile_backend_*)

2. **Test Reproduction**
   - [ ] Run the failing test in isolation: ``pytest -k test_name -v``
   - [ ] Check test logs for error messages
   - [ ] Verify database state before and after test

3. **Database State Verification**
   - [ ] Confirm database initializes without errors
   - [ ] Verify insert/update/delete operations succeed
   - [ ] Check storage layer integrity
   - [ ] Validate caching middleware behavior

4. **Async Operation Verification**
   - [ ] Check event loop is properly initialized
   - [ ] Verify async fixtures are available
   - [ ] Test concurrent operations for race conditions
   - [ ] Validate asyncio_mode configuration

5. **Mobile Client Simulation**
   - [ ] Verify mobile state initializes correctly
   - [ ] Check pending operations queue logic
   - [ ] Review conflict detection mechanism
   - [ ] Validate state consistency with backend

6. **Integration Context**
   - [ ] Confirm backend and mobile state are synchronized
   - [ ] Check sync queue behavior
   - [ ] Verify conflict logging
   - [ ] Validate context initialization

Test Infrastructure Components
-------------------------------

**Fixture System** (tests/conftest.py)

The fixture system provides the foundation for mobile/backend testing:

- ``db``: Parameterized fixture for memory/JSON storage
- ``async_db``: Async-compatible database instance
- ``mobile_db_state``: Mobile client state simulator
- ``mobile_backend_context``: Full integration context
- ``storage``: Caching middleware test harness
- ``event_loop``: Asyncio event loop manager

**Test Organization** (tests/)

Tests are organized by concern:

- ``test_mobile_backend_integration.py``: Integration test suite
- ``test_backend_stability.py``: Backend stability and error handling
- Other test files: Core functionality tests

Common Failure Patterns
-----------------------

**Pattern 1: Database State Corruption**

Symptoms:
- Inconsistent document counts
- Missing or duplicate records
- Update operations affect wrong documents

Debugging Steps:
1. Add assertions to verify document counts: ``assert len(db.all()) == expected_count``
2. Check document IDs are unique: ``assert len(set(d.doc_id for d in db.all())) == len(db.all())``
3. Verify update targeting: ``assert db.get(doc_id=x)['field'] == expected_value``
4. Run test_db_transaction_safety to check consistency

**Pattern 2: Mobile Sync Failures**

Symptoms:
- Pending operations not processed
- Conflicts not detected
- State misalignment between mobile and backend

Debugging Steps:
1. Verify mobile_db_state initializes: ``assert mobile_db_state['sync_state'] == 'idle'``
2. Check pending operations: ``assert isinstance(mobile_db_state['pending_ops'], list)``
3. Review sync queue: ``assert len(sync_queue) == expected_ops``
4. Validate conflict log: ``assert len(conflict_log) >= 0``

**Pattern 3: Async Operation Hangs**

Symptoms:
- Tests timeout waiting for async operations
- Event loop not processing callbacks
- Async fixtures not initializing

Debugging Steps:
1. Verify pytest-asyncio is installed: ``pytest --version`` should show asyncio
2. Check event loop fixture: ``assert event_loop is not None``
3. Enable asyncio debug: set ``PYTHONASYNCDEBUG=1``
4. Add timeout decorator: ``@pytest.mark.timeout(5)``

**Pattern 4: Concurrent Access Issues**

Symptoms:
- Race conditions in concurrent inserts
- Inconsistent state with parallel operations
- Deadlocks in multi-threaded scenarios

Debugging Steps:
1. Run test_concurrent_insert_safety for basic verification
2. Add debug logging to track operation order
3. Use pytest-mock to simulate timing issues
4. Verify storage layer thread safety

Environment Configuration
-------------------------

**pytest.ini Settings**

Critical configuration for mobile/backend debugging::

    [pytest]
    asyncio_mode = auto              # Enable auto asyncio fixture management
    testpaths = tests               # Test discovery path
    markers = mobile, backend, integration, async, slow  # Available markers

**pyproject.toml Dependencies**

Required for mobile/backend testing::

    dev = [
        "pytest>=7.0",              # Test framework
        "pytest-asyncio>=0.21.0",   # Async test support
        "pytest-mock>=3.10.0",      # Mocking utilities
        "httpx>=0.24.0",            # HTTP client simulation
        "asyncio-contextmanager>=1.0.0",  # Async context support
    ]

Performance Considerations
---------------------------

**Database Performance**

- ``MemoryStorage``: Fast for unit tests, suitable for quick iterations
- ``JSONStorage``: Slower but tests persistence, use for integration tests
- Batch operations: Use ``insert_multiple`` for better performance

**Test Execution Speed**

- Skip slow tests in CI: ``pytest -m "not slow"``
- Run mobile/backend tests separately for faster feedback
- Use memory storage for quick iteration cycles

**Concurrency Testing**

- Keep concurrent test batches small (< 100 operations)
- Use deterministic test data for reproducibility
- Document timing-sensitive tests with ``@pytest.mark.slow``

Debugging Tools
----------------

**pytest-cov**: Code coverage analysis

::

    pytest --cov=tinydb --cov-report=html

**pytest-mock**: Object mocking

::

    def test_with_mock(mocker):
        mock_db = mocker.MagicMock()
        # Use mock_db in test

**pytest-timeout**: Timeout detection

::

    @pytest.mark.timeout(5)
    def test_timeout_protected():
        # Test code

**Python asyncio debug mode**: Enable for debugging event loop issues

::

    export PYTHONASYNCDEBUG=1
    pytest -m async -v
