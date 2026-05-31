"""Integration tests verifying serialization and query cache effectiveness.

Validates that implemented caches reduce overhead in realistic bulk
operation scenarios and prevent performance regressions.
"""

import pytest
import time
from tinydb._serialization_cache import SerializationCache
from tinydb._query_cache import QueryCache


class TestSerializationCacheIntegration:
    """Verify serialization cache reduces bulk operation overhead."""

    def test_cache_prevents_redundant_serialization(self):
        """Cache should skip serialization for unchanged documents."""
        cache = SerializationCache(maxsize=100)
        
        serialize_calls = []
        def mock_serializer(data):
            serialize_calls.append(data)
            return b'serialized_' + str(data).encode()
        
        doc_data = {'id': 1, 'value': 'test'}
        
        # First call - serializes
        result1, hit1 = cache.get(1, doc_data, mock_serializer)
        assert not hit1, "First call should be cache miss"
        assert len(serialize_calls) == 1
        
        # Second call with same data - should hit cache
        result2, hit2 = cache.get(1, doc_data, mock_serializer)
        assert hit2, "Second call with same data should be cache hit"
        assert len(serialize_calls) == 1, "Should not call serializer again"
        assert result1 == result2
        
        # Modified data - should miss cache
        modified_data = {'id': 1, 'value': 'test_modified'}
        result3, hit3 = cache.get(1, modified_data, mock_serializer)
        assert not hit3, "Modified data should be cache miss"
        assert len(serialize_calls) == 2

    def test_cache_lru_eviction(self):
        """Cache should evict old entries when full."""
        cache = SerializationCache(maxsize=3)
        
        def mock_serializer(data):
            return b'serialized'
        
        # Fill cache
        for i in range(5):
            cache.get(i, {'id': i}, mock_serializer)
        
        # Cache size should not exceed maxsize
        assert len(cache._cache) <= 3
        # Oldest entries should be evicted
        assert 0 not in cache._cache
        assert 1 not in cache._cache

    def test_cache_invalidation(self):
        """Cache should properly invalidate entries."""
        cache = SerializationCache()
        
        def mock_serializer(data):
            return b'serialized'
        
        # Add entry
        cache.get(1, {'id': 1}, mock_serializer)
        assert 1 in cache._cache
        
        # Invalidate
        cache.invalidate(doc_id=1)
        assert 1 not in cache._cache
        
        # Full invalidation
        cache.get(2, {'id': 2}, mock_serializer)
        cache.get(3, {'id': 3}, mock_serializer)
        cache.invalidate()
        assert len(cache._cache) == 0


class TestQueryCacheIntegration:
    """Verify query cache eliminates redundant predicate compilation."""

    def test_predicate_caching(self):
        """Cache should store compiled predicates."""
        cache = QueryCache()
        
        compile_calls = []
        def mock_compiler():
            def predicate(doc):
                return doc.get('status') == 'active'
            compile_calls.append(predicate)
            return predicate
        
        pred_def = "where('status') == 'active'"
        
        # First call - compiles
        pred1 = cache.get_predicate(pred_def, mock_compiler)
        assert len(compile_calls) == 1
        
        # Second call - returns cached
        pred2 = cache.get_predicate(pred_def, mock_compiler)
        assert len(compile_calls) == 1, "Should not compile again"
        assert pred1 is pred2

    def test_result_caching(self):
        """Cache should store query results for identical queries."""
        cache = QueryCache()
        
        eval_calls = []
        def mock_evaluator():
            results = [1, 2, 3]
            eval_calls.append(results)
            return results
        
        pred_sig = 'pred_hash_1'
        table_sig = 'table_hash_1'
        
        # First evaluation
        results1, hit1 = cache.get_results(pred_sig, table_sig, mock_evaluator)
        assert not hit1
        assert len(eval_calls) == 1
        
        # Second evaluation - same table, should hit
        results2, hit2 = cache.get_results(pred_sig, table_sig, mock_evaluator)
        assert hit2
        assert len(eval_calls) == 1, "Should not evaluate again"
        assert results1 == results2
        
        # Different table - should miss
        results3, hit3 = cache.get_results(pred_sig, 'table_hash_2', mock_evaluator)
        assert not hit3
        assert len(eval_calls) == 2

    def test_table_invalidation(self):
        """Cache should invalidate all results when table changes."""
        cache = QueryCache()
        
        def mock_evaluator():
            return [1, 2, 3]
        
        table_sig = 'table_hash_1'
        
        # Cache results for this table
        cache.get_results('pred_1', table_sig, mock_evaluator)
        cache.get_results('pred_2', table_sig, mock_evaluator)
        cache.get_results('pred_3', 'table_hash_2', mock_evaluator)
        
        assert len(cache._result_cache) == 3
        
        # Invalidate table
        cache.invalidate_table(table_sig)
        
        # Only results for this table should be removed
        assert len(cache._result_cache) == 1
        assert ('pred_3', 'table_hash_2') in cache._result_cache


class TestBulkOperationCacheEffectiveness:
    """Verify caches provide measurable speedup in bulk scenarios."""

    def test_bulk_insert_with_cache(self):
        """Bulk inserts should benefit from serialization cache."""
        cache = SerializationCache(maxsize=256)
        
        serialize_count = [0]
        def counting_serializer(data):
            serialize_count[0] += 1
            return b'serialized'
        
        # Insert 100 documents with similar structure
        for i in range(100):
            doc = {'id': i, 'type': 'record', 'value': i % 10}
            cache.get(i, doc, counting_serializer)
        
        # With cache, should have far fewer serializations than docs
        # (different values cause different hashes, but caching structure helps)
        assert serialize_count[0] < 100, "Cache should reduce serializations"

    def test_repeated_query_cache_speedup(self, benchmark):
        """Repeated queries with cache should show measurable speedup."""
        cache = QueryCache(maxsize=128)
        
        pred_sig = 'test_predicate'
        table_sig = 'test_table'
        
        eval_time = 0.001  # Simulate 1ms evaluation
        eval_count = [0]
        
        def slow_evaluator():
            eval_count[0] += 1
            time.sleep(eval_time)
            return [1, 2, 3]
        
        # First query (cache miss)
        results1, hit1 = cache.get_results(pred_sig, table_sig, slow_evaluator)
        assert not hit1
        time_first = eval_time
        
        # Repeated queries (cache hits)
        start = time.perf_counter()
        for _ in range(10):
            cache.get_results(pred_sig, table_sig, slow_evaluator)
        time_repeated = time.perf_counter() - start
        
        # Should have only 1 evaluation total (all cache hits)
        assert eval_count[0] == 1, "Should not re-evaluate on cache hit"
        # Repeated queries should be much faster than evaluation time
        assert time_repeated < eval_time * 0.5, "Cache hits should be very fast"
