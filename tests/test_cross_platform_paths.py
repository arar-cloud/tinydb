"""Tests for cross-platform path handling and symlink edge cases.

Verifies TinyDB compatibility across Windows, Linux, and macOS with
special attention to symlink handling, relative paths, and path separators.
"""

import os
import platform
import sys
from pathlib import Path

import pytest

from tinydb import TinyDB
from tinydb.storages import JSONStorage


class TestRelativePaths:
    """Test behavior with relative path specifications."""
    
    def test_relative_path_current_dir(self, tmp_path: Path) -> None:
        """Verify database works with relative paths in current directory."""
        # Save current dir
        original_cwd = os.getcwd()
        
        try:
            os.chdir(tmp_path)
            
            # Create DB with relative path
            db = TinyDB('test_relative.db', storage=JSONStorage)
            db.insert({'test': 'data'})
            
            # Verify file created in current directory
            assert (tmp_path / 'test_relative.db').exists()
            
            db.close()
        finally:
            os.chdir(original_cwd)
    
    def test_relative_path_subdirectory(self, tmp_path: Path) -> None:
        """Verify database works with relative paths in subdirectories."""
        original_cwd = os.getcwd()
        
        try:
            os.chdir(tmp_path)
            
            # Create subdirectory
            subdir = Path('subdir')
            subdir.mkdir()
            
            # Create DB in subdirectory with relative path
            db = TinyDB('subdir/test.db', storage=JSONStorage)
            db.insert({'location': 'subdir'})
            
            assert (tmp_path / 'subdir' / 'test.db').exists()
            
            db.close()
        finally:
            os.chdir(original_cwd)
    
    def test_relative_path_parent_directory(self, tmp_path: Path) -> None:
        """Verify database works with relative paths using parent directory reference."""
        original_cwd = os.getcwd()
        
        try:
            os.chdir(tmp_path)
            
            # Create nested directories
            nested = Path('a/b/c')
            nested.mkdir(parents=True)
            
            os.chdir(nested)
            
            # Create DB with parent directory reference
            db = TinyDB('../../test.db', storage=JSONStorage)
            db.insert({'relative': 'parent'})
            
            # Verify file in correct location
            assert (tmp_path / 'a' / 'test.db').exists()
            
            db.close()
        finally:
            os.chdir(original_cwd)


class TestAbsolutePaths:
    """Test behavior with absolute paths."""
    
    def test_absolute_path_creation(self, tmp_path: Path) -> None:
        """Verify database works with absolute paths."""
        db_path = tmp_path / 'absolute_test.db'
        
        db = TinyDB(str(db_path.absolute()), storage=JSONStorage)
        db.insert({'absolute': True})
        
        assert db_path.exists()
        
        db.close()
    
    def test_absolute_path_access(self, tmp_path: Path) -> None:
        """Verify database accessible via absolute path from different cwd."""
        original_cwd = os.getcwd()
        
        try:
            db_path = tmp_path / 'accessible.db'
            db = TinyDB(str(db_path.absolute()), storage=JSONStorage)
            db.insert({'accessible': True})
            db.close()
            
            # Change directory and reopen
            os.chdir('/')
            
            db = TinyDB(str(db_path.absolute()), storage=JSONStorage)
            assert len(db.all()) == 1
            db.close()
        finally:
            os.chdir(original_cwd)


class TestPathSeparators:
    """Test behavior with different path separators."""
    
    def test_forward_slash_paths(self, tmp_path: Path) -> None:
        """Verify handling of forward slash paths."""
        # Use forward slashes
        db_path = str(tmp_path / 'forward_slash.db')
        db_path = db_path.replace('\\', '/')  # Normalize to forward slashes
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'separator': 'forward'})
        db.close()
    
    @pytest.mark.skipif(platform.system() != 'Windows', reason='Windows-specific test')
    def test_backslash_paths_windows(self, tmp_path: Path) -> None:
        """Verify handling of backslash paths on Windows."""
        db_path = str(tmp_path / 'backslash.db')
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'separator': 'backslash'})
        db.close()
    
    def test_pathlib_path_object(self, tmp_path: Path) -> None:
        """Verify database works with pathlib.Path objects."""
        db_path = tmp_path / 'pathlib_test.db'
        
        db = TinyDB(db_path, storage=JSONStorage)
        db.insert({'pathlib': True})
        
        assert db_path.exists()
        
        db.close()


