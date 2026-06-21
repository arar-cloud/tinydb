# TinyDB Error Classification and Retry Reference

## Overview

This reference documents error classification for JSONStorage operations, specifying which errors are transient (retryable) and which are permanent (fail-fast). Used by developers to understand retry behavior, design robust applications, and debug consistency issues.

## Quick Reference: Error Classification by errno

### Transient Errors (Retryable - Automatic Exponential Backoff)

| errno | Name | Cause | Recovery | Max Retries | Example |
|-------|------|-------|----------|-------------|----------|
| 11 | EAGAIN / EWOULDBLOCK | File lock, resource unavailable | Backoff & retry | 3 | Another process holds write lock |
| 24 | EMFILE | Process open file descriptor limit exceeded | Backoff allows cleanup | 3 | Too many concurrent open files |
| 23 | ENFILE | System-wide file table full | Backoff allows cleanup | 3 | System resource exhaustion |
| 12 | ENOMEM | Memory pressure (temporary) | Backoff allows GC | 3 | Swap exhaustion, cleanup frees RAM |
| 16 | EBUSY | Device or resource busy | Backoff allows device recovery | 3 | NFS mount hiccup, disk cache flush |
| 110 | ETIMEDOUT | Operation timeout (NFS lag) | Backoff tries again | 3 | Network filesystem timeout |

**String-based Detection**:
- Message contains `'lock'` (case-insensitive): Treated as transient file lock

### Permanent Errors (No Retry - Fail Immediately)

| errno | Exception | Cause | Why No Retry | Example |
|-------|-----------|-------|--------------|----------|
| 28 | OSError(ENOSPC) | Disk full / no space available | Retries cannot free disk space | Storage disk full |
| 1 | OSError(EPERM) | Operation not permitted | Retries do not change permissions | User lacks write permission |
| 13 | PermissionError / OSError(EACCES) | Permission denied on file/directory | Retries do not change permissions | Directory not writable |
| 22 | OSError(EINVAL) | Invalid argument to system call | Bug in code, not transient | File opened with wrong flags |
| 21 | IsADirectoryError | Path is a directory, not a file | Path validation error | Database path is a folder |
| 20 | NotADirectoryError | Parent path is not a directory | Path validation error | Parent of db file is a file |
| — | FileNotFoundError | File does not exist | Path validation error (post-creation) | File deleted by external process |
| — | PermissionError | No read/write permission | Access control, not transient | User lacks file permissions |
| — | json.JSONDecodeError | Corrupted JSON in file | Data corruption, not transient | File contains invalid JSON |
| — | UnicodeDecodeError | Invalid UTF-8 encoding in file | Encoding error, not transient | File has binary data |
| — | ValueError | JSON deserialization error | Data format mismatch | Custom decoder fails |
| — | TypeError | Data not JSON-serializable | Code bug, not transient | Object is not serializable |

## Operation-Specific Retry Semantics

### JSONStorage.read()

**Operation**:
1. Seek to end of file and check size
2. If empty, return None (uninitialized)
3. Seek to start and deserialize JSON

**Transient Failures**:
- File locked by another process (EAGAIN, lock string)
- Too many open files (EMFILE, ENFILE)
- Memory pressure (ENOMEM)
- Device busy (EBUSY)
- NFS timeout (ETIMEDOUT)

**Permanent Failures** (immediate):
- PermissionError: No read access
- FileNotFoundError: File deleted
- json.JSONDecodeError: Corrupted data
- UnicodeDecodeError: Invalid encoding

**Retry Behavior**:
```
Attempt 1: Try read
├─ Transient Error (e.g., EAGAIN)
│  └─ Sleep 100ms + jitter → Attempt 2
│
Attempt 2: Try read
├─ Success → Return data
├─ Transient Error
│  └─ Sleep 200ms + jitter → Attempt 3
└─ Permanent Error → Raise immediately

Attempt 3: Try read
├─ Success → Return data
└─ Any Error → Raise (no more retries)
```

**Max Retries**: 3 (after 3 failures, raise immediately)

