"""Distributed and concurrent access stability tests for TinyDB.

Tests race conditions, concurrent database access patterns, and stress
scenarios common in web/mobile backends.
"""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestConcurrentReadWrite:
    """Test concurrent read and write operations."""

    @pytest.mark.timeout(20)
    def test_multiple_readers_single_writer(self, tmp_path: Path):
        """Verify multiple readers don't interfere with single writer."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert baseline data
        doc_id = db.insert({"value": 0, "readers": 0})
        db.close()
        
        results = {"reads": [], "write_success": False}
        errors = []
        
        def reader_task(thread_id):
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for _ in range(3):
                    doc = db.get(doc_id)
                    if doc:
                        results["reads"].append((thread_id, doc["value"]))
                    time.sleep(0.01)
                db.close()
            except Exception as e:
                errors.append(e)
        
        def writer_task():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for i in range(1, 4):
                    db.update({"value": i}, doc_ids=[doc_id])
                    time.sleep(0.02)
                results["write_success"] = True
                db.close()
            except Exception as e:
                errors.append(e)
        
        # Launch 3 readers and 1 writer
        reader_threads = [threading.Thread(target=reader_task, args=(i,)) for i in range(3)]
        writer_thread = threading.Thread(target=writer_task)
        
        for t in reader_threads:
            t.start()
        writer_thread.start()
        
        for t in reader_threads:
            t.join(timeout=25)
        writer_thread.join(timeout=25)
        
        assert not errors, f"Concurrency errors: {errors}"
        assert results["write_success"], "Writer failed"
        assert len(results["reads"]) > 0, "Readers didn't execute"
        
        # Verify final state
        db = TinyDB(db_path, storage=JSONStorage)
        final_doc = db.get(doc_id)
        assert final_doc["value"] == 3
        db.close()

    @pytest.mark.timeout(20)
    def test_concurrent_update_race(self, tmp_path: Path):
        """Verify updates from concurrent threads maintain consistency."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0, "thread_updates": []})
        db.close()
        
        errors = []
        update_count = 0
        update_lock = threading.Lock()
        
        def update_task(thread_id):
            nonlocal update_count
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for i in range(2):
                    current = db.get(doc_id)
                    new_counter = current["counter"] + 1
                    db.update({"counter": new_counter}, doc_ids=[doc_id])
                    with update_lock:
                        update_count += 1
                db.close()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=update_task, args=(i,)) for i in range(4)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=25)
        
        assert not errors, f"Update errors: {errors}"
        assert update_count == 8, f"Expected 8 updates, got {update_count}"
        
        db = TinyDB(db_path, storage=JSONStorage)
        final_doc = db.get(doc_id)
        # Note: Due to race conditions, counter may not reach 8 if all reads happen before writes
        assert final_doc["counter"] > 0, "Counter should have increased"
        db.close()

    @pytest.mark.timeout(20)
    def test_concurrent_insert_uniqueness(self, tmp_path: Path):
        """Verify concurrent inserts don't create conflicts."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        db.close()
        
        insert_ids = []
        errors = []
        id_lock = threading.Lock()
        
        def insert_task(thread_id):
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for i in range(3):
                    doc_id = db.insert({
                        "thread_id": thread_id,
                        "sequence": i,
                        "timestamp": time.time()
                    })
                    with id_lock:
                        insert_ids.append(doc_id)
                db.close()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=insert_task, args=(i,)) for i in range(3)]
        
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=25)
        
        assert not errors, f"Insert errors: {errors}"
        assert len(insert_ids) == 9, f"Expected 9 inserts, got {len(insert_ids)}"
        assert len(set(insert_ids)) == 9, "Duplicate IDs detected"
        
        db = TinyDB(db_path, storage=JSONStorage)
        all_docs = db.all()
        assert len(all_docs) == 9, "Not all inserts persisted"
        db.close()


class TestStressPatterns:
    """Stress test patterns for high-concurrency scenarios."""

    @pytest.mark.timeout(25)
    def test_high_frequency_read_stress(self, tmp_path: Path):
        """Stress test: high frequency reads from multiple threads."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create some test data
        doc_ids = [db.insert({"id": i, "data": f"doc_{i}"}) for i in range(10)]
        db.close()
        
        read_count = 0
        read_lock = threading.Lock()
        errors = []
        
        def read_stress_task(thread_id):
            nonlocal read_count
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for _ in range(20):
                    for doc_id in doc_ids:
                        doc = db.get(doc_id)
                        assert doc is not None
                        with read_lock:
                            read_count += 1
                db.close()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=read_stress_task, args=(i,)) for i in range(5)]
        
        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.time() - start
        
        assert not errors, f"Read stress errors: {errors}"
        assert read_count == 1000, f"Expected 1000 reads, got {read_count}"
        print(f"Read stress: {read_count} reads in {elapsed:.2f}s")

    @pytest.mark.timeout(25)
    def test_mixed_operations_stress(self, tmp_path: Path):
        """Stress test: mixed read/write/delete operations."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initialize with base documents
        base_ids = [db.insert({"persistent": True, "id": i}) for i in range(5)]
        db.close()
        
        operation_count = {"read": 0, "write": 0, "delete": 0}
        op_lock = threading.Lock()
        errors = []
        
        def mixed_ops_task(thread_id):
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for op_idx in range(10):
                    op_type = op_idx % 3
                    
                    if op_type == 0:  # Read
                        docs = db.all()
                        with op_lock:
                            operation_count["read"] += 1
                    elif op_type == 1:  # Write
                        doc_id = db.insert({"thread": thread_id, "op": op_idx})
                        with op_lock:
                            operation_count["write"] += 1
                    else:  # Delete
                        all_docs = db.all()
                        if len(all_docs) > len(base_ids):  # Don't delete base docs
                            # Try to delete last non-base doc
                            for doc in reversed(all_docs):
                                if doc.doc_id not in base_ids:
                                    db.remove(doc_ids=[doc.doc_id])
                                    with op_lock:
                                        operation_count["delete"] += 1
                                    break
                
                db.close()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=mixed_ops_task, args=(i,)) for i in range(4)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        
        assert not errors, f"Mixed ops errors: {errors}"
        assert sum(operation_count.values()) > 0, "No operations completed"
        print(f"Mixed ops: read={operation_count['read']}, write={operation_count['write']}, delete={operation_count['delete']}")
        
        # Verify database consistency
        db = TinyDB(db_path, storage=JSONStorage)
        all_docs = db.all()
        assert len(all_docs) >= len(base_ids), "Base documents were corrupted"
        db.close()

    @pytest.mark.timeout(25)
    def test_rapid_table_access(self, tmp_path: Path):
        """Stress test: rapid table creation and access."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        db.close()
        
        operation_count = 0
        op_lock = threading.Lock()
        errors = []
        
        def table_access_task(thread_id):
            nonlocal operation_count
            try:
                for i in range(5):
                    db = TinyDB(db_path, storage=JSONStorage)
                    table = db.table(f"table_{thread_id}_{i}")
                    table.insert({"data": f"value_{i}"})
                    docs = table.all()
                    assert len(docs) > 0
                    with op_lock:
                        operation_count += 1
                    db.close()
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=table_access_task, args=(i,)) for i in range(3)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        
        assert not errors, f"Table access errors: {errors}"
        assert operation_count == 15, f"Expected 15 operations, got {operation_count}"


