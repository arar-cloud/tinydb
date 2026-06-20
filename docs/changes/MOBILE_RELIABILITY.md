# TinyDB Mobile Platform Reliability Guide

## Mobile Platform Overview

TinyDB on mobile platforms (iOS via React Native, Android via React Native/Flutter, hybrid via Ionic) faces unique reliability challenges:

- **Storage constraints**: Limited filesystem space
- **Memory pressure**: OS may suspend or terminate background processes
- **Permission restrictions**: Runtime permission model for file/storage access
- **Background execution**: Limited time for operations when app suspended
- **Network variability**: Frequent connectivity changes

## Storage Constraints

### Available Space Checks

Always verify available storage before large operations:

```python
import os
import json

def get_storage_status(db_path):
    """Check available storage and database size."""
    stat = os.statvfs(os.path.dirname(db_path))
    available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
    return {
        'available_mb': available_mb,
        'db_size_mb': db_size_mb,
        'can_write': available_mb > 10  # 10MB buffer
    }

def safe_insert_with_storage_check(db, documents):
    """Insert only if storage available."""
    status = get_storage_status(db.get_default_table().storage.path)
    if not status['can_write']:
        # Fallback: Use memory storage or queue for later
        return None
    return db.insert_multiple(documents)
```

### Cleanup Strategy

Implement periodic cleanup to maintain adequate free space:

```python
def cleanup_old_records(db, days=30):
    """Remove records older than specified days."""
    from datetime import datetime, timedelta
    from tinydb import Query
    
    cutoff = datetime.now() - timedelta(days=days)
    doc = Query()
    deleted = db.remove(doc.created_at < cutoff.isoformat())
    return len(deleted)
```

## Memory Pressure Handling

### Detecting Memory Pressure

Android and iOS provide memory warnings. Respond by:

1. Clearing caches
2. Pausing non-critical operations
3. Flushing pending writes
4. Reducing query result sizes

```python
class MobileAwareTinyDB:
    def __init__(self, db_path, max_batch_size=100):
        self.db = TinyDB(db_path)
        self.max_batch_size = max_batch_size
        self.under_memory_pressure = False
    
    def on_memory_pressure(self):
        """Called by OS when memory is constrained."""
        self.under_memory_pressure = True
        self.db._cache.clear()  # Clear caches if available
        self.flush_pending()
    
    def on_memory_available(self):
        """Called by OS when memory pressure eases."""
        self.under_memory_pressure = False
    
    def query_with_paging(self, query, page_size=50):
        """Return paginated results to limit memory."""
        if self.under_memory_pressure:
            page_size = min(page_size, self.max_batch_size // 2)
        
        results = self.db.search(query)
        for i in range(0, len(results), page_size):
            yield results[i:i+page_size]
```

## Background Process Handling

### Suspension Lifecycle

1. **App entering background**: Checkpoint current operation state
2. **App suspended**: OS may kill process at any time
3. **App resuming**: Validate database state, retry failed operations
4. **Time limits**: Most platforms allow 30-600 seconds of background execution

```python
class BackgroundTaskManager:
    def __init__(self, db):
        self.db = db
        self.pending_operations = []
        self.checkpoint_path = None
    
    def on_app_background(self):
        """Save state before potential termination."""
        # Write pending operations to checkpoint
        checkpoint = {
            'pending': self.pending_operations,
            'db_state': self._snapshot_db()
        }
        self._save_checkpoint(checkpoint)
    
    def on_app_foreground(self):
        """Resume and validate after potential suspension."""
        checkpoint = self._load_checkpoint()
        if checkpoint:
            # Retry pending operations
            for op in checkpoint['pending']:
                self._retry_operation(op)
            # Validate consistency
            self._validate_consistency(checkpoint['db_state'])
    
    def _retry_operation(self, operation, max_retries=3):
        """Retry with exponential backoff, up to time limit."""
        import time
        for attempt in range(max_retries):
            try:
                return operation['fn'](*operation['args'], **operation['kwargs'])
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                delay = 50 * (2 ** attempt)  # Exponential backoff
                time.sleep(delay / 1000.0)  # Convert to seconds
```

## Storage Permission Management

### Permission Requests

Different platforms require different permissions:

**Android**:
- `READ_EXTERNAL_STORAGE` (API < 33)
- `WRITE_EXTERNAL_STORAGE` (API < 33)
- Scoped storage (API >= 33)

**iOS**:
- No explicit storage permissions
- App sandbox provides automatic isolation

