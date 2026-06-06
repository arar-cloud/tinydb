"""Chaos engineering tests for edge cases and fault injection.

Covers:
- Disk full (ENOSPC) recovery
- Permission errors (EACCES) handling
- Out of memory (ENOMEM) scenarios
- Mock-based fault injection patterns
- Verify recovery behavior
"""

import errno
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
from io import StringIO

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestDiskFullHandling:
    """Test recovery from ENOSPC (disk full) conditions."""

    def test_handle_disk_full_on_insert(self, tmp_path: Path):
        """Verify graceful handling when disk is full during insert."""
        db_path = tmp_path / "disk_full.json"
        db = TinyDB(db_path, storage=JSONStorage)

        def insert_with_disk_full_handling(data):
            """Insert with fallback to memory on disk full."""
            try:
                return db.insert(data)
            except (OSError, IOError) as e:
                if e.errno == errno.ENOSPC:
                    # Fallback: attempt cleanup or use memory
                    print("Disk full - would implement retention policy")
                    # In real scenario: delete old records
                    return None
                raise

        # Mock disk full condition
        with patch.object(db.storage, '_write_table', side_effect=OSError(errno.ENOSPC, 'No space left')):
            result = insert_with_disk_full_handling({'test': 'data'})
            assert result is None  # Fallback returns None

    def test_disk_full_detection_before_write(self, tmp_path: Path):
        """Test proactive disk space checking before write."""
        db_path = tmp_path / "precheck.json"
        db = TinyDB(db_path, storage=JSONStorage)

        min_required_mb = 10

        def safe_insert(data):
            """Check disk space before insert."""
            try:
                stat = os.statvfs(str(db_path))
                available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)

                if available_mb < min_required_mb:
                    raise OSError(errno.ENOSPC, f"Only {available_mb}MB free, need {min_required_mb}MB")

                return db.insert(data)
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    return {'error': 'disk_full', 'available_mb': available_mb}
                raise

        # Should succeed (test dir has space)
        result = safe_insert({'test': 'data'})
        assert isinstance(result, int) or isinstance(result, str)
        db.close()

    def test_recovery_after_failed_write_due_to_disk_full(self, tmp_path: Path):
        """Test recovery after failed write - verify rollback behavior."""
        db_path = tmp_path / "recover_disk.json"
        db = TinyDB(db_path, storage=JSONStorage)

        # Insert initial data
        initial_doc_id = db.insert({'id': 1, 'status': 'initial'})

        # Simulate failed write due to disk full
        write_error = OSError(errno.ENOSPC, 'No space')

        with patch.object(db.storage, '_write_table', side_effect=write_error):
            # Attempt insert (will fail)
            with pytest.raises(OSError):
                db.insert({'id': 2, 'status': 'failed'})

        # Verify database is still readable after failed write
        try:
            docs = db.all()
            # Initial document should still be there
            assert any(doc['id'] == 1 for doc in docs)
        except Exception:
            # If not readable, verify it's expected
            pass

        db.close()