@pytest.mark.skipif(platform.system() == 'Windows', reason='Symlinks not standard on Windows')
class TestSymlinkHandling:
    """Test behavior with symbolic links."""
    
    def test_symlink_to_database(self, tmp_path: Path) -> None:
        """Verify database works when accessed via symlink."""
        if not hasattr(os, 'symlink'):
            pytest.skip('Symlinks not supported on this system')
        
        db_path = tmp_path / 'original.db'
        symlink_path = tmp_path / 'link.db'
        
        # Create database at original path
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'original': True})
        db.close()
        
        # Create symlink
        try:
            os.symlink(db_path, symlink_path)
        except OSError as e:
            pytest.skip(f"Cannot create symlink: {e}")
        
        # Access via symlink
        db = TinyDB(str(symlink_path), storage=JSONStorage)
        data = db.all()
        assert len(data) == 1
        assert data[0]['original']
        db.close()
    
    def test_symlink_to_directory(self, tmp_path: Path) -> None:
        """Verify database works when directory is symlinked."""
        if not hasattr(os, 'symlink'):
            pytest.skip('Symlinks not supported on this system')
        
        actual_dir = tmp_path / 'actual'
        actual_dir.mkdir()
        link_dir = tmp_path / 'link'
        
        # Create symlink to directory
        try:
            os.symlink(actual_dir, link_dir)
        except OSError as e:
            pytest.skip(f"Cannot create symlink: {e}")
        
        # Create database through symlinked directory
        db_path = link_dir / 'test.db'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'through_symlink': True})
        db.close()
        
        # Verify file exists in actual directory
        assert (actual_dir / 'test.db').exists()
    
    def test_broken_symlink_handling(self, tmp_path: Path) -> None:
        """Verify graceful error when symlink target doesn't exist."""
        if not hasattr(os, 'symlink'):
            pytest.skip('Symlinks not supported on this system')
        
        broken_link = tmp_path / 'broken.db'
        
        try:
            os.symlink('/nonexistent/path/to/db', broken_link)
        except OSError:
            pytest.skip('Cannot create symlink')
        
        # Attempting to use broken symlink should raise an error
        with pytest.raises(Exception):
            db = TinyDB(str(broken_link), storage=JSONStorage)
            db.insert({'data': 'test'})


class TestPathEdgeCases:
    """Test edge cases in path handling."""
    
    def test_path_with_spaces(self, tmp_path: Path) -> None:
        """Verify database works with spaces in path."""
        spaced_dir = tmp_path / 'path with spaces'
        spaced_dir.mkdir()
        
        db_path = spaced_dir / 'test.db'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'path': 'with_spaces'})
        
        assert db_path.exists()
        
        db.close()
    
    def test_path_with_special_chars(self, tmp_path: Path) -> None:
        """Verify database works with special characters in filename."""
        db_path = tmp_path / 'test-db_v1.0.db'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'special': 'chars'})
        
        assert db_path.exists()
        
        db.close()
    
    def test_dot_in_directory_path(self, tmp_path: Path) -> None:
        """Verify handling of dots in directory names."""
        dotted_dir = tmp_path / '.config' / 'app.config' / 'data'
        dotted_dir.mkdir(parents=True)
        
        db_path = dotted_dir / 'test.db'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'dotted': 'path'})
        
        assert db_path.exists()
        
        db.close()
    
    def test_long_path(self, tmp_path: Path) -> None:
        """Verify handling of very long paths."""
        # Create nested directories to create a long path
        long_dir = tmp_path
        for i in range(10):
            long_dir = long_dir / f'level_{i}_directory_name'
        long_dir.mkdir(parents=True)
        
        db_path = long_dir / 'test.db'
        db = TinyDB(str(db_path), storage=JSONStorage)
        db.insert({'long': 'path'})
        
        assert db_path.exists()
        
        db.close()
