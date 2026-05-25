# TinyDB Test Infrastructure

## Overview

This directory contains the complete test suite for TinyDB, organized to support testing across multiple stack targets: backend, mobile, and web.

## Test Discovery and Execution

### Test Files
- Test files follow the naming convention: `test_*.py` or `*_test.py`
- All tests are automatically discovered by pytest from the `tests/` directory
- Test functions are identified by the `test_*` naming convention

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with verbose output and coverage
python -m pytest -v --cov=tinydb

# Run specific test file
python -m pytest tests/test_module.py

# Run tests matching a pattern
python -m pytest -k "test_query"

# Run tests with specific markers (see Markers section below)
python -m pytest -m backend
python -m pytest -m "not slow"
```

## Test Markers

Tests are organized using pytest markers for platform-specific and functional categorization:

### Platform Markers
- `@pytest.mark.backend`: Core database functionality tests (storage, queries, transactions)
- `@pytest.mark.mobile`: Performance-critical tests, memory efficiency tests
- `@pytest.mark.web`: Web framework integration tests, documentation examples
- `@pytest.mark.integration`: Tests spanning multiple components

### Functional Markers
- `@pytest.mark.slow`: Long-running tests (deselect with `-m "not slow"`)
- `@pytest.mark.requires_json`: Tests requiring JSON storage support
- `@pytest.mark.requires_memory`: Tests requiring memory storage support

### Example Usage

```python
import pytest

@pytest.mark.backend
def test_query_basic():
    """Test basic query functionality."""
    pass

@pytest.mark.mobile
@pytest.mark.slow
def test_performance_large_dataset():
    """Performance test for mobile platforms."""
    pass

@pytest.mark.web
@pytest.mark.integration
def test_web_framework_integration():
    """Integration test with web framework."""
    pass
```

## Fixtures

### Database Fixtures

#### `db` (Parameterized)
Provides database instances for both Memory and JSON storage backends.

```python
def test_with_db(db):
    """Test using parameterized database fixture.
    
    Args:
        db: TinyDB instance (memory or json storage)
    """
    # Database is pre-populated with test data
    assert db.count() == 3
```

#### `storage`
Provides a CachingMiddleware-wrapped MemoryStorage instance.

```python
def test_with_storage(storage):
    """Test using storage fixture."""
    # storage is a CachingMiddleware instance
    pass
```

## Environment Setup

### Test Environment Requirements
- Python >= 3.10
- pytest >= 7.0
- pytest-cov >= 4.0 (for coverage reporting)
- mypy >= 1.0 (for type checking)

### Installation for Development

```bash
# Install project with test dependencies
pip install -e ".[dev]"

# Or install specific tools
pip install pytest pytest-cov mypy
```

### Temporary Directory Handling
Tests that use JSON storage rely on the system temp directory. If tests fail due to permission errors:
1. Verify temp directory is writable: `ls -l /tmp`
2. Override temp directory: `export TMPDIR=/path/to/writable/dir`
3. The test environment will skip if temp directory is not writable

## Type Checking

MyPy strict type checking is enabled to catch latent bugs early:

```bash
# Run type checking
mypy tinydb tests

# Type checking is configured in mypy.ini with strict mode enabled
```

## Debugging Failed Tests

### Verbose Output
```bash
python -m pytest -v --tb=long tests/test_module.py::test_function
```

### Stop on First Failure
```bash
python -m pytest -x tests/
```

### Show Local Variables in Traceback
```bash
python -m pytest -l tests/
```

### Platform-Specific Debugging
```bash
# Run only backend tests
python -m pytest -m backend -v

# Run only mobile tests
python -m pytest -m mobile -v

# Run only web tests
python -m pytest -m web -v
```

### Multiplatform Test Isolation
If tests pass in one environment but fail in another:
1. Check Python version: `python --version` (should be 3.10+)
2. Check temporary directory writability
3. Check for platform-specific imports or OS-specific behavior
4. Use markers to isolate platform-specific tests

## Conftest Setup

The `conftest.py` file provides:
- Pytest configuration and marker registration
- Test environment validation (`setup_test_environment` fixture)
- Platform-specific marker application
- Database and storage fixtures with proper cleanup

## Coverage Reporting

Coverage is automatically tracked during test execution:

```bash
# Run tests with coverage report
python -m pytest --cov=tinydb --cov-report=html

# View coverage report
open htmlcov/index.html
```

Coverage requirements and exclusions are configured in `pyproject.toml`.

## Continuous Integration

Tests are configured to run in CI environments with:
- Strict marker enforcement (`--strict-markers`)
- Verbose output for debugging
- Coverage tracking and reporting
- Multiplatform test execution (backend, mobile, web)

## Troubleshooting

### Tests not discovered
- Ensure test files follow naming convention: `test_*.py` or `*_test.py`
- Verify `tests/__init__.py` exists (even if empty)
- Check `pytest.ini` has `testpaths = tests`

### Import errors
- Verify project root is in `sys.path`
- Install in editable mode: `pip install -e .`
- Check Python version: `python --version` (need 3.10+)

### Fixture errors
- Verify fixtures are defined in `conftest.py`
- Check fixture scope matches test requirements
- Ensure temporary directories are writable for JSON storage tests

### Platform-specific test failures
- Use `pytest -m <marker> -v` to isolate by platform
- Check for OS-specific imports or behavior
- Verify environment variables are set correctly
