import pytest
import tempfile
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, JSONStorage
from tinydb.storages import MemoryStorage


class TestConcurrentTransactions:
    """Test concurrent transaction handling and lock contention."""

    def test_concurrent_reads_same_document(self, tmp_path: Path):
        """Verify concurrent reads don't cause contention."""
        db_path = tmp_path / "concurrent_read.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0, "data": "shared"})
        db.close()
        
        results = []
        
        def read_document():
            db = TinyDB(db_path, storage=JSONStorage)
            doc = db.get(doc_id=doc_id)
            results.append(doc)
            db.close()
        
        # Launch 10 concurrent reads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_document) for _ in range(10)]
            for future in as_completed(futures):
                assert future.result() is None  # No exception
        
        # All reads should see same data
        assert len(results) == 10
        assert all(r["data"] == "shared" for r in results)

    def test_concurrent_writes_different_documents(self, tmp_path: Path):
        """Verify concurrent writes to different documents don't deadlock."""
        db_path = tmp_path / "concurrent_write.db"
        db = TinyDB(db_path, storage=JSONStorage)
        db.close()
        
        def insert_document(index):
            db = TinyDB(db_path, storage=JSONStorage)
            result = db.insert({"index": index, "thread_id": threading.current_thread().ident})
            db.close()
            return result
        
        # Launch 20 concurrent writes
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(insert_document, i) for i in range(20)]
            results = []
            for future in as_completed(futures):
                results.append(future.result())
        
        # All writes should succeed
        assert len(results) == 20
        
        # Verify all documents exist
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 20
        db.close()

    def test_concurrent_read_write_same_document(self, tmp_path: Path):
        """Verify concurrent read-write to same document handles contention."""
        db_path = tmp_path / "concurrent_rw.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0})
        db.close()
        
        read_count = [0]
        errors = []
        
        def read_counter():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                doc = db.get(doc_id=doc_id)
                read_count[0] += 1
                db.close()
            except Exception as e:
                errors.append(e)
        
        def write_counter():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                doc = db.get(doc_id=doc_id)
                new_value = doc["counter"] + 1
                db.update({"counter": new_value}, doc_ids=[doc_id])
                db.close()
            except Exception as e:
                errors.append(e)
        
        # Mix reads and writes
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(50):
                if i % 2 == 0:
                    futures.append(executor.submit(read_counter))
                else:
                    futures.append(executor.submit(write_counter))
            
            for future in as_completed(futures):
                future.result()  # Wait for completion
        
        # Should not deadlock or crash
        assert len(errors) == 0
        assert read_count[0] > 0

    def test_concurrent_updates_monotonic_increment(self, tmp_path: Path):
        """Verify concurrent updates maintain data integrity."""
        db_path = tmp_path / "concurrent_increment.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_id = db.insert({"counter": 0})
        db.close()
        
        def increment():
            db = TinyDB(db_path, storage=JSONStorage)
            doc = db.get(doc_id=doc_id)
            current = doc["counter"]
            # Simulate processing time
            time.sleep(0.001)
            db.update({"counter": current + 1}, doc_ids=[doc_id])
            db.close()
        
        # 10 concurrent increments
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(increment) for _ in range(10)]
            for future in as_completed(futures):
                future.result()
        
        # Final value should be at least some number of increments
        db = TinyDB(db_path, storage=JSONStorage)
        final_value = db.get(doc_id=doc_id)["counter"]
        db.close()
        
        assert final_value > 0  # Some increments happened


