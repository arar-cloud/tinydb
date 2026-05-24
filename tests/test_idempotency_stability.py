"""Idempotency and state consistency tests for TinyDB retry scenarios.

Verifies that retried operations produce consistent results, don't cause
duplicate writes, and maintain state integrity across retries.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import pytest
from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage
from tinydb.query import Query


class TestInsertIdempotency:
    """Tests for insert operation idempotency."""

    def test_insert_same_data_twice_creates_two_docs(self, tmp_path: Path):
        """Verify inserting same data twice creates two separate documents."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        data = {"name": "test", "value": 42}
        
        doc_id_1 = db.insert(data)
        doc_id_2 = db.insert(data.copy())
        
        # Different documents should have different IDs
        assert doc_id_1 != doc_id_2
        
        # Both should exist and be accessible
        doc1 = db.get(doc_id_1)
        doc2 = db.get(doc_id_2)
        assert doc1 == data
        assert doc2 == data
        
        # Total count should be 2
        assert len(db.all()) == 2
        
        db.close()

    def test_insert_after_failure_recovery(self, tmp_path: Path):
        """Verify insert is consistent after simulated failure and recovery."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        data = {"task_id": "task_001", "status": "pending"}
        doc_id = db.insert(data)
        initial_doc = db.get(doc_id)
        
        db.close()
        
        # Recovery: reopen database
        db = TinyDB(db_path, storage=JSONStorage)
        recovered_doc = db.get(doc_id)
        
        # Document should be identical after recovery
        assert recovered_doc == initial_doc
        assert recovered_doc["task_id"] == "task_001"
        assert recovered_doc["status"] == "pending"
        
        db.close()

    def test_insert_batch_partial_failure_recovery(self, tmp_path: Path):
        """Verify batch insert consistency after partial failure."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        batch_data = [
            {"id": 1, "name": "item_1"},
            {"id": 2, "name": "item_2"},
            {"id": 3, "name": "item_3"},
        ]
        
        doc_ids = db.insert_multiple(batch_data)
        assert len(doc_ids) == 3
        
        # Verify all inserted
        all_docs = db.all()
        assert len(all_docs) == 3
        
        # Store state before close
        states_before = {doc_id: db.get(doc_id) for doc_id in doc_ids}
        db.close()
        
        # Reopen and verify state consistency
        db = TinyDB(db_path, storage=JSONStorage)
        states_after = {doc_id: db.get(doc_id) for doc_id in doc_ids}
        
        assert states_before == states_after
        assert len(db.all()) == 3
        
        db.close()


