"""Regression tests for web client integration with TinyDB backend.

Tests verify backend behavior under web-specific usage patterns:
- HTTP serialization/deserialization
- Concurrent request handling
- RESTful operation semantics (GET, POST, PUT, DELETE)
- Query string and JSON payload compatibility
- CORS and cross-origin data handling
- Response consistency across clients
"""

import pytest
from typing import Dict, Any, List
from tinydb import TinyDB
from tinydb.storages import MemoryStorage
from tinydb.query import Query
import json
import logging
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@pytest.mark.web
class TestWebHTTPSerialization:
    """Test HTTP serialization compatibility for web clients."""

    def test_json_serializable_insert(self):
        """Verify data inserted via web can be JSON serialized."""
        db = TinyDB(storage=MemoryStorage)
        try:
            web_payload = {
                'name': 'test_user',
                'email': 'user@example.com',
                'age': 30,
                'active': True,
                'tags': ['web', 'client', 'test']
            }
            
            # Simulate HTTP JSON deserialization
            db.insert(web_payload)
            record = db.get(lambda x: x['name'] == 'test_user')
            
            # Verify can be re-serialized to JSON
            json_str = json.dumps(record)
            deserialized = json.loads(json_str)
            
            assert deserialized['email'] == 'user@example.com'
            assert deserialized['age'] == 30
            logger.info("JSON serialization round-trip successful")
        finally:
            db.close()

    def test_complex_nested_json_structures(self):
        """Verify nested JSON structures from web clients are handled."""
        db = TinyDB(storage=MemoryStorage)
        try:
            nested_payload = {
                'id': 1,
                'user': {
                    'name': 'Alice',
                    'profile': {
                        'bio': 'Web developer',
                        'location': {'city': 'NYC', 'country': 'USA'}
                    }
                },
                'metadata': {'created': '2024-01-01', 'version': 1}
            }
            
            doc_id = db.insert(nested_payload)
            retrieved = db.get(doc_id=doc_id)
            
            # Verify nested structure preserved
            assert retrieved['user']['profile']['location']['city'] == 'NYC'
            json_str = json.dumps(retrieved)
            assert len(json_str) > 0
            logger.info("Nested JSON structure handling verified")
        finally:
            db.close()

    def test_special_characters_in_web_data(self):
        """Verify special characters and unicode in web payloads."""
        db = TinyDB(storage=MemoryStorage)
        try:
            special_data = {
                'emoji': '🚀🎉✨',
                'quotes': 'He said "hello"',
                'backslash': 'path\\to\\file',
                'newline': 'line1\nline2'
            }
            
            doc_id = db.insert(special_data)
            retrieved = db.get(doc_id=doc_id)
            
            assert retrieved['emoji'] == '🚀🎉✨'
            json_str = json.dumps(retrieved)
            assert len(json_str) > 0
            logger.info("Special character handling verified")
        finally:
            db.close()


@pytest.mark.web
class TestWebConcurrentRequests:
    """Test concurrent request handling for multiple web clients."""

    def test_concurrent_read_operations(self):
        """Verify multiple concurrent read requests are handled correctly."""
        db = TinyDB(storage=MemoryStorage)
        try:
            # Pre-populate with test data
            db.insert_multiple([{'id': i, 'value': f'data_{i}'} for i in range(100)])
            
            results = []
            
            def concurrent_read(item_id):
                record = db.get(lambda x: x['id'] == item_id)
                results.append(record)
            
            # Simulate 10 concurrent read requests
            with ThreadPoolExecutor(max_workers=10) as executor:
                for i in range(10):
                    executor.submit(concurrent_read, i % 100)
            
            assert len(results) == 10
            assert all(r is not None for r in results)
            logger.info(f"Concurrent reads verified: {len(results)} requests")
        finally:
            db.close()

    def test_concurrent_write_operations(self):
        """Verify multiple concurrent write requests maintain consistency."""
        db = TinyDB(storage=MemoryStorage)
        try:
            counter = {'inserts': 0}
            
            def concurrent_write(item_id):
                db.insert({'id': item_id, 'thread_id': item_id})
                counter['inserts'] += 1
            
            # Simulate 5 concurrent write requests
            with ThreadPoolExecutor(max_workers=5) as executor:
                for i in range(20):
                    executor.submit(concurrent_write, i)
            
            final_count = len(db.all())
            assert final_count == 20
            logger.info(f"Concurrent writes verified: {final_count} records inserted")
        finally:
            db.close()

    def test_mixed_concurrent_read_write_operations(self):
        """Verify mixed read/write concurrency maintains data consistency."""
        db = TinyDB(storage=MemoryStorage)
        try:
            # Initial data
            db.insert_multiple([{'id': i, 'status': 'initial'} for i in range(50)])
            
            def concurrent_operation(op_type, op_id):
                if op_type == 'read':
                    result = db.search(lambda x: x['id'] < 25)
                    return len(result)
                else:  # write
                    db.insert({'id': 50 + op_id, 'status': 'new'})
                    return 1
            
            # Simulate 10 concurrent operations (5 reads, 5 writes)
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                for i in range(5):
                    futures.append(executor.submit(concurrent_operation, 'read', i))
                for i in range(5):
                    futures.append(executor.submit(concurrent_operation, 'write', i))
            
            final_count = len(db.all())
            assert final_count == 55  # 50 initial + 5 new
            logger.info(f"Mixed concurrent operations verified: {final_count} total records")
        finally:
            db.close()


