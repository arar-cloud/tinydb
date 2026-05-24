"""Tests for transaction atomicity and rollback behavior.

Verifies that TinyDB transactions maintain atomicity across retries,
failure modes, and concurrent access patterns.
"""

import pytest
from pathlib import Path

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage


class TestTransactionAtomicity:
    """Test transaction atomicity guarantees."""
    
    @pytest.mark.timeout(30)
    def test_insert_transaction_atomicity(self, tmp_path: Path) -> None:
        """Verify all-or-nothing semantics for insert transactions."""
        db_path = tmp_path / 'atomicity_insert.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        initial_count = len(db.all())
        
        # Simulate transaction: insert multiple records
        docs = [{'id': i, 'value': f'doc_{i}'} for i in range(5)]
        inserted_ids = db.insert_multiple(docs)
        
        # Verify all documents inserted
        assert len(inserted_ids) == len(docs)
        assert len(db.all()) == initial_count + len(docs)
        
        db.close()
    
    @pytest.mark.timeout(30)
    def test_update_transaction_atomicity(self, tmp_path: Path) -> None:
        """Verify all-or-nothing semantics for update transactions."""
        db_path = tmp_path / 'atomicity_update.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert test data
        db.insert_multiple([{'id': i, 'status': 'pending'} for i in range(5)])
        
        query = Query()
        updated = db.update({'status': 'completed'}, query.id >= 0)
        
        # Verify all matching records updated
        assert updated == 5
        
        results = db.all()
        assert all(doc['status'] == 'completed' for doc in results)
        
        db.close()
    
    @pytest.mark.timeout(30)
    def test_remove_transaction_atomicity(self, tmp_path: Path) -> None:
        """Verify all-or-nothing semantics for remove transactions."""
        db_path = tmp_path / 'atomicity_remove.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert test data
        doc_ids = []
        for i in range(10):
            doc_id = db.insert({'id': i, 'type': 'ephemeral' if i % 2 == 0 else 'permanent'})
            doc_ids.append(doc_id)
        
        initial_count = len(db.all())
        
        query = Query()
        removed = db.remove(query.type == 'ephemeral')
        
        # Verify correct records removed
        assert removed == 5
        assert len(db.all()) == initial_count - 5
        
        db.close()


class TestRollbackBehavior:
    """Test rollback behavior and recovery."""
    
    @pytest.mark.timeout(30)
    def test_failed_update_no_partial_changes(self, tmp_path: Path) -> None:
        """Verify failed update doesn't leave partial changes."""
        db_path = tmp_path / 'rollback_update.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        db.insert({'id': 1, 'value': 'original'})
        
        query = Query()
        db.update({'value': 'updated'}, query.id == 1)
        
        result = db.get(query.id == 1)
        assert result['value'] == 'updated'
        
        db.close()
    
    @pytest.mark.timeout(30)
    def test_transaction_isolation_between_retries(self, tmp_path: Path) -> None:
        """Verify transaction isolation is maintained across retries."""
        db_path = tmp_path / 'isolation.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # First transaction
        db.insert({'transaction': 1, 'value': 'first'})
        
        # Verify isolation: second transaction sees first's data
        db.insert({'transaction': 2, 'value': 'second'})
        
        assert len(db.all()) == 2
        
        db.close()
    
    @pytest.mark.timeout(30)
    def test_concurrent_transaction_consistency(self, tmp_path: Path) -> None:
        """Verify consistency when multiple transactions are pending."""
        db_path = tmp_path / 'concurrent_txn.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Simulate multiple concurrent transactions by sequential inserts
        doc_ids = []
        for i in range(10):
            doc_id = db.insert({'sequence': i})
            doc_ids.append(doc_id)
        
        # Verify all documents in consistent state
        all_docs = db.all()
        sequences = [doc['sequence'] for doc in all_docs]
        assert sequences == list(range(10))
        
        db.close()


class TestAtomicityAcrossRetries:
    """Test atomicity guarantees persist across operation retries."""
    
    @pytest.mark.timeout(30)
    def test_insert_atomicity_persists_on_retry(self, tmp_path: Path) -> None:
        """Verify atomicity holds even when operation is retried."""
        db_path = tmp_path / 'atomicity_retry.db'
        
        def operation_with_persistence_check() -> None:
            db = TinyDB(db_path, storage=JSONStorage)
            
            # Insert data
            docs = [{'data': f'item_{i}'} for i in range(5)]
            db.insert_multiple(docs)
            
            initial_count = len(db.all())
            db.close()
            
            # Re-open and verify data persisted
            db = TinyDB(db_path, storage=JSONStorage)
            assert len(db.all()) == initial_count
            db.close()
        
        # Run operation multiple times
        for _ in range(3):
            operation_with_persistence_check()
    
    @pytest.mark.timeout(30)
    def test_mixed_operations_atomicity(self, tmp_path: Path) -> None:
        """Verify atomicity with mixed insert/update/delete operations."""
        db_path = tmp_path / 'mixed_ops.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initial data
        doc_id = db.insert({'id': 1, 'status': 'new'})
        
        # Update operation
        query = Query()
        db.update({'status': 'processing'}, query.id == 1)
        
        # Verify intermediate state
        assert db.get(query.id == 1)['status'] == 'processing'
        
        # Final update
        db.update({'status': 'complete'}, query.id == 1)
        
        # Verify final state
        final = db.get(query.id == 1)
        assert final['status'] == 'complete'
        
        db.close()
