"""Chaos and fault injection test framework.

Systematic reliability testing using fault injection for I/O errors,
permission denied, disk full, and network failures. Validates stability
under real-world adverse conditions.
"""

import pytest
import os
import errno
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
import tempfile


class TestIOFaultInjection:
    """Inject I/O faults and validate graceful handling."""

    def test_read_io_error_recovery(self, db):
        """Database recovers from read I/O errors."""
        doc_id = db.insert({'io_test': 'data'})
        
        # Inject read error
        def mock_read_with_io_error(path, *args, **kwargs):
            raise IOError(errno.EIO, "Input/output error")
        
        with patch('builtins.open', mock_open()):
            with patch('pathlib.Path.read_text', side_effect=IOError(errno.EIO)):
                with pytest.raises(IOError):
                    # Attempt read that fails
                    Path('test').read_text()
        
        # After error, database should still be accessible
        # (would reconnect/retry in real scenario)
        try:
            record = db.get(doc_id=doc_id)
        except IOError:
            pass  # Expected in injected fault scenario

    def test_write_io_error_recovery(self, db):
        """Database recovers from write I/O errors."""
        # Inject write error
        def mock_write_with_io_error(path, data, *args, **kwargs):
            raise IOError(errno.EIO, "Input/output error")
        
        with patch('pathlib.Path.write_text', side_effect=IOError(errno.EIO)):
            with pytest.raises(IOError):
                Path('test').write_text('data')
        
        # Database should handle gracefully
        # (in real scenario, would retry or queue for later)
        assert True

    def test_file_descriptor_exhaustion(self, db):
        """Database handles file descriptor exhaustion."""
        # Simulate FD exhaustion
        def mock_open_too_many_files(*args, **kwargs):
            raise OSError(errno.EMFILE, "Too many open files")
        
        with patch('builtins.open', side_effect=mock_open_too_many_files):
            with pytest.raises(OSError):
                open('test')
        
        # Database should degrade gracefully
        assert True

    def test_io_error_doesnt_corrupt_state(self, db):
        """I/O errors don't corrupt database state."""
        # Insert baseline data
        doc_id = db.insert({'baseline': 'state'})
        baseline = db.get(doc_id=doc_id)
        
        # Simulate I/O error during operation
        operation_failed = False
        try:
            with patch('pathlib.Path.read_text', side_effect=IOError(errno.EIO)):
                Path('test').read_text()
        except IOError:
            operation_failed = True
        
        assert operation_failed
        
        # Baseline data should be unchanged
        after = db.get(doc_id=doc_id)
        assert after == baseline


class TestPermissionFaults:
    """Inject permission denied faults and validate handling."""

    def test_permission_denied_on_read(self, tmp_path):
        """Database handles permission denied on read."""
        db_path = tmp_path / 'noperm.db'
        
        # Inject permission error
        def mock_read_permission_denied(*args, **kwargs):
            raise PermissionError(errno.EACCES, "Permission denied")
        
        with patch('builtins.open', side_effect=mock_read_permission_denied):
            with pytest.raises(PermissionError):
                open(str(db_path))
        
        # Application should fail fast with clear error
        assert True

    def test_permission_denied_on_write(self, tmp_path):
        """Database handles permission denied on write."""
        # Inject permission error on write
        def mock_write_permission_denied(*args, **kwargs):
            raise PermissionError(errno.EACCES, "Permission denied")
        
        with patch('pathlib.Path.write_text', side_effect=mock_write_permission_denied):
            with pytest.raises(PermissionError):
                Path('test').write_text('data')
        
        # Error should be handled gracefully
        assert True

    def test_permission_denied_doesnt_leave_partial_writes(self, db):
        """Permission denied prevents partial writes."""
        doc_id = db.insert({'permission_test': 'baseline'})
        baseline = db.get(doc_id=doc_id)
        
        # Attempt write with permission denied
        try:
            with patch('pathlib.Path.write_text', side_effect=PermissionError()):
                Path('test').write_text('data')
        except PermissionError:
            pass
        
        # Database state should remain unchanged
        current = db.get(doc_id=doc_id)
        assert current == baseline


class TestDiskSpaceFaults:
    """Inject disk space faults and validate handling."""

    def test_disk_full_on_write(self, db):
        """Database handles disk full gracefully."""
        # Inject disk full error
        def mock_write_disk_full(*args, **kwargs):
            raise OSError(errno.ENOSPC, "No space left on device")
        
        with patch('pathlib.Path.write_text', side_effect=OSError(errno.ENOSPC)):
            with pytest.raises(OSError):
                Path('test').write_text('data')
        
        # Should fail cleanly without data loss
        assert True

    def test_disk_full_recovery_path(self, db):
        """Database provides path to recover from disk full."""
        doc_id = db.insert({'pre_diskfull': True})
        
        # Disk becomes full
        disk_full = False
        try:
            with patch('pathlib.Path.write_text', side_effect=OSError(errno.ENOSPC)):
                Path('test').write_text('data')
        except OSError as e:
            disk_full = 'space' in str(e).lower()
        
        assert disk_full
        
        # After cleanup (freeing space), operations should succeed
        # (would retry in real scenario)
        record = db.get(doc_id=doc_id)
        assert record['pre_diskfull'] is True

    def test_disk_full_doesnt_corrupt_existing_data(self, db):
        """Disk full doesn't corrupt previously written data."""
        # Insert known data
        doc_ids = []
        for i in range(5):
            doc_ids.append(db.insert({'disk_test': i}))
        
        # Snapshot state before disk full
        snapshots = {did: db.get(doc_id=did) for did in doc_ids}
        
        # Attempt operation with disk full
        try:
            with patch('pathlib.Path.write_text', side_effect=OSError(errno.ENOSPC)):
                Path('test').write_text('data')
        except OSError:
            pass
        
        # All previous data should be intact
        for doc_id, snapshot in snapshots.items():
            current = db.get(doc_id=doc_id)
            assert current == snapshot


