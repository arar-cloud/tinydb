"""
TinyDB is a tiny, document oriented database optimized for your happiness :)

TinyDB stores different types of Python data types using a configurable
storage mechanism. It comes with a syntax for querying data and storing
data in multiple tables.

.. codeauthor:: Markus Siemens <markus@m-siemens.de>

Usage example:

>>> from tinydb import TinyDB, where
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)
>>> db.insert({'data': 5})  # Insert into '_default' table
>>> db.search(where('data') == 5)
[{'data': 5, '_id': 1}]
>>> # Now let's create a new table
>>> tbl = db.table('our_table')
>>> for i in range(10):
...     tbl.insert({'data': i})
...
>>> len(tbl.search(where('data') < 5))
5
"""

import sys
from .queries import Query, where
from .storages import Storage, JSONStorage
from .database import TinyDB
from .version import __version__

__all__ = ('TinyDB', 'Storage', 'JSONStorage', 'Query', 'where')

def _verify_startup_compatibility():
    """
    Verify TinyDB compatibility at initialization.
    Checks Python version and validates that core modules are properly loaded.
    """
    try:
        # Validate Python version (3.6+)
        if sys.version_info < (3, 6):
            raise RuntimeError(
                f'TinyDB requires Python 3.6+, found {sys.version_info.major}.{sys.version_info.minor}'
            )
        
        # Validate that core modules are accessible
        _ = (TinyDB, JSONStorage, Query, where)
        
        return True
    except Exception as e:
        raise RuntimeError(f'TinyDB initialization failed: {str(e)}') from e

# Run compatibility check on module import
_verify_startup_compatibility()