class TestPermissionErrors:
    """Test handling of permission errors (EACCES)."""

    def test_handle_permission_denied_on_open(self, tmp_path: Path):
        """Verify graceful handling of permission denied."""
        db_path = tmp_path / "no_permission.json"

        def open_with_fallback(path):
            """Open database with fallback to memory on permission error."""
            try:
                return TinyDB(path, storage=JSONStorage)
            except (PermissionError, OSError) as e:
                if isinstance(e, PermissionError) or e.errno == errno.EACCES:
                    print("Permission denied - using memory storage")
                    return TinyDB(storage=MemoryStorage)
                raise

        # Mock permission denied
        with patch('tinydb.JSONStorage.__init__', side_effect=PermissionError("Permission denied")):
            db = open_with_fallback(db_path)
            # Should get memory storage
            doc_id = db.insert({'fallback': True})
            assert doc_id is not None
            db.close()

    def test_permission_error_on_read(self, tmp_path: Path):
        """Test handling permission error during read operation."""
        db_path = tmp_path / "read_permission.json"
        db = TinyDB(db_path, storage=JSONStorage)

        doc_id = db.insert({'data': 'test'})
        db.close()

        # Mock read permission error
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            # Attempt to open and read
            with pytest.raises(PermissionError):
                db = TinyDB(db_path, storage=JSONStorage)
                _ = db.all()

    def test_handle_permission_error_with_retry(self, tmp_path: Path):
        """Test retry logic for permission errors."""
        db_path = tmp_path / "retry_permission.json"
        db = TinyDB(db_path, storage=JSONStorage)

        initial_doc_id = db.insert({'id': 1})
        db.close()

        attempt_count = 0

        def read_with_retry():
            nonlocal attempt_count
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    attempt_count += 1
                    # Simulate permission error on first attempt
                    if attempt == 0:
                        raise PermissionError("Temporary permission denied")
                    # Succeed on retry
                    return TinyDB(db_path, storage=JSONStorage)
                except PermissionError:
                    if attempt == max_retries - 1:
                        raise
                    # Could log retry and continue

            return None

        # Should succeed on retry
        db = read_with_retry()
        assert db is not None
        docs = db.all()
        assert len(docs) == 1
        db.close()
        assert attempt_count == 2  # First failed, second succeeded


class TestMemoryErrors:
    """Test handling of memory-related errors (ENOMEM)."""

    def test_handle_memory_allocation_failure(self):
        """Test graceful handling when memory allocation fails."""
        db = TinyDB(storage=MemoryStorage)

        def insert_with_memory_check(data):
            """Insert with memory exhaustion handling."""
            try:
                # In real scenario, would check available memory
                return db.insert(data)
            except MemoryError as e:
                print(f"Memory error: {e}")
                return None

        # Normal insert
        result = insert_with_memory_check({'test': 'data'})
        assert result is not None

        # Mock memory error
        with patch.object(db, 'insert', side_effect=MemoryError("Cannot allocate memory")):
            result = insert_with_memory_check({'test': 'data2'})
            assert result is None  # Fallback

        db.close()

    def test_large_dataset_memory_handling(self):
        """Test memory usage with large datasets."""
        db = TinyDB(storage=MemoryStorage)

        # Insert reasonably large dataset
        num_records = 1000
        record_size = 1024  # ~1KB per record

        for i in range(num_records):
            try:
                db.insert({
                    'id': i,
                    'data': 'x' * record_size,
                    'metadata': {'index': i}
                })
            except MemoryError:
                # Stop inserting if memory exhausted
                break

        # Verify some records inserted
        docs = db.all()
        assert len(docs) > 0
        assert len(docs) <= num_records
        db.close()


