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

## References

- [Failure Modes and Recovery Procedures](./failure_modes.md): Detailed classification, testing strategy, configuration
- Issue tracking: `[debugging:issue-b68db1c961]`
- Design review: Atomic writes, retry strategy, idempotency
