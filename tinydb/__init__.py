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

# Deferred imports to prevent circular dependencies at module load time
try:
    from .storages import Storage, JSONStorage
except ImportError as e:
    raise ImportError(f"Failed to import storages: {e}") from e

try:
    from .database import TinyDB
except ImportError as e:
    raise ImportError(f"Failed to import database: {e}") from e

try:
    from .queries import Query, where
except ImportError as e:
    raise ImportError(f"Failed to import queries: {e}") from e

try:
    from .version import __version__
except ImportError:
    __version__ = "unknown"

__all__ = ('TinyDB', 'Storage', 'JSONStorage', 'Query', 'where', '__version__')