**Backoff Schedule** (with ±10% jitter):
- After Attempt 1 failure: 100ms
- After Attempt 2 failure: 200ms
- After Attempt 3 failure: Raise (no sleep)
- Maximum delay: 5000ms (capped exponential backoff)

### JSONStorage.write()

**Operation** (Atomic):
1. Seek to file start
2. Serialize entire database state (json.dumps)
3. Write JSON to file
4. Flush OS buffers
5. fsync() to disk (durability)
6. Truncate if file is shorter

**Idempotency**: Yes. Each write overwrites the entire file atomically. Multiple retries produce the identical result (deterministic final state).

**Transient Failures**:
- File locked (EAGAIN, lock string)
- Too many open files (EMFILE, ENFILE)
- Memory pressure (ENOMEM)
- Device busy (EBUSY)
- NFS timeout (ETIMEDOUT)

**Permanent Failures** (immediate):
- io.UnsupportedOperation: File not opened in write mode
- PermissionError: No write access
- OSError(ENOSPC): Disk full
- TypeError: Data not JSON-serializable

**Retry Behavior**:
```
Attempt 1: Try atomic write (seek, write, flush, fsync, truncate)
├─ Transient Error (e.g., EBUSY)
│  └─ Sleep 100ms + jitter → Attempt 2
│
Attempt 2: Try atomic write
├─ Success → Return
├─ Transient Error
│  └─ Sleep 200ms + jitter → Attempt 3
└─ Permanent Error → Raise immediately

Attempt 3: Try atomic write
├─ Success → Return
└─ Any Error → Raise (no more retries)
```

**Max Retries**: 3 (after 3 failures, raise immediately)

**Backoff Schedule** (with ±10% jitter):
- After Attempt 1 failure: 100ms
- After Attempt 2 failure: 200ms
- After Attempt 3 failure: Raise (no sleep)
- Maximum delay: 5000ms (capped exponential backoff)

## Decision Tree: Is This Error Transient?

```
Exception raised during read() or write()?
│
├─ json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError
│  └─ → PERMANENT. Data corrupted or type mismatch. Retry will fail.
│
├─ PermissionError, FileNotFoundError, IsADirectoryError, NotADirectoryError
│  └─ → PERMANENT. Path validation failed. Retry will fail.
│
├─ OSError or IOError?
│  │
│  ├─ errno == ENOSPC (28)?
│  │  └─ → PERMANENT. Disk full. Retry will fail.
│  │
│  ├─ errno == EPERM (1) or EACCES (13)?
│  │  └─ → PERMANENT. Permission denied. Retry will fail.
│  │
│  ├─ errno in (EAGAIN, EWOULDBLOCK, EMFILE, ENFILE, ENOMEM, EBUSY, ETIMEDOUT)?
│  │  └─ → TRANSIENT. Resource contention. Retry with backoff.
│  │
│  └─ Message contains 'lock' (case-insensitive)?
│     └─ → TRANSIENT. File lock contention. Retry with backoff.
│
└─ Other exception
   └─ → PERMANENT by default. Raise immediately.
```

## Backoff Strategy

### Exponential Backoff with Jitter

**Formula**:
```
delay_ms = min(initial_backoff_ms * (2^attempt), max_backoff_ms)
jitter_ms = delay_ms * jitter_fraction * random_sign
sleep_time_s = max(0, (delay_ms + jitter_ms) / 1000)
```

**Configuration**:
- `initial_backoff_ms = 100` (100ms first retry)
- `max_backoff_ms = 5000` (capped at 5 seconds)
- `jitter_fraction = 0.1` (±10% random variation)
- `max_retries = 3` (3 total attempts)

**Schedule Example**:
```
Attempt 1 fails at T=0ms
  Sleep: 100ms ± 10ms = 90-110ms
  Attempt 2 starts at T≈100ms

Attempt 2 fails at T≈100ms
  Sleep: 200ms ± 20ms = 180-220ms
  Attempt 3 starts at T≈300ms

Attempt 3 fails at T≈300ms
  No sleep
  Raise exception
```

**Maximum Possible Delay**: 100ms + 200ms = 300ms (before giving up)

