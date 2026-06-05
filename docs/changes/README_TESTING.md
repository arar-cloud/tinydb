# TinyDB Test Suite Documentation

## Test Categories and Markers

Tests are organized using pytest markers for selective execution and categorization:

### Core Markers

- **`@pytest.mark.stability`**: Stability and reliability focused tests
- **`@pytest.mark.retry`**: Tests for retry behavior and idempotency
- **`@pytest.mark.exception`**: Exception handling and recovery tests
- **`@pytest.mark.platform`**: Platform-specific tests (filesystem, permissions)
- **`@pytest.mark.concurrent`**: Concurrent access and thread-safety tests
- **`@pytest.mark.stress`**: Stress and load tests
- **`@pytest.mark.chaos`**: Chaos and failure injection tests
- **`@pytest.mark.slow`**: Slow-running tests (long operations, large datasets)

### Running Tests by Category

```bash
# Run only stability tests
pytest -m stability

# Run retry/idempotency tests
pytest -m retry

# Run exception handling tests
pytest -m exception

# Run platform-specific tests
pytest -m platform

# Run concurrent access tests
pytest -m concurrent

# Run stress tests
pytest -m stress

# Skip slow tests
pytest -m "not slow"

# Run stability but not slow tests
pytest -m "stability and not slow"
```

## Test Fixtures

### Database Fixtures

#### `db` (parametrized)
- **Description**: Main database fixture with both MemoryStorage and JSONStorage backends
- **Parameters**: `memory`, `json`
- **Scope**: Function
- **Cleanup**: Automatically drops all tables after test

```python
def test_something(db):
    db.insert({'test': 'data'})
    assert len(db) == 1  # Plus 3 from fixture setup
```

#### `storage`
- **Description**: CachingMiddleware with MemoryStorage for low-level storage testing
- **Scope**: Function

### Failure Injection Fixtures

#### `failing_storage_on_write`
- **Description**: Storage that raises IOError on write operations (simulates disk full)
- **Use Case**: Testing write failure handling

```python
def test_write_failure(failing_storage_on_write):
    db = TinyDB(storage=failing_storage_on_write)
    with pytest.raises(IOError):
        db.insert({'test': 'data'})
```

#### `failing_storage_on_read`
- **Description**: Storage that raises IOError on read operations (simulates permission denied)
- **Use Case**: Testing read failure handling

#### `partial_write_storage`
- **Description**: Storage that simulates partial write scenarios
- **Use Case**: Testing recovery from incomplete writes

#### `slow_storage`
- **Description**: Storage with artificial I/O delays (50ms per operation)
- **Use Case**: Testing timeout handling and concurrent access under slow I/O

### Temporary Path Fixture

#### `tmp_path` (pytest built-in)
- **Description**: Temporary directory for each test (auto-cleanup)
- **Use Case**: JSONStorage file-based tests

```python
def test_json_storage(tmp_path):
    db_path = tmp_path / 'test.db'
    db = TinyDB(db_path, storage=JSONStorage)
    # ... test code ...
    db.close()
```

## Test Isolation and Cleanup

### Automatic Cleanup

All fixtures include automatic cleanup:

1. **Database fixtures**: Call `db.drop_tables()` or `db.truncate()` after each test
2. **File fixtures**: Use `tmp_path` which auto-deletes after test
3. **Temp files**: Use `cleanup_temp_files` autouse fixture

### Manual Cleanup Requirements

1. **Always close database objects**:
   ```python
   db = TinyDB(path, storage=JSONStorage)
   try:
       # ... operations ...
   finally:
       db.close()
   ```

2. **Clean file permissions** (if modified):
   ```python
   import os
   os.chmod(path, 0o644)  # Restore readable/writable
   ```

3. **Remove symbolic links** (if created):
   ```python
   import os
   os.unlink(symlink_path)
   ```

## Test Organization

### Module Structure

- **`test_retry_idempotency.py`**: Retry behavior and idempotent operation validation
- **`test_exception_recovery.py`**: Exception handling and database recovery
- **`test_platform_stability.py`**: Filesystem, permission, and resource constraints
- **`test_stress.py`**: Large datasets, memory, and performance under load
- **`conftest.py`**: Shared fixtures and test configuration

