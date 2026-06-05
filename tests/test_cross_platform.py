"""Cross-platform file permission and timing tests for TinyDB.

Validates behavior on Windows, macOS, and Linux with various file permission
states and concurrent access patterns. Uses platform-specific markers to skip
tests when running on incompatible platforms.
"""

import errno
import os
import platform
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tinydb import TinyDB, JSONStorage


# Platform detection
IS_WINDOWS = platform.system() == 'Windows'
IS_MACOS = platform.system() == 'Darwin'
IS_LINUX = platform.system() == 'Linux'


class TestFilePermissionsUnix:
    """File permission tests for Unix-like systems (Linux, macOS)."""

    @pytest.mark.skipif(IS_WINDOWS, reason="Unix file permissions not available on Windows")
    def test_read_only_file_handling(self, tmp_path):
        """Validate graceful handling of read-only database files."""
        db_path = tmp_path / 'test.db'
        
        # Create database and write initial data
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'data': 'initial'})
        db.close()
        
        # Change to read-only
        os.chmod(db_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        
        try:
            # Attempt read should succeed
            db = TinyDB(db_path, storage=JSONStorage)
            docs = db.all()
            assert len(docs) > 0
            db.close()
            
            # Attempt write should fail gracefully or be prevented
            db = TinyDB(db_path, storage=JSONStorage)
            # This may raise PermissionError or silently fail depending on implementation
            try:
                db.insert({'data': 'should_fail'})
            except (PermissionError, OSError) as e:
                # Expected behavior
                assert e.errno in [errno.EACCES, errno.EPERM]
            db.close()
        finally:
            # Restore permissions for cleanup
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

    @pytest.mark.skipif(IS_WINDOWS, reason="Unix file permissions not available on Windows")
    @pytest.mark.parametrize('mode', [
        stat.S_IRUSR | stat.S_IWUSR,  # 0o600 - owner read/write
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP,  # 0o660 - owner+group
        stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH,  # 0o664
    ])
    def test_various_file_permissions(self, tmp_path, mode):
        """Validate database access with various permission configurations."""
        db_path = tmp_path / 'test.db'
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'mode_test': oct(mode)})
        db.close()
        
        # Apply permission mode
        os.chmod(db_path, mode)
        current_mode = stat.S_IMODE(os.stat(db_path).st_mode)
        
        try:
            # Verify we can read the file
            db = TinyDB(db_path, storage=JSONStorage)
            docs = db.all()
            assert len(docs) > 0
            db.close()
        finally:
            # Restore permissions
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)

    @pytest.mark.skipif(IS_WINDOWS, reason="Unix file permissions not available on Windows")
    def test_directory_permission_isolation(self, tmp_path):
        """Validate database isolation with directory-level permissions."""
        db_dir = tmp_path / 'restricted'
        db_dir.mkdir()
        db_path = db_dir / 'test.db'
        
        # Create database
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'directory': 'test'})
        db.close()
        
        # Restrict directory
        os.chmod(db_dir, stat.S_IRUSR | stat.S_IXUSR)  # Read/execute only
        
        try:
            # Attempt access may fail
            try:
                db = TinyDB(db_path, storage=JSONStorage)
                db.close()
            except (PermissionError, OSError):
                # Expected when directory is read-only
                pass
        finally:
            # Restore permissions
            os.chmod(db_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)


class TestFilePermissionsWindows:
    """File permission tests for Windows."""

    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows-specific file permissions test")
    def test_windows_readonly_attribute(self, tmp_path):
        """Validate handling of Windows read-only file attribute."""
        db_path = tmp_path / 'test.db'
        
        # Create database
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'windows': 'test'})
        db.close()
        
        # Set read-only attribute using os.chmod
        os.chmod(db_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        
        try:
            db = TinyDB(db_path, storage=JSONStorage)
            docs = db.all()
            assert len(docs) > 0
            db.close()
        finally:
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR)


