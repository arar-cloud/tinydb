# TinyDB Retry Strategy and Stability Guide

## Overview

This document outlines retry behavior, idempotency guarantees, and error recovery strategies for TinyDB operations across backend and mobile platforms.

## Retry Behavior

### Core Principles

1. **Idempotency**: All database operations (read, write, delete) must be idempotent—repeated execution with identical parameters produces the same result.
2. **Consistency**: Multiple retries of the same operation maintain data consistency across concurrent scenarios.
3. **Resilience**: The database gracefully handles transient failures and resource constraints.

### Backoff Strategies

#### Exponential Backoff
```
delay = base_delay * (exponential_base ** attempt_number)
```

- **Base delay**: 100ms (configurable)
- **Exponential base**: 2.0
- **Max retries**: 3
- **Max delay**: 5000ms

#### Linear Backoff (Mobile)
For resource-constrained mobile environments:
```
delay = base_delay * attempt_number
```

- **Base delay**: 50ms
- **Max retries**: 5
- **Max delay**: 2000ms

## Operation Guarantees

### Read Operations

- **Idempotency**: ✓ Guaranteed (no state change)
- **Consistency**: ✓ Snapshot isolation
- **Retry behavior**: Safe to retry unlimited times
- **Mobile constraints**: Minimize in background tasks; cache results when possible

### Write Operations (Insert/Update/Upsert)

- **Idempotency**: ✓ Guaranteed with identical parameters
- **Consistency**: ✓ Atomic per-document
- **Retry behavior**: Use unique identifiers to ensure idempotency
- **Mobile constraints**: Batch writes; respect storage quota

### Delete Operations

- **Idempotency**: ✓ Guaranteed (idempotent deletion)
- **Consistency**: ✓ Immediate on success
- **Retry behavior**: Safe to retry; deleting non-existent records is a no-op
- **Mobile constraints**: Queue deletions; verify free space before operations

## Concurrent Access Patterns

### Thread Safety

- **Single-threaded**: Native support; no retries needed
- **Multi-threaded**: Use locks or queue serialization
- **Async operations**: Ensure exclusive access during operations

### Race Condition Handling

1. **Write-Write Conflicts**: Last-write-wins (LWW) with timestamp
2. **Read-Write Conflicts**: Readers see committed state
3. **Deadlock Prevention**: Operation timeout + exponential backoff

### Recommended Patterns

```python
# Backend: Concurrent writes with retry
for attempt in range(max_retries):
    try:
        db.update(doc, cond=Query().version == current_version)
        break
    except Exception as e:
        if attempt == max_retries - 1:
            raise
        time.sleep(backoff_delay(attempt))

# Mobile: Offline-first with eventual consistency
local_changes = []
while offline:
    local_changes.append(operation)

when_online:
    for change in local_changes:
        retry_with_backoff(lambda: db.update(change))
```

## Mobile-Specific Considerations

### Storage Constraints

- **Quota management**: Monitor available storage before large operations
- **Cleanup**: Implement periodic cleanup of old/unused documents
- **Compression**: Consider compressed storage for large datasets

### Memory Pressure

- **Batch processing**: Limit results per query to prevent OOM
- **Streaming**: Use iterators instead of loading full result sets
- **Caching**: Clear caches on memory pressure warnings

### Background Process Handling

- **Suspension**: Save operation state before background suspension
- **Resume**: Validate state consistency on resume; retry failed operations
- **Timeout**: Use aggressive timeouts for background operations

### Permission Management

- **Storage access**: Verify permissions before file operations
- **Graceful failure**: Fall back to memory storage if file access denied
- **Permission changes**: Detect and re-request as needed

## Error Recovery Guarantees

### Transient Errors (Retry)

- Lock contention → Exponential backoff
- Memory pressure → Release caches, retry
- I/O timeouts → Exponential backoff + fallback to memory storage
- Permissions denied (mobile) → Request permissions, retry

### Permanent Errors (Fail)

- Database corruption → Manual intervention required
- Invalid schema → Must fix application code
- Disk full (non-mobile) → Cleanup required
- Missing file (mobile) → Reinitialize database

## Testing Retry Behavior

All database operations must pass retry validation tests:

1. **Retry resilience tests** (`@pytest.mark.retry`)
   - Verify consistent results across multiple retries
   - Test with simulated transient failures

2. **Idempotency tests** (`@pytest.mark.idempotent`)
   - Ensure repeated operations produce identical state
   - Validate write, update, delete idempotency

3. **Concurrency tests** (`@pytest.mark.concurrent`)
   - Simulate race conditions under retry scenarios
   - Validate thread-safe access patterns

4. **Mobile tests** (`@pytest.mark.mobile`)
   - Test storage quota constraints
   - Simulate permission scenarios
   - Validate background process handling

## Configuration Best Practices

### Backend Deployments

```python
# High availability with aggressive retries
max_retries = 5
base_delay = 100  # ms
exponential_base = 2.0
timeout = 5000    # ms
```

### Mobile Deployments

```python
# Resource-aware with conservative retries
max_retries = 3
base_delay = 50   # ms
backoff_style = 'linear'  # Less aggressive
timeout = 2000    # ms
storage_quota_buffer = 10  # MB reserve
```

## References

- [TinyDB Documentation](https://tinydb.readthedocs.io/)
- [Idempotency patterns](https://en.wikipedia.org/wiki/Idempotence)
- [Distributed Systems: Retry patterns](https://aws.amazon.com/blogs/architecture/)
