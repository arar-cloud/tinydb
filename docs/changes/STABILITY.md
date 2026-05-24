# TinyDB Stability Patterns and Retry Policies

## Retry Strategy Guidelines

### Exponential Backoff with Jitter
Recommended for all database operations:
```python
import time
import random

def retry_with_backoff(func, max_retries=3, base_delay=0.1):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
            time.sleep(delay)
```

## Idempotency Guarantees

### Write Operations
- Insert operations are idempotent when document IDs are stable
- Update operations should be applied as atomic patches, not cumulative
- Delete operations by ID are idempotent

### Read Operations
- Always idempotent; safe to retry without side effects
- Use query snapshots for consistency across retries

## Transactional Atomicity

- Database writes are atomic at the table level
- Multi-table transactions should use explicit locking or retry logic
- WAL (Write-Ahead Log) recovery ensures consistency after crashes

## Cross-Platform Consistency

### Backend (Python/REST API)
- Use connection pooling with timeout enforcement
- Implement circuit breakers for cascade failure prevention

### Mobile (Android/iOS via Python)
- Enforce strict timeouts (5s read, 10s write)
- Cache query results locally to reduce retry load

### Web Clients
- Validate idempotency keys before retry attempts
- Use exponential backoff with max 5s wait time

## Error Handling

| Error Type | Recoverable | Retry Strategy |
|------------|------------|----------------|
| IOError | Yes | Exponential backoff up to 3 retries |
| CorruptionError | No | Log and alert; manual recovery required |
| ConcurrencyError | Yes | Exponential backoff with conflict resolution |
| TimeoutError | Yes | Exponential backoff up to 5 retries |

## Recovery Procedures

### Corrupted Database Recovery
1. Backup the corrupted file
2. Reload from last valid WAL checkpoint
3. Validate data integrity before resume
4. Implement automated corruption detection

## Testing for Stability

All changes to retry logic must include tests covering:
- Transactional atomicity validation
- Concurrent access patterns
- Operation replay consistency
- Partial write recovery
- Cross-platform behavior equivalence