### Graceful Permission Failure

```python
def safe_db_init(db_path=None):
    """Initialize database with permission fallback."""
    try:
        if db_path:
            # Try file-based storage
            db = TinyDB(db_path, storage=JSONStorage)
        else:
            raise FileNotFoundError()
    except (PermissionError, FileNotFoundError):
        # Fall back to memory storage
        print("Warning: Using memory storage (data not persisted)")
        db = TinyDB(storage=MemoryStorage)
    return db

def request_storage_permission_and_retry(db, operation):
    """Request permission and retry operation."""
    # Platform-specific: Show permission dialog
    # Pseudo-code:
    # platform.request_permission('WRITE_STORAGE')
    
    # Retry operation
    try:
        return operation()
    except PermissionError:
        # Permission still denied
        return None
```

## Reliability Patterns for Mobile

### Offline-First Architecture

```python
class OfflineFirstDB:
    def __init__(self, db_path):
        self.db = TinyDB(db_path)
        self.pending_sync = []
    
    def insert_local(self, data):
        """Insert locally, sync later."""
        doc_id = self.db.insert(data)
        self.pending_sync.append({
            'type': 'insert',
            'id': doc_id,
            'data': data
        })
        return doc_id
    
    def sync_when_online(self, sync_fn):
        """Sync pending changes when network available."""
        while self.pending_sync:
            operation = self.pending_sync.pop(0)
            try:
                # Retry with backoff
                self._retry_with_backoff(lambda: sync_fn(operation))
            except Exception as e:
                # Re-queue for later
                self.pending_sync.insert(0, operation)
                break
    
    def _retry_with_backoff(self, fn, max_retries=3):
        """Execute with exponential backoff for mobile."""
        import time
        for attempt in range(max_retries):
            try:
                return fn()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                delay = 50 * (2 ** attempt)
                time.sleep(delay / 1000.0)
```

### Batch Operations for Efficiency

```python
class MobileBatchDB:
    def __init__(self, db, batch_size=100):
        self.db = db
        self.batch_size = batch_size
        self.pending_writes = []
    
    def queue_write(self, data):
        """Queue a write operation."""
        self.pending_writes.append(data)
        if len(self.pending_writes) >= self.batch_size:
            self.flush_writes()
    
    def flush_writes(self):
        """Execute all pending writes in one operation."""
        if not self.pending_writes:
            return
        
        try:
            self.db.insert_multiple(self.pending_writes)
            self.pending_writes.clear()
        except Exception as e:
            # Retry individually for granular error handling
            for data in self.pending_writes:
                try:
                    self.db.insert(data)
                except Exception:
                    # Log failure but continue
                    pass
            self.pending_writes.clear()
```

## Testing Mobile Reliability

All mobile-specific scenarios must have dedicated tests (`@pytest.mark.mobile`):

### Storage Quota Simulation
```python
@pytest.mark.mobile
def test_graceful_failure_when_storage_full(mobile_storage_db, retry_tracker):
    """Verify database fails gracefully when storage quota exceeded."""
    # Simulate storage full scenario
    # Verify operation returns error without crashing
```

### Memory Pressure Simulation
```python
@pytest.mark.mobile
def test_memory_pressure_cache_clearing(mobile_storage_db):
    """Verify caches clear under memory pressure."""
    # Trigger memory pressure event
    # Verify cache is cleared and operations continue
```

### Permission Scenarios
```python
@pytest.mark.mobile
def test_permission_denied_fallback(mobile_storage_db):
    """Verify fallback to memory storage on permission denial."""
    # Simulate permission denied
    # Verify operation succeeds with memory storage
```

## Deployment Checklist

- [ ] Storage quota checks implemented for all write operations
- [ ] Memory pressure handler integrated with OS events
- [ ] Checkpoint/resume logic tested for background suspension
- [ ] Permission fallback strategy configured
- [ ] Offline-first architecture validated
- [ ] Batch operations tested for efficiency
- [ ] Mobile-specific tests passing with `@pytest.mark.mobile`
- [ ] Retry strategies configured for mobile (shorter timeouts, linear backoff)
- [ ] Documentation provided for integration in apps

## References

- [Android Storage Documentation](https://developer.android.com/training/data-storage)
- [iOS File System Documentation](https://developer.apple.com/documentation/foundation/file_system)
- [React Native Background Tasks](https://github.com/react-native-background-timer/react-native-background-timer)
- [Flutter Background Execution](https://flutter.dev/docs/development/packages-and-plugins/background-processes)
