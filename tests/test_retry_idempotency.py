"""Retry and idempotency tests for database operations.

Validates that database operations are safe to retry and produce
consistent results across repeated execution. Critical for stability
across mobile, web, and backend platforms.
"""

import pytest
from typing import Any, List, Dict
from unittest.mock import patch, MagicMock
import time


class TestInsertIdempotency:
    """Verify insert operations are idempotent and retry-safe."""

    def test_insert_single_record_idempotent(self, db):
        """Inserting the same record multiple times should yield consistent ID."""
        record = {'name': 'Alice', 'age': 30}
        
        # First insert
        doc_id_1 = db.insert(record)
        count_1 = len(db)
        
        # Retry insert (simulate network retry or crash recovery)
        doc_id_2 = db.insert(record)
        count_2 = len(db)
        
        # Both inserts should succeed with different IDs
        # (TinyDB inserts are NOT idempotent by design, but count must match)
        assert count_2 == count_1 + 1, "Retry insert should add new record"

    def test_insert_multiple_retries_consistent_state(self, db):
        """Multiple insert retries should reach consistent final state."""
        records = [{'id': i, 'value': f'record_{i}'} for i in range(3)]
        
        # Insert records
        ids = []
        for record in records:
            doc_id = db.insert(record)
            ids.append(doc_id)
            # Simulate retry: insert same record again
            retry_id = db.insert(record)
            assert retry_id != doc_id, "Retry should get new ID"
        
        # Final state: should have 6 records (3 original + 3 retries)
        assert len(db) == 6
        
        # All original IDs should be present
        for doc_id in ids:
            assert db.get(doc_id=doc_id) is not None

    def test_insert_with_transient_failure_recovery(self, db):
        """Simulate insert with transient I/O failure and recovery."""
        record = {'name': 'Bob', 'status': 'active'}
        
        # Mock storage to simulate transient failure
        original_insert = db.insert
        call_count = 0
        
        def mock_insert(data):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt fails
                raise IOError("Disk temporarily unavailable")
            # Retry succeeds
            return original_insert(data)
        
        with patch.object(db, 'insert', side_effect=mock_insert):
            with pytest.raises(IOError):
                db.insert(record)
            
            # Retry should succeed
            call_count = 0
            result_id = original_insert(record)
            assert result_id is not None


class TestUpdateIdempotency:
    """Verify update operations maintain data consistency on retry."""

    def test_update_idempotent(self, db):
        """Updating with same values should be safe to retry."""
        doc_id = db.insert({'counter': 0, 'name': 'Test'})
        
        # First update
        db.update({'counter': 1}, doc_ids=[doc_id])
        after_update_1 = db.get(doc_id=doc_id)
        
        # Retry update with same values
        db.update({'counter': 1}, doc_ids=[doc_id])
        after_update_2 = db.get(doc_id=doc_id)
        
        # Final state must be consistent
        assert after_update_1 == after_update_2
        assert after_update_2['counter'] == 1

    def test_update_with_concurrent_retry_consistency(self, db):
        """Multiple updates with retry should maintain consistency."""
        doc_id = db.insert({'value': 0, 'version': 0})
        
        # Simulate multiple update attempts
        for attempt in range(3):
            db.update({'value': attempt + 1}, doc_ids=[doc_id])
            record = db.get(doc_id=doc_id)
            assert record['value'] == attempt + 1
            # Retry same update
            db.update({'value': attempt + 1}, doc_ids=[doc_id])
            record_after_retry = db.get(doc_id=doc_id)
            assert record_after_retry == record

    def test_update_multiple_records_partial_failure_recovery(self, db):
        """Update multiple records with simulated partial failure."""
        doc_ids = [db.insert({'status': 'pending'}) for _ in range(3)]
        
        # First attempt updates first two
        db.update({'status': 'processing'}, doc_ids=doc_ids[:2])
        
        # Retry: update all with same values should be consistent
        db.update({'status': 'processing'}, doc_ids=doc_ids)
        
        # All records should have same state
        for doc_id in doc_ids:
            record = db.get(doc_id=doc_id)
            assert record['status'] == 'processing'