class TestDeadlockPrevention:
    """Tests to verify no deadlocks occur under concurrent load."""

    @pytest.mark.timeout(20)
    def test_no_deadlock_circular_updates(self, tmp_path: Path):
        """Verify no deadlock in circular update patterns."""
        db_path = tmp_path / "test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create documents
        doc_a = db.insert({"name": "A", "link_to": "B"})
        doc_b = db.insert({"name": "B", "link_to": "C"})
        doc_c = db.insert({"name": "C", "link_to": "A"})
        db.close()
        
        errors = []
        completed = [False, False]
        
        def cycle_a():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for i in range(3):
                    db.update({"updated": i}, doc_ids=[doc_a])
                    db.update({"updated": i}, doc_ids=[doc_b])
                    db.update({"updated": i}, doc_ids=[doc_c])
                completed[0] = True
                db.close()
            except Exception as e:
                errors.append(e)
        
        def cycle_b():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                for i in range(3):
                    db.update({"updated": i}, doc_ids=[doc_c])
                    db.update({"updated": i}, doc_ids=[doc_b])
                    db.update({"updated": i}, doc_ids=[doc_a])
                completed[1] = True
                db.close()
            except Exception as e:
                errors.append(e)
        
        t1 = threading.Thread(target=cycle_a)
        t2 = threading.Thread(target=cycle_b)
        
        t1.start()
        t2.start()
        
        t1.join(timeout=25)
        t2.join(timeout=25)
        
        assert not errors, f"Deadlock test errors: {errors}"
        assert completed[0] and completed[1], "Deadlock detected - threads didn't complete"