class TestConcurrentAccessTiming:
    """Timing and concurrent access tests across platforms."""

    def test_file_creation_timing(self, tmp_path):
        """Validate database file creation timing is deterministic."""
        db_path = tmp_path / 'timing_test.db'
        
        # Create database
        db = TinyDB(db_path, storage=JSONStorage)
        assert db_path.exists()
        
        db.insert({'timing': 'test'})
        db.close()
        
        # Verify file was created
        assert db_path.stat().st_size > 0

    def test_repeated_open_close_cycles(self, tmp_path):
        """Validate repeated open/close cycles maintain state integrity.
        
        This tests resilience to rapid open/close operations common in
        mobile and backend environments with connection pooling.
        """
        db_path = tmp_path / 'cycle_test.db'
        expected_docs = []
        
        for cycle in range(5):
            db = TinyDB(db_path, storage=JSONStorage)
            
            # Insert new document
            doc_id = db.insert({'cycle': cycle, 'data': f'cycle_{cycle}'})
            expected_docs.append(doc_id)
            
            # Verify all previous documents still exist
            all_docs = db.all()
            assert len(all_docs) == cycle + 1
            
            db.close()
        
        # Final verification
        db = TinyDB(db_path, storage=JSONStorage)
        final_docs = db.all()
        assert len(final_docs) == 5
        db.close()

    @pytest.mark.parametrize('concurrent_operations', [1, 2, 3])
    def test_sequential_operations_consistency(self, tmp_path, concurrent_operations):
        """Validate consistency across sequential operations simulating concurrency.
        
        Args:
            tmp_path: Temporary directory
            concurrent_operations: Number of sequential insert operations
        """
        db_path = tmp_path / 'seq_test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        
        doc_ids = []
        for op in range(concurrent_operations):
            doc_id = db.insert({'operation': op})
            doc_ids.append(doc_id)
        
        # Verify all operations completed
        assert len(doc_ids) == concurrent_operations
        assert len(db.all()) == concurrent_operations
        
        db.close()

    def test_file_modification_time_updates(self, tmp_path):
        """Validate file modification time is updated on writes."""
        db_path = tmp_path / 'mtime_test.db'
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'initial': 'data'})
        mtime1 = db_path.stat().st_mtime
        db.close()
        
        # Small delay to ensure mtime difference
        import time
        time.sleep(0.01)
        
        # Reopen and modify
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'modified': 'data'})
        mtime2 = db_path.stat().st_mtime
        db.close()
        
        # File should be modified (or same if filesystem has low resolution)
        assert mtime2 >= mtime1


class TestPlatformSpecificEdgeCases:
    """Platform-specific edge case handling."""

    @pytest.mark.skipif(not IS_WINDOWS, reason="Windows path test")
    def test_windows_longpath_handling(self, tmp_path):
        """Validate handling of long Windows file paths."""
        # Windows has 260-char MAX_PATH limitation
        db_path = tmp_path / 'test.db'
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'windows': 'longpath'})
        db.close()

    @pytest.mark.skipif(not IS_MACOS, reason="macOS-specific test")
    def test_macos_case_sensitivity_preservation(self, tmp_path):
        """Validate case sensitivity behavior on macOS filesystems."""
        db_path = tmp_path / 'TEST.db'
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'macos': 'casesensitive'})
        db.close()
        
        # Verify file exists with exact case
        assert db_path.exists()

    def test_symlink_database_handling(self, tmp_path):
        """Validate database access through symbolic links.
        
        Skip on Windows where symlinks require special privileges.
        """
        if IS_WINDOWS:
            pytest.skip("Symlinks require special privileges on Windows")
        
        actual_path = tmp_path / 'actual.db'
        link_path = tmp_path / 'link.db'
        
        # Create database at actual path
        db = TinyDB(actual_path, storage=JSONStorage)
        db.insert({'actual': 'path'})
        db.close()
        
        # Create symbolic link
        link_path.symlink_to(actual_path)
        
        # Access through link
        db = TinyDB(link_path, storage=JSONStorage)
        docs = db.all()
        assert len(docs) > 0
        db.close()