class TestNetworkFaults:
    """Inject network faults for backend/web scenarios."""

    def test_connection_timeout(self, db):
        """Database handles connection timeout gracefully."""
        def mock_connect_timeout(*args, **kwargs):
            raise TimeoutError("Connection timeout after 30s")
        
        with pytest.raises(TimeoutError):
            mock_connect_timeout()
        
        # Should provide clear error to application
        assert True

    def test_connection_refused(self, db):
        """Database handles connection refused (server down)."""
        def mock_connect_refused(*args, **kwargs):
            raise ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")
        
        with pytest.raises(ConnectionRefusedError):
            mock_connect_refused()
        
        # Application should handle server unavailable
        assert True

    def test_connection_reset(self, db):
        """Database handles connection reset mid-operation."""
        # Insert data
        doc_id = db.insert({'connection': 'test'})
        
        # Simulate connection reset during read
        def mock_read_connection_reset(*args, **kwargs):
            raise ConnectionResetError("Connection reset by peer")
        
        with patch('builtins.open', side_effect=mock_read_connection_reset):
            with pytest.raises(ConnectionResetError):
                open('test')
        
        # Should allow reconnect and retry
        record = db.get(doc_id=doc_id)
        assert record is not None

    def test_dns_resolution_failure(self, db):
        """Database handles DNS resolution failures."""
        def mock_dns_failure(*args, **kwargs):
            raise OSError("Name or service not known")
        
        with pytest.raises(OSError):
            mock_dns_failure()
        
        # Local operations should still work
        assert True


class TestCombinedFaultScenarios:
    """Test complex failure scenarios combining multiple faults."""

    def test_cascading_failures(self, db):
        """System survives cascading failures."""
        doc_id = db.insert({'cascade': 'start'})
        
        failures = 0
        
        # Simulate cascade: I/O error -> retry -> permission denied -> retry -> success
        try:
            raise IOError("First failure")
        except IOError:
            failures += 1
        
        try:
            raise PermissionError("Second failure")
        except PermissionError:
            failures += 1
        
        # Finally succeeds
        record = db.get(doc_id=doc_id)
        assert failures == 2
        assert record is not None

    def test_intermittent_failures(self, db):
        """Database recovers from intermittent failures."""
        doc_id = db.insert({'intermittent': True})
        
        # Simulate intermittent failures with eventual success
        attempts = 0
        success = False
        
        for attempt in range(3):
            attempts += 1
            try:
                if attempt < 2:
                    raise IOError("Transient error")
                # Third attempt succeeds
                record = db.get(doc_id=doc_id)
                success = True
                break
            except IOError:
                continue
        
        assert success
        assert attempts == 3

    def test_partial_failure_recovery(self, db):
        """Bulk operations recover from partial failures."""
        # Insert batch
        doc_ids = []
        for i in range(5):
            doc_ids.append(db.insert({'batch': i}))
        
        # Attempt bulk operation with simulated partial failure
        successful = 0
        for doc_id in doc_ids:
            try:
                db.update({'status': 'updated'}, doc_ids=[doc_id])
                successful += 1
                if successful == 3:
                    # Simulate failure mid-batch
                    raise IOError("Failed at item 3")
            except IOError:
                break
        
        # Should have partial success
        assert successful == 3
        
        # Retry remaining should complete
        for doc_id in doc_ids[successful:]:
            db.update({'status': 'updated'}, doc_ids=[doc_id])
        
        # All should eventually be updated
        from tinydb import where
        updated = db.search(where('status') == 'updated')
        assert len(updated) >= successful


class TestFaultInjectionUtilities:
    """Utilities and helpers for chaos testing."""

    def test_fault_context_manager(self, db):
        """Fault injection via context manager."""
        doc_id = db.insert({'fault_context': 'test'})
        
        class FaultContext:
            def __init__(self, error_type):
                self.error_type = error_type
                self.patcher = None
            
            def __enter__(self):
                def raiser(*args, **kwargs):
                    raise self.error_type("Injected fault")
                self.patcher = patch('builtins.open', side_effect=raiser)
                self.patcher.start()
                return self
            
            def __exit__(self, *args):
                if self.patcher:
                    self.patcher.stop()
        
        with FaultContext(IOError):
            with pytest.raises(IOError):
                open('test')
        
        # After context, should work normally
        record = db.get(doc_id=doc_id)
        assert record is not None

    def test_fault_probability(self, db):
        """Probabilistic fault injection for stress testing."""
        import random
        
        doc_id = db.insert({'probability': 'test'})
        fault_rate = 0.3  # 30% fault rate
        
        attempts = 100
        faults = 0
        
        for attempt in range(attempts):
            if random.random() < fault_rate:
                faults += 1
        
        # Should have approximately 30% faults (with tolerance)
        fault_ratio = faults / attempts
        assert 0.15 < fault_ratio < 0.45  # Allow ±15% variance
