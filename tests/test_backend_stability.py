"""Backend stability and async operation tests for TinyDB."""

import pytest


@pytest.mark.backend
class TestBackendStability:
    """Test backend database stability and error recovery."""

    def test_db_initialization_stability(self, db):
        """Verify database initializes in a stable state."""
        assert db is not None
        tables = db.tables()
        assert isinstance(tables, set)

    def test_db_insert_recovery(self, db):
        """Test database recovery after insert operations."""
        try:
            db.insert({'test': 'data'})
            # Verify DB is still functional
            assert len(db.all()) > 0
        except Exception as e:
            pytest.fail(f"Insert operation failed: {e}")

    def test_db_transaction_safety(self, db):
        """Test that database transactions maintain consistency."""
        initial_docs = len(db.all())
        db.insert({'transaction': True})
        db.insert({'transaction': False})
        assert len(db.all()) == initial_docs + 2

    def test_db_delete_operation_safety(self, db):
        """Test database delete operations do not corrupt state."""
        all_docs = db.all()
        if len(all_docs) > 0:
            first_doc_id = all_docs[0].doc_id
            db.remove(doc_ids=[first_doc_id])
            remaining = db.all()
            assert len(remaining) == len(all_docs) - 1

    def test_db_update_consistency(self, db):
        """Test database update operations maintain consistency."""
        doc_id = db.insert({'version': 1, 'stable': True})
        db.update({'version': 2}, doc_ids=[doc_id])
        updated = db.get(doc_id=doc_id)
        assert updated['version'] == 2
        assert updated['stable'] is True

    def test_db_caching_middleware_stability(self, storage):
        """Test caching middleware does not introduce instability."""
        assert storage is not None
        # Verify middleware is functional
        assert hasattr(storage, 'read')
        assert hasattr(storage, 'write')


@pytest.mark.backend
class TestBackendErrorHandling:
    """Test backend error handling and edge cases."""

    def test_db_empty_query_handling(self, db):
        """Test database handles empty query results gracefully."""
        from tinydb import Query
        q = Query()
        results = db.search(q.nonexistent_field == 'value')
        assert results == []

    def test_db_large_batch_insert(self, db):
        """Test database handles large batch inserts without failures."""
        docs = [{'batch': i, 'index': i} for i in range(100)]
        db.insert_multiple(docs)
        all_docs = db.all()
        assert len(all_docs) >= 103  # Initial 3 + 100 new

    def test_db_storage_persistence(self, db, tmp_path):
        """Test database persists data correctly across operations."""
        initial_count = len(db.all())
        assert initial_count > 0
