"""Foundation test cases for TinyDB active failure reproduction and debugging.

These tests are designed to:
1. Reproduce active failures on master branch
2. Verify backend and mobile stack stability
3. Test cross-platform compatibility
4. Capture root cause conditions for debugging
"""

import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage


class TestTinyDBBasicOperations:
    """Basic operations tests marked for regression and failure tracking."""

    @pytest.mark.regression
    def test_insert_and_retrieve(self, db):
        """Test basic insert and retrieve operations."""
        doc_id = db.insert({"name": "test", "value": 42})
        assert doc_id > 0
        doc = db.get(doc_id=doc_id)
        assert doc is not None
        assert doc["name"] == "test"
        assert doc["value"] == 42

    @pytest.mark.regression
    def test_update_operations(self, db):
        """Test document update operations."""
        db.truncate()
        doc_id = db.insert({"count": 1, "status": "pending"})
        db.update({"status": "completed"}, doc_ids=[doc_id])
        doc = db.get(doc_id=doc_id)
        assert doc["status"] == "completed"

    @pytest.mark.regression
    def test_query_operations(self, db):
        """Test query operations across records."""
        results = db.search(lambda x: x["int"] == 1)
        assert len(results) >= 1

    @pytest.mark.backend
    def test_memory_storage_backend(self):
        """Test backend memory storage layer."""
        db = TinyDB(storage=MemoryStorage)
        db.insert({"type": "backend", "value": "test"})
        doc = db.get(doc_id=1)
        assert doc["type"] == "backend"

    @pytest.mark.mobile
    def test_mobile_compatibility(self, db):
        """Test mobile stack compatibility."""
        # Mobile operations often have stricter resource constraints
        db.insert({"mobile": True, "data": "x" * 100})
        docs = db.all()
        assert len(docs) > 0

    @pytest.mark.python
    def test_python_version_compatibility(self):
        """Test Python version-specific code paths."""
        db = TinyDB(storage=MemoryStorage)
        # Test type hints and modern Python features
        result = db.insert({"python_compat": True})
        assert isinstance(result, int)