### Test Class Organization

Tests are organized in classes by concern:

```python
@pytest.mark.stability
@pytest.mark.retry
class TestRetryIdempotency:
    def test_insert_is_idempotent(self, db):
        ...
    def test_update_idempotency_same_values(self, db):
        ...
```

## Coverage Requirements

- **Minimum Coverage**: 90% of `tinydb/` module
- **Coverage Report**: Run `pytest --cov-report term-missing` for details
- **Exclusions**: `tests/`, `conftest.py`, and type-ignore comments

## Running the Full Test Suite

```bash
# All tests with coverage
pytest --cov=tinydb --cov-report=term-missing

# Quick test (exclude slow tests)
pytest -m "not slow"

# Stability tests only
pytest -m stability

# Verbose output with timing
pytest -v --durations=10

# Stop on first failure
pytest -x

# Run with verbose output
pytest -vv
```

## CI/CD Integration

The test suite is designed for CI/CD environments:

1. **Type Checking**: `mypy` validates type safety (non-PyPy only)
2. **Coverage Enforcement**: `pytest-cov` fails if coverage < 90%
3. **Parallel Execution**: `pytest-xdist` enables `-n auto` for parallel runs
4. **Markers**: Use markers to categorize tests for selective CI runs

### Example CI Command

```bash
pytest -v -m "not slow" --cov=tinydb --cov-fail-under=90
```

## Troubleshooting Flaky Tests

### Common Issues

1. **Permission Errors**: Tests may fail if run as root or in restricted environments
   - Solution: Use `pytest.skip()` for platform-specific tests

2. **File Path Issues**: Deeply nested paths or special characters
   - Solution: Use `tmp_path` fixture for all file operations

3. **Timeout Issues**: Slow storage tests timing out
   - Solution: Adjust `slow_storage` delay or mark as `@pytest.mark.slow`

4. **Isolation Failures**: Tests affecting each other
   - Solution: Ensure all fixtures use function scope and cleanup resources

### Debug Test Execution

```bash
# Run single test with full output
pytest tests/test_retry_idempotency.py::TestRetryIdempotency::test_insert_is_idempotent -vv -s

# Run with print statements visible
pytest -s

# Show local variables on failure
pytest -l

# Drop to pdb on failure
pytest --pdb
```

## Contributing New Tests

### Checklist

- [ ] Add appropriate `@pytest.mark.*` decorator
- [ ] Use `db` or appropriate fixture parameter
- [ ] Ensure cleanup with `try/finally` for file operations
- [ ] Add docstring explaining test purpose
- [ ] Name test with `test_` prefix and descriptive name
- [ ] Run locally: `pytest tests/test_file.py -v`
- [ ] Check coverage: `pytest --cov-report term-missing`

### Example Template

```python
"""Module docstring explaining test focus."""
import pytest
from tinydb import TinyDB, Query

@pytest.mark.stability  # Add appropriate markers
class TestYourFeature:
    """Test class for feature validation."""

    def test_specific_behavior(self, db):
        """Descriptive test docstring."""
        # Arrange
        db.insert({'data': 'value'})
        
        # Act
        result = db.get(Query().data == 'value')
        
        # Assert
        assert result is not None
```

## Performance Benchmarking

For stress tests, collect timing information:

```bash
# Show slowest 10 tests
pytest --durations=10 -m stress

# Profile with pytest-benchmark (if installed)
pytest --benchmark-only
```

## Concurrent/Thread-Safety Testing

Use `pytest-xdist` for parallel test execution:

```bash
# Run tests in parallel (auto-detect CPU cores)
pytest -n auto

# Run tests with explicit worker count
pytest -n 4

# Combine with markers
pytest -n auto -m "concurrent"
```

## Type Checking Integration

Type checking is configured in `pyproject.toml` and enforced via `mypy`:

```bash
# Run mypy on source code
mypy tinydb/

# Check with strict settings
mypy --strict tinydb/
```
