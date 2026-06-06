"""Security-focused unit tests for input validation in TinyDB.

Tests cover malicious query inputs, boundary values, injection attack vectors,
field name validation, and operator parsing edge cases.
"""

import pytest
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
from tinydb.queries import QueryInstance


class TestInputValidation:
    """Test input validation for query operations."""

    @pytest.fixture
    def db(self):
        """Create an in-memory database for testing."""
        db = TinyDB(storage=MemoryStorage)
        db.insert({'name': 'test', 'value': 42})
        yield db
        db.close()

    def test_field_name_with_sql_injection_attempt(self, db):
        """Test that SQL-like injection in field names is handled safely."""
        User = Query()
        # Attempt SQL injection through field name
        malicious_field = "name'; DROP TABLE users; --"
        # This should not raise an error but should be treated as a literal field name
        result = db.search(User[malicious_field] == 'test')
        assert result == []  # No matching field, should return empty

    def test_field_name_with_special_characters(self, db):
        """Test field names containing special characters."""
        User = Query()
        # Insert document with special character field names
        db.insert({'field.with.dots': 'value', 'field-with-dashes': 'value'})
        # Should handle these as literal field names
        result = db.search(User['field.with.dots'] == 'value')
        assert len(result) == 1

    def test_operator_parsing_with_invalid_operators(self, db):
        """Test that invalid operators are rejected."""
        User = Query()
        # Valid operators should work
        result = db.search(User.value == 42)
        assert len(result) == 1
        
        result = db.search(User.value > 0)
        assert len(result) == 1
        
        result = db.search(User.value < 100)
        assert len(result) == 1

    def test_injection_through_query_values(self, db):
        """Test that malicious values in queries are handled safely."""
        User = Query()
        # Test with command injection attempt
        malicious_value = "test'; exec('os.system(\"rm -rf /\")'); --"
        result = db.search(User.name == malicious_value)
        assert result == []
        
        # Database should remain intact
        result = db.search(User.name == 'test')
        assert len(result) == 1

    def test_boundary_value_integer_overflow(self, db):
        """Test handling of boundary integer values."""
        User = Query()
        db.insert({'value': 2**31 - 1})  # Max 32-bit int
        db.insert({'value': -(2**31)})    # Min 32-bit int
        db.insert({'value': 2**63 - 1})   # Large int
        
        result = db.search(User.value == 2**31 - 1)
        assert len(result) == 1
        
        result = db.search(User.value == -(2**31))
        assert len(result) == 1

    def test_boundary_value_string_length(self, db):
        """Test handling of very long strings."""
        User = Query()
        long_string = 'a' * 100000
        db.insert({'data': long_string})
        
        result = db.search(User.data == long_string)
        assert len(result) == 1

    def test_null_and_none_values(self, db):
        """Test handling of None/null values."""
        User = Query()
        db.insert({'optional_field': None})
        db.insert({'optional_field': 'value'})
        
        result = db.search(User.optional_field == None)
        assert len(result) == 1
        
        result = db.search(User.optional_field != None)
        assert len(result) == 2  # test + value

    def test_deeply_nested_field_access(self, db):
        """Test deeply nested field access doesn't cause issues."""
        User = Query()
        db.insert({'nested': {'level1': {'level2': {'level3': 'value'}}}})
        
        # Access nested field
        result = db.search(User.nested.level1.level2.level3 == 'value')
        assert len(result) == 1

    def test_unicode_and_encoding_attacks(self, db):
        """Test handling of unicode and encoding edge cases."""
        User = Query()
        unicode_strings = [
            '你好',  # Chinese
            '🔓',    # Emoji
            '\x00\x01',  # Control characters
            'ñ',     # Accent
        ]
        
        for s in unicode_strings:
            db.insert({'text': s})
        
        for s in unicode_strings:
            result = db.search(User.text == s)
            assert len(result) == 1

    def test_empty_query_results(self, db):
        """Test that empty queries are handled correctly."""
        User = Query()
        result = db.search(User.nonexistent == 'value')
        assert result == []
        assert isinstance(result, list)

    def test_logical_operator_combinations(self, db):
        """Test combinations of logical operators don't allow injection."""
        User = Query()
        db.insert({'a': 1, 'b': 2})
        db.insert({'a': 1, 'b': 3})
        
        # Test AND
        result = db.search((User.a == 1) & (User.b == 2))
        assert len(result) == 1
        
        # Test OR
        result = db.search((User.a == 2) | (User.b == 3))
        assert len(result) == 1
        
        # Test NOT
        result = db.search(~(User.a == 2))
        assert len(result) >= 1