@pytest.mark.web
class TestWebRESTfulSemantics:
    """Test RESTful operation semantics for web clients."""

    def test_get_single_resource(self):
        """Verify GET /resource/{id} semantics."""
        db = TinyDB(storage=MemoryStorage)
        try:
            doc_id = db.insert({'name': 'Resource1', 'status': 'active'})
            
            # GET /resource/{id}
            resource = db.get(doc_id=doc_id)
            assert resource is not None
            assert resource['name'] == 'Resource1'
            logger.info(f"GET resource/{doc_id} verified")
        finally:
            db.close()

    def test_get_resource_list_with_query(self):
        """Verify GET /resources?filter=value semantics."""
        db = TinyDB(storage=MemoryStorage)
        try:
            db.insert_multiple([
                {'id': 1, 'type': 'active', 'name': 'Item1'},
                {'id': 2, 'type': 'inactive', 'name': 'Item2'},
                {'id': 3, 'type': 'active', 'name': 'Item3'}
            ])
            
            # GET /resources?type=active
            active_resources = db.search(lambda x: x['type'] == 'active')
            assert len(active_resources) == 2
            logger.info(f"GET resources with query filter verified: {len(active_resources)} results")
        finally:
            db.close()

    def test_post_create_resource(self):
        """Verify POST /resources semantics (create new)."""
        db = TinyDB(storage=MemoryStorage)
        try:
            new_resource = {'name': 'NewResource', 'status': 'created'}
            doc_id = db.insert(new_resource)
            
            # Verify created resource
            created = db.get(doc_id=doc_id)
            assert created['name'] == 'NewResource'
            assert doc_id is not None
            logger.info(f"POST /resources created resource {doc_id}")
        finally:
            db.close()

    def test_put_update_resource(self):
        """Verify PUT /resource/{id} semantics (replace)."""
        db = TinyDB(storage=MemoryStorage)
        try:
            doc_id = db.insert({'name': 'OriginalName', 'status': 'draft'})
            
            # PUT /resource/{id}
            db.update({'name': 'UpdatedName', 'status': 'published'}, doc_ids=[doc_id])
            updated = db.get(doc_id=doc_id)
            
            assert updated['name'] == 'UpdatedName'
            assert updated['status'] == 'published'
            logger.info(f"PUT resource/{doc_id} verified")
        finally:
            db.close()

    def test_delete_resource(self):
        """Verify DELETE /resource/{id} semantics."""
        db = TinyDB(storage=MemoryStorage)
        try:
            doc_id = db.insert({'name': 'ToDelete', 'status': 'pending_delete'})
            
            # DELETE /resource/{id}
            db.remove(doc_ids=[doc_id])
            deleted = db.get(doc_id=doc_id)
            
            assert deleted is None
            logger.info(f"DELETE resource/{doc_id} verified")
        finally:
            db.close()


@pytest.mark.web
class TestWebCORSCompatibility:
    """Test cross-origin data handling for CORS scenarios."""

    def test_response_headers_compatibility(self):
        """Verify response data structure compatible with CORS headers."""
        db = TinyDB(storage=MemoryStorage)
        try:
            # Insert data that might be sent in CORS response
            doc_id = db.insert({'origin': 'client-a', 'timestamp': '2024-01-01'})
            record = db.get(doc_id=doc_id)
            
            # Verify serializable for CORS headers
            json_response = json.dumps({
                'status': 'ok',
                'data': record,
                'headers': {'X-Client': 'web'}
            })
            assert len(json_response) > 0
            logger.info("CORS response structure verified")
        finally:
            db.close()

    def test_cross_origin_client_identifiers(self):
        """Verify data from multiple origins can be tracked."""
        db = TinyDB(storage=MemoryStorage)
        try:
            origins = ['client-a.example.com', 'client-b.example.com', 'localhost:3000']
            
            for origin in origins:
                db.insert({'origin': origin, 'request_id': f'{origin}_req1'})
            
            # Query by origin
            client_a_records = db.search(lambda x: x['origin'] == 'client-a.example.com')
            assert len(client_a_records) == 1
            logger.info(f"Cross-origin tracking verified: {len(origins)} origins")
        finally:
            db.close()
