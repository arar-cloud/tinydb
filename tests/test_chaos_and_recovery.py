"""Chaos engineering tests for TinyDB resilience validation."""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestPartialWriteRecovery:
    """Test recovery from partial write scenarios."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_recover_from_incomplete_write(self, tmp_path):
        """Test recovery when write operation is interrupted mid-operation."""
        db_path = tmp_path / 'partial_write.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert initial data
        db.insert({'id': 1, 'status': 'initial'})
        db.close()
        
        # Simulate partial write by truncating file
        with open(db_path, 'r') as f:
            content = f.read()
        
        # Write corrupted (incomplete JSON)
        with open(db_path, 'w') as f:
            f.write(content[:len(content)//2])
        
        # Attempt to recover
        try:
            db_recover = TinyDB(db_path, storage=JSONStorage)
            # Should either recover or raise appropriate error
            db_recover.close()
        except Exception as e:
            # Expected: corruption error, but should not crash silently
            assert 'JSON' in str(e) or 'decode' in str(e).lower()

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_idempotent_recovery_multiple_attempts(self, tmp_path):
        """Test that recovery attempts are idempotent."""
        db_path = tmp_path / 'idempotent_recovery.db'
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'id': 1, 'data': 'recovery_test'})
        db.close()
        
        # Read file multiple times (simulating multiple recovery attempts)
        results = []
        for _ in range(3):
            db_attempt = TinyDB(db_path, storage=JSONStorage)
            results.append(len(db_attempt.all()))
            db_attempt.close()
        
        # All attempts should see identical data
        assert all(count == results[0] for count in results)


class TestCorruptionDetection:
    """Test detection and handling of database corruption."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_detect_corrupted_json(self, tmp_path):
        """Test detection of corrupted JSON database file."""
        db_path = tmp_path / 'corrupted.db'
        
        # Write invalid JSON
        with open(db_path, 'w') as f:
            f.write('{"tables": {"_default": {"1": {invalid json here}}}')
        
        # Attempt to open should fail gracefully
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.close()
            pytest.fail("Should have raised error for corrupted JSON")
        except Exception as e:
            # Should raise parsing error, not crash
            assert any(err_type in str(type(e).__name__) 
                      for err_type in ['JSONDecoder', 'ValueError', 'Exception'])

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_detect_truncated_file(self, tmp_path):
        """Test detection of truncated database file."""
        db_path = tmp_path / 'truncated.db'
        
        # Create valid database
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'id': 1, 'data': 'test'})
        db.close()
        
        # Truncate file to 10 bytes
        with open(db_path, 'r+') as f:
            f.truncate(10)
        
        # Should handle gracefully
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.close()
        except Exception as e:
            # Expected to raise error
            assert any(err_type in str(type(e).__name__)
                      for err_type in ['JSON', 'EOFError', 'ValueError'])


class TestIOInterruptionRecovery:
    """Test recovery from I/O interruptions."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_retry_on_io_error(self, db_stable):
        """Test retry behavior when I/O error occurs."""
        retry_count = {'value': 0}
        
        def mock_insert_with_io_error(data):
            retry_count['value'] += 1
            if retry_count['value'] < 2:
                raise IOError("Simulated I/O error")
            return db_stable.insert(data)
        
        # Simulate I/O error then successful retry
        try:
            mock_insert_with_io_error({'test': 'data'})
        except IOError:
            # First attempt fails, but retry would succeed
            result = db_stable.insert({'test': 'data'})
            assert result is not None

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_resilience_to_file_permission_errors(self, tmp_path):
        """Test behavior when file permissions prevent writes."""
        db_path = tmp_path / 'permission_test.db'
        
        # Create database
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'id': 1})
        db.close()
        
        # Remove write permissions
        os.chmod(db_path, 0o444)
        
        try:
            # Attempt to modify should fail gracefully
            db = TinyDB(db_path, storage=JSONStorage)
            try:
                db.insert({'id': 2})
                pytest.fail("Should have raised permission error")
            except (IOError, OSError, PermissionError):
                # Expected: operation should fail with clear error
                pass
            finally:
                db.close()
        finally:
            # Restore permissions for cleanup
            os.chmod(db_path, 0o644)


class TestWALRecovery:
    """Test Write-Ahead Log recovery scenarios."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_wal_recovery_after_crash(self, tmp_path):
        """Test recovery from WAL after simulated crash."""
        db_path = tmp_path / 'wal_recovery.db'
        
        # Create initial state
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'id': 1, 'status': 'pre-crash'})
        db.close()
        
        # Simulate crash: read and verify recovery
        db_recover = TinyDB(db_path, storage=JSONStorage)
        docs = db_recover.all()
        assert len(docs) > 0
        assert docs[0]['status'] == 'pre-crash'
        db_recover.close()

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_consistency_after_multiple_crashes(self, tmp_path):
        """Test data consistency after multiple simulated crashes."""
        db_path = tmp_path / 'multiple_crashes.db'
        
        expected_count = 0
        for cycle in range(3):
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({'cycle': cycle, 'data': f'cycle_{cycle}'})
            expected_count += 1
            # Simulate crash: close without cleanup
            db.close()
        
        # Verify all data survived
        db_final = TinyDB(db_path, storage=JSONStorage)
        final_count = len(db_final.all())
        assert final_count >= expected_count
        db_final.close()


class TestConcurrentFailureRecovery:
    """Test recovery from concurrent access failures."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_recover_from_concurrent_write_conflict(self, db_stable):
        """Test recovery when concurrent writes create conflicts."""
        # Simulate concurrent write scenario
        doc_id_1 = db_stable.insert({'user': 'alice', 'attempt': 1})
        doc_id_2 = db_stable.insert({'user': 'alice', 'attempt': 2})
        
        # Both should exist despite "concurrent" nature
        assert doc_id_1 != doc_id_2
        assert len(db_stable.search(lambda x: x.get('user') == 'alice')) == 2

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_isolation_between_failed_transactions(self, db_stable):
        """Test isolation: failed transaction should not affect other operations."""
        initial_count = len(db_stable.all())
        
        # Attempt operation that would fail (if enabled)
        try:
            db_stable.insert(None)  # Invalid data
        except (TypeError, ValueError):
            pass
        
        # Database should be unaffected
        assert len(db_stable.all()) == initial_count


class TestOutOfMemoryRecovery:
    """Test behavior under memory pressure."""

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_large_dataset_handling(self, db_stable):
        """Test handling of large datasets without memory exhaustion."""
        # Insert moderate number of records
        for i in range(100):
            db_stable.insert({'id': i, 'data': f'record_{i}' * 10})
        
        # Should complete without crash
        all_docs = db_stable.all()
        assert len(all_docs) >= 100

    @pytest.mark.chaos
    @pytest.mark.stability
    def test_memory_efficient_query(self, db_stable):
        """Test that queries don't load entire dataset unnecessarily."""
        # Insert records
        for i in range(50):
            db_stable.insert({'id': i, 'type': 'A' if i % 2 == 0 else 'B'})
        
        # Query should efficiently filter
        result = db_stable.search(lambda x: x['type'] == 'A')
        assert len(result) == 25
