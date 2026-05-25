"""Smoke tests to verify test configuration and basic functionality."""
import pytest
from tinydb import TinyDB
from tinydb.storages import MemoryStorage


@pytest.mark.backend
class TestBackendSmoke:
    """Backend smoke tests."""

    def test_backend_db_fixture(self, backend_db):
        """Test backend_db fixture is available."""
        assert backend_db is not None
        assert isinstance(backend_db, TinyDB)

    def test_backend_memory_db_fixture(self, backend_memory_db):
        """Test backend_memory_db fixture is available."""
        assert backend_memory_db is not None
        assert isinstance(backend_memory_db, TinyDB)

    def test_mock_storage_fixture(self, mock_storage):
        """Test mock_storage fixture is available."""
        assert mock_storage is not None

    def test_backend_db_operations(self, backend_db):
        """Test basic backend database operations."""
        table = backend_db.table('test_table')
        table.insert({'name': 'backend_test', 'value': 42})
        results = table.all()
        assert len(results) == 1
        assert results[0]['name'] == 'backend_test'


@pytest.mark.mobile
class TestMobileSmoke:
    """Mobile smoke tests."""

    def test_mobile_db_fixture(self, mobile_db):
        """Test mobile_db fixture is available."""
        assert mobile_db is not None
        assert isinstance(mobile_db, TinyDB)

    def test_constrained_db_fixture(self, constrained_db):
        """Test constrained_db fixture is available."""
        assert constrained_db is not None
        assert isinstance(constrained_db, TinyDB)

    def test_mock_network_fixture(self, mock_network):
        """Test mock_network fixture is available."""
        assert mock_network is not None
        assert mock_network.is_connected is True

    def test_mobile_db_operations(self, mobile_db):
        """Test basic mobile database operations."""
        table = mobile_db.table('mobile_table')
        table.insert({'device': 'mobile', 'data': 'test'})
        results = table.all()
        assert len(results) == 1
        assert results[0]['device'] == 'mobile'


@pytest.mark.unit
def test_db_fixture(db):
    """Test parametrized db fixture works."""
    assert db is not None
    assert isinstance(db, TinyDB)
    results = db.all()
    assert len(results) == 3


@pytest.mark.unit
def test_storage_fixture(storage):
    """Test storage fixture is available."""
    assert storage is not None