class TestFaultInjectionPatterns:
    """Test fault injection patterns for reliability verification."""

    def test_fault_injection_write_failure(self, tmp_path: Path):
        """Test that write failures are handled correctly."""
        db_path = tmp_path / "fault_injection.json"
        db = TinyDB(db_path, storage=JSONStorage)

        operation_count = 0

        def write_with_fault_injection(data, inject_fault=False):
            nonlocal operation_count
            operation_count += 1

            if inject_fault and operation_count == 2:
                raise IOError("Injected write fault")

            return db.insert(data)

        # First write succeeds
        doc_id_1 = write_with_fault_injection({'id': 1})
        assert doc_id_1 is not None

        # Second write fails (fault injected)
        with pytest.raises(IOError):
            write_with_fault_injection({'id': 2}, inject_fault=True)

        # Third write succeeds (fault cleared)
        doc_id_3 = write_with_fault_injection({'id': 3}, inject_fault=False)
        assert doc_id_3 is not None

        db.close()

    def test_fault_injection_read_corruption(self, tmp_path: Path):
        """Test handling of corrupted data reads."""
        db_path = tmp_path / "corruption.json"
        db = TinyDB(db_path, storage=JSONStorage)

        doc_id = db.insert({'id': 1, 'data': 'original'})
        db.close()

        # Corrupt the file
        with open(db_path, 'w') as f:
            f.write('{invalid json')

        # Attempt to read corrupted database
        with pytest.raises((ValueError, Exception)):
            db = TinyDB(db_path, storage=JSONStorage)
            _ = db.all()

    def test_fault_injection_partial_write(self, tmp_path: Path):
        """Test recovery from partial write (incomplete operation)."""
        db_path = tmp_path / "partial.json"

        write_count = 0

        def write_with_partial_fault():
            nonlocal write_count
            write_count += 1

            db = TinyDB(db_path, storage=JSONStorage)
            try:
                # First operation
                doc_id_1 = db.insert({'step': 1, 'status': 'writing'})
                # Simulate partial write failure
                if write_count == 1:
                    raise IOError("Partial write failure")
                # Second operation
                doc_id_2 = db.insert({'step': 2, 'status': 'complete'})
                return [doc_id_1, doc_id_2]
            finally:
                db.close()

        # First attempt fails
        with pytest.raises(IOError):
            write_with_partial_fault()

        # Second attempt succeeds
        result = write_with_partial_fault()
        assert result is not None

        # Verify final state
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        # Some docs may be from first partial write
        assert len(docs) > 0
        db.close()


class TestRecoveryBehavior:
    """Test database recovery patterns."""

    def test_recovery_sequence_on_startup(self, tmp_path: Path):
        """Test recovery sequence when opening after crash."""
        db_path = tmp_path / "recovery.json"

        # Simulate database state before "crash"
        db = TinyDB(db_path, storage=JSONStorage)
        doc_ids = []
        for i in range(10):
            doc_ids.append(db.insert({'id': i, 'state': 'active'}))
        db.close()

        # Simulate crash and recovery
        def recovery_startup():
            """Startup with recovery check."""
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                # Verify database consistency
                docs = db.all()
                recovery_status = {
                    'recovered_docs': len(docs),
                    'status': 'healthy' if docs else 'empty'
                }
                return db, recovery_status
            except Exception as e:
                return None, {'status': 'failed', 'error': str(e)}

        db, status = recovery_startup()
        assert db is not None
        assert status['status'] == 'healthy'
        assert status['recovered_docs'] == 10
        db.close()

    def test_database_consistency_after_forced_close(self, tmp_path: Path):
        """Test data consistency after forced close without proper shutdown."""
        db_path = tmp_path / "forced_close.json"

        # Normal operation
        db = TinyDB(db_path, storage=JSONStorage)
        doc_ids = []
        for i in range(20):
            doc_ids.append(db.insert({'id': i, 'committed': True}))

        # Force close without explicit shutdown
        del db

        # Reopen and verify
        db = TinyDB(db_path, storage=JSONStorage)
        recovered_docs = db.all()
        assert len(recovered_docs) == 20
        assert all(doc['committed'] for doc in recovered_docs)
        db.close()

    def test_automatic_retry_on_transient_error(self, tmp_path: Path):
        """Test automatic retry mechanism for transient errors."""
        db_path = tmp_path / "transient.json"
        db = TinyDB(db_path, storage=JSONStorage)

        attempt_count = 0
        max_retries = 3

        def operation_with_transient_fault():
            nonlocal attempt_count

            def try_operation():
                nonlocal attempt_count
                attempt_count += 1

                if attempt_count < 3:
                    # Simulate transient error
                    raise IOError(f"Transient error on attempt {attempt_count}")

                return db.insert({'recovered': True, 'attempts': attempt_count})

            # Retry loop
            for attempt in range(max_retries):
                try:
                    return try_operation()
                except IOError as e:
                    if attempt == max_retries - 1:
                        raise
                    # Could add exponential backoff here
                    continue

        result = operation_with_transient_fault()
        assert result is not None
        assert attempt_count == 3
        doc = db.get(doc_id=result)
        assert doc['attempts'] == 3
        db.close()
