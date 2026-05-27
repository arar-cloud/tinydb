"""Comprehensive unit tests for core TinyDB functionality."""

import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage


@pytest.mark.unit
class TestDatabaseOperations:
    """Test suite for basic database CRUD operations."""

    def test_insert_single_document(self, memory_db: TinyDB) -> None:
        """Test insertion of a single document."""
        memory_db.drop_tables()
        doc_id = memory_db.insert({'name': 'test', 'value': 42})
        assert doc_id is not None
        assert memory_db.get(doc_id) is not None

    def test_insert_multiple_documents(self, memory_db: TinyDB) -> None:
        """Test insertion of multiple documents at once."""
        memory_db.drop_tables()
        docs = [{'id': i, 'name': f'doc_{i}'} for i in range(5)]
        doc_ids = memory_db.insert_multiple(docs)
        assert len(doc_ids) == 5
        assert len(memory_db) == 5

    def test_query_documents(self, sample_data_db: TinyDB) -> None:
        """Test querying documents with conditions."""
        User = Query()
        results = sample_data_db.search(User.age > 28)
        assert len(results) == 2
        assert all(doc['age'] > 28 for doc in results)

    def test_update_document(self, memory_db: TinyDB) -> None:
        """Test updating document fields."""
        memory_db.drop_tables()
        doc_id = memory_db.insert({'status': 'inactive', 'count': 0})
        memory_db.update({'status': 'active', 'count': 1}, doc_ids=[doc_id])
        updated = memory_db.get(doc_id)
        assert updated['status'] == 'active'
        assert updated['count'] == 1

    def test_delete_document(self, memory_db: TinyDB) -> None:
        """Test deleting a document."""
        memory_db.drop_tables()
        doc_id = memory_db.insert({'name': 'to_delete'})
        memory_db.remove(doc_ids=[doc_id])
        assert memory_db.get(doc_id) is None
        assert len(memory_db) == 0

    def test_delete_with_condition(self, sample_data_db: TinyDB) -> None:
        """Test conditional document deletion."""
        User = Query()
        initial_count = len(sample_data_db)
        sample_data_db.remove(User.status == 'inactive')
        assert len(sample_data_db) == initial_count - 1

    def test_all_documents(self, sample_data_db: TinyDB) -> None:
        """Test retrieving all documents."""
        all_docs = sample_data_db.all()
        assert len(all_docs) == 4
        assert all('name' in doc for doc in all_docs)

    def test_count_documents(self, sample_data_db: TinyDB) -> None:
        """Test counting documents."""
        count = len(sample_data_db)
        assert count == 4

    def test_clear_table(self, memory_db: TinyDB) -> None:
        """Test clearing all documents from a table."""
        assert len(memory_db) > 0
        memory_db.truncate()
        assert len(memory_db) == 0

    def test_get_by_id(self, sample_data_db: TinyDB) -> None:
        """Test retrieving a document by ID."""
        first_doc = sample_data_db.all()[0]
        doc_id = first_doc.doc_id
        retrieved = sample_data_db.get(doc_id)
        assert retrieved is not None
        assert retrieved.doc_id == doc_id


@pytest.mark.unit
class TestQueryOperations:
    """Test suite for query functionality."""

    def test_query_equality(self, sample_data_db: TinyDB) -> None:
        """Test equality query."""
        User = Query()
        results = sample_data_db.search(User.name == 'Alice')
        assert len(results) == 1
        assert results[0]['name'] == 'Alice'

    def test_query_greater_than(self, sample_data_db: TinyDB) -> None:
        """Test greater-than query."""
        User = Query()
        results = sample_data_db.search(User.age > 26)
        assert all(doc['age'] > 26 for doc in results)

    def test_query_less_than(self, sample_data_db: TinyDB) -> None:
        """Test less-than query."""
        User = Query()
        results = sample_data_db.search(User.age < 30)
        assert all(doc['age'] < 30 for doc in results)

    def test_query_and_condition(self, sample_data_db: TinyDB) -> None:
        """Test AND condition in query."""
        User = Query()
        results = sample_data_db.search((User.age > 25) & (User.status == 'active'))
        assert all(doc['age'] > 25 and doc['status'] == 'active' for doc in results)

    def test_query_or_condition(self, sample_data_db: TinyDB) -> None:
        """Test OR condition in query."""
        User = Query()
        results = sample_data_db.search((User.name == 'Alice') | (User.name == 'Bob'))
        assert len(results) == 2


@pytest.mark.unit
class TestDataSerialization:
    """Test suite for data serialization and storage."""

    def test_json_serialization(self, sample_data_db: TinyDB, serialization_validator) -> None:
        """Test that documents can be JSON serialized without data loss."""
        docs = sample_data_db.all()
        for doc in docs:
            # Remove doc_id as it's internal
            doc_dict = {k: v for k, v in doc.items() if k != 'doc_id'}
            assert serialization_validator(doc_dict)

    def test_complex_data_types(self, empty_db: TinyDB) -> None:
        """Test storage of various Python data types."""
        doc_id = empty_db.insert({
            'string': 'test',
            'integer': 42,
            'float': 3.14,
            'boolean': True,
            'null': None,
            'list': [1, 2, 3],
            'dict': {'nested': 'value'}
        })
        retrieved = empty_db.get(doc_id)
        assert retrieved['string'] == 'test'
        assert retrieved['integer'] == 42
        assert retrieved['float'] == 3.14
        assert retrieved['boolean'] is True
        assert retrieved['null'] is None
        assert retrieved['list'] == [1, 2, 3]
        assert retrieved['dict'] == {'nested': 'value'}


@pytest.mark.stability
class TestDatabaseStability:
    """Test suite for database stability and edge cases."""

    def test_empty_query_result(self, sample_data_db: TinyDB) -> None:
        """Test querying with no matching results."""
        User = Query()
        results = sample_data_db.search(User.name == 'NonExistent')
        assert results == []

    def test_duplicate_insertion(self, memory_db: TinyDB) -> None:
        """Test that duplicate data can be inserted (no unique constraint)."""
        memory_db.drop_tables()
        doc1 = memory_db.insert({'value': 'duplicate'})
        doc2 = memory_db.insert({'value': 'duplicate'})
        assert doc1 != doc2
        assert len(memory_db) == 2

    def test_update_nonexistent_document(self, memory_db: TinyDB) -> None:
        """Test updating non-existent document IDs."""
        memory_db.drop_tables()
        # Should not raise, just do nothing
        memory_db.update({'value': 'new'}, doc_ids=[9999])
        assert len(memory_db) == 0

    def test_large_batch_insert(self, memory_db: TinyDB) -> None:
        """Test inserting a large batch of documents."""
        memory_db.drop_tables()
        large_batch = [{'index': i, 'data': f'doc_{i}'} for i in range(1000)]
        doc_ids = memory_db.insert_multiple(large_batch)
        assert len(doc_ids) == 1000
        assert len(memory_db) == 1000

    def test_table_isolation(self, memory_db: TinyDB) -> None:
        """Test that different tables are isolated."""
        memory_db.drop_tables()
        table_a = memory_db.table('table_a')
        table_b = memory_db.table('table_b')
        
        table_a.insert({'name': 'in_a'})
        table_b.insert({'name': 'in_b'})
        
        assert len(table_a) == 1
        assert len(table_b) == 1
        assert table_a.all()[0]['name'] == 'in_a'
        assert table_b.all()[0]['name'] == 'in_b'
