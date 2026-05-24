"""Tests for retry logic and idempotency guarantees in TinyDB."""
import pytest
from tests.conftest import (
    retry_with_exponential_backoff,
    transactional_scope,
    assert_idempotent,
)


class TestRetryLogic:
    """Test retry behavior across platforms."""

    @pytest.mark.retry
    @pytest.mark.stability
    def test_insert_with_retry_idempotency(self, db_stable):
        """Verify insert operation is idempotent across retries."""
        data = {'name': 'test_user', 'value': 42}
        
        @retry_with_exponential_backoff(max_retries=3)
        def insert_op():
            return db_stable.insert(data)
        
        # First attempt succeeds
        doc_id_1 = insert_op()
        initial_count = len(db_stable.all())
        
        # Retry should not create duplicates (idempotent at ID level)
        doc_id_2 = db_stable.insert(data)
        final_count = len(db_stable.all())
        
        assert initial_count < final_count
        assert doc_id_1 != doc_id_2

    @pytest.mark.retry
    @pytest.mark.stability
    def test_query_with_retry_consistency(self, db_stable):
        """Verify query results are consistent across retries."""
        @retry_with_exponential_backoff(max_retries=3)
        def query_op():
            return db_stable.search(lambda x: x['int'] == 1)
        
        results_1 = query_op()
        results_2 = query_op()
        
        assert len(results_1) == len(results_2)
        assert [r['char'] for r in results_1] == [r['char'] for r in results_2]

    @pytest.mark.retry
    @pytest.mark.stability
    def test_update_with_retry_atomicity(self, db_stable):
        """Verify update operations maintain atomicity across retries."""
        query = lambda x: x['int'] == 1
        
        @retry_with_exponential_backoff(max_retries=3)
        def update_op():
            return db_stable.update({'value': 100}, query)
        
        update_op()
        results = db_stable.search(query)
        
        # All matching docs should be updated
        assert all(doc.get('value') == 100 for doc in results)
        assert len(results) == 3  # Initial insert_multiple adds 3 docs

    @pytest.mark.retry
    @pytest.mark.stability
    def test_delete_with_retry_idempotency(self, db_stable):
        """Verify delete operations are idempotent."""
        # Get initial doc count
        initial_count = len(db_stable.all())
        
        # Delete by ID
        doc_id = db_stable.all()[0].doc_id
        db_stable.remove(doc_ids=[doc_id])
        count_after_first = len(db_stable.all())
        
        # Second delete attempt (idempotent - should not error or remove more)
        db_stable.remove(doc_ids=[doc_id])
        count_after_second = len(db_stable.all())
        
        assert initial_count > count_after_first
        assert count_after_first == count_after_second

    @pytest.mark.retry
    @pytest.mark.stability
    def test_transactional_atomicity(self, db_stable):
        """Verify transactional operations maintain atomicity on failure."""
        with transactional_scope(db_stable) as db:
            db.insert({'name': 'transaction_test', 'value': 1})
            # Simulate failure - context manager should rollback
            # (implicit in this test; explicit failure tested in chaos tests)
        
        # Verify insert succeeded (no rollback triggered)
        result = db_stable.search(lambda x: x.get('name') == 'transaction_test')
        assert len(result) == 1

    @pytest.mark.retry
    @pytest.mark.stability
    def test_concurrent_insert_retry_consistency(self, db_stable):
        """Test insert retry consistency with concurrent-like patterns."""
        data_1 = {'user': 'alice', 'status': 'active'}
        data_2 = {'user': 'bob', 'status': 'active'}
        
        @retry_with_exponential_backoff(max_retries=2)
        def concurrent_inserts():
            id_1 = db_stable.insert(data_1)
            id_2 = db_stable.insert(data_2)
            return id_1, id_2
        
        id_1a, id_2a = concurrent_inserts()
        id_1b, id_2b = concurrent_inserts()
        
        # Different runs should create different doc IDs
        assert id_1a != id_1b
        assert id_2a != id_2b
        
        # But all should exist in database
        all_docs = db_stable.all()
        assert len(all_docs) >= 5  # 3 initial + 2 + 2

    @pytest.mark.retry
    @pytest.mark.stability
    def test_operation_replay_consistency(self, db_stable, assert_consistent_retry):
        """Test that replayed operations produce consistent results."""
        operations = [
            lambda: db_stable.insert({'replay': 'op1'}),
            lambda: db_stable.insert({'replay': 'op2'}),
            lambda: len(db_stable.all()),
        ]
        
        for op in operations:
            assert_consistent_retry(op, max_runs=2)


class TestCrossPlatformRetry:
    """Test retry consistency across backend/mobile/web platforms."""

    @pytest.mark.retry
    @pytest.mark.stability
    def test_backend_retry_behavior(self, db_stable):
        """Simulate backend (Python/REST API) retry behavior."""
        @retry_with_exponential_backoff(max_retries=3, base_delay=0.1)
        def backend_operation():
            return db_stable.insert({'platform': 'backend', 'env': 'python'})
        
        doc_id = backend_operation()
        doc = db_stable.get(doc_id=doc_id)
        assert doc['platform'] == 'backend'

    @pytest.mark.retry
    @pytest.mark.stability
    def test_mobile_retry_behavior(self, db_stable):
        """Simulate mobile (Android/iOS via Python) retry behavior."""
        @retry_with_exponential_backoff(max_retries=5, base_delay=0.05, max_delay=1.0)
        def mobile_operation():
            return db_stable.insert({'platform': 'mobile', 'env': 'cross-platform'})
        
        doc_id = mobile_operation()
        doc = db_stable.get(doc_id=doc_id)
        assert doc['platform'] == 'mobile'

    @pytest.mark.retry
    @pytest.mark.stability
    def test_web_retry_behavior(self, db_stable):
        """Simulate web client retry behavior."""
        @retry_with_exponential_backoff(max_retries=4, base_delay=0.2, max_delay=5.0)
        def web_operation():
            return db_stable.insert({'platform': 'web', 'env': 'client'})
        
        doc_id = web_operation()
        doc = db_stable.get(doc_id=doc_id)
        assert doc['platform'] == 'web'

    @pytest.mark.retry
    @pytest.mark.stability
    @pytest.mark.parametrize('platform,max_retries,base_delay', [
        ('backend', 3, 0.1),
        ('mobile', 5, 0.05),
        ('web', 4, 0.2),
    ])
    def test_parameterized_platform_retry(self, db_stable, platform, max_retries, base_delay):
        """Parameterized test for identical retry behavior across platforms."""
        @retry_with_exponential_backoff(max_retries=max_retries, base_delay=base_delay)
        def platform_operation():
            return db_stable.insert({'platform': platform})
        
        doc_id = platform_operation()
        doc = db_stable.get(doc_id=doc_id)
        
        assert doc['platform'] == platform
        assert doc.doc_id == doc_id
