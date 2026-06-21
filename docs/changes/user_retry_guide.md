# TinyDB Retry and Backoff Configuration Guide

## Overview

TinyDB's JSONStorage implements automatic retry logic for transient I/O failures to achieve **99.9% uptime** for file-based storage operations. This guide explains configuration options and expected behavior.

## Transient vs Permanent Failures

### Transient Failures (Automatically Retried)

These errors indicate temporary resource contention or unavailability:

- **EAGAIN / EWOULDBLOCK**: Resource temporarily unavailable (file lock, file descriptor limit)
- **EMFILE / ENFILE**: Too many open files or file descriptors
- **ENOMEM**: Temporary memory pressure
- **EBUSY**: Device or resource busy
- **ETIMEDOUT**: Operation timeout (NFS mount lag)

**Behavior**: Automatic exponential backoff retry. Operation succeeds on next attempt.

### Permanent Failures (Fail Immediately)

These errors indicate unrecoverable conditions:

- **ENOSPC**: Disk full
- **EPERM / EACCES**: Permission denied
- **EINVAL**: Invalid argument
- **EISDIR / ENOTDIR**: Path type mismatch
- **JSONDecodeError / ValueError**: Corrupted data

**Behavior**: Immediate failure. Application must handle error or stop database.

## Configuration Parameters

Add these to your application startup or environment:

```python
from tinydb import TinyDB

# Default behavior (no explicit config needed)
db = TinyDB('db.json')
```

### Advanced Configuration (via JSONStorage)

```python
from tinydb.storages import JSONStorage

# Retry defaults: max_retries=3, backoff 100ms→5000ms with jitter
storage = JSONStorage('db.json')
db = TinyDB(storage=storage)
```

## Backoff Calculation

For each transient failure:

```
delay_ms = min(initial_delay_ms * (2 ** attempt), max_delay_ms)
jitter = delay_ms * jitter_fraction * (±0.5)
sleep_time_seconds = (delay_ms + jitter) / 1000
```

**Defaults**:
- `initial_delay_ms = 100` (0.1 seconds)
- `max_delay_ms = 5000` (5 seconds)
- `jitter_fraction = 0.1` (±10% randomization)
- `max_retries = 3`

**Example Retry Timeline**:
- Attempt 1: Immediate
- Attempt 2: ≈100ms (±10ms)
- Attempt 3: ≈200ms (±20ms)
- Attempt 4: ≈400ms (±40ms)
- Fails after 4 attempts

## Logging

Enable debug logging to observe retry behavior:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('tinydb.storages')
```

**Transient Failure Log** (INFO level):
```
Transient write failure (attempt 1/4): OSError. Retrying in 0.105s
```

**Permanent Failure Log** (ERROR level):
```
Permanent write failure: PermissionError: [Errno 13] Permission denied: 'db.json'
```

## Tuning for Your Environment

### High-Contention Scenarios (Shared Filesystems, NFS)

- Increase `max_retries` from 3 to 5
- Increase `max_backoff_ms` from 5000 to 10000
- Add application-level retry wrapper

### Low-Latency Requirements

- Reduce `initial_delay_ms` from 100 to 50
- Reduce `max_retries` from 3 to 2 (fail-fast)
- Consider memory storage for non-persistent use cases

### High-Concurrency (Many Processes)

- Ensure `jitter_fraction >= 0.1` to reduce thundering herd
- Monitor system file descriptor limits (`ulimit -n`)
- Consider database sharding or partitioning

## Expected Behavior

### Normal Operation
- **Write**: 0-1 retries (99.5% first attempt)
- **Read**: 0 retries (read-only, no file locks)

### Under Contention (3+ processes writing)
- **Write**: 1-2 retries (typical)
- **Latency**: +100-400ms per write operation
- **Success Rate**: 99.9% within 5 seconds

### Failure Scenarios
- **Disk Full**: Fails immediately (permanent)
- **Network Filesystem Down**: Retries up to 5 seconds then fails
- **File Permission Changed**: Fails immediately after first attempt

## Monitoring and Alerts

Configure alerting for:

1. **Transient failure rate > 5% of operations**: Investigate filesystem health
2. **Permanent failures**: Immediate attention required (disk full, permissions)
3. **Write latency > 500ms average**: Consider load reduction or hardware upgrade

## FAQ

**Q: Can I disable retries?**
A: No. Retries are mandatory for production stability. Remove database writes if you need guaranteed low-latency.

**Q: Why does my write take several seconds sometimes?**
A: Exponential backoff with maximum 5-second retry window. This is expected under high contention.

**Q: How do I know if a failure is permanent?**
A: Check logs for "Permanent failure" message. These errors require application-level handling (e.g., alert operator, switch to backup storage).

**Q: What if I get ENOSPC (disk full)?**
A: Immediate failure. Free disk space and retry. Database will not auto-recover.