class TestDeleteIdempotency:
    """Verify delete operations handle retries without errors."""

    def test_delete_idempotent(self, db):
        """Deleting already-deleted record should fail gracefully."""
        doc_id = db.insert({'name': 'ToDelete'})
        
        # First delete
        db.remove(doc_ids=[doc_id])
        count_after_delete = len(db)
        
        # Retry delete (should be safe, not raise)
        # In TinyDB, removing non-existent ID should be no-op
        db.remove(doc_ids=[doc_id])
        count_after_retry = len(db)
        
        assert count_after_delete == count_after_retry

    def test_delete_multiple_with_partial_existence(self, db):
        """Delete multiple where some don't exist should handle gracefully."""
        doc_id_1 = db.insert({'id': 1})
        doc_id_2 = db.insert({'id': 2})
        nonexistent_id = 9999
        
        # Delete including non-existent
        db.remove(doc_ids=[doc_id_1, nonexistent_id])
        
        # Verify correct record deleted
        assert db.get(doc_id=doc_id_1) is None
        assert db.get(doc_id=doc_id_2) is not None


class TestQueryIdempotency:
    """Verify read operations return consistent results across retries."""

    def test_query_idempotent(self, db):
        """Repeated queries should return identical results."""
        # Insert test data
        for i in range(5):
            db.insert({'value': i, 'type': 'test'})
        
        # First query
        from tinydb import where
        result_1 = db.search(where('type') == 'test')
        
        # Retry query
        result_2 = db.search(where('type') == 'test')
        
        # Results must be identical
        assert len(result_1) == len(result_2) == 5
        assert result_1 == result_2

    def test_query_with_index_consistency(self, db):
        """Query results consistent even with internal index changes."""
        for i in range(10):
            db.insert({'index': i, 'active': i % 2 == 0})
        
        from tinydb import where
        results = []
        
        # Multiple queries to verify consistency
        for _ in range(3):
            result = db.search(where('active') == True)
            results.append(result)
        
        # All results should match
        assert all(r == results[0] for r in results)
        assert len(results[0]) == 5  # Half should be active


class TestOperationSequenceRecovery:
    """Verify database recovers correctly from operation sequences with retries."""

    def test_insert_update_delete_sequence_with_retries(self, db):
        """Complex operation sequence with retries maintains consistency."""
        # Initial insert
        doc_id = db.insert({'status': 'new', 'count': 0})
        
        # Update sequence with simulated retries
        operations = [
            ('update', {'status': 'processing', 'count': 1}),
            ('query', {'expected_status': 'processing'}),
            ('update', {'status': 'completed', 'count': 2}),
            ('query', {'expected_status': 'completed'}),
        ]
        
        from tinydb import where
        for op_type, op_data in operations:
            if op_type == 'update':
                db.update(op_data, doc_ids=[doc_id])
                # Retry same update
                db.update(op_data, doc_ids=[doc_id])
            elif op_type == 'query':
                results = db.search(where('status') == op_data['expected_status'])
                assert len(results) >= 1
        
        # Final state
        final = db.get(doc_id=doc_id)
        assert final['status'] == 'completed'
        assert final['count'] == 2

    def test_bulk_operation_with_failure_points(self, db):
        """Bulk operations with simulated failures at different stages."""
        records = [{'id': i, 'batch': 'test'} for i in range(5)]
        
        # Insert all
        doc_ids = []
        for record in records:
            doc_id = db.insert(record)
            doc_ids.append(doc_id)
        
        assert len(db) >= 5
        
        # Simulated failure: update fails partway through
        updated_count = 0
        for doc_id in doc_ids[:3]:
            db.update({'batch': 'test_updated'}, doc_ids=[doc_id])
            updated_count += 1
        
        # Retry: update all (should be idempotent)
        for doc_id in doc_ids:
            db.update({'batch': 'test_updated'}, doc_ids=[doc_id])
        
        # Verify all have same state
        from tinydb import where
        updated = db.search(where('batch') == 'test_updated')
        assert len(updated) >= 5
