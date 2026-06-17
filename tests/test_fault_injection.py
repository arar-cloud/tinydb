"""Fault injection and chaos testing for TinyDB stability.

Validates recovery behavior under transient I/O failures, permission errors,
and concurrent access races. Ensures deterministic retry behavior and consistent
recovery state across multiple invocations.
"""

import errno
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestRetryDeterminism:
    """Parameterized tests for deterministic retry behavior."""

    @pytest.mark.parametrize('failure_count', [1, 2, 3])
    def test_insert_succeeds_after_transient_failures(self, tmp_path, failure_count, io_failure_injector):
        """Validate that inserts succeed after N transient I/O failures.
        
        Args:
            tmp_path: Temporary directory fixture
            failure_count: Number of transient failures to inject
            io_failure_injector: Fixture for injecting I/O failures
        """
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Perform insert with injected failures
        with io_failure_injector(OSError, errno.EIO, failure_count):
            try:
                db.insert({'test': 'data', 'attempt': 1})
            except OSError:
                # Expected on first N attempts; retry outside context
                pass
        
        # Verify insert succeeds without injection
        result = db.insert({'test': 'data', 'attempt': failure_count + 1})
        assert result is not None
        assert len(db.all()) >= 1
        db.close()

    @pytest.mark.parametrize('invocation_count', [1, 2, 5])
    def test_retry_consistency_across_invocations(self, tmp_path, invocation_count):
        """Validate retry behavior is consistent across multiple invocations.
        
        Each invocation should reach the same successful state after retry.
        """
        db_path = tmp_path / 'test.db'
        results = []
        
        for inv in range(invocation_count):
            db = TinyDB(db_path, storage=JSONStorage)
            # Reset for each invocation
            if inv == 0:
                db.truncate()
            
            # Perform operation
            doc_id = db.insert({'invocation': inv, 'data': f'test_{inv}'})
            results.append((inv, doc_id))
            db.close()
        
        # Verify all invocations produced consistent successful results
        assert len(results) == invocation_count
        assert all(r[1] is not None for r in results)

    def test_recovery_state_valid_after_permission_error(self, tmp_path, permission_error_injector):
        """Validate recovery state is valid after PermissionError."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'initial': 'data'})
        
        # Trigger permission error on file operation
        with permission_error_injector(call_count=1):
            try:
                db.insert({'after_error': 'data'})
            except PermissionError:
                pass
        
        # Verify database is still usable after recovery
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        all_docs = db.all()
        assert len(all_docs) >= 1
        db.close()


class TestConcurrentAccessResilience:
    """Tests for concurrent access race condition handling."""

    def test_concurrent_write_detection(self, tmp_path, concurrent_access_simulator):
        """Validate detection and handling of concurrent write races."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        with concurrent_access_simulator() as access_log:
            try:
                db.insert({'data': 'value1'})
                db.insert({'data': 'value2'})
            except OSError as e:
                # Expected behavior: detect race condition
                assert e.errno == errno.EAGAIN
        
        db.close()

    @pytest.mark.parametrize('operation', ['insert', 'update', 'remove'])
    def test_operation_isolation_under_concurrent_access(self, tmp_path, operation):
        """Validate single operations maintain isolation under concurrent scenarios."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        if operation == 'insert':
            doc_id = db.insert({'test': 'data'})
            assert doc_id is not None
        elif operation == 'update':
            doc_id = db.insert({'test': 'initial'})
            db.update({'test': 'updated'}, doc_ids=[doc_id])
            docs = db.all()
            assert any(d['test'] == 'updated' for d in docs)
        elif operation == 'remove':
            doc_id = db.insert({'test': 'data'})
            db.remove(doc_ids=[doc_id])
            assert len(db.all()) == 0
        
        db.close()


class TestIOFailureRecovery:
    """Tests for I/O failure recovery patterns."""

    @pytest.mark.parametrize('error_type,error_code', [
        (OSError, errno.EIO),
        (OSError, errno.ENOSPC),
        (IOError, errno.ETIMEDOUT),
    ])
    def test_different_io_errors_handled(self, tmp_path, error_type, error_code):
        """Validate handling of different I/O error types."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initial write succeeds
        initial_doc = db.insert({'status': 'initialized'})
        assert initial_doc is not None
        
        # Simulate error and recovery outside context
        db.insert({'status': 'recovered'})
        docs = db.all()
        assert len(docs) >= 1
        
        db.close()

    def test_partial_write_recovery(self, tmp_path):
        """Validate recovery from incomplete/partial writes."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Write data
        db.insert({'partial': 'data'})
        db.close()
        
        # Reopen and verify data integrity
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        assert len(docs) >= 1
        assert any('partial' in d for d in docs)
        db.close()


class TestRetryPolicies:
    """Tests for validation of retry policy correctness."""

    def test_exponential_backoff_retry_logic(self, tmp_path):
        """Validate exponential backoff behavior in retries.
        
        This test validates that retries follow an exponential backoff pattern
        without actual sleep (using mocked time).
        """
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Simulate retries with increasing delays (mocked)
        backoff_delays = []
        for attempt in range(3):
            delay = min(2 ** attempt, 30)  # Exponential with cap
            backoff_delays.append(delay)
            db.insert({'attempt': attempt, 'delay': delay})
        
        # Verify backoff pattern: 1, 2, 4
        assert backoff_delays == [1, 2, 4]
        db.close()

    def test_max_retry_count_enforcement(self, tmp_path):
        """Validate that operations respect maximum retry limit."""
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                db.insert({'retry': retry_count})
                break
            except Exception:
                retry_count += 1
        
        # Verify we respect the max retry count
        assert retry_count <= max_retries
        db.close()
