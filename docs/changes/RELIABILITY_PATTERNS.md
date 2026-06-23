# TinyDB Reliability Patterns for Backend & Mobile

## Backend API Patterns

### 1. Automatic Retry with Circuit Breaker

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from functools import wraps
import logging

logger = logging.getLogger(__name__)

class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None

    def is_open(self):
        if self.failure_count >= self.failure_threshold:
            if time.time() - self.last_failure_time > self.timeout:
                self.reset()
                return False
            return True
        return False

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

    def reset(self):
        self.failure_count = 0
        self.last_failure_time = None

breaker = CircuitBreaker()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((IOError, TimeoutError)),
)
def query_db_with_cb(db, query_fn):
    if breaker.is_open():
        raise Exception("Circuit breaker is open")
    try:
        result = query_fn(db)
        breaker.reset()
        return result
    except (IOError, TimeoutError) as e:
        breaker.record_failure()
        logger.error(f"Database query failed: {e}")
        raise
```

### 2. Bulkhead Pattern (Limiting Concurrent Connections)

```python
from threading import Semaphore
from contextlib import contextmanager

class DatabasePool:
    def __init__(self, max_connections=5):
        self.semaphore = Semaphore(max_connections)
        self.db_instances = {}

    @contextmanager
    def get_connection(self, db_path):
        self.semaphore.acquire()
        try:
            if db_path not in self.db_instances:
                self.db_instances[db_path] = TinyDB(db_path)
            yield self.db_instances[db_path]
        finally:
            self.semaphore.release()

pool = DatabasePool(max_connections=10)

# Usage in Flask/FastAPI
@app.get("/users/{user_id}")
def get_user(user_id: int):
    with pool.get_connection('users.db') as db:
        return db.search(lambda x: x.id == user_id)
```

### 3. Request-Scoped Caching

```python
from functools import lru_cache
import hashlib

class CachedQuery:
    def __init__(self, db, cache_ttl=60):
        self.db = db
        self.cache = {}
        self.cache_ttl = cache_ttl
        self.last_clear = time.time()

    def search(self, query_fn, cache_key=None):
        # Clear cache if TTL expired
        if time.time() - self.last_clear > self.cache_ttl:
            self.cache.clear()
            self.last_clear = time.time()

        key = cache_key or hashlib.md5(str(query_fn).encode()).hexdigest()
        if key in self.cache:
            return self.cache[key]

        result = self.db.search(query_fn)
        self.cache[key] = result
        return result
```

## Mobile App Patterns

### 1. Offline-First with Background Sync

```python
# For React Native or Flutter native module
from threading import Thread
import queue

class OfflineFirstDB:
    def __init__(self, local_db, remote_sync_fn):
        self.local_db = local_db
        self.remote_sync_fn = remote_sync_fn
        self.sync_queue = queue.Queue()
        self.start_background_sync()

    def insert(self, data):
        # Write to local DB immediately
        result = self.local_db.insert(data)
        # Queue for remote sync
        self.sync_queue.put(('insert', result))
        return result

    def start_background_sync(self):
        thread = Thread(target=self._sync_worker, daemon=True)
        thread.start()

    def _sync_worker(self):
        while True:
            try:
                operation, data = self.sync_queue.get(timeout=5)
                self.remote_sync_fn(operation, data)
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Sync failed: {e}")
                # Re-queue for retry
                self.sync_queue.put((operation, data))
```

### 2. Graceful Degradation on Error

```python
def fetch_user_data(user_id, db):
    try:
        with db:
            result = db.search(lambda x: x.id == user_id)
            return {"status": "success", "data": result}
    except IOError:
        logger.warning(f"Database IO error for user {user_id}")
        return {
            "status": "degraded",
            "data": get_cached_user(user_id),
            "message": "Serving from cache due to temporary database issue"
        }
    except TimeoutError:
        return {
            "status": "timeout",
            "data": None,
            "message": "Request timed out; please retry"
        }
```

### 3. Adaptive Timeout Based on Network Conditions

```python
class AdaptiveDB:
    def __init__(self, db_path, base_timeout=5):
        self.db = TinyDB(db_path)
        self.base_timeout = base_timeout
        self.slow_query_count = 0
        self.current_timeout = base_timeout

    def search_adaptive(self, query_fn):
        try:
            start = time.time()
            result = self.db.search(query_fn)
            elapsed = time.time() - start

            # Adjust timeout based on observed latency
            if elapsed > self.current_timeout * 0.8:
                self.slow_query_count += 1
                if self.slow_query_count > 3:
                    self.current_timeout = min(self.current_timeout * 1.5, 30)
                    self.slow_query_count = 0
            else:
                self.slow_query_count = max(0, self.slow_query_count - 1)

            return result
        except TimeoutError:
            self.current_timeout = max(self.current_timeout * 1.2, self.base_timeout)
            raise
```

## Concurrency Safety

### Thread-Safe Wrapper

```python
from threading import Lock, RLock

class ThreadSafeDB:
    def __init__(self, db_path):
        self.db = TinyDB(db_path)
        self.lock = RLock()  # Reentrant lock

    def search(self, query_fn):
        with self.lock:
            return self.db.search(query_fn)

    def insert(self, data):
        with self.lock:
            return self.db.insert(data)

    def update(self, data, query_fn):
        with self.lock:
            return self.db.update(data, query_fn)

# Usage
db = ThreadSafeDB('app.db')

def worker():
    db.insert({'worker_id': 1})

threads = [Thread(target=worker) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Error Handling Checklist

- [ ] Wrap database operations in try-except for IOError and TimeoutError
- [ ] Implement exponential backoff for retries (min 1s, max 60s)
- [ ] Use circuit breaker to prevent cascading failures
- [ ] Log all database errors with context (user_id, operation, timestamp)
- [ ] Set operation timeouts (backend: 30s, mobile: 10s)
- [ ] Test with simulated failures (see pytest markers)
- [ ] Monitor error rates and alert on threshold breach
- [ ] Implement graceful degradation (cache fallback, read-only mode)
