"""
Unit tests for leviathanctl API endpoints.
"""
import pytest
import os
from fastapi.testclient import TestClient
from datetime import datetime

from leviathan.control_plane.api import app, initialize_stores
from leviathan.graph.schema import NodeType, EdgeType


class TestLeviathanctlAPIEndpoints:
    """Test API endpoints for leviathanctl."""
    
    def setup_method(self):
        """Set up test client and stores."""
        # Set required environment variable
        os.environ["LEVIATHAN_CONTROL_PLANE_TOKEN"] = "test-token-12345"
        
        # Initialize stores
        initialize_stores()
        
        # Create test client
        self.client = TestClient(app)
        self.token = "test-token-12345"
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_list_attempts_unauthorized(self):
        """Should return 401 without valid token."""
        response = self.client.get("/v1/attempts")
        assert response.status_code == 401
    
    def test_list_attempts_empty(self):
        """Should return empty list when no attempts."""
        response = self.client.get("/v1/attempts", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert 'attempts' in data
        assert 'count' in data
        assert data['count'] == 0
    
    def test_list_attempts_with_limit(self):
        """Should respect limit parameter."""
        response = self.client.get("/v1/attempts?limit=5", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['attempts'], list)
    
    def test_list_attempts_with_target_filter(self):
        """Should accept target filter parameter."""
        response = self.client.get("/v1/attempts?target=test-target", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['attempts'], list)
    
    def test_list_failures_unauthorized(self):
        """Should return 401 without valid token."""
        response = self.client.get("/v1/failures")
        assert response.status_code == 401
    
    def test_list_failures_returns_list(self):
        """Should return failures list."""
        response = self.client.get("/v1/failures", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert 'failures' in data
        assert 'count' in data
        assert isinstance(data['failures'], list)
        assert isinstance(data['count'], int)
    
    def test_list_failures_with_limit(self):
        """Should respect limit parameter."""
        response = self.client.get("/v1/failures?limit=20", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['failures'], list)
    
    def test_list_failures_with_target_filter(self):
        """Should accept target filter parameter."""
        response = self.client.get("/v1/failures?target=test-target", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['failures'], list)
    
    def test_invalidate_attempt_unauthorized(self):
        """Should return 401 without valid token."""
        response = self.client.post(
            "/v1/attempts/attempt-123/invalidate",
            json={"reason": "Test"}
        )
        assert response.status_code == 401
    
    def test_invalidate_attempt_not_found(self):
        """Should return 404 for non-existent attempt."""
        response = self.client.post(
            "/v1/attempts/nonexistent/invalidate",
            headers=self.headers,
            json={"reason": "Test"}
        )
        assert response.status_code == 404
        data = response.json()
        assert 'detail' in data
        assert 'not found' in data['detail'].lower()
    
    def test_invalidate_attempt_missing_reason(self):
        """Should return 422 when reason is missing."""
        response = self.client.post(
            "/v1/attempts/attempt-123/invalidate",
            headers=self.headers,
            json={}
        )
        assert response.status_code == 422
    
    def test_invalidate_request_schema(self):
        """Should validate request schema."""
        # Valid request
        response = self.client.post(
            "/v1/attempts/test-attempt/invalidate",
            headers=self.headers,
            json={"reason": "Valid reason"}
        )
        # Will be 404 since attempt doesn't exist, but schema is valid
        assert response.status_code == 404
        
        # Invalid request - extra fields should be ignored
        response = self.client.post(
            "/v1/attempts/test-attempt/invalidate",
            headers=self.headers,
            json={"reason": "Valid", "extra": "field"}
        )
        assert response.status_code == 404  # Still 404, extra field ignored
    
    def test_attempts_list_response_schema(self):
        """Should return correct response schema."""
        response = self.client.get("/v1/attempts", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify schema
        assert 'attempts' in data
        assert 'count' in data
        assert isinstance(data['attempts'], list)
        assert isinstance(data['count'], int)
    
    def test_failures_list_response_schema(self):
        """Should return correct response schema."""
        response = self.client.get("/v1/failures", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify schema
        assert 'failures' in data
        assert 'count' in data
        assert isinstance(data['failures'], list)
        assert isinstance(data['count'], int)
