"""
A collection of update operations for TinyDB.

They are used for updates like this:

>>> db.update(delete('foo'), where('foo') == 2)

This would delete the ``foo`` field from all documents where ``foo`` equals 2.
"""


from typing import Callable, Mapping, Any, Union

# Maximum document size to prevent unbounded growth (100 MB)
MAX_DOCUMENT_SIZE = 100 * 1024 * 1024


def _validate_operation_data(data: Any, operation_name: str) -> None:
    """
    Validate data for operations to catch edge cases early.
    
    :param data: Data to validate
    :param operation_name: Name of operation for error messages
    :raises: ValueError if data is invalid
    :raises: TypeError if data type is invalid
    """
    if data is None:
        raise ValueError(f'{operation_name}: Cannot operate on null/None values')
    
    if isinstance(data, (list, dict, str)) and len(data) == 0:
        raise ValueError(f'{operation_name}: Cannot operate on empty collections')
    
    # Estimate size for oversized documents
    if isinstance(data, (dict, list)):
        import sys
        if sys.getsizeof(data) > MAX_DOCUMENT_SIZE:
            raise ValueError(f'{operation_name}: Document exceeds maximum size of {MAX_DOCUMENT_SIZE} bytes')


def delete(field: str) -> Callable[[Mapping], None]:
    """
    Delete a given field from the document.
    """
    def transform(doc: Mapping):
        del doc[field]

    return transform


def add(field: str, n: Union[int, float]) -> Callable[[Mapping], None]:
    """
    Add ``n`` to a given field in the document.
    """
    def transform(doc: Mapping):
        doc[field] += n

    return transform


def subtract(field: str, n: Union[int, float]) -> Callable[[Mapping], None]:
    """
    Subtract ``n`` to a given field in the document.
    """
    def transform(doc: Mapping):
        doc[field] -= n

    return transform


def set(field: str, val: Any) -> Callable[[Mapping], None]:
    """
    Set a given field to ``val``.
    """
    _validate_operation_data(val, 'set')
    def transform(doc: Mapping):
        if not isinstance(doc, dict):
            raise TypeError(f'Set operation requires dict, got {type(doc).__name__}')
        doc[field] = val

    return transform


def increment(field: str) -> Callable[[Mapping], None]:
    """
    Increment a given field in the document by 1.
    """
    def transform(doc: Mapping):
        doc[field] += 1

    return transform


def decrement(field: str) -> Callable[[Mapping], None]:
    """
    Decrement a given field in the document by 1.
    """
    def transform(doc: Mapping):
        doc[field] -= 1

    return transform
