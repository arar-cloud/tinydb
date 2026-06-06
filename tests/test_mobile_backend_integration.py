"""Integration tests for mobile and backend deployment scenarios.

Covers:
- Simulated network delays and latency
- Connection timeouts and interruptions
- Graceful degradation with limited resources
- Sync and batch operation patterns
"""

import os
import time
import pytest
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestMobileScenarios:
    """Test patterns typical in mobile deployments."""

    def test_local_first_write_with_eventual_sync(self, tmp_path: Path):
        """Verify local-first write pattern for mobile offline scenarios."""
        local_db_path = tmp_path / "local.json"
        local_db = TinyDB(local_db_path, storage=JSONStorage)

        # Insert locally (offline)
        local_doc_id = local_db.insert({
            'content': 'offline draft',
            'synced': False,
            'timestamp': time.time()
        })
        assert local_doc_id is not None

        # Simulate connection delay before sync
        time.sleep(0.05)

        # Sync operation (connection restored)
        local_doc = local_db.get(doc_id=local_doc_id)
        assert local_doc is not None
        assert not local_doc['synced']

        # Mark as synced
        local_db.update({'synced': True}, doc_ids=[local_doc_id])
        synced_doc = local_db.get(doc_id=local_doc_id)
        assert synced_doc['synced']

        local_db.close()

    def test_batch_operations_reduce_io(self, tmp_path: Path):
        """Verify batch operations reduce I/O overhead for mobile."""
        db_path = tmp_path / "batch.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Batch insert is more efficient than individual inserts
        records = [
            {'id': i, 'data': f'record_{i}', 'synced': False}
            for i in range(100)
        ]

        start = time.time()
        doc_ids = db.insert_multiple(records)
        batch_time = time.time() - start

        assert len(doc_ids) == 100
        assert batch_time < 5  # Batch should be fast

        # Verify all records inserted
        all_docs = db.all()
        assert len(all_docs) == 100
        db.close()

    def test_fallback_to_memory_on_permission_denied(self, tmp_path: Path):
        """Test graceful fallback to memory storage on permission errors."""
        # Create a directory we'll restrict
        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()
        db_path = restricted_dir / "app.json"

        # Create DB normally first
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'test': 'data'})
        db.close()

        # Now restrict permissions (Unix-like systems)
        try:
            os.chmod(restricted_dir, 0o000)

            # Attempt to open database (permission denied)
            fallback_db = None
            try:
                fallback_db = TinyDB(db_path, storage=JSONStorage)
            except (PermissionError, OSError):
                # Fallback to memory storage
                fallback_db = TinyDB(storage=MemoryStorage)

            # Verify fallback works
            doc_id = fallback_db.insert({'fallback': 'data'})
            assert doc_id is not None
            assert fallback_db.get(doc_id=doc_id)['fallback'] == 'data'
            fallback_db.close()

        finally:
            # Restore permissions for cleanup
            os.chmod(restricted_dir, 0o755)

    def test_detect_and_handle_limited_storage(self, tmp_path: Path):
        """Test detection of limited storage space."""
        db_path = tmp_path / "limited_storage.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Check available space
        stat = os.statvfs(str(tmp_path))
        available_bytes = stat.f_bavail * stat.f_frsize
        available_mb = available_bytes / (1024 * 1024)

        # Verify we can detect low disk space
        assert available_mb > 0  # Test directory should have space

        # Insert data while checking space
        min_required_mb = 1  # Require at least 1MB free

        for i in range(10):
            stat = os.statvfs(str(tmp_path))
            available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)

            if available_mb < min_required_mb:
                # Would implement cleanup here
                break

            db.insert({
                'index': i,
                'data': 'x' * 1024,  # 1KB per record
                'available_mb': available_mb
            })

        # Verify some records inserted
        assert len(db.all()) > 0
        db.close()