**Jitter Purpose**: Avoid "thundering herd" when many processes retry simultaneously (e.g., after NFS timeout).

## SLO and Latency Budgets

### Uptime Target
- **99.9% uptime** over 30-day rolling window
- **Error Budget**: 43.2 minutes of downtime per month
- **Permanent Failures** reduce uptime (no retry)
- **Transient Failures** retried automatically (may not reduce uptime if recovered)

### Latency Targets (with Retries)
- **Read P99**: < 500ms (includes up to 3 retries)
- **Write P99**: < 1000ms (includes up to 3 retries)
- **Retry Overhead**: < 100ms per operation

## Concurrent Access and Data Consistency

### File Lock Handling

**Scenario**: Process A and Process B both try to write simultaneously.

1. Process A: Calls write() → seeks(0) → writes JSON → fsync() → truncate() → SUCCESS
2. Process B: Calls write() during Process A's fsync()
   - Gets OSError(EAGAIN, "Resource locked")
   - Classified as TRANSIENT
   - Sleeps 100ms
   - Retries write() after Process A releases lock
   - SUCCESS

**Consistency Guarantee**: Last-write-wins. The process that completes write() last determines the file state.

### Idempotency Guarantee

**No Partial Writes**: Atomic pattern (seek → write → fsync → truncate) means:
- Either the entire update succeeds (file replaced completely)
- Or the entire update fails (file unchanged)
- **Never** a partial update (half-written state)

Retries are safe because:
- Each retry writes the complete database state
- Final state is deterministic (same data written on retry)
- No accumulation of partial updates

## Testing Error Scenarios

### Unit Test: Transient Error Injection

```python
import errno
from unittest.mock import patch

def test_read_retry_on_emfile():
    storage = JSONStorage("test.json")
    
    # Mock json.load to fail with EMFILE on first call
    with patch('json.load') as mock_load:
        mock_load.side_effect = [
            OSError(errno.EMFILE, "Too many open files"),
            {"data": "test"}  # Success on retry
        ]
        result = storage.read()
    
    assert result == {"data": "test"}
    assert mock_load.call_count == 2  # Called twice (1 fail + 1 success)
```

### Integration Test: Concurrent Access

```python
import threading

def test_concurrent_read_write():
    storage = JSONStorage("test.json")
    success_count = [0]
    
    def reader():
        data = storage.read()
        success_count[0] += 1
    
    def writer():
        storage.write({"data": "updated"})
        success_count[0] += 1
    
    # Launch 10 readers + 5 writers
    threads = [
        *[threading.Thread(target=reader) for _ in range(10)],
        *[threading.Thread(target=writer) for _ in range(5)],
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert success_count[0] == 15  # All succeeded
```

## Logging and Debugging

### Log Messages

**Transient Failure (Retry)**:
```
WARNING: Transient read failure (attempt 1/3): OSError: [Errno 11] Resource temporarily unavailable. Retrying in 0.095s
```

**Permanent Failure (No Retry)**:
```
ERROR: Permanent read failure: FileNotFoundError: [Errno 2] No such file or directory: 'db.json'
```

**Max Retries Exceeded**:
```
ERROR: Read failed after 3 attempt(s): OSError: [Errno 24] Too many open files
```

### Debugging Steps

1. **Check Error Type**: Is it in transient or permanent list?
2. **Check Retry Count**: Did retries occur? (WARNING logs)
3. **Check Backoff Timing**: Did sleep durations match expected schedule?
4. **Check SLO**: Did P99 latency exceed budget?
5. **Check Concurrency**: Were multiple processes/threads involved?

## Version and Configuration

- **TinyDB Version**: 4.8.2
- **Retry Library**: tenacity (optional, fallback graceful)
- **Configuration File**: pyproject.toml [project.stability]
- **Test Configuration**: pytest.ini (markers, timeout, logging)

## References

- [TinyDB Retry and Backoff Guide](user_retry_guide.md)
- [Failure Modes and Recovery](failure_modes.md)
- [Reliability SLA and Guarantees](reliability_sla.md)
- [Test Implementation Guide](test_implementation_guide.md)
