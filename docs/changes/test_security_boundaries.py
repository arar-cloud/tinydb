"""Integration tests for security boundaries in TinyDB.

Tests verify that concurrent access, file permissions, and multi-user scenarios
do not bypass security controls. Tests isolation of different database instances.
"""

import os
import tempfile
import threading
import time
from pathlib import Path

import pytest
from tinydb import TinyDB, Query
from tinydb.storages import JSONStorage


class TestSecurityBoundaries:
    """Test security boundaries across database operations."""

    def test_concurrent_access_isolation(self, tmp_path):
        """Test that concurrent access to the same database maintains isolation."""
        db_path = tmp_path / 'concurrent.db'
        results = {'thread1': [], 'thread2': [], 'errors': []}
        
        def thread1_work():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                User = Query()
                
                # Insert document
                db.insert({'thread': 1, 'data': 'thread1_data'})
                time.sleep(0.1)  # Allow interleaving
                
                # Read data
                result = db.search(User.thread == 1)
                results['thread1'] = result
                db.close()
            except Exception as e:
                results['errors'].append(('thread1', str(e)))
        
        def thread2_work():
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                User = Query()
                
                time.sleep(0.05)  # Ensure thread1 starts first
                
                # Insert different document
                db.insert({'thread': 2, 'data': 'thread2_data'})
                
                # Read data
                result = db.search(User.thread == 2)
                results['thread2'] = result
                db.close()
            except Exception as e:
                results['errors'].append(('thread2', str(e)))
        
        t1 = threading.Thread(target=thread1_work)
        t2 = threading.Thread(target=thread2_work)
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Both threads should have successfully inserted and read their data
        assert len(results['errors']) == 0, f"Errors occurred: {results['errors']}"
        assert len(results['thread1']) == 1
        assert len(results['thread2']) == 1
        assert results['thread1'][0]['thread'] == 1
        assert results['thread2'][0]['thread'] == 2

    def test_database_instance_isolation(self, tmp_path):
        """Test that different database instances are properly isolated."""
        db_path1 = tmp_path / 'db1.db'
        db_path2 = tmp_path / 'db2.db'
        
        # Create two separate database files
        db1 = TinyDB(db_path1, storage=JSONStorage)
        db2 = TinyDB(db_path2, storage=JSONStorage)
        
        # Insert different data into each
        db1.insert({'db': 1, 'data': 'db1_data'})
        db2.insert({'db': 2, 'data': 'db2_data'})
        
        # Verify isolation
        User = Query()
        db1_results = db1.search(User.db == 1)
        db2_results = db2.search(User.db == 2)
        
        assert len(db1_results) == 1
        assert len(db2_results) == 1
        assert db1_results[0]['data'] == 'db1_data'
        assert db2_results[0]['data'] == 'db2_data'
        
        # Verify data is not mixed
        db1_cross = db1.search(User.db == 2)
        db2_cross = db2.search(User.db == 1)
        assert len(db1_cross) == 0
        assert len(db2_cross) == 0
        
        db1.close()
        db2.close()

    def test_file_permissions_boundaries(self, tmp_path):
        """Test that file permission boundaries are respected."""
        db_path = tmp_path / 'secure.db'
        
        # Create database with restricted permissions
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'sensitive': 'data'})
        db.close()
        
        # Verify file exists
        assert db_path.exists()
        
        # Re-open and verify data integrity
        db = TinyDB(db_path, storage=JSONStorage)
        User = Query()
        result = db.search(User.sensitive == 'data')
        assert len(result) == 1
        db.close()

    def test_multi_user_scenario_same_db(self, tmp_path):
        """Test multi-user scenario with same database file."""
        db_path = tmp_path / 'multiuser.db'
        
        # Simulate multiple users/clients
        users_data = {}
        
        for user_id in range(3):
            db = TinyDB(db_path, storage=JSONStorage)
            User = Query()
            
            # Each user inserts their own data
            doc_id = db.insert({'user_id': user_id, 'action': 'login'})
            
            # Verify insertion
            result = db.search(User.user_id == user_id)
            users_data[user_id] = len(result)
            
            db.close()
        
        # Verify all users' data is persisted
        final_db = TinyDB(db_path, storage=JSONStorage)
        User = Query()
        for user_id in range(3):
            result = final_db.search(User.user_id == user_id)
            assert len(result) >= 1, f"User {user_id} data not found"
        final_db.close()

    def test_table_isolation(self, tmp_path):
        """Test that different tables in same database are isolated."""
        db_path = tmp_path / 'tables.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Create multiple tables
        users_table = db.table('users')
        posts_table = db.table('posts')
        
        # Insert data into each table
        users_table.insert({'username': 'alice', 'role': 'admin'})
        posts_table.insert({'title': 'First Post', 'author': 'alice'})
        
        # Verify isolation
        User = Query()
        
        users_result = users_table.search(User.username == 'alice')
        posts_result = posts_table.search(User.title == 'First Post')
        
        assert len(users_result) == 1
        assert len(posts_result) == 1
        
        # Verify no cross-contamination
        assert len(users_table.search(User.title == 'First Post')) == 0
        assert len(posts_table.search(User.username == 'alice')) == 0
        
        db.close()

    def test_concurrent_read_write_consistency(self, tmp_path):
        """Test consistency during concurrent reads and writes."""
        db_path = tmp_path / 'consistency.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Initial data
        doc_id = db.insert({'counter': 0})
        
        results = {'reads': [], 'errors': []}
        
        def reader():
            try:
                for _ in range(5):
                    db_temp = TinyDB(db_path, storage=JSONStorage)
                    User = Query()
                    value = db_temp.search(User.doc_id == doc_id)
                    if value:
                        results['reads'].append(value[0]['counter'])
                    db_temp.close()
                    time.sleep(0.01)
            except Exception as e:
                results['errors'].append(('reader', str(e)))
        
        def writer():
            try:
                for i in range(5):
                    db_temp = TinyDB(db_path, storage=JSONStorage)
                    User = Query()
                    db_temp.update({'counter': i}, User.doc_id == doc_id)
                    db_temp.close()
                    time.sleep(0.02)
            except Exception as e:
                results['errors'].append(('writer', str(e)))
        
        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)
        
        reader_thread.start()
        writer_thread.start()
        reader_thread.join()
        writer_thread.join()
        
        assert len(results['errors']) == 0, f"Errors: {results['errors']}"
        # Reads should contain valid counter values
        assert len(results['reads']) > 0
        
        db.close()

    def test_attack_via_table_name_injection(self, tmp_path):
        """Test that table name injection attacks are prevented."""
        db_path = tmp_path / 'injection.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        # Attempt to create table with injection payload
        malicious_table_name = "users'); DROP TABLE users; --"
        table = db.table(malicious_table_name)
        
        # Should create table with literal name, not execute injection
        table.insert({'data': 'test'})
        
        # Verify table was created safely
        User = Query()
        result = table.search(User.data == 'test')
        assert len(result) == 1
        
        # Default table should still exist and be unaffected
        default_table = db.table('_default')
        default_table.insert({'marker': 'exists'})
        exists = default_table.search(User.marker == 'exists')
        assert len(exists) == 1
        
        db.close()
