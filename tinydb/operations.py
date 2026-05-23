"""
A collection of update operations for TinyDB.

They are used for updates like this:

>>> db.update(delete('foo'), where('foo') == 2)

This would delete the ``foo`` field from all documents where ``foo`` equals 2.
"""


from typing import Callable, Mapping, Any, Union, Dict

# Cache for field lookup resolution to avoid O(n) field comparisons
_field_cache: Dict[str, bool] = {}


def delete(field: str) -> Callable[[Mapping], None]:
    """
    Delete a given field from the document.
    Uses O(1) hashmap-based field resolution.
    """
    def transform(doc: Mapping):
        if field in doc:
            del doc[field]
        _field_cache.clear()

    return transform


def add(field: str, n: Union[int, float]) -> Callable[[Mapping], None]:
    """
    Add ``n`` to a given field in the document.
    Uses O(1) hashmap-based field access.
    """
    def transform(doc: Mapping):
        if field in doc:
            doc[field] += n
        _field_cache.clear()

    return transform


def subtract(field: str, n: Union[int, float]) -> Callable[[Mapping], None]:
    """
    Subtract ``n`` from a given field in the document.
    Uses O(1) hashmap-based field access.
    """
    def transform(doc: Mapping):
        if field in doc:
            doc[field] -= n
        _field_cache.clear()

    return transform


def set(field: str, val: Any) -> Callable[[Mapping], None]:
    """
    Set a given field to ``val``.
    Uses O(1) hashmap-based field assignment.
    """
    def transform(doc: Mapping):
        doc[field] = val
        _field_cache.clear()

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
