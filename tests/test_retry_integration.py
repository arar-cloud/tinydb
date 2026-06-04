"""Integration tests validating cross-retry state consistency."""
import pytest
from tenacity import retry, stop_after_attempt, wait_exponential

from tinydb import TinyDB
from tinydb.storages import MemoryStorage


@pytest.mark.integration
@pytest.mark.state_recovery
def test_insert_retry_consistency(db_with_recovery):
    """Validate database state remains consistent across retried insert operations."""
    db, assert_recovery = db_with_recovery
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),
    )
    def retryable_insert():
        db.insert({'test': 'data', 'status': 'inserted'})
    
    retryable_insert()
    assert_recovery()
    assert len(db) > 0, "Insert operation did not persist"


@pytest.mark.integration
@pytest.mark.state_recovery
def test_update_retry_idempotency(db_with_recovery):
    """Validate database state consistency for retried update operations (idempotency)."""
    db, assert_recovery = db_with_recovery
    doc_id = db.insert({'status': 'initial', 'count': 0})
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),
    )
    def retryable_update():
        db.update({'count': db.get(doc_id=doc_id)['count'] + 1}, doc_ids=[doc_id])
    
    retryable_update()
    assert_recovery()
    final_doc = db.get(doc_id=doc_id)
    assert final_doc is not None, "Update did not persist"


@pytest.mark.integration
@pytest.mark.state_recovery
def test_transient_failure_recovery(db_with_recovery, transient_failure_simulator):
    """Validate database recovery after simulated transient failures."""
    db, assert_recovery = db_with_recovery
    transient_failure_simulator.set_failure_count(2)
    
    def simulate_operation():
        if transient_failure_simulator.should_fail():
            raise RuntimeError("Simulated transient failure")
        return db.insert({'recovered': True})
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),
    )
    def retryable_operation():
        return simulate_operation()
    
    result = retryable_operation()
    assert_recovery()
    assert result is not None, "Operation did not complete successfully"


@pytest.mark.integration
@pytest.mark.fault_injection
def test_partial_write_recovery(db_with_recovery, chaos_injection):
    """Validate recovery from partial write failures."""
    db, assert_recovery = db_with_recovery
    chaos_injection.enable_partial_write()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.01, min=0.01, max=0.1),
    )
    def retryable_write():
        if chaos_injection.partial_write_enabled:
            chaos_injection.reset()
        return db.insert({'partial_write': 'completed'})
    
    result = retryable_write()
    assert_recovery()
    assert result is not None, "Partial write recovery failed"
