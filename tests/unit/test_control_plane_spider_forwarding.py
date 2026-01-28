"""
Unit tests for Spider Node event forwarding from control plane.

Tests that forwarding is best-effort and never blocks control plane operations.
"""
import pytest
import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from leviathan.control_plane.api import app, initialize_stores
from leviathan.control_plane.spider_forwarder import SpiderForwarder


class TestSpiderForwarding:
    """Test Spider Node event forwarding."""
    
    def setup_method(self):
        """Setup test environment."""
        # Set auth token BEFORE initializing stores
        os.environ["LEVIATHAN_CONTROL_PLANE_TOKEN"] = "test-token"
        
        # Initialize stores for testing
        initialize_stores(ndjson_dir="/tmp/test_spider_forwarding", artifacts_dir="/tmp/test_artifacts")
        
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token"}
    
    def test_spider_disabled_no_forwarding(self):
        """When Spider disabled, no forwarding should be attempted."""
        # Ensure Spider is disabled
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "false"
        
        forwarder = SpiderForwarder()
        assert forwarder.enabled is False
        
        # Ingest should succeed without forwarding
        bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-1",
            "events": [
                {
                    "event_id": "event-1",
                    "event_type": "attempt.created",
                    "timestamp": "2026-01-28T12:00:00.000000",
                    "actor_id": "test-actor",
                    "payload": {
                        "attempt_id": "attempt-1",
                        "task_id": "task-1",
                        "target_id": "test-target",
                        "attempt_number": 1
                    }
                }
            ]
        }
        
        response = self.client.post("/v1/events/ingest", json=bundle, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingested"] == 1
    
    @patch('httpx.AsyncClient')
    def test_spider_enabled_but_unreachable_returns_200(self, mock_client):
        """When Spider unreachable, ingest should still return 200."""
        # Enable Spider
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "true"
        os.environ["LEVIATHAN_SPIDER_URL"] = "http://unreachable-spider:8001"
        
        # Mock httpx to raise ConnectError
        import httpx
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-2",
            "events": [
                {
                    "event_id": "event-2",
                    "event_type": "attempt.started",
                    "timestamp": "2026-01-28T12:01:00.000000",
                    "actor_id": "test-actor",
                    "payload": {
                        "attempt_id": "attempt-2",
                        "task_id": "task-2",
                        "target_id": "test-target"
                    }
                }
            ]
        }
        
        # Ingest should succeed even if Spider is unreachable
        response = self.client.post("/v1/events/ingest", json=bundle, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingested"] == 1
    
    @patch('httpx.AsyncClient')
    def test_spider_timeout_does_not_block_ingest(self, mock_client):
        """When Spider times out, ingest should still succeed."""
        # Enable Spider
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "true"
        os.environ["LEVIATHAN_SPIDER_URL"] = "http://slow-spider:8001"
        
        # Mock httpx to raise TimeoutException
        import httpx
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = httpx.TimeoutException("Request timeout")
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-3",
            "events": [
                {
                    "event_id": "event-3",
                    "event_type": "attempt.succeeded",
                    "timestamp": "2026-01-28T12:02:00.000000",
                    "actor_id": "test-actor",
                    "payload": {
                        "attempt_id": "attempt-3",
                        "task_id": "task-3",
                        "target_id": "test-target"
                    }
                }
            ]
        }
        
        # Ingest should succeed even if Spider times out
        response = self.client.post("/v1/events/ingest", json=bundle, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingested"] == 1
    
    @patch('httpx.AsyncClient')
    def test_spider_returns_non_200_does_not_block_ingest(self, mock_client):
        """When Spider returns non-200, ingest should still succeed."""
        # Enable Spider
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "true"
        os.environ["LEVIATHAN_SPIDER_URL"] = "http://spider:8001"
        
        # Mock httpx to return 500
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = mock_instance
        
        bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-4",
            "events": [
                {
                    "event_id": "event-4",
                    "event_type": "attempt.failed",
                    "timestamp": "2026-01-28T12:03:00.000000",
                    "actor_id": "test-actor",
                    "payload": {
                        "attempt_id": "attempt-4",
                        "task_id": "task-4",
                        "target_id": "test-target",
                        "error": "test error"
                    }
                }
            ]
        }
        
        # Ingest should succeed even if Spider returns error
        response = self.client.post("/v1/events/ingest", json=bundle, headers=self.headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingested"] == 1
    
    def test_spider_forwarder_disabled_when_url_missing(self):
        """Spider forwarder should disable if URL not set."""
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "true"
        os.environ.pop("LEVIATHAN_SPIDER_URL", None)
        
        forwarder = SpiderForwarder()
        
        # Should auto-disable if URL missing
        assert forwarder.enabled is False
    
    @pytest.mark.asyncio
    async def test_forward_event_bundle_returns_immediately_when_disabled(self):
        """Forward should return immediately when disabled."""
        os.environ["LEVIATHAN_SPIDER_ENABLED"] = "false"
        
        forwarder = SpiderForwarder()
        
        bundle = {"bundle_id": "test", "events": []}
        
        # Should return immediately without error
        await forwarder.forward_event_bundle(bundle)
        
        # No exception raised = success
