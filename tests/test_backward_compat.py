import pytest
import tempfile
from pathlib import Path
import json
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestBackwardCompatibility:
    """Test compatibility with older database formats."""

    def test_open_legacy_format_v1(self, tmp_path: Path):
        """Verify ability to open database in legacy format v1."""
        db_path = tmp_path / "legacy_v1.db"
        
        # Create legacy format (simplified structure)
        legacy_data = {
            "_default": [
                {"id": 1, "name": "Alice", "age": 30},
                {"id": 2, "name": "Bob", "age": 25}
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(legacy_data, f)
        
        # Should be able to open
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert len(docs) == 2
        assert docs[0]["name"] == "Alice"
        assert docs[1]["name"] == "Bob"
        
        db.close()

    def test_open_legacy_format_without_metadata(self, tmp_path: Path):
        """Verify opening database missing metadata fields."""
        db_path = tmp_path / "no_metadata.db"
        
        # Create data without metadata
        legacy_data = {
            "_default": [
                {"id": 1, "data": "test"},
                {"id": 2, "data": "example"}
            ]
            # Note: no _metadata field
        }
        
        with open(db_path, 'w') as f:
            json.dump(legacy_data, f)
        
        # Should open without error
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert len(docs) == 2
        db.close()

    def test_open_database_from_version_3(self, tmp_path: Path):
        """Verify opening database from version 3.x."""
        db_path = tmp_path / "version_3.db"
        
        # Simulate v3 format
        v3_data = {
            "_default": [
                {"_id": 1, "content": "v3 data 1"},
                {"_id": 2, "content": "v3 data 2"},
                {"_id": 3, "content": "v3 data 3"}
            ],
            "_version": "3.0.0"
        }
        
        with open(db_path, 'w') as f:
            json.dump(v3_data, f)
        
        # Should be readable
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert len(docs) >= 1
        db.close()

    def test_preserve_unknown_fields_on_open(self, tmp_path: Path):
        """Verify unknown fields are preserved when opening old database."""
        db_path = tmp_path / "unknown_fields.db"
        
        # Data with unknown fields
        data = {
            "_default": [
                {
                    "id": 1,
                    "name": "Test",
                    "unknown_field_v2": "should_preserve",
                    "another_custom_field": 12345
                }
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(data, f)
        
        db = TinyDB(db_path, storage=JSONStorage)
        doc = db.get(doc_id=1)
        
        # Unknown fields should still be accessible
        assert doc.get("unknown_field_v2") == "should_preserve"
        assert doc.get("another_custom_field") == 12345
        
        db.close()


class TestSchemaMigration:
    """Test schema migration and version upgrades."""

    def test_add_field_migration(self, tmp_path: Path):
        """Verify migration when adding new fields."""
        db_path = tmp_path / "migrate_add_field.db"
        
        # Original data
        original = {
            "_default": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(original, f)
        
        # Open and add field
        db = TinyDB(db_path, storage=JSONStorage)
        
        for doc in db.all():
            db.update({"email": f"{doc['name'].lower()}@example.com"}, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify migration
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert all("email" in doc for doc in docs)
        assert docs[0]["email"] == "alice@example.com"
        assert docs[1]["email"] == "bob@example.com"
        
        db.close()

    def test_rename_field_migration(self, tmp_path: Path):
        """Verify migration when renaming fields."""
        db_path = tmp_path / "migrate_rename.db"
        
        # Original data with old field name
        original = {
            "_default": [
                {"id": 1, "user_name": "Alice"},
                {"id": 2, "user_name": "Bob"}
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(original, f)
        
        # Migrate: rename user_name to name
        db = TinyDB(db_path, storage=JSONStorage)
        
        for doc in db.all():
            if "user_name" in doc:
                db.update({"name": doc["user_name"]}, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert all("name" in doc for doc in docs)
        assert docs[0]["name"] == "Alice"
        
        db.close()

    def test_transform_data_types_migration(self, tmp_path: Path):
        """Verify migration when transforming data types."""
        db_path = tmp_path / "migrate_types.db"
        
        # Original data with string numbers
        original = {
            "_default": [
                {"id": 1, "count": "10"},
                {"id": 2, "count": "20"}
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(original, f)
        
        # Migrate: convert string counts to integers
        db = TinyDB(db_path, storage=JSONStorage)
        
        for doc in db.all():
            db.update({"count": int(doc["count"])}, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert all(isinstance(doc["count"], int) for doc in docs)
        assert docs[0]["count"] == 10
        assert docs[1]["count"] == 20
        
        db.close()

    def test_remove_deprecated_field_migration(self, tmp_path: Path):
        """Verify migration when removing deprecated fields."""
        db_path = tmp_path / "migrate_remove.db"
        
        # Data with deprecated field
        original = {
            "_default": [
                {"id": 1, "name": "Alice", "deprecated_field": "old_value"},
                {"id": 2, "name": "Bob", "deprecated_field": "old_value"}
            ]
        }
        
        with open(db_path, 'w') as f:
            json.dump(original, f)
        
        # Migrate: remove deprecated field
        db = TinyDB(db_path, storage=JSONStorage)
        
        for doc in db.all():
            doc_dict = dict(doc)
            if "deprecated_field" in doc_dict:
                del doc_dict["deprecated_field"]
            db.update(doc_dict, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify
        db = TinyDB(db_path, storage=JSONStorage)
        docs = db.all()
        
        assert all("deprecated_field" not in doc for doc in docs)
        
        db.close()

    def test_migration_preserves_data_integrity(self, tmp_path: Path):
        """Verify migration doesn't lose data."""
        db_path = tmp_path / "migrate_integrity.db"
        
        # Original data
        original_docs = [
            {"id": 1, "name": "Alice", "score": 100},
            {"id": 2, "name": "Bob", "score": 95},
            {"id": 3, "name": "Charlie", "score": 88}
        ]
        
        original = {"_default": original_docs}
        
        with open(db_path, 'w') as f:
            json.dump(original, f)
        
        # Complex migration
        db = TinyDB(db_path, storage=JSONStorage)
        initial_count = len(db.all())
        
        for doc in db.all():
            db.update({
                "grade": "A" if doc["score"] >= 90 else "B",
                "active": True
            }, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify integrity
        db = TinyDB(db_path, storage=JSONStorage)
        final_count = len(db.all())
        
        assert final_count == initial_count
        assert all("name" in doc for doc in db.all())
        assert all("score" in doc for doc in db.all())
        assert all("grade" in doc for doc in db.all())
        
        db.close()

    def test_migration_with_multiple_tables(self, tmp_path: Path):
        """Verify migration works across multiple tables."""
        db_path = tmp_path / "migrate_tables.db"
        
        # Create database with multiple tables
        db = TinyDB(db_path, storage=JSONStorage)
        
        users_table = db.table("users")
        users_table.insert({"id": 1, "name": "Alice"})
        
        settings_table = db.table("settings")
        settings_table.insert({"key": "theme", "value": "dark"})
        
        db.close()
        
        # Migrate both tables
        db = TinyDB(db_path, storage=JSONStorage)
        
        for doc in db.table("users").all():
            db.table("users").update({"migrated": True}, doc_ids=[doc.doc_id])
        
        for doc in db.table("settings").all():
            db.table("settings").update({"migrated": True}, doc_ids=[doc.doc_id])
        
        db.close()
        
        # Verify
        db = TinyDB(db_path, storage=JSONStorage)
        
        assert all("migrated" in doc for doc in db.table("users").all())
        assert all("migrated" in doc for doc in db.table("settings").all())
        
        db.close()
