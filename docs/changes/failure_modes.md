# TinyDB Failure Modes and Recovery Procedures

## Overview

This document outlines failure classification, recovery strategies, and retry behavior for TinyDB storage operations to achieve **99.9% uptime for file-based storage operations**.

## Failure Classification

### Transient Failures

Transient failures are temporary I/O issues that may succeed on retry:

- **File Lock Contention**: Another process holds write lock (Windows `PermissionError`, Unix `IOError`)
  - Recovery: Exponential backoff retry (100ms → 200ms → 400ms)
  - Retry Limit: 3 attempts
  - Idempotent: YES (atomic writes ensure consistency)

- **Temporary Filesystem Unavailability**: NFS mount temporarily unreachable, disk busy
  - Recovery: Exponential backoff with jitter
  - Retry Limit: 5 attempts over 10 seconds
  - Idempotent: YES

- **Resource Exhaustion**: EMFILE (too many open files), ENOMEM
  - Recovery: Backoff + garbage collection + retry
  - Retry Limit: 2 attempts after cleanup
  - Idempotent: YES

### Permanent Failures

Permanent failures indicate unrecoverable data/access issues:

- **Permission Denied**: Database file not readable/writable, directory not accessible
  - Recovery: None - fail immediately
  - Action: Raise PermissionError with context

- **File Not Found**: Parent directory deleted, database file removed during operation
  - Recovery: None - fail immediately
  - Action: Raise FileNotFoundError with context

- **Disk Full**: `ENOSPC` error during write
  - Recovery: None - fail immediately
  - Action: Raise OSError with disk space diagnostics

- **Corrupted File**: JSON decode fails, checksum mismatch
  - Recovery: Manual intervention required
  - Action: Raise JSONDecodeError or ValueError with backup path suggestion

- **Type/Schema Error**: Invalid data type in storage layer
  - Recovery: None - fail immediately
  - Action: Raise TypeError or ValueError

## Retry Strategy

### Exponential Backoff Formula

```
delay = min(initial_delay * (2 ^ attempt), max_delay) + random_jitter
where:
  initial_delay = 100ms
  max_delay = 5000ms
  jitter = random(0, delay * 0.1)
```

### Idempotency Guarantees

- **Write Operations**: Atomic file replacement (write-to-temp, rename) ensures at most once semantics
- **Read Operations**: No state change, always idempotent
- **Delete Operations**: Atomic inode removal ensures idempotency

Failed operations leave no partial state on disk.

## Storage Layer Error Handling

### JSONStorage.read()

- **Transient**: IOError, OSError with errno in [EAGAIN, EWOULDBLOCK, EMFILE, ENFILE]
  - Action: Retry with exponential backoff
- **Permanent**: PermissionError, FileNotFoundError, JSONDecodeError, UnicodeDecodeError
  - Action: Propagate immediately

### JSONStorage.write()

- **Transient**: IOError, OSError with errno in [EAGAIN, EWOULDBLOCK, EMFILE, ENFILE, ENOMEM]
  - Action: Retry with exponential backoff
- **Permanent**: PermissionError, FileNotFoundError, OSError with ENOSPC, TypeError
  - Action: Propagate immediately

### MemoryStorage

- No I/O failures; all operations are in-process
- No retry logic needed

## Recovery Procedures

### User-Facing Steps

1. **Transient Failure (automatic retry engaged)**
   - Database library automatically retries with backoff
   - Monitor logs for repeated failures (→ may indicate permanent issue)
   - No user action required unless all retries exhausted

2. **Permanent Failure (application halt)**
   - Read logs for specific error (Permission, Disk Full, Corruption)
   - Permission: Check file/directory ownership and ACLs
   - Disk Full: Free disk space and retry
   - Corruption: Restore from backup; disable auto-restart until root cause found

### Operational Monitoring

- Log all I/O exceptions with context: operation (read/write), path, errno, attempt count
- Alert if any single operation exceeds 2 retries
- Alert if any operation sequence shows >5% failure rate over 1-minute window
- Track correlation between failures and system metrics (disk I/O, memory, open file count)

## Testing Strategy

### Transient Failure Tests

- Hypothesis-based property tests with fault injection
- Simulate file lock contention via mock OS operations
- Simulate EMFILE by configuring ulimit
- Verify retry count and backoff timing
- Verify idempotency across multiple retries

### Permanent Failure Tests

- Verify immediate propagation (no retry)
- Verify error context and stack traces
- Verify no partial state left on disk

### Integration Tests

- Multi-retry consistency: Write, fail, retry, verify consistency
- Concurrent retry resilience: Multiple threads retrying same operation
- Filesystem variant coverage: Test across local FS, tmpfs, network mounts (if applicable)

## Configuration

Default retry configuration in TinyDB:

```python
# Storage layer defaults (not yet exposed in public API)
INITIAL_RETRY_DELAY_MS = 100
MAX_RETRY_DELAY_MS = 5000
MAX_RETRIES_TRANSIENT = 3
JITTER_FRACTION = 0.1
```

Future enhancement: Make these configurable via storage options.

## References

- Issue: `[debugging:issue-0989e16c26]`
- Related tests: `tests/test_storages.py` (transient_failure, idempotent markers)
- Type hints: See `tinydb/storages.py` for complete Storage interface