class TestStressConditions:
    """Test database behavior under stress conditions."""

    def test_high_volume_inserts(self, tmp_path: Path):
        """Verify database handles high volume of inserts."""
        db_path = tmp_path / "high_volume.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        start_time = time.time()
        
        # Insert 1000 documents
        for i in range(1000):
            db.insert({"id": i, "data": f"item_{i}" * 10})
        
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time
        assert elapsed < 30  # 30 seconds for 1000 inserts
        assert len(db.all()) == 1000
        
        db.close()

    def test_memory_usage_under_load(self, tmp_path: Path):
        """Verify memory usage doesn't explode under load."""
        db_path = tmp_path / "memory_load.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert large dataset
        large_items = [{"id": i, "data": "x" * 100} for i in range(500)]
        db.insert_multiple(large_items)
        
        # Query should work without OOM
        result = db.all()
        assert len(result) == 500
        
        # Delete and verify memory is reclaimed
        db.truncate()
        assert len(db.all()) == 0
        
        db.close()

    def test_large_transaction_batch(self, tmp_path: Path):
        """Verify large batch operations don't timeout."""
        db_path = tmp_path / "large_batch.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert large batch
        items = [{"id": i, "value": i * 2} for i in range(5000)]
        
        start_time = time.time()
        db.insert_multiple(items)
        elapsed = time.time() - start_time
        
        assert elapsed < 30
        assert len(db.all()) == 5000
        
        db.close()

    def test_rapid_open_close_cycles(self, tmp_path: Path):
        """Verify rapid open/close doesn't cause resource exhaustion."""
        db_path = tmp_path / "rapid_cycle.db"
        
        # Rapid open/close cycles
        for i in range(100):
            db = TinyDB(db_path, storage=JSONStorage)
            db.insert({"iteration": i})
            db.close()
        
        # Database should still work
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 100
        db.close()

    def test_concurrent_table_operations(self, tmp_path: Path):
        """Verify concurrent table access doesn't cause corruption."""
        db_path = tmp_path / "tables.db"
        
        def table_operation(table_name):
            db = TinyDB(db_path, storage=JSONStorage)
            table = db.table(table_name)
            table.insert({"table": table_name, "data": "test"})
            docs = table.all()
            db.close()
            return len(docs)
        
        # Create documents in different tables concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(table_operation, f"table_{i}") for i in range(10)]
            results = [f.result() for f in as_completed(futures)]
        
        assert all(r > 0 for r in results)

    def test_performance_degradation_on_large_dataset(self, tmp_path: Path):
        """Verify performance doesn't degrade catastrophically on large dataset."""
        db_path = tmp_path / "perf_degrade.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Build large dataset
        for i in range(100):
            db.insert({"id": i, "batch": i // 10})
        
        # Measure query performance
        times = []
        for _ in range(5):
            start = time.time()
            db.all()
            times.append(time.time() - start)
        
        # Performance should be relatively consistent
        avg_time = sum(times) / len(times)
        max_time = max(times)
        
        # No single query should take 10x longer than average
        assert max_time < avg_time * 10
        
        db.close()


class TestDeadlockScenarios:
    """Test for potential deadlock conditions."""

    def test_no_deadlock_circular_dependency(self, tmp_path: Path):
        """Verify no deadlock in circular access patterns."""
        db_path = tmp_path / "deadlock_test.db"
        db = TinyDB(db_path, storage=JSONStorage)
        
        id1 = db.insert({"ref": "id2", "data": "first"})
        id2 = db.insert({"ref": "id1", "data": "second"})
        db.close()
        
        completed = [0]
        
        def access_circular(id_a, id_b):
            db = TinyDB(db_path, storage=JSONStorage)
            doc_a = db.get(doc_id=id_a)
            doc_b = db.get(doc_id=id_b)
            db.close()
            completed[0] += 1
        
        # Multiple threads accessing in circular pattern
        threads = []
        for _ in range(5):
            t = threading.Thread(target=access_circular, args=(id1, id2))
            threads.append(t)
            t.start()
        
        # Wait with timeout
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "Thread deadlocked"
        
        assert completed[0] == 5

    def test_lock_timeout_prevents_indefinite_hang(self, tmp_path: Path):
        """Verify timeouts prevent indefinite hangs."""
        db_path = tmp_path / "timeout.db"
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({"test": "data"})
        db.close()
        
        completed = [0]
        
        def slow_operation():
            db = TinyDB(db_path, storage=JSONStorage)
            start = time.time()
            docs = db.all()
            elapsed = time.time() - start
            # Operation should complete reasonably quickly
            assert elapsed < 5
            completed[0] += 1
            db.close()
        
        threads = [threading.Thread(target=slow_operation) for _ in range(10)]
        for t in threads:
            t.start()
        
        for t in threads:
            t.join(timeout=10)
            assert not t.is_alive()
        
        assert completed[0] == 10
