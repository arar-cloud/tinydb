Performance Tuning Guide
=======================

This guide provides recommendations for optimizing TinyDB performance in mobile and backend environments.

Core Performance Principles
---------------------------

**1. Batch Operations**

Use ``insert_multiple()`` instead of repeated ``insert()`` calls for better throughput:

.. code-block:: python

    # ❌ Slow: N separate insertions
    for doc in documents:
        db.insert(doc)
    
    # ✅ Fast: Single batch operation
    db.insert_multiple(documents)

Batch operations reduce I/O overhead and improve memory efficiency by 10-30% depending on document size.

**2. Caching Middleware**

Use ``CachingMiddleware`` to reduce repeated I/O operations:

.. code-block:: python

    from tinydb import TinyDB
    from tinydb.middlewares import CachingMiddleware
    from tinydb.storages import JSONStorage
    
    db = TinyDB('db.json', middlewares=[CachingMiddleware(JSONStorage)])

Caching prevents redundant disk reads and can improve query performance by 5-15x for repeated queries.

**3. Query Optimization**

Build queries efficiently to minimize computation:

.. code-block:: python

    from tinydb import Query
    
    q = Query()
    
    # ✅ Efficient: Use indexed/simple conditions
    result = db.search(q.status == 'active')
    
    # ⚠️  Less efficient: Complex nested conditions
    result = db.search((q.a == 1) & (q.b == 2) & (q.c == 3))
    # Use this only if necessary; consider denormalizing data

**4. Memory Management for Mobile**

For mobile deployments, avoid loading entire large tables into memory:

.. code-block:: python

    # ❌ Risky on mobile: Loads all docs
    all_docs = db.all()
    
    # ✅ Safe: Process with queries
    result = db.search(q.created_date >= start_date)
    
    # ✅ Safest: Use table partitioning
    archived_table = db.table('archived_records')
    active_table = db.table('active_records')

**5. Batch Updates**

Like inserts, batch updates using ``update()`` with conditions:

.. code-block:: python

    from tinydb import Query
    
    q = Query()
    
    # ✅ Efficient: Single update operation
    db.update({'status': 'processed'}, q.status == 'pending')
    
    # ❌ Inefficient: Loop + individual updates
    for doc in db.search(q.status == 'pending'):
        db.update({'status': 'processed'}, doc_ids=[doc.doc_id])

Data Structure Recommendations
------------------------------

**Denormalization for Read Performance**

For read-heavy workloads, store computed values:

.. code-block:: python

    # ✅ Better for performance
    db.insert({
        'user_id': 123,
        'name': 'Alice',
        'email': 'alice@example.com',
        'order_count': 42,  # Pre-computed
        'total_spent': 1200.50  # Pre-computed
    })
    
    # Update precomputed fields on transaction
    db.update(
        {'order_count': 43, 'total_spent': 1350.50},
        doc_ids=[user_id]
    )

**Table Partitioning**

For large datasets, split into multiple tables by logical boundaries:

.. code-block:: python

    # Partition by status
    active_orders = db.table('orders_active')
    completed_orders = db.table('orders_completed')
    cancelled_orders = db.table('orders_cancelled')
    
    # Each table is smaller, queries are faster
    active_orders.insert(new_order)
    completed_orders.insert(completed_order)

Backend Deployment Optimization
-------------------------------

**1. Storage Backend Selection**

- **MemoryStorage**: Fastest for transient data, no persistence
- **JSONStorage**: Good for persistent small-to-medium datasets (<100MB)
- **Custom Storage**: Implement for cloud backends (S3, DynamoDB, etc.)

**2. Connection Pooling for Concurrent Access**

For multi-threaded backends, use separate DB instances per thread:

.. code-block:: python

    import threading
    
    thread_local = threading.local()
    
    def get_db():
        if not hasattr(thread_local, 'db'):
            thread_local.db = TinyDB('db.json')
        return thread_local.db

**3. Periodic Maintenance**

Truncate or archive old records periodically:

.. code-block:: python

    from datetime import datetime, timedelta
    from tinydb import Query
    
    q = Query()
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # Archive old records
    old_records = db.search(q.created_date < cutoff_date)
    archive_table.insert_multiple(old_records)
    
    # Clean up main table
    db.remove(q.created_date < cutoff_date)

Performance Monitoring
----------------------

Run the performance benchmark suite to track regressions:

.. code-block:: bash

    # Run all performance tests
    pytest -m benchmark tests/test_performance.py -v
    
    # Run with memory profiling
    pytest -m memory tests/test_performance.py -v
    
    # Run specific benchmark
    pytest tests/test_performance.py::TestInsertPerformance::test_insert_bulk_1000_documents -v

Measure your own operations with timing:

.. code-block:: python

    import time
    
    start = time.perf_counter()
    db.insert_multiple(large_dataset)
    elapsed = time.perf_counter() - start
    print(f"Inserted 10,000 docs in {elapsed:.2f}s")

Common Performance Pitfalls
---------------------------

| Pitfall | Impact | Solution |
|---------|--------|----------|
| Repeated individual inserts | O(n) I/O operations | Use ``insert_multiple()`` |
| Querying entire table repeatedly | Memory waste, CPU overhead | Use caching middleware |
| Complex nested conditions | Slow filtering | Simplify or denormalize |
| No table partitioning for large datasets | High memory, slow queries | Split by logical boundary |
| Synchronous I/O in async handlers | Blocking threads | Use MemoryStorage + periodic sync |
| No timeout enforcement | Runaway queries on mobile | Set pytest markers |

Summary Checklist
-----------------

For production deployments:

- [ ] Use batch operations (insert_multiple, update with conditions)
- [ ] Enable caching middleware for read-heavy workloads
- [ ] Monitor with performance benchmarks regularly
- [ ] Partition large tables by logical boundaries
- [ ] Set timeouts on long-running operations
- [ ] Denormalize data for high-frequency reads
- [ ] Archive old records periodically
- [ ] Use thread-local storage for multi-threaded backends
- [ ] Profile memory usage with memory-profiler
- [ ] Test on target mobile/backend hardware
