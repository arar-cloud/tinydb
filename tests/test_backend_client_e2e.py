"""End-to-end tests for backend-client communication patterns.

Tests simulate complete request/response cycles for both mobile and web clients,
verifying data consistency, error handling, and communication protocol compliance.
"""

import pytest
from typing import Dict, Any, List, Optional
from tinydb import TinyDB
from tinydb.storages import MemoryStorage
import json
import logging
from threading import Event
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class MockAPIResponse:
    """Simulate API response from backend."""
    
    def __init__(self, status: int, data: Any = None, error: Optional[str] = None):
        self.status = status
        self.data = data
        self.error = error
    
    def to_json(self) -> str:
        return json.dumps({
            'status': self.status,
            'data': self.data,
            'error': self.error
        })


class BackendClient:
    """Simulate backend client interface."""
    
    def __init__(self, db: TinyDB):
        self.db = db
        self.request_count = 0
        self.error_count = 0
    
    def get_record(self, record_id: int) -> MockAPIResponse:
        """GET /api/record/{id}"""
        self.request_count += 1
        try:
            record = self.db.get(doc_id=record_id)
            if record is None:
                self.error_count += 1
                return MockAPIResponse(404, error="Record not found")
            return MockAPIResponse(200, data=record)
        except Exception as e:
            self.error_count += 1
            return MockAPIResponse(500, error=str(e))
    
    def list_records(self, query_filter: Optional[str] = None) -> MockAPIResponse:
        """GET /api/records?filter=..."""
        self.request_count += 1
        try:
            records = self.db.all()
            if query_filter:
                records = [r for r in records if query_filter.lower() in str(r).lower()]
            return MockAPIResponse(200, data=records)
        except Exception as e:
            self.error_count += 1
            return MockAPIResponse(500, error=str(e))
    
    def create_record(self, data: Dict[str, Any]) -> MockAPIResponse:
        """POST /api/records"""
        self.request_count += 1
        try:
            doc_id = self.db.insert(data)
            return MockAPIResponse(201, data={'id': doc_id, **data})
        except Exception as e:
            self.error_count += 1
            return MockAPIResponse(500, error=str(e))
    
    def update_record(self, record_id: int, data: Dict[str, Any]) -> MockAPIResponse:
        """PUT /api/record/{id}"""
        self.request_count += 1
        try:
            existing = self.db.get(doc_id=record_id)
            if existing is None:
                self.error_count += 1
                return MockAPIResponse(404, error="Record not found")
            self.db.update(data, doc_ids=[record_id])
            updated = self.db.get(doc_id=record_id)
            return MockAPIResponse(200, data=updated)
        except Exception as e:
            self.error_count += 1
            return MockAPIResponse(500, error=str(e))
    
    def delete_record(self, record_id: int) -> MockAPIResponse:
        """DELETE /api/record/{id}"""
        self.request_count += 1
        try:
            existing = self.db.get(doc_id=record_id)
            if existing is None:
                self.error_count += 1
                return MockAPIResponse(404, error="Record not found")
            self.db.remove(doc_ids=[record_id])
            return MockAPIResponse(204, data=None)
        except Exception as e:
            self.error_count += 1
            return MockAPIResponse(500, error=str(e))


