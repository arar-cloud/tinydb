"""Database security hardening reference implementation.

This module demonstrates secure patterns for file path validation,
document ID immutability, and input validation in database operations.

To be integrated with the main tinydb/database.py module.
"""

from pathlib import Path
from typing import Union, Optional, Dict, Any

from .security import (
    validate_file_path,
    validate_document_id,
    validate_document_size,
    validate_table_name,
    SecurityError,
)


class SecureDatabaseMixin:
    """Mixin providing security validation for database operations."""
    
    def __init__(self, path: Union[str, Path]):
        """Initialize database with validated file path.
        
        Args:
            path: Path to database file
            
        Raises:
            SecurityError: If path validation fails
        """
        # Validate path to prevent directory traversal
        self._validated_path = validate_file_path(path)
    
    def _validate_insert_operation(self, doc: Dict[str, Any]) -> None:
        """Validate document before insertion.
        
        Args:
            doc: Document to validate
            
        Raises:
            SecurityError: If validation fails
        """
        # Check document size
        validate_document_size(doc)
        
        # Verify document is a dict
        if not isinstance(doc, dict):
            raise SecurityError("Document must be a dictionary")
    
    def _validate_update_operation(self, doc_id: int, doc: Dict[str, Any]) -> None:
        """Validate document ID and content before update.
        
        Args:
            doc_id: Document ID to update
            doc: Updated document content
            
        Raises:
            SecurityError: If validation fails
        """
        # Ensure ID is immutable (must be positive integer)
        validate_document_id(doc_id)
        
        # Validate document content
        self._validate_insert_operation(doc)
    
    def _validate_remove_operation(self, doc_id: int) -> None:
        """Validate document ID before removal.
        
        Args:
            doc_id: Document ID to remove
            
        Raises:
            SecurityError: If validation fails
        """
        # Ensure ID is valid
        validate_document_id(doc_id)
    
    def _validate_table_access(self, table_name: str) -> None:
        """Validate table name before access.
        
        Args:
            table_name: Name of table to access
            
        Raises:
            SecurityError: If table name is invalid
        """
        validate_table_name(table_name)


class SecureFilePermissions:
    """Enforce secure file permissions on database files."""
    
    # Secure file permissions: owner read/write only (0o600)
    SECURE_MODE = 0o600
    
    @staticmethod
    def ensure_secure_permissions(file_path: Path) -> None:
        """Ensure database file has secure permissions.
        
        Args:
            file_path: Path to database file
            
        Raises:
            SecurityError: If permissions cannot be set
        """
        try:
            # Set restrictive permissions (owner read/write only)
            file_path.chmod(SecureFilePermissions.SECURE_MODE)
        except Exception as e:
            raise SecurityError(f"Failed to set secure permissions: {e}")
    
    @staticmethod
    def verify_secure_permissions(file_path: Path) -> bool:
        """Verify database file has secure permissions.
        
        Args:
            file_path: Path to database file
            
        Returns:
            True if permissions are secure, False otherwise
        """
        try:
            stat_info = file_path.stat()
            # Check if permissions match secure mode
            return (stat_info.st_mode & 0o777) == SecureFilePermissions.SECURE_MODE
        except Exception:
            return False


class DocumentIDGenerator:
    """Secure document ID generation ensuring immutability and uniqueness."""
    
    def __init__(self):
        """Initialize with sequential ID counter."""
        self._counter = 0
    
    def next_id(self) -> int:
        """Generate next document ID.
        
        Returns:
            Next sequential ID (always positive integer)
        """
        self._counter += 1
        return self._counter
    
    def validate_id_format(self, doc_id: Any) -> bool:
        """Validate that ID matches expected format.
        
        Args:
            doc_id: ID to validate
            
        Returns:
            True if ID is valid integer, False otherwise
        """
        return isinstance(doc_id, int) and doc_id > 0


class OperationValidation:
    """Validate query and operation parameters to prevent injection."""
    
    @staticmethod
    def validate_query_parameter(param: Any) -> None:
        """Validate query parameter for safety.
        
        Args:
            param: Query parameter to validate
            
        Raises:
            SecurityError: If parameter contains dangerous content
        """
        # Reject callable objects in queries (prevents lambda/function injection)
        if callable(param):
            raise SecurityError("Callable objects not allowed in query parameters")
        
        # Reject dangerous attributes
        if isinstance(param, str):
            dangerous_patterns = ['__', 'eval', 'exec', 'compile']
            if any(pattern in param.lower() for pattern in dangerous_patterns):
                raise SecurityError(f"Suspicious pattern detected in query parameter: {param}")
