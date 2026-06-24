Stability and Reliability Patterns
==================================

This guide covers best practices for deploying TinyDB reliably in backend and mobile environments, focusing on retry logic, transient failure handling, and consistent behavior across retries.

Overview
--------

TinyDB is optimized for single-process workloads with file-based persistence. This guide addresses deployment patterns for environments with transient failures, file system contention, and network interruptions common in backend services and mobile applications.

Retry and Transient Failure Handling
------------------------------------

Basic Retry Pattern
~~~~~~~~~~~~~~~~~~~

When accessing the database, wrap operations in retry logic to handle transient file lock timeouts::

    import time
    from functools import wraps

    def retry_on_failure(max_attempts=3, delay=0.1, backoff=2.0):
        """Decorator for retrying database operations on transient failures."""
        def decorator(func):
            def wrapper(*args, **kwargs):
                attempt = 0
                current_delay = delay
                last_error = None
                
                while attempt < max_attempts:
                    try:
                        return func(*args, **kwargs)
                    except (OSError, IOError) as e:
                        last_error = e
                        attempt += 1
                        if attempt >= max_attempts:
                            raise
                        time.sleep(current_delay)
                        current_delay *= backoff
                
                raise last_error
            return wrapper
        return decorator

    # Usage
    @retry_on_failure(max_attempts=3, delay=0.1, backoff=2.0)
    def query_with_retry(db, table_name, query):
        return db.table(table_name).search(query)

Timeout Configuration
~~~~~~~~~~~~~~~~~~~~~

Configure appropriate timeouts to prevent indefinite blocking on database operations::

    class DatabaseWithTimeout:
        def __init__(self, db_path, operation_timeout=5.0):
            self.db_path = db_path
            self.operation_timeout = operation_timeout
            self.db = TinyDB(db_path)
        
        def execute_with_timeout(self, operation):
            """Execute database operation with timeout."""
            # Use threading.Timer for cross-platform timeout support
            result = [None]
            exception = [None]
            
            def run_operation():
                try:
                    result[0] = operation(self.db)
                except Exception as e:
                    exception[0] = e
            
            thread = threading.Thread(target=run_operation)
            thread.daemon = True
            thread.start()
            thread.join(timeout=self.operation_timeout)
            
            if thread.is_alive():
                raise TimeoutError(f"Database operation exceeded {self.operation_timeout}s timeout")
            
            if exception[0]:
                raise exception[0]
            
            return result[0]

File Lock and Concurrent Access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

TinyDB uses file-based locking. When multiple processes/threads access the database:

1. **Use memory storage for high-contention scenarios**: For in-process high-frequency access, use MemoryStorage.
2. **Implement process-level serialization**: Queue operations through a single writer thread.
3. **Monitor lock timeouts**: Log and alert on lock acquisition failures.

Graceful Degradation on Lock Timeout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement fallback strategies when lock acquisition fails::

    from tinydb import TinyDB
    from tinydb.storages import JSONStorage
    import time

    class ResilientDatabase:
        def __init__(self, db_path, max_retries=5, retry_delay=0.05):
            self.db_path = db_path
            self.max_retries = max_retries
            self.retry_delay = retry_delay
            self.db = TinyDB(db_path, storage=JSONStorage)
        
        def query_with_fallback(self, table_name, query_func, fallback_func=None):
            """Query with automatic fallback on lock timeout."""
            for attempt in range(self.max_retries):
                try:
                    table = self.db.table(table_name)
                    return query_func(table)
                except (OSError, IOError) as e:
                    if "lock" in str(e).lower() or "temporarily unavailable" in str(e).lower():
                        if attempt < self.max_retries - 1:
                            time.sleep(self.retry_delay * (2 ** attempt))
                            continue
                        # Last attempt failed; use fallback if available
                        if fallback_func:
                            return fallback_func()
                    raise
            return None

Cross-Version Stability
-----------------------

TinyDB maintains compatibility across Python 3.10-3.14. Ensure your retry/timeout logic accounts for:

- **asyncio behavior changes**: Different event loop handling between Python versions.
- **Threading differences**: Thread management varies slightly; use explicit daemon flags.
- **File descriptor limits**: Lower limits on some systems; batch operations when possible.
- **Exception hierarchy**: Handle both OSError and IOError for maximum compatibility.

Best Practices
--------------

1. **Always use timeouts**: Prevent indefinite blocking on file locks or I/O operations.
2. **Implement exponential backoff**: Use geometric backoff (2x, 4x, 8x) to avoid thundering herd problems.
3. **Log lock failures**: Track patterns of contention for capacity planning and debugging.
4. **Use MemoryStorage for tests**: Avoid file system dependencies in unit tests.
5. **Validate consistency after retries**: Verify data integrity after transient failures.
6. **Monitor file system health**: Check disk space, permissions, and inode availability before deployment.
7. **Test under load**: Validate retry behavior with concurrent write scenarios.
8. **Batch operations**: Reduce lock contention by batching multiple writes together.

Mobile Deployment
------------------

On mobile platforms (iOS/Android via Python runtimes):

- Use shorter timeouts (1-2 seconds) due to battery and resource constraints.
- Minimize file system operations; batch writes when possible.
- Handle background process suspension gracefully with operation checkpoints.
- Use in-memory caching layer to reduce lock contention and file system pressure.
- Validate file permissions on application startup; mobile sandboxing differs by platform.

Troubleshooting
---------------

Lock Timeouts
~~~~~~~~~~~~~

**Symptom**: Frequent "OSError: [Errno 11] Resource temporarily unavailable"

**Solutions**:

- Increase retry delay or reduce write frequency from concurrent processes.
- Check for file descriptor exhaustion (run ``ulimit -n`` on Unix systems).
- Verify file system is not running out of space or inodes.
- Consider using MemoryStorage if file system contention is the bottleneck.

Data Corruption After Failure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom**: Database file appears corrupted after retry.

**Solutions**:

- Ensure each process uses separate database files or implement proper write serialization.
- Validate disk integrity; corrupted file systems can cause this issue.
- Implement transaction-level validation to detect and skip corrupted records.

Memory Exhaustion with Retries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom**: Memory usage grows during high-contention periods.

**Solutions**:

- Implement maximum retry attempts and fail-fast strategy.
- Use MemoryStorage with explicit size limits for cache middleware.
- Monitor memory usage and set alarms for anomalies.
- Consider implementing database connection pooling with limits.

See Also
--------

- `TinyDB Documentation <https://tinydb.readthedocs.io/>`_
- `Python Retry Patterns <https://python-patterns.guide/python/retry-requests/>`_
- `Resilience4j Documentation <https://resilience4j.readme.io/>`_ (for inspiration on retry strategies)
