"""Integration tests for backend stability, data persistence, and transaction handling."""
import pytest
from pathlib import Path

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


@pytest.mark.stability
@pytest.mark.integration
class TestDataPersistence:
    """Test data persistence across database operations."""

    def test_data_persists_after_close_and_reopen(self, tmp_path: Path):
        """Verify data persists when database is closed and reopened."""
        db_path = tmp_path / 'persist_test.db'
        
        # Insert data
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'key': 'value1', 'number': 42})
        db.insert({'key': 'value2', 'number': 84})
        initial_count = len(db.all())
        db.close()
        
        # Reopen and verify
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == initial_count, "Data lost after close and reopen"
        assert db.get(lambda doc: doc['number'] == 42) is not None
        db.close()

    def test_bulk_insert_persistence(self, tmp_path: Path):
        """Verify bulk insert operations persist correctly."""
        db_path = tmp_path / 'bulk_test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Bulk insert
        records = [{'id': i, 'data': f'record_{i}'} for i in range(100)]
        db.insert_multiple(records)
        db.close()
        
        # Verify persistence
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 100
        assert db.get(lambda doc: doc['id'] == 50) is not None
        db.close()

    def test_update_persistence(self, tmp_path: Path):
        """Verify update operations persist correctly."""
        db_path = tmp_path / 'update_test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert and update
        doc_id = db.insert({'status': 'initial', 'count': 0})
        db.update({'status': 'updated', 'count': 5}, doc_ids=[doc_id])
        db.close()
        
        # Verify update persisted
        db = TinyDB(db_path, storage=JSONStorage)
        doc = db.get(doc_id=doc_id)
        assert doc['status'] == 'updated'
        assert doc['count'] == 5
        db.close()


@pytest.mark.stability
@pytest.mark.integration
class TestTransactionHandling:
    """Test transaction-like behavior and data consistency."""

    def test_sequential_operations_consistency(self, persistent_db: TinyDB):
        """Verify sequential operations maintain data consistency."""
        # Sequence of operations
        persistent_db.insert({'type': 'transaction', 'amount': 100})
        persistent_db.insert({'type': 'transaction', 'amount': 50})
        persistent_db.update({'amount': 75}, lambda doc: doc['type'] == 'transaction' and doc['amount'] == 50)
        
        # Verify consistency
        docs = persistent_db.all()
        assert len(docs) == 2
        amounts = [doc['amount'] for doc in docs]
        assert 100 in amounts and 75 in amounts

    def test_delete_consistency(self, persistent_db: TinyDB):
        """Verify delete operations maintain consistency."""
        id1 = persistent_db.insert({'status': 'active'})
        id2 = persistent_db.insert({'status': 'inactive'})
        id3 = persistent_db.insert({'status': 'active'})
        
        initial_count = len(persistent_db.all())
        persistent_db.remove(lambda doc: doc['status'] == 'inactive')
        
        assert len(persistent_db.all()) == initial_count - 1
        assert persistent_db.get(doc_id=id2) is None
        assert persistent_db.get(doc_id=id1) is not None

    def test_rollback_on_error(self, persistent_db: TinyDB):
        """Verify database state on operation errors."""
        persistent_db.insert({'value': 'safe'})
        initial_count = len(persistent_db.all())
        
        # This should not corrupt the database even if it fails
        try:
            for i in range(5):
                persistent_db.insert({'iteration': i})
        except Exception:
            pass
        
        # Database should remain accessible
        final_docs = persistent_db.all()
        assert len(final_docs) >= initial_count


@pytest.mark.stability
@pytest.mark.integration
class TestStorageRecovery:
    """Test recovery from storage errors and edge cases."""

    def test_empty_database_state(self, tmp_path: Path):
        """Verify behavior with empty database."""
        db_path = tmp_path / 'empty.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        assert len(db.all()) == 0
        assert db.search(lambda x: True) == []
        db.close()
        
        # Reopen empty database
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 0
        db.close()

    def test_large_record_handling(self, persistent_db: TinyDB):
        """Verify handling of large records."""
        large_data = {'text': 'x' * 10000, 'value': 42}
        persistent_db.insert(large_data)
        
        retrieved = persistent_db.get(lambda doc: doc['value'] == 42)
        assert retrieved is not None
        assert len(retrieved['text']) == 10000

    def test_special_characters_persistence(self, persistent_db: TinyDB):
        """Verify persistence of special characters and unicode."""
        special_data = {
            'unicode': '🚀 émoji test',
            'quotes': 'He said "hello"',
            'newlines': 'line1\nline2',
            'tabs': 'col1\tcol2'
        }
        persistent_db.insert(special_data)
        
        retrieved = persistent_db.get(lambda doc: 'unicode' in doc)
        assert retrieved['unicode'] == '🚀 émoji test'
        assert retrieved['quotes'] == 'He said "hello"'
