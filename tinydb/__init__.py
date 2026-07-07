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

from .queries import Query, where
from .storages import Storage, JSONStorage
from .database import TinyDB
from .version import __version__

__all__ = ('TinyDB', 'Storage', 'JSONStorage', 'Query', 'where')

# Security guidelines for Query and where functions
# ===================================================
# Query and where are used to construct database queries. To prevent query
# injection attacks:
#
# 1. Never construct queries from untrusted user input
# 2. Always use parameterized queries or whitelisted field/operator combinations
# 3. Validate field names against an allowed list
# 4. Use Query objects only with known, safe field names
#
# UNSAFE example:
#   field_name = user_input  # Never do this!
#   db.search(Query()[field_name] == value)
#
# SAFE example:
#   ALLOWED_FIELDS = {'name', 'email', 'age'}
#   if field_name in ALLOWED_FIELDS:
#       db.search(Query()[field_name] == value)
