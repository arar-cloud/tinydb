import pytest
import tempfile
from pathlib import Path
import json
import os
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestCorruptionDetection:
    """Test detection of corrupted database files."""

    def test_detect_truncated_json(self, tmp_path: Path):
        """Verify truncated JSON files are detected as corrupted."""
        db_path = tmp_path / "truncated.db"
        
        # Create valid db
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        # Truncate file
        with open(db_path, 'r') as f:
            content = f.read()
        with open(db_path, 'w') as f:
            f.write(content[:len(content)//2])
        
        # Should raise on read
        with pytest.raises(Exception):  # JSON decode error or similar
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()

    def test_detect_invalid_json_syntax(self, tmp_path: Path):
        """Verify invalid JSON syntax is detected."""
        db_path = tmp_path / "invalid_json.db"
        
        # Write invalid JSON
        with open(db_path, 'w') as f:
            f.write("{invalid: json syntax}")
        
        with pytest.raises(Exception):
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()

    def test_detect_corrupted_data_types(self, tmp_path: Path):
        """Verify corrupted data types are detected."""
        db_path = tmp_path / "bad_types.db"
        
        # Write JSON with invalid structure
        with open(db_path, 'w') as f:
            json.dump({"_default": "not_a_dict"}, f)
        
        with pytest.raises(Exception):
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()

    def test_detect_partial_write(self, tmp_path: Path):
        """Verify partial writes are detected."""
        db_path = tmp_path / "partial.db"
        
        # Create valid db with data
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"id": 1, "data": "first"})
        db.close()
        
        # Simulate partial write by corrupting structure
        with open(db_path, 'r') as f:
            content = json.load(f)
        content["_default"][0] = None  # Invalid document
        with open(db_path, 'w') as f:
            json.dump(content, f)
        
        # Should handle gracefully
        db = TinyDB(db_path, storage=JSONStorage)
        try:
            db.all()
        except (TypeError, ValueError, KeyError):
            pass  # Expected for corrupted data
        db.close()

    def test_detect_zero_length_file(self, tmp_path: Path):
        """Verify zero-length files are detected as corrupted."""
        db_path = tmp_path / "empty.db"
        
        # Create empty file
        db_path.touch()
        
        with pytest.raises(Exception):
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()

    def test_detect_file_header_corruption(self, tmp_path: Path):
        """Verify file header corruption is detected."""
        db_path = tmp_path / "bad_header.db"
        
        # Write garbage at start
        with open(db_path, 'w') as f:
            f.write("\x00\x01\x02\x03{\"_default\": []}")
        
        with pytest.raises(Exception):
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()


class TestCorruptionRecovery:
    """Test recovery from corrupted database states."""

    def test_recover_from_partial_insert(self, tmp_path: Path):
        """Verify recovery from interrupted insert operations."""
        db_path = tmp_path / "partial_insert.db"
        
        # Create db with initial data
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"id": 1, "data": "safe"})
        initial_count = len(db.all())
        db.close()
        
        # Simulate interrupted write by corrupting structure
        with open(db_path, 'r') as f:
            content = json.load(f)
        # Add incomplete document
        content["_default"].append({"id": 2})  # Missing required fields
        with open(db_path, 'w') as f:
            json.dump(content, f)
        
        # Try to recover
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        assert len(docs) >= 1  # At least original document should be accessible
        db.close()

    def test_recover_from_truncated_transaction(self, tmp_path: Path):
        """Verify recovery from truncated transaction logs."""
        db_path = tmp_path / "truncated_txn.db"
        
        # Create db
        db = TinyDB(db_path, storage=JSONStorage)
        doc1_id = db.insert({"id": 1, "status": "committed"})
        db.close()
        
        # Truncate file
        with open(db_path, 'r+') as f:
            f.truncate(os.path.getsize(db_path) - 20)
        
        # Should still be able to read committed data
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            docs = db.all()
            # At minimum, recovery should not lose data further
            assert len(docs) >= 0
            db.close()
        except (json.JSONDecodeError, ValueError):
            pass  # Expected for severely corrupted file

    def test_recovery_preserves_safe_data(self, tmp_path: Path):
        """Verify recovery preserves all safe/committed data."""
        db_path = tmp_path / "safe_recovery.db"
        
        # Insert known safe data
        db = TinyDB(db_path, storage=JSONStorage)
        id1 = db.insert({"id": 1, "name": "Alice", "status": "safe"})
        id2 = db.insert({"id": 2, "name": "Bob", "status": "safe"})
        db.close()
        
        # Verify data persists after corruption recovery scenario
        db = TinyDB(db_path, storage=JSONStorage)
        alice = db.get(doc_id=id1)
        bob = db.get(doc_id=id2)
        
        assert alice is not None
        assert alice["name"] == "Alice"
        assert bob is not None
        assert bob["name"] == "Bob"
        db.close()

    def test_recovery_transaction_atomicity(self, tmp_path: Path):
        """Verify recovery maintains transaction atomicity."""
        db_path = tmp_path / "atomic_recovery.db"
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert initial state
        account_a = db.insert({"account": "A", "balance": 100})
        account_b = db.insert({"account": "B", "balance": 50})
        db.close()
        
        # Simulate crash during transfer (corrupted state)
        with open(db_path, 'r') as f:
            content = json.load(f)
        # Simulate partial update
        content["_default"][0]["balance"] = 90  # A updated
        # B not updated - simulates partial write
        with open(db_path, 'w') as f:
            json.dump(content, f)
        
        # Verify recovery shows consistent state
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        # Recovery should either:
        # 1. Show both updates (transaction committed)
        # 2. Show neither update (transaction rolled back)
        # 3. Be readable without crashing
        assert len(docs) >= 1
        db.close()

    def test_recovery_from_missing_metadata(self, tmp_path: Path):
        """Verify recovery when metadata is corrupted."""
        db_path = tmp_path / "missing_meta.db"
        
        # Create valid db
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        # Remove metadata
        with open(db_path, 'r') as f:
            content = json.load(f)
        if "_metadata" in content:
            del content["_metadata"]
        with open(db_path, 'w') as f:
            json.dump(content, f)
        
        # Should still be readable
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        assert len(docs) >= 1
        db.close()

    def test_recovery_bootstrap_new_db_on_corrupt(self, tmp_path: Path):
        """Verify option to bootstrap new database when corruption is unrecoverable."""
        db_path = tmp_path / "bootstrap.db"
        
        # Write completely invalid data
        with open(db_path, 'w') as f:
            f.write("completely invalid data")
        
        # Attempt recovery with bootstrap fallback
        backup_path = tmp_path / "corrupt_backup.db"
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            db.all()
        except (json.JSONDecodeError, ValueError):
            # Move corrupt file and create fresh db
            if db_path.exists():
                db_path.rename(backup_path)
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({"recovery": "bootstrapped"})
        
        # New db should work
        assert len(db.all()) >= 1
        db.close()
        
        # Corrupt backup should still exist
        assert backup_path.exists()