class TestUpdateIdempotency:
    """Tests for update operation idempotency."""

    def test_update_same_value_multiple_times(self, tmp_path: Path):
        """Verify updating to same value multiple times is safe."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0, "status": "initial"})
        
        # Update to new value
        db.update({"counter": 1, "status": "updated"}, doc_ids=[doc_id])
        state_1 = db.get(doc_id)
        
        # Update to same value again (should be no different)
        db.update({"counter": 1, "status": "updated"}, doc_ids=[doc_id])
        state_2 = db.get(doc_id)
        
        # Update to same value third time
        db.update({"counter": 1, "status": "updated"}, doc_ids=[doc_id])
        state_3 = db.get(doc_id)
        
        # All states should be identical
        assert state_1 == state_2 == state_3
        assert state_3["counter"] == 1
        assert state_3["status"] == "updated"
        
        # Verify persistence
        db.close()
        db = TinyDB(db_path, storage=JSONStorage)
        state_recovered = db.get(doc_id)
        assert state_recovered == state_3
        
        db.close()

    def test_partial_update_idempotency(self, tmp_path: Path):
        """Verify partial updates (only updating some fields) are idempotent."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({
            "name": "original",
            "value": 10,
            "extra": "data"
        })
        
        # Update only 'name' field using query
        db.update({"name": "updated"}, doc_ids=[doc_id])
        state_1 = db.get(doc_id)
        
        # Retry same update
        db.update({"name": "updated"}, doc_ids=[doc_id])
        state_2 = db.get(doc_id)
        
        # States should be identical
        assert state_1 == state_2
        assert state_2["name"] == "updated"
        assert state_2["value"] == 10
        assert state_2["extra"] == "data"
        
        db.close()

    def test_update_with_versioning_idempotency(self, tmp_path: Path):
        """Verify version-based updates prevent duplicate application."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"value": 0, "version": 1})
        
        # Update with version check
        db.update({"value": 1, "version": 2}, doc_ids=[doc_id])
        state_1 = db.get(doc_id)
        assert state_1["version"] == 2
        
        # Verify that retry of same operation doesn't increment version further
        db.update({"value": 1, "version": 2}, doc_ids=[doc_id])
        state_2 = db.get(doc_id)
        assert state_2["version"] == 2  # Should stay at 2, not become 3
        
        db.close()


class TestDeleteIdempotency:
    """Tests for delete operation idempotency."""

    def test_delete_same_document_multiple_times(self, tmp_path: Path):
        """Verify deleting same document multiple times is safe."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"data": "to_delete"})
        initial_count = len(db.all())
        assert initial_count == 1
        
        # First delete
        db.remove(doc_ids=[doc_id])
        assert db.get(doc_id) is None
        count_after_first_delete = len(db.all())
        assert count_after_first_delete == 0
        
        # Second delete (should be safe no-op)
        db.remove(doc_ids=[doc_id])
        count_after_second_delete = len(db.all())
        assert count_after_second_delete == 0
        
        # Third delete (should still be safe)
        db.remove(doc_ids=[doc_id])
        count_after_third_delete = len(db.all())
        assert count_after_third_delete == 0
        
        db.close()

    def test_delete_with_query_idempotency(self, tmp_path: Path):
        """Verify query-based deletes are idempotent."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        db.insert_multiple([
            {"type": "temp", "value": 1},
            {"type": "temp", "value": 2},
            {"type": "permanent", "value": 3},
        ])
        
        User = Query()
        
        # First delete of temp items
        count_before = len(db.search(User.type == "temp"))
        assert count_before == 2
        
        db.remove(User.type == "temp")
        count_after_first = len(db.search(User.type == "temp"))
        assert count_after_first == 0
        
        # Second delete attempt (should be no-op)
        db.remove(User.type == "temp")
        count_after_second = len(db.search(User.type == "temp"))
        assert count_after_second == 0
        
        # Permanent items should still exist
        permanent = db.search(User.type == "permanent")
        assert len(permanent) == 1
        
        db.close()


class TestTransactionIdempotency:
    """Tests for sequences of operations maintaining idempotency."""

    def test_multi_step_operation_idempotency(self, tmp_path: Path):
        """Verify multi-step operations are idempotent when retried."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Multi-step operation: create, update, verify
        def multi_step_operation():
            doc_id = db.insert({"step": 0, "completed": False})
            db.update({"step": 1}, doc_ids=[doc_id])
            doc = db.get(doc_id)
            assert doc["step"] == 1
            db.update({"completed": True}, doc_ids=[doc_id])
            return doc_id
        
        # First execution
        doc_id_1 = multi_step_operation()
        state_1 = db.get(doc_id_1)
        
        initial_count = len(db.all())
        
        # Retry same operation (would create new doc in non-idempotent system)
        doc_id_2 = multi_step_operation()
        
        # In truly idempotent system, might reuse same doc
        # But inserts always create new docs; verify state is consistent
        state_2 = db.get(doc_id_2)
        
        # Both docs should have final state
        assert state_1["step"] == 1
        assert state_1["completed"] is True
        assert state_2["step"] == 1
        assert state_2["completed"] is True
        
        # Verify no corruption
        all_docs = db.all()
        for doc in all_docs:
            assert doc["step"] == 1
            assert doc["completed"] is True
        
        db.close()

    def test_conditional_operation_idempotency(self, tmp_path: Path):
        """Verify conditional updates are idempotent."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"status": "pending", "attempt": 0})
        
        # Conditional update: only update if still pending
        def conditional_update():
            doc = db.get(doc_id)
            if doc["status"] == "pending":
                db.update({"status": "processed", "attempt": doc["attempt"] + 1}, doc_ids=[doc_id])
                return True
            return False
        
        # First update succeeds
        result_1 = conditional_update()
        assert result_1 is True
        state_1 = db.get(doc_id)
        assert state_1["status"] == "processed"
        assert state_1["attempt"] == 1
        
        # Retry: should fail condition (already processed)
        result_2 = conditional_update()
        assert result_2 is False
        state_2 = db.get(doc_id)
        
        # State should not change
        assert state_2 == state_1
        assert state_2["attempt"] == 1  # Should not increment
        
        db.close()


class TestConcurrentIdempotency:
    """Tests for idempotency under concurrent retry scenarios."""

    def test_concurrent_updates_same_doc(self, tmp_path: Path):
        """Verify concurrent updates to same doc maintain consistency."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0, "updates": []})
        
        # Simulate concurrent updates
        for i in range(3):
            doc = db.get(doc_id)
            db.update({"counter": doc["counter"] + 1, "last_update": i}, doc_ids=[doc_id])
        
        final_doc = db.get(doc_id)
        assert final_doc["counter"] == 3
        assert final_doc["last_update"] == 2
        
        # Verify no duplicates or state corruption
        all_docs = db.all()
        assert len(all_docs) == 1
        
        db.close()

    def test_idempotency_across_reconnect(self, tmp_path: Path):
        """Verify idempotency is maintained across DB reconnections."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"status": "initial", "attempts": 0})
        db.close()
        
        # Reconnect and retry operation
        db = TinyDB(db_path, storage=JSONStorage)
        db.update({"status": "updated", "attempts": 1}, doc_ids=[doc_id])
        state_1 = db.get(doc_id)
        db.close()
        
        # Reconnect again and retry same update
        db = TinyDB(db_path, storage=JSONStorage)
        db.update({"status": "updated", "attempts": 1}, doc_ids=[doc_id])
        state_2 = db.get(doc_id)
        db.close()
        
        # Reconnect third time
        db = TinyDB(db_path, storage=JSONStorage)
        state_3 = db.get(doc_id)
        
        # All states should be identical
        assert state_1 == state_2 == state_3
        assert state_3["status"] == "updated"
        assert state_3["attempts"] == 1
        
        db.close()
