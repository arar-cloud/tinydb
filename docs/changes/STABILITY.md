# TinyDB Stability & Reliability Guide

## Overview

This guide documents TinyDB's reliability guarantees, failure modes, and recommended patterns for handling transient failures in backend and mobile deployments.

## Stability Guarantees

### Data Consistency
- **ACID Compliance**: TinyDB provides transaction-like semantics for single-table operations
- **Crash Recovery**: JSON storage maintains write-ahead integrity; memory storage is volatile
- **Concurrent Access**: File-based storage is protected by OS-level locking; memory storage requires external synchronization

### Transient Failure Handling

TinyDB does **not** automatically retry on transient failures. Applications must implement retry logic using the following patterns:

#### Recommended: Tenacity Library

```python
from tenacity import retry, stop_after_attempt, wait_exponential
from tinydb import TinyDB

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def query_with_retry(db):
    return db.search(lambda x: x.value > 10)

db = TinyDB('db.json')
result = query_with_retry(db)
```

#### Manual Retry Pattern

```python
import time
from tinydb import TinyDB

def query_with_retry(db, max_attempts=3):
    for attempt in range(1, max_attempts + 1):
        try:
            return db.search(lambda x: x.value > 10)
        except IOError as e:
            if attempt == max_attempts:
                raise
            wait_time = 2 ** attempt  # Exponential backoff
            time.sleep(wait_time)
```

## Failure Modes

### Disk I/O Errors
- **Cause**: File permission issues, disk full, filesystem errors
- **Recovery**: Retry with exponential backoff (2s, 4s, 8s)
- **Permanent**: Replace storage device or fix filesystem

### Lock Contention
- **Cause**: Multiple processes/threads accessing same database simultaneously
- **Impact**: Queries may block or timeout
- **Resolution**: Use connection pooling or distributed locking (Redis)

### Memory Exhaustion
- **Cause**: Large datasets or unclosed database connections
- **Recovery**: Close connections explicitly; use pagination for large queries
- **Prevention**: Monitor memory usage; implement connection limits

### Concurrency Issues
- **Race Condition**: File modified during read operation
- **Mitigation**: TinyDB uses file locks (fcntl/msvcrt); ensure atomic operations
- **Testing**: Enable concurrency markers in pytest

## Testing for Stability

TinyDB includes pytest markers for stability validation:

```bash
# Run only transient failure tests
pytest -m transient

# Run concurrency/race condition tests
pytest -m concurrency

# Run flaky/retry validation tests
pytest -m retry

# Run all stability tests
pytest -m stability
```

### Simulating Failures

Use the provided fixtures in `tests/conftest.py`:

```python
def test_retry_on_io_error(transient_failure_simulator):
    simulator = transient_failure_simulator
    simulator.reset(fail_count=2)  # Fail twice, succeed on 3rd try
    
    if simulator.should_fail():
        raise IOError("Simulated disk error")
```

## Deployment Recommendations

### Backend (Python/API)
1. Use `tenacity` for automatic retries on transient failures
2. Configure timeouts: `pytest --timeout=30` during testing
3. Monitor error rates and slow queries
4. Use shared storage (NFS, cloud storage) for multi-instance deployments
5. Implement circuit breakers for cascading failures

### Mobile (React Native, Flutter)
1. Handle IOError and TimeoutError gracefully in UI
2. Implement offline-first caching with eventual consistency
3. Use background sync with retry queue
4. Set shorter timeouts for user-facing operations (5-10s)
5. Test on slow/unreliable networks

### Configuration

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tinydb import TinyDB

# Production-grade retry configuration
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=60),
    retry=retry_if_exception_type((IOError, TimeoutError)),
    reraise=True
)
def db_operation(db, operation):
    return operation(db)
```

## Performance Under Load

- **Single-threaded**: 1000+ ops/sec for in-memory storage
- **Multi-threaded**: File locking may reduce throughput; use memory storage if possible
- **JSON serialization**: ~100ms per 100KB for typical datasets
- **Recommended**: For >10MB datasets or >100 concurrent connections, consider PostgreSQL or MongoDB

## See Also

- [TinyDB Documentation](https://tinydb.readthedocs.io/)
- [Tenacity Retry Library](https://tenacity.readthedocs.io/)
- [Python Asyncio Patterns](https://docs.python.org/3/library/asyncio.html)
