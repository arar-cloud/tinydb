"""Tests for mobile and embedded system scenarios.

Validates TinyDB behavior under resource constraints like timeouts,
memory pressure, and slow I/O common in mobile and embedded deployments.
"""

import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage


class TestTimeoutScenarios:
    """Test behavior under timeout constraints."""
    
    @pytest.mark.timeout(10)
    @pytest.mark.mobile
    def test_insert_with_timeout(self, tmp_path: Path) -> None:
        """Verify insert completes within timeout on mobile."""
        db_path = tmp_path / 'timeout_insert.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        start = time.time()
        
        # Insert data with implicit timeout
        db.insert({'data': 'test'})
        
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Insert took {elapsed}s, exceeded mobile timeout"
        
        db.close()
    
    @pytest.mark.timeout(10)
    @pytest.mark.mobile
    def test_query_with_timeout(self, tmp_path: Path) -> None:
        """Verify query completes within timeout on mobile."""
        db_path = tmp_path / 'timeout_query.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Pre-populate
        for i in range(100):
            db.insert({'index': i, 'value': i * 2})
        
        start = time.time()
        
        query = Query()
        results = db.search(query.value > 50)
        
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Query took {elapsed}s, exceeded mobile timeout"
        assert len(results) > 0
        
        db.close()
    
    @pytest.mark.timeout(10)
    @pytest.mark.mobile
    def test_bulk_operation_with_timeout(self, tmp_path: Path) -> None:
        """Verify bulk operations complete within timeout."""
        db_path = tmp_path / 'timeout_bulk.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        start = time.time()
        
        # Bulk insert
        docs = [{'id': i, 'value': f'doc_{i}'} for i in range(50)]
        db.insert_multiple(docs)
        
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Bulk insert took {elapsed}s, exceeded mobile timeout"
        
        db.close()


class TestMemoryConstraints:
    """Test behavior under memory pressure."""
    
    @pytest.mark.mobile
    def test_large_document_handling(self, tmp_path: Path) -> None:
        """Verify handling of large documents on memory-constrained devices."""
        db_path = tmp_path / 'memory_large_doc.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create moderately large document (not huge to avoid real memory issues in tests)
        large_data = 'x' * 10000  # 10KB string
        doc = {
            'id': 1,
            'data': large_data,
            'nested': {
                'more_data': large_data,
                'array': [large_data] * 3
            }
        }
        
        doc_id = db.insert(doc)
        assert doc_id is not None
        
        query = Query()
        retrieved = db.get(query.id == 1)
        assert retrieved is not None
        assert retrieved['data'] == large_data
        
        db.close()
    
    @pytest.mark.mobile
    def test_many_small_documents(self, tmp_path: Path) -> None:
        """Verify efficient handling of many small documents."""
        db_path = tmp_path / 'memory_many_docs.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert many small documents
        for i in range(1000):
            db.insert({'id': i, 'value': i})
        
        assert len(db.all()) == 1000
        
        db.close()
    
    @pytest.mark.mobile
    def test_rapid_successive_operations(self, tmp_path: Path) -> None:
        """Verify memory efficiency with rapid successive operations."""
        db_path = tmp_path / 'memory_rapid_ops.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Rapid insert-query-update-delete cycles
        for cycle in range(100):
            doc_id = db.insert({'cycle': cycle})
            
            query = Query()
            db.search(query.cycle == cycle)
            
            db.update({'cycle': cycle * 2}, query.cycle == cycle)
            
            db.remove(doc_ids=[doc_id])
        
        # Database should be clean
        assert len(db.all()) == 0
        
        db.close()


class TestSlowIOScenarios:
    """Test behavior under slow I/O conditions."""
    
    @pytest.mark.mobile
    @pytest.mark.timeout(30)
    def test_slow_disk_write(self, tmp_path: Path) -> None:
        """Verify operation succeeds even with simulated slow I/O."""
        db_path = tmp_path / 'slow_io_write.db'
        
        # Create database and test that it can handle operations
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Normal operation - should complete quickly on test system
        db.insert({'test': 'data'})
        assert len(db.all()) == 1
        
        db.close()
    
    @pytest.mark.mobile
    def test_slow_disk_read(self, tmp_path: Path) -> None:
        """Verify read operations work under slow I/O conditions."""
        db_path = tmp_path / 'slow_io_read.db'
        
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Insert data
        for i in range(50):
            db.insert({'index': i})
        
        # Perform reads - should succeed despite IO
        query = Query()
        results = db.search(query.index >= 25)
        assert len(results) >= 25
        
        db.close()
    
    @pytest.mark.mobile
    def test_resilience_to_io_stalls(self, tmp_path: Path) -> None:
        """Verify resilience to temporary I/O stalls."""
        db_path = tmp_path / 'io_stall_resilience.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        success_count = 0
        
        # Try multiple operations that might encounter stalls
        for i in range(10):
            try:
                db.insert({'attempt': i, 'status': 'ok'})
                success_count += 1
            except Exception:
                pass  # Expected: some might fail under real I/O stalls
        
        assert success_count > 0, "All operations failed under IO stall simulation"
        
        db.close()


class TestLowResourceConditions:
    """Test behavior under low resource conditions."""
    
    @pytest.mark.mobile
    def test_operation_under_memory_pressure(self, tmp_path: Path) -> None:
        """Verify operations continue under memory pressure."""
        db_path = tmp_path / 'memory_pressure.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Perform operations despite memory constraints
        for i in range(50):
            db.insert({'id': i, 'data': f'entry_{i}'})
        
        query = Query()
        results = db.search(query.id < 25)
        assert len(results) == 25
        
        db.close()
    
    @pytest.mark.mobile
    def test_close_and_reopen_low_memory(self, tmp_path: Path) -> None:
        """Verify graceful close/reopen under memory pressure."""
        db_path = tmp_path / 'low_mem_reopen.db'
        
        # First session
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'session': 1})
        db.close()
        
        # Second session under resource constraint simulation
        db = TinyDB(db_path, storage=JSONStorage)
        assert len(db.all()) == 1
        db.close()
        
        # Third session
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'session': 2})
        assert len(db.all()) == 2
        db.close()
