"""
Integration tests for /v1/events/ingest with PR events missing pr_number.
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone
from leviathan.control_plane.api import app, reset_stores, initialize_stores
from leviathan.graph.events import EventStore
from leviathan.graph.store import GraphStore


@pytest.fixture
def client(tmp_path):
    """Create test client with isolated storage."""
    reset_stores()
    initialize_stores(ndjson_dir=str(tmp_path / "events"), artifacts_dir=str(tmp_path / "artifacts"))
    return TestClient(app)


@pytest.fixture
def auth_token():
    """Get auth token from environment or use test token."""
    return "test-token-12345"


class TestAPIEventIngestPR:
    """Test /v1/events/ingest endpoint with PR events."""
    
    def test_ingest_pr_event_without_pr_number(self, client, auth_token):
        """Should accept PR event with only pr_url (no pr_number) and return 200."""
        event_bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-1",
            "events": [
                {
                    "event_id": "test-pr-no-number-1",
                    "event_type": "pr.created",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "pr_url": "https://github.com/test/repo/pull/placeholder",
                        "title": "Test PR without number",
                        "state": "open"
                    }
                }
            ]
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=event_bundle,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_ingest_pr_event_with_pr_number(self, client, auth_token):
        """Should accept PR event with pr_number and return 200."""
        event_bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-2",
            "events": [
                {
                    "event_id": "test-pr-with-number-1",
                    "event_type": "pr.created",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "pr_number": 456,
                        "pr_url": "https://github.com/test/repo/pull/456",
                        "title": "Test PR with number",
                        "state": "open"
                    }
                }
            ]
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=event_bundle,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_ingest_pr_event_with_attempt_link(self, client, auth_token):
        """Should accept PR event with attempt_id and create graph edge."""
        event_bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-3",
            "events": [
                {
                    "event_id": "attempt-start-1",
                    "event_type": "attempt.started",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "attempt_id": "attempt-999",
                        "task_id": "task-1"
                    }
                },
                {
                    "event_id": "pr-linked-1",
                    "event_type": "pr.created",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "pr_url": "https://github.com/test/repo/pull/linked",
                        "title": "Linked PR",
                        "state": "open",
                        "attempt_id": "attempt-999"
                    }
                }
            ]
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=event_bundle,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_ingest_multiple_pr_events_no_500(self, client, auth_token):
        """Should handle multiple PR events without pr_number and not return 500."""
        event_bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-4",
            "events": [
                {
                    "event_id": f"pr-event-{i}",
                    "event_type": "pr.created",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "pr_url": f"https://github.com/test/repo/pull/test-{i}",
                        "title": f"Test PR {i}",
                        "state": "open"
                    }
                }
                for i in range(5)
            ]
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=event_bundle,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should not crash with 500
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    def test_ingest_pr_event_minimal_payload(self, client, auth_token):
        """Should handle PR event with minimal required fields."""
        event_bundle = {
            "target": "test-target",
            "bundle_id": "test-bundle-5",
            "events": [
                {
                    "event_id": "minimal-pr-1",
                    "event_type": "pr.created",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "actor_id": "test-worker",
                    "payload": {
                        "pr_url": "https://github.com/test/repo/pull/minimal",
                        "title": "Minimal",
                        "state": "open"
                        # No pr_number, no attempt_id
                    }
                }
            ]
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=event_bundle,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        # Should succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