class TestBackendScenarios:
    """Test patterns typical in backend deployments."""

    def test_connection_reuse_across_requests(self, tmp_path: Path):
        """Verify single connection instance across multiple requests."""
        db_path = tmp_path / "backend.json"
        # Simulate application-level connection pool
        db = TinyDB(db_path, storage=JSONStorage)

        request_count = 0

        def handle_request(request_id):
            nonlocal request_count
            # Each request uses the shared connection
            doc_id = db.insert({
                'request_id': request_id,
                'timestamp': time.time()
            })
            request_count += 1
            return doc_id

        # Simulate multiple requests
        for i in range(50):
            handle_request(i)

        # Single connection handled all requests
        assert request_count == 50
        assert len(db.all()) == 50
        db.close()

    def test_health_check_under_load(self, tmp_path: Path):
        """Test health check endpoint performance under load."""
        db_path = tmp_path / "health.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Insert test data
        for i in range(1000):
            db.insert({'id': i, 'data': f'record_{i}'})

        def health_check():
            start = time.time()
            try:
                # Quick check: verify database is responsive
                count = len(db.all())
                latency_ms = (time.time() - start) * 1000
                return {
                    'status': 'healthy' if latency_ms < 100 else 'degraded',
                    'document_count': count,
                    'latency_ms': latency_ms
                }
            except Exception as e:
                return {
                    'status': 'unhealthy',
                    'error': str(e)
                }

        # Run health checks
        for _ in range(10):
            health = health_check()
            assert health['status'] in ['healthy', 'degraded', 'unhealthy']
            assert health['document_count'] == 1000

        db.close()

    def test_graceful_shutdown_with_pending_operations(self, tmp_path: Path):
        """Test graceful shutdown doesn't lose pending operations."""
        db_path = tmp_path / "shutdown.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Insert data
        doc_ids = []
        for i in range(100):
            doc_id = db.insert({
                'operation': 'pending',
                'index': i
            })
            doc_ids.append(doc_id)

        # Graceful close
        db.close()

        # Reopen and verify all data persisted
        db = TinyDB(db_path, storage=JSONStorage)
        reopened_docs = db.all()
        assert len(reopened_docs) == 100
        assert all(doc['operation'] == 'pending' for doc in reopened_docs)
        db.close()

    def test_concurrent_requests_with_simulated_latency(self, tmp_path: Path):
        """Test backend handles concurrent requests with network latency."""
        db_path = tmp_path / "concurrent_requests.json"
        db = TinyDB(db_path, storage=JSONStorage)

        successful_requests = 0
        failed_requests = 0
        lock = threading.Lock()

        def simulated_request(request_id):
            nonlocal successful_requests, failed_requests
            try:
                # Simulate network latency
                time.sleep(0.01)

                # Database operation
                doc_id = db.insert({
                    'request_id': request_id,
                    'status': 'processed'
                })

                # Simulate response time
                time.sleep(0.01)

                with lock:
                    successful_requests += 1
            except Exception as e:
                with lock:
                    failed_requests += 1

        # Simulate concurrent requests
        threads = []
        for i in range(20):
            t = threading.Thread(target=simulated_request, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert successful_requests == 20
        assert failed_requests == 0
        assert len(db.all()) == 20
        db.close()


class TestNetworkSimulation:
    """Test behavior with simulated network conditions."""

    def test_timeout_handling(self, tmp_path: Path):
        """Test timeout handling during slow operations."""
        db_path = tmp_path / "timeout.json"
        db = TinyDB(db_path, storage=JSONStorage)

        def operation_with_timeout(timeout_sec=1.0):
            start = time.time()

            # Simulate slow operation
            time.sleep(0.5)

            # Check if exceeded timeout
            elapsed = time.time() - start
            if elapsed > timeout_sec:
                raise TimeoutError(f"Operation took {elapsed}s, exceeded {timeout_sec}s")

            return db.insert({'status': 'completed', 'duration': elapsed})

        # Operation completes within timeout
        doc_id = operation_with_timeout(timeout_sec=1.0)
        assert doc_id is not None

        # Verify timeout logic works
        with pytest.raises(TimeoutError):
            operation_with_timeout(timeout_sec=0.1)  # Too short

        db.close()

    def test_retry_with_simulated_intermittent_failure(self, tmp_path: Path):
        """Test retry logic handles intermittent failures."""
        db_path = tmp_path / "intermittent.json"
        db = TinyDB(db_path, storage=JSONStorage)

        call_count = 0

        def flaky_operation():
            nonlocal call_count
            call_count += 1
            # Fail on first 2 calls, succeed on 3rd
            if call_count < 3:
                raise ConnectionError(f"Attempt {call_count} failed")
            return db.insert({'status': 'recovered', 'attempts': call_count})

        # Retry with exponential backoff
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = flaky_operation()
                break
            except ConnectionError:
                if attempt == max_retries - 1:
                    raise
                # Exponential backoff
                time.sleep(0.01 * (2 ** attempt))

        assert result is not None
        assert call_count == 3
        assert db.get(doc_id=result)['attempts'] == 3
        db.close()

    def test_batch_sync_with_partial_failures(self, tmp_path: Path):
        """Test batch sync handles partial failures gracefully."""
        db_path = tmp_path / "batch_sync.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Local records to sync
        records_to_sync = [
            {'id': i, 'data': f'sync_{i}', 'synced': False}
            for i in range(20)
        ]

        synced_count = 0
        failed_count = 0

        for record in records_to_sync:
            try:
                # Simulate that some syncs fail
                if record['id'] % 3 == 0:  # Every 3rd fails
                    raise ConnectionError("Sync failed")

                # Insert synced record
                db.insert({'status': 'synced', **record})
                synced_count += 1
            except ConnectionError:
                failed_count += 1
                # Would retry later

        # Verify partial sync
        assert synced_count + failed_count == 20
        assert synced_count > 0
        assert failed_count > 0
        assert len(db.all()) == synced_count
        db.close()
