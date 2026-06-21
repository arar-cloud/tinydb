# TinyDB Reliability SLA and Guarantees

## Service Level Objectives (SLOs)

### Uptime Target
- **File-based Storage (JSONStorage)**: 99.9% uptime over 30-day rolling window
- **Memory Storage (MemoryStorage)**: 99.95% uptime (no I/O failures, single process only)
- Excludes scheduled maintenance windows

### Error Budget
- **File-based Storage**: 43.2 minutes of downtime per 30 days
- **Memory Storage**: 21.6 minutes of downtime per 30 days

## Recovery Time Objectives (RTO)

### Transient Failures
- **Target RTO**: < 5 seconds
- **Mechanism**: Exponential backoff retry with jitter (100ms → 5s max)
- **Retry Limit**: 3-5 attempts depending on failure type
- **Idempotent Operations**: Atomic write-to-temp-rename pattern ensures consistency

### Permanent Failures
- **Target RTO**: < 15 minutes
- **Mechanism**: Manual recovery or restore from backup
- **Failure Types**: Permission denied, disk full, corrupted data
- **Operator Action**: Review logs, address root cause (permissions, disk space), restore backup if necessary

## Recovery Point Objective (RPO)

### File-based Storage
- **RPO**: 0 seconds (sync-on-write with fsync)
- **Guarantee**: Every successful write operation is durably written to disk
- **Caveat**: Unacknowledged writes lost on crash; committed writes are persistent

### Memory Storage
- **RPO**: Not applicable (volatile, restart results in data loss)
- **Use Case**: Development, caching, ephemeral workloads only

## Failure Modes and Guarantees

For comprehensive failure classification, recovery strategies, and testing procedures, see [Failure Modes and Recovery Procedures](./failure_modes.md).

### Key Guarantees

1. **Atomicity**: Write operations use atomic file replacement; partial writes do not occur
2. **Idempotency**: Retry of any failed operation results in exactly-once semantics
3. **Consistency**: No silent data corruption; failures are explicit or transient-retriable
4. **Durability**: fsync on write ensures durable persistence (subject to filesystem/hardware reliability)

## Monitoring and Alerting

### Metrics to Track
- **I/O operation latency**: p50, p99 (target: <100ms p99 for reads, <200ms p99 for writes)
- **Retry rate**: % of operations requiring 1+ retries (alert if >2% over 5-min window)
- **Error rate**: % of operations failing after all retries (alert if >0.1% over 5-min window)
- **Failure categories**: Transient vs. Permanent (track correlation with system metrics)

### Alert Thresholds
- **Single operation >2 retries**: WARN (may indicate system contention)
- **Operation sequence >5% failure rate over 1 min**: ALERT
- **Permanent failure detected**: CRITICAL (disk full, permissions, corruption)

## Operational Runbooks

### Transient Failure Response
1. Monitor TinyDB logs for retry messages
2. If retries consistently succeed, no action required
3. If retries exhaust, check system metrics (disk I/O, open file count, memory)
4. Adjust concurrency or retry timeouts if necessary

### Permanent Failure Response
1. Identify failure type from logs (Permission, Disk Full, Corruption, Type Error)
2. **Permission**: Check file/directory ownership and ACLs
3. **Disk Full**: Free disk space, restart application
4. **Corruption**: Restore from backup, investigate cause before restart
5. **Type Error**: Verify database schema, apply migrations if needed

## Design Constraints

- **No external coordination**: File-based storage is single-process; concurrency within single process uses in-memory locking
- **Filesystem dependency**: Reliability depends on underlying filesystem (ext4, NTFS, etc.); network mounts have higher latency and failure rates
- **Hardware limits**: Operating system I/O limits (EMFILE, ENFILE) may trigger retries under high concurrency

## Metrics Collection and Integration

### Logging Configuration

All storage layer operations must log:
```
[TIMESTAMP] [LEVEL] [storage.py:write] operation=write path=/data/tinydb.db attempt=1 delay_ms=0 status=success
[TIMESTAMP] [LEVEL] [storage.py:write] operation=write path=/data/tinydb.db attempt=2 delay_ms=100 status=retry errno=24
[TIMESTAMP] [LEVEL] [storage.py:write] operation=write path=/data/tinydb.db attempt=3 delay_ms=200 status=permanent_failure errno=28
```

### Prometheus Metrics

Expose metrics for collection:
```
tinydb_io_operations_total{operation="read",status="success"} 15234
tinydb_io_operations_total{operation="read",status="retry"} 42
tinydb_io_operations_total{operation="read",status="permanent_failure"} 1
tinydb_io_operation_duration_seconds{operation="read",quantile="0.99"} 0.087
tinydb_io_operation_duration_seconds{operation="read",quantile="0.999"} 0.342
tinydb_io_retries_total{failure_type="file_lock"} 12
tinydb_io_retries_total{failure_type="emfile"} 3
tinydb_io_retries_total{failure_type="eagain"} 27
```

### CI/CD Integration Points

1. **Pre-deployment verification**:
   - Run chaos tests with `pytest -m chaos_injection` to verify retry logic
   - Validate 90% test coverage with `-v --cov-fail-under=90`
   - Execute stress tests: `pytest -m stress_test --durations=10`

2. **Post-deployment validation**:
   - Collect baseline metrics from first 1 hour of production traffic
   - Alert if retry rate >2% or permanent failure rate >0.1%
   - Compare p99 latency to historical baseline ±10%

3. **Continuous monitoring**:
   - Export metrics every 60 seconds to time-series database
   - Calculate rolling 30-day uptime: (total_seconds - failure_seconds) / total_seconds
   - Alert if 30-day uptime projected to miss 99.9% SLO

## References

- [Failure Modes and Recovery Procedures](./failure_modes.md): Detailed classification, testing strategy, configuration
- Issue tracking: `[debugging:issue-b68db1c961]`
- Design review: Atomic writes, retry strategy, idempotency
- Configuration schema: See `pyproject.toml [tool.tinydb]` for metrics and alert thresholds
