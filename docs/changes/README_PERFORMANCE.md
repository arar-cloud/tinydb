# Performance Regression Tests

This document describes TinyDB's performance regression test suite, which ensures database operations maintain consistent performance across Python versions and prevent performance degradation in future releases.

## Overview

The performance test suite (`test_performance.py`) measures:

1. **Write Throughput**: Insert performance for single and batch operations
2. **Query Latency**: Search and retrieval speed on various dataset sizes
3. **Update/Delete Performance**: Modification operation throughput
4. **Memory Efficiency**: Reasonable memory usage with large datasets
5. **Storage Backend Comparison**: Performance differences between storage backends

## Test Categories

### Insert Performance (`TestInsertPerformance`)

Measures write throughput and latency:

- `test_insert_single_document_latency`: Single insert latency (< 1ms)
- `test_insert_batch_1000_throughput`: Batch insert 1000 docs (< 500ms)
- `test_insert_batch_10000_throughput`: Large batch insert 10000 docs (< 5s)
- `test_insert_to_json_storage`: Insert performance with JSONStorage backend

**Baseline**: ~1000+ documents/second on MemoryStorage

### Query Performance (`TestQueryPerformance`)

Measures search and retrieval speed:

- `test_simple_query_1000_documents`: Simple equality query (< 50ms)
- `test_complex_query_1000_documents`: Complex multi-condition query (< 100ms)
- `test_query_count_1000_documents`: Count query (< 10ms)
- `test_query_all_documents`: Retrieve all documents (< 50ms)

**Baseline**: Query 1000 documents in < 100ms

### Update Performance (`TestUpdatePerformance`)

Measures modification throughput:

- `test_update_single_document`: Single update latency (< 1ms)
- `test_update_batch_1000_documents`: Batch update 1000 docs (< 500ms)

**Baseline**: ~1000+ updates/second on MemoryStorage

### Delete Performance (`TestDeletePerformance`)

Measures deletion throughput:

- `test_delete_single_document`: Single delete latency (< 1ms)
- `test_delete_batch_1000_documents`: Batch delete 1000 docs (< 500ms)

**Baseline**: ~1000+ deletes/second on MemoryStorage

### Memory Usage (`TestMemoryUsage`)

Verifies memory efficiency:

- `test_memory_efficiency_with_large_documents`: Large document handling
- `test_memory_efficiency_after_many_operations`: Memory cleanup after cycles

### Storage Backend Comparison (`TestStorageBackendPerformance`)

Compares performance across storage backends:

- `test_memory_vs_json_storage_insert`: Insert performance comparison
- `test_memory_vs_json_storage_query`: Query performance comparison

## Running the Tests

### Run all performance tests:

```bash
python -m pytest tests/test_performance.py -v
```

### Run specific test category:

```bash
python -m pytest tests/test_performance.py::TestInsertPerformance -v
```

### Run with detailed timing output:

```bash
python -m pytest tests/test_performance.py -v -s
```

### Run performance tests only (with marker):

```bash
python -m pytest tests/test_performance.py -v -m benchmark
```

## Understanding Results

Each test prints performance metrics:

```
test_insert_batch_1000_throughput 1234 docs/sec
test_query_simple_1000_documents 5.23ms
```

### Performance Metrics Explained

- **Throughput** (docs/sec): Higher is better. Measures operations per second.
- **Latency** (ms): Lower is better. Measures time for operation to complete.
- **Memory**: Efficient if no excessive accumulation after operations.

## Performance Baselines

These baselines are measured on a standard development machine with Python 3.10+:

| Operation | Dataset Size | Threshold | Typical Performance |
|-----------|--------------|-----------|--------------------|
| Insert (single) | 1 | < 1ms | ~0.2ms |
| Insert (batch) | 1000 | < 500ms | ~150ms |
| Insert (large batch) | 10000 | < 5s | ~500ms |
| Query (simple) | 1000 | < 50ms | ~5ms |
| Query (complex) | 1000 | < 100ms | ~20ms |
| Update (batch) | 1000 | < 500ms | ~100ms |
| Delete (batch) | 1000 | < 500ms | ~100ms |

## Adjusting Thresholds

If tests fail due to environmental factors:

1. **Identify the slow operation**: Which test failed?
2. **Understand the context**: Running on slow hardware? Different Python version?
3. **Update baseline if justified**: Edit `PerformanceBenchmarks` class in `test_performance.py`
4. **Document the change**: Add comment explaining why threshold was adjusted
5. **Verify consistency**: Run tests multiple times to ensure stable results

Example adjustment in `test_performance.py`:

```python
class PerformanceBenchmarks:
    # Increased from 0.5s due to Python 3.13 optimizations not yet applied
    INSERT_BATCH_1000_THRESHOLD = 0.75
```

## Interpreting Regression Detection

When a test fails:

1. **Check error message**: Shows actual time vs. threshold
2. **Run multiple times**: Ensure it's not a fluke (system load)
3. **Check recent changes**: Review recent commits to `tinydb/` module
4. **Profile the operation**: Use Python's `cProfile` to identify bottleneck
5. **Investigate**: Is this a real regression or expected on new Python version?

## Integration with CI/CD

These tests should run in CI/CD pipeline:

```yaml
# .github/workflows/test.yml
- name: Run performance regression tests
  run: python -m pytest tests/test_performance.py -v
```

Failing performance tests should:
- Be visible in CI/CD reports
- Block merges if regression is confirmed
- Include performance metrics in PR checks

## Future Improvements

Potential enhancements:

1. **Profile-guided optimization**: Track performance over time
2. **Python version matrix**: Test across Python 3.10, 3.11, 3.12, 3.13
3. **Storage backend benchmarks**: Compare custom storage implementations
4. **Memory profiling**: Detailed memory usage tracking
5. **Concurrency tests**: Multi-threaded insert/query performance

## Contributing

When adding new performance tests:

1. Add test to appropriate class (or create new one)
2. Set realistic baseline thresholds
3. Include docstring explaining what's being measured
4. Use `time.perf_counter()` for high-resolution timing
5. Test on multiple machines to establish baseline
6. Update this documentation

See `test_performance.py` for examples and structure.
