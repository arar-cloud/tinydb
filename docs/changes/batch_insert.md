# Batch Insert Feature

## Overview

The `batch_insert()` method enables efficient bulk insertion of multiple documents into a TinyDB table. This is particularly useful for bootstrap scenarios where you need to initialize a database with large datasets.

## Signature

```python
table.batch_insert(documents: list, bootstrap_mode: bool = False) -> list
```

## Parameters

- `documents` (list): A list of dictionaries representing the documents to insert
- `bootstrap_mode` (bool, optional): When True, optimizes for bulk initialization by buffering writes. Default is False.

## Returns

A list of document IDs that were inserted.

## Usage Examples

### Basic Usage

```python
from tinydb import TinyDB

db = TinyDB('db.json')
table = db.table('users')

documents = [
    {'name': 'Alice', 'age': 30},
    {'name': 'Bob', 'age': 25},
    {'name': 'Charlie', 'age': 35},
]

ids = table.batch_insert(documents)
print(ids)  # [1, 2, 3]
```

### Bootstrap Mode for Large Datasets

```python
from tinydb import TinyDB

db = TinyDB('db.json')
table = db.table('products')

# Generate 10,000 products
products = [
    {'id': i, 'name': f'Product {i}', 'price': 9.99}
    for i in range(10000)
]

# Use bootstrap_mode for better performance
ids = table.batch_insert(products, bootstrap_mode=True)
print(f'Inserted {len(ids)} documents')
```

## Performance Benefits

- **Reduced I/O Operations**: Instead of writing after each insert, bootstrap mode buffers all inserts and writes once at the end
- **Faster Initialization**: Ideal for application startup when loading initial datasets
- **Atomic Operations**: In bootstrap mode, all inserts complete before any write to disk

## Comparison with Loop Insert

### Without batch_insert (slow):
```python
for doc in documents:
    table.insert(doc)  # Writes to disk after each insert
```

### With batch_insert (fast):
```python
table.batch_insert(documents, bootstrap_mode=True)  # Single write operation
```