@pytest.mark.integration
class TestBackendClientE2E:
    """End-to-end tests for backend-client communication."""

    def test_simple_request_response_cycle(self):
        """Verify basic request/response cycle works correctly."""
        db = TinyDB(storage=MemoryStorage)
        client = BackendClient(db)
        try:
            # Create
            create_resp = client.create_record({'name': 'Test Item', 'value': 100})
            assert create_resp.status == 201
            created_id = create_resp.data['id']
            
            # Read
            get_resp = client.get_record(created_id)
            assert get_resp.status == 200
            assert get_resp.data['name'] == 'Test Item'
            
            # Update
            update_resp = client.update_record(created_id, {'value': 200})
            assert update_resp.status == 200
            assert update_resp.data['value'] == 200
            
            # Delete
            delete_resp = client.delete_record(created_id)
            assert delete_resp.status == 204
            
            # Verify deleted
            get_deleted_resp = client.get_record(created_id)
            assert get_deleted_resp.status == 404
            
            logger.info(f"E2E cycle completed: {client.request_count} requests, {client.error_count} errors")
        finally:
            db.close()

    def test_error_handling_in_request_cycle(self):
        """Verify proper error handling for various failure scenarios."""
        db = TinyDB(storage=MemoryStorage)
        client = BackendClient(db)
        try:
            # Get non-existent record
            resp_404 = client.get_record(99999)
            assert resp_404.status == 404
            
            # Update non-existent record
            resp_update_404 = client.update_record(99999, {'data': 'value'})
            assert resp_update_404.status == 404
            
            # Delete non-existent record
            resp_delete_404 = client.delete_record(99999)
            assert resp_delete_404.status == 404
            
            assert client.error_count == 3
            logger.info(f"Error handling verified: {client.error_count} errors captured correctly")
        finally:
            db.close()

    def test_concurrent_client_requests(self):
        """Verify multiple clients can make concurrent requests."""
        db = TinyDB(storage=MemoryStorage)
        
        # Pre-populate with test data
        for i in range(50):
            db.insert({'id': i, 'client': f'client_{i % 5}', 'data': f'data_{i}'})
        
        try:
            clients = [BackendClient(db) for _ in range(5)]
            results = []
            
            def client_request_cycle(client_idx):
                client = clients[client_idx]
                # Each client makes multiple requests
                list_resp = client.list_records()
                get_resp = client.get_record(client_idx + 1)
                create_resp = client.create_record({'client': client_idx, 'concurrent': True})
                return {
                    'client': client_idx,
                    'requests': client.request_count,
                    'errors': client.error_count,
                    'list_status': list_resp.status,
                    'get_status': get_resp.status,
                    'create_status': create_resp.status
                }
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(client_request_cycle, i) for i in range(5)]
                for future in as_completed(futures):
                    results.append(future.result())
            
            # Verify all requests completed
            total_requests = sum(r['requests'] for r in results)
            total_errors = sum(r['errors'] for r in results)
            assert total_requests > 0
            assert total_errors == 0
            
            final_db_size = len(db.all())
            assert final_db_size == 55  # 50 pre-populated + 5 created
            
            logger.info(f"Concurrent requests verified: {total_requests} total requests, {final_db_size} records")
        finally:
            db.close()

    def test_data_consistency_across_operations(self):
        """Verify data consistency across multiple operations."""
        db = TinyDB(storage=MemoryStorage)
        client = BackendClient(db)
        try:
            # Create multiple records
            ids = []
            for i in range(10):
                resp = client.create_record({'index': i, 'status': 'active', 'value': i * 10})
                ids.append(resp.data['id'])
            
            # Verify all created
            list_resp = client.list_records()
            assert len(list_resp.data) == 10
            
            # Update some records
            for doc_id in ids[::2]:  # Every other record
                client.update_record(doc_id, {'status': 'inactive'})
            
            # Verify state
            all_records = db.all()
            active = [r for r in all_records if r['status'] == 'active']
            inactive = [r for r in all_records if r['status'] == 'inactive']
            
            assert len(active) == 5
            assert len(inactive) == 5
            
            logger.info(f"Data consistency verified: 5 active, 5 inactive out of 10 total")
        finally:
            db.close()

    def test_bulk_operations_performance(self):
        """Verify bulk operations complete efficiently."""
        db = TinyDB(storage=MemoryStorage)
        client = BackendClient(db)
        try:
            import time
            
            # Bulk create
            start = time.time()
            for i in range(100):
                client.create_record({'bulk_index': i, 'timestamp': time.time()})
            create_time = time.time() - start
            
            # Bulk read
            start = time.time()
            list_resp = client.list_records()
            list_time = time.time() - start
            
            assert len(list_resp.data) == 100
            assert create_time < 5.0, f"Bulk create took {create_time}s"
            assert list_time < 1.0, f"Bulk list took {list_time}s"
            
            logger.info(f"Bulk operations: create {create_time:.3f}s, list {list_time:.3f}s")
        finally:
            db.close()

    def test_serialization_round_trip(self):
        """Verify data survives JSON serialization round-trip."""
        db = TinyDB(storage=MemoryStorage)
        client = BackendClient(db)
        try:
            # Create record with various data types
            original_data = {
                'name': 'Test',
                'count': 42,
                'ratio': 3.14,
                'active': True,
                'tags': ['a', 'b', 'c'],
                'metadata': {'key': 'value', 'nested': {'deep': True}}
            }
            
            create_resp = client.create_record(original_data)
            record_id = create_resp.data['id']
            
            # Serialize to JSON
            json_str = create_resp.to_json()
            deserialized = json.loads(json_str)
            
            # Verify round-trip
            assert deserialized['data']['name'] == 'Test'
            assert deserialized['data']['count'] == 42
            assert deserialized['data']['active'] is True
            assert len(deserialized['data']['tags']) == 3
            
            logger.info("Serialization round-trip verified")
        finally:
            db.close()
