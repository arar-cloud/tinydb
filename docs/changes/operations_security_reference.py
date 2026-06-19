"""Operations security hardening reference implementation.

This module demonstrates secure patterns for query operations and
evaluation without using eval(), exec(), or dynamic code generation.

To be integrated with the main tinydb/operations.py module.
"""

from typing import Any, Callable, Dict, Optional
from abc import ABC, abstractmethod

from .security import SecurityError


class SafeOperationValidator:
    """Validate query operations to prevent injection and unsafe patterns."""
    
    # Whitelist of allowed operation types
    ALLOWED_OPERATIONS = {
        'eq',  # equals
        'ne',  # not equals
        'lt',  # less than
        'le',  # less than or equal
        'gt',  # greater than
        'ge',  # greater than or equal
        'in',  # in list
        'nin',  # not in list
        'exists',  # field exists
        'matches',  # regex match
        'contains',  # string/list contains
    }
    
    @staticmethod
    def validate_operation_type(op_type: str) -> None:
        """Validate that operation type is in whitelist.
        
        Args:
            op_type: Operation type to validate
            
        Raises:
            SecurityError: If operation type is not whitelisted
        """
        if op_type not in SafeOperationValidator.ALLOWED_OPERATIONS:
            raise SecurityError(
                f"Operation '{op_type}' is not allowed. "
                f"Allowed: {SafeOperationValidator.ALLOWED_OPERATIONS}"
            )
    
    @staticmethod
    def validate_operation_callable(func: Any) -> None:
        """Validate that operation parameter is not a dangerous callable.
        
        Args:
            func: Function or callable to validate
            
        Raises:
            SecurityError: If callable is potentially dangerous
        """
        if callable(func):
            # Check function name for dangerous patterns
            func_name = getattr(func, '__name__', '')
            dangerous_patterns = [
                'eval', 'exec', 'compile', '__import__',
                'system', 'popen', 'spawn', 'subprocess'
            ]
            
            if any(pattern in func_name.lower() for pattern in dangerous_patterns):
                raise SecurityError(
                    f"Function '{func_name}' contains dangerous pattern and is not allowed"
                )
            
            # Reject lambda functions (anonymous functions are hard to verify)
            if func_name == '<lambda>':
                raise SecurityError(
                    "Lambda functions are not allowed in operations. "
                    "Use named functions from the whitelist."
                )
    
    @staticmethod
    def validate_query_parameter(param: Any) -> None:
        """Validate query parameter for safety.
        
        Args:
            param: Parameter to validate
            
        Raises:
            SecurityError: If parameter is potentially dangerous
        """
        if isinstance(param, str):
            # Reject strings that look like code
            dangerous_patterns = [
                '__', 'eval(', 'exec(', 'compile(',
                'import ', 'from ', '__import__',
            ]
            if any(pattern in param for pattern in dangerous_patterns):
                raise SecurityError(
                    f"Query parameter contains suspicious pattern: {param}"
                )
        
        elif callable(param):
            SafeOperationValidator.validate_operation_callable(param)


class SafeComparison(ABC):
    """Abstract base class for safe comparison operations."""
    
    @abstractmethod
    def compare(self, a: Any, b: Any) -> bool:
        """Perform safe comparison.
        
        Args:
            a: Value to compare
            b: Reference value
            
        Returns:
            Comparison result
        """
        pass


class EqualityComparison(SafeComparison):
    """Safe equality comparison operation."""
    
    def compare(self, a: Any, b: Any) -> bool:
        """Compare equality with type safety."""
        try:
            return a == b
        except Exception as e:
            raise SecurityError(f"Comparison failed: {e}")


class InListComparison(SafeComparison):
    """Safe 'in list' comparison operation."""
    
    def compare(self, a: Any, b: Any) -> bool:
        """Check if value is in list."""
        if not isinstance(b, (list, tuple, set)):
            raise SecurityError(f"Expected list/tuple/set for 'in' operation, got {type(b)}")
        
        try:
            return a in b
        except Exception as e:
            raise SecurityError(f"Comparison failed: {e}")


class RangeComparison(SafeComparison):
    """Safe range comparison operations."""
    
    def __init__(self, op_type: str):
        """Initialize with operation type.
        
        Args:
            op_type: One of 'lt', 'le', 'gt', 'ge'
        """
        if op_type not in ('lt', 'le', 'gt', 'ge'):
            raise SecurityError(f"Invalid range operation: {op_type}")
        self.op_type = op_type
    
    def compare(self, a: Any, b: Any) -> bool:
        """Perform range comparison."""
        try:
            if self.op_type == 'lt':
                return a < b
            elif self.op_type == 'le':
                return a <= b
            elif self.op_type == 'gt':
                return a > b
            elif self.op_type == 'ge':
                return a >= b
        except Exception as e:
            raise SecurityError(f"Comparison failed: {e}")
        
        return False


class StringMatchComparison(SafeComparison):
    """Safe string matching operation."""
    
    def compare(self, a: Any, b: Any) -> bool:
        """Check if string contains substring."""
        if not isinstance(a, str):
            return False
        
        if not isinstance(b, str):
            raise SecurityError(f"String comparison requires string value, got {type(b)}")
        
        try:
            return b in a
        except Exception as e:
            raise SecurityError(f"Comparison failed: {e}")


class OperationFactory:
    """Factory for creating safe operation instances."""
    
    # Map operation types to their implementations
    OPERATION_REGISTRY: Dict[str, type] = {
        'eq': EqualityComparison,
        'ne': EqualityComparison,  # Implemented with negation
        'lt': RangeComparison,
        'le': RangeComparison,
        'gt': RangeComparison,
        'ge': RangeComparison,
        'in': InListComparison,
        'contains': StringMatchComparison,
    }
    
    @staticmethod
    def create_operation(op_type: str) -> SafeComparison:
        """Create a safe operation instance.
        
        Args:
            op_type: Type of operation
            
        Returns:
            Operation instance
            
        Raises:
            SecurityError: If operation type is not registered
        """
        SafeOperationValidator.validate_operation_type(op_type)
        
        if op_type == 'eq':
            return EqualityComparison()
        elif op_type in ('lt', 'le', 'gt', 'ge'):
            return RangeComparison(op_type)
        elif op_type == 'in':
            return InListComparison()
        elif op_type == 'contains':
            return StringMatchComparison()
        else:
            raise SecurityError(f"No implementation for operation: {op_type}")


class QueryValidator:
    """Validate entire query structures."""
    
    @staticmethod
    def validate_query(query: Any) -> None:
        """Validate query object structure.
        
        Args:
            query: Query to validate
            
        Raises:
            SecurityError: If query is malformed or dangerous
        """
        if isinstance(query, dict):
            for key, value in query.items():
                if isinstance(value, dict):
                    QueryValidator.validate_query(value)
                elif callable(value):
                    SafeOperationValidator.validate_operation_callable(value)
        elif callable(query):
            SafeOperationValidator.validate_operation_callable(query)
