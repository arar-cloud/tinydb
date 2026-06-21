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

## Operator Runbooks

### Transient Failure Response Procedures

#### 1. File Lock Contention Detected

**Symptoms**: `IOError: File is locked` or `PermissionError` in logs, retry attempts visible

**Response Steps**:
1. Check open file descriptors: `lsof | grep tinydb.db`
2. Identify blocking process: Look for processes with write lock
3. Check retry logs for backoff timing: Expected 100ms → 200ms → 400ms delays
4. Monitor latency spike: p99 write latency should return to <200ms post-retry
5. If contention persists >10s: Scale down concurrent writers or implement request queueing

**Validation**: Verify retry count in logs matches expected exponential backoff sequence

#### 2. EMFILE (Too Many Open Files)

**Symptoms**: `OSError: [Errno 24] Too many open files` after repeated write attempts

**Response Steps**:
1. Check current ulimit: `ulimit -n`
2. Check actual open files: `lsof | wc -l`
3. Increase ulimit (Linux): `ulimit -n 4096`
4. Identify file descriptor leaks: Check for unclosed file handles in application code
5. Restart application if leak suspected

**Validation**: Verify EMFILE errors decrease after retry backoff; open file count should stabilize

#### 3. Temporary Filesystem Unavailability (NFS, Disk Busy)

**Symptoms**: `OSError: [Errno 11] Resource temporarily unavailable` (EAGAIN/EWOULDBLOCK)

**Response Steps**:
1. Check filesystem mount status: `mount | grep db-path`
2. Check disk I/O latency: `iostat -x 1` (look for %util, await)
3. Monitor NFS mount availability: `nfsstat` (for NFS mounts)
4. Check system load: `uptime`, `top`
5. If NFS unavailable: Verify network path, check server availability

**Validation**: Confirm retry backoff recovers database access; I/O latency should normalize

### Permanent Failure Response Procedures

#### 1. Permission Denied

**Symptoms**: `PermissionError: [Errno 13] Permission denied` on read/write, no retry attempts

**Response Steps**:
1. Check file ownership: `ls -la data/tinydb.db`
2. Check directory ownership: `ls -la data/`
3. Verify application process user: `ps -u | grep app`
4. Fix permissions: `chown app:app data/tinydb.db` and `chmod 600 data/tinydb.db`
5. Verify ACLs: `getfacl data/tinydb.db` (if ACLs enabled)

**Validation**: Retry operation manually; should succeed immediately

#### 2. Disk Full (ENOSPC)

**Symptoms**: `OSError: [Errno 28] No space left on device`, application halts on write

**Response Steps**:
1. Check disk usage: `df -h`
2. Identify large files: `du -sh *` in parent directory
3. Free disk space: Delete old backups, logs, or temporary files
4. Target: At least 20% free space
5. Monitor space after cleanup: `watch -n 5 'df -h'`

**Validation**: Retry write operation; should succeed after disk space freed

#### 3. Corrupted JSON Data

**Symptoms**: `json.JSONDecodeError` on read, database cannot be loaded

**Response Steps**:
1. Backup corrupted file: `cp data/tinydb.db data/tinydb.db.corrupted`
2. Check backup integrity: `python -c "import json; json.load(open('data/backup.db'));"`
3. Restore from backup: `cp data/backup.db data/tinydb.db`
4. Verify restored data: Query database and validate record count
5. Investigate corruption cause: Check for crashes, disk errors, or concurrent writes

**Validation**: Confirm database reads successfully after restore

### Monitoring Checklist

**Every 5 minutes** (automated alerts):
- Check retry rate: Target <2% of operations retry once
- Check error rate: Alert if >0.1% permanent failures
- Track latency p99: Alert if >5 second operation latency

**Every hour** (manual review):
- Parse logs for repeated failures: Indicates systemic issue
- Check disk space trend: Alert if <30% free
- Verify backup freshness: Last backup <24 hours old

**Every day** (operational verification):
- Test restore procedure: Ensure backup recovery works
- Review failure classification: Transient vs permanent ratio
- Verify SLO tracking: Confirm uptime targets on pace

## References

- Issue: `[debugging:issue-0989e16c26]`
- Related tests: `tests/test_storages.py` (transient_failure, idempotent markers)
- Type hints: See `tinydb/storages.py` for complete Storage interface
- Reliability SLA: See `docs/changes/reliability_sla.md` for uptime targets and RTO/RPO guarantees
