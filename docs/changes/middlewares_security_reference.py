"""Middleware security hardening reference implementation.

This module demonstrates secure patterns for JSON serialization,
deserialization, and data validation in middleware operations.

To be integrated with the main tinydb/middlewares.py module.
"""

import json
from typing import Any, Dict, Optional

from .security import (
    sanitize_json_input,
    validate_document_size,
    check_database_size,
    SecurityError,
    MAX_DATABASE_SIZE,
)


class SecureSerializationMiddleware:
    """Secure JSON serialization with strict validation."""
    
    def __init__(self, strict: bool = True):
        """Initialize secure serialization middleware.
        
        Args:
            strict: Enable strict parsing mode
        """
        self.strict = strict
    
    def serialize(self, obj: Dict[str, Any]) -> str:
        """Safely serialize object to JSON string.
        
        Args:
            obj: Object to serialize
            
        Returns:
            JSON string
            
        Raises:
            SecurityError: If serialization fails
        """
        try:
            # Validate object before serialization
            validate_document_size(obj)
            
            # Use default serializer for standard types
            return json.dumps(
                obj,
                separators=(',', ':'),  # Compact format
                ensure_ascii=True,  # Prevent unicode injection
                sort_keys=True,  # Deterministic output
            )
        except TypeError as e:
            raise SecurityError(f"Serialization failed: {e}")
    
    def deserialize(self, data: str) -> Dict[str, Any]:
        """Safely deserialize JSON string with strict validation.
        
        Args:
            data: JSON string to deserialize
            
        Returns:
            Deserialized object
            
        Raises:
            SecurityError: If deserialization or validation fails
        """
        # Use sanitization to prevent injection attacks
        if self.strict:
            return sanitize_json_input(data)
        else:
            try:
                parsed = json.loads(data, strict=True)
                if not isinstance(parsed, dict):
                    raise SecurityError("Root object must be a dictionary")
                return parsed
            except json.JSONDecodeError as e:
                raise SecurityError(f"Invalid JSON: {e}")


class SizeCheckingMiddleware:
    """Middleware enforcing size limits on database operations."""
    
    def __init__(self, max_db_size: int = MAX_DATABASE_SIZE):
        """Initialize size checking middleware.
        
        Args:
            max_db_size: Maximum database size in bytes
        """
        self.max_db_size = max_db_size
        self.current_size = 0
    
    def check_insert_size(self, data: str) -> None:
        """Verify that insert operation won't exceed size limits.
        
        Args:
            data: Serialized data to insert
            
        Raises:
            SecurityError: If operation would exceed size limit
        """
        data_size = len(data.encode('utf-8'))
        check_database_size(self.current_size, data_size, self.max_db_size)
    
    def record_write(self, data: str) -> None:
        """Record size of written data.
        
        Args:
            data: Serialized data that was written
        """
        self.current_size += len(data.encode('utf-8'))
    
    def reset_size(self, size: int) -> None:
        """Reset tracked size (for initialization or compaction).
        
        Args:
            size: New tracked size
        """
        if size < 0:
            raise SecurityError("Size cannot be negative")
        self.current_size = size


class InputSanitizationMiddleware:
    """Middleware for sanitizing input data before processing."""
    
    @staticmethod
    def sanitize_before_parse(raw_data: str) -> str:
        """Pre-parse sanitization to remove dangerous content.
        
        Args:
            raw_data: Raw input data
            
        Returns:
            Sanitized data
            
        Raises:
            SecurityError: If dangerous content detected
        """
        # Check for null bytes
        if '\x00' in raw_data:
            raise SecurityError("Input contains null bytes")
        
        # Check for excessive length
        if len(raw_data) > MAX_DATABASE_SIZE:
            raise SecurityError("Input exceeds maximum size")
        
        return raw_data
    
    @staticmethod
    def sanitize_keys(obj: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize dictionary keys for safety.
        
        Args:
            obj: Dictionary to sanitize
            
        Returns:
            Sanitized dictionary
            
        Raises:
            SecurityError: If keys contain dangerous patterns
        """
        sanitized = {}
        
        for key, value in obj.items():
            if not isinstance(key, str):
                raise SecurityError(f"Key must be string, got {type(key)}")
            
            # Reject dangerous key patterns
            dangerous_patterns = ['__', 'eval', 'exec', 'compile', 'globals', 'locals']
            if any(pattern in key.lower() for pattern in dangerous_patterns):
                raise SecurityError(f"Dangerous key pattern detected: {key}")
            
            sanitized[key] = value
        
        return sanitized


class SchemaValidationMiddleware:
    """Middleware for document schema validation."""
    
    def __init__(self, allowed_types: Optional[tuple] = None):
        """Initialize schema validation middleware.
        
        Args:
            allowed_types: Tuple of allowed value types (default: common types)
        """
        self.allowed_types = allowed_types or (
            type(None), bool, int, float, str, list, dict
        )
    
    def validate_schema(self, obj: Dict[str, Any]) -> None:
        """Validate that object conforms to allowed schema.
        
        Args:
            obj: Object to validate
            
        Raises:
            SecurityError: If schema validation fails
        """
        for key, value in obj.items():
            if not isinstance(value, self.allowed_types):
                raise SecurityError(
                    f"Value for key '{key}' has unsupported type {type(value)}"
                )
            
            # Recursively validate nested dicts
            if isinstance(value, dict):
                self.validate_schema(value)
