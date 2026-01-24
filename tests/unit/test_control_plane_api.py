"""
Unit tests for Graph Control Plane API.

Tests authentication, event ingestion, and query endpoints.
"""
import pytest
import os
import uuid
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from fastapi.testclient import TestClient

# Set test token before importing API
os.environ["LEVIATHAN_CONTROL_PLANE_TOKEN"] = "test-token-12345"
os.environ["LEVIATHAN_BACKEND"] = "ndjson"

from leviathan.control_plane.api import app
from leviathan.graph.events import EventType


class TestAuthentication:
    """Test API authentication."""
    
    def setup_method(self):
        """Create test client."""
        self.client = TestClient(app)
    
    def test_healthz_no_auth_required(self):
        """Health check should not require authentication."""
        response = self.client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    def test_ingest_requires_auth(self):
        """Ingest endpoint should require authentication."""
        response = self.client.post("/v1/events/ingest", json={
            "target": "test",
            "bundle_id": "test-bundle",
            "events": []
        })
        assert response.status_code == 401  # No auth header
    
    def test_ingest_rejects_invalid_token(self):
        """Ingest should reject invalid token."""
        response = self.client.post(
            "/v1/events/ingest",
            json={
                "target": "test",
                "bundle_id": "test-bundle",
                "events": []
            },
            headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401
    
    def test_ingest_accepts_valid_token(self):
        """Ingest should accept valid token."""
        response = self.client.post(
            "/v1/events/ingest",
            json={
                "target": "test",
                "bundle_id": "test-bundle",
                "events": []
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        assert response.status_code == 200
    
    def test_summary_requires_auth(self):
        """Summary endpoint should require authentication."""
        response = self.client.get("/v1/graph/summary")
        assert response.status_code == 401
    
    def test_summary_accepts_valid_token(self):
        """Summary should accept valid token."""
        response = self.client.get(
            "/v1/graph/summary",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        assert response.status_code == 200


class TestEventIngestion:
    """Test event ingestion endpoint."""
    
    def setup_method(self):
        """Create test client and temporary event store."""
        self.client = TestClient(app)
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_ingest_minimal_event_bundle(self):
        """Should ingest minimal valid event bundle."""
        bundle_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        
        response = self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": bundle_id,
                "events": [
                    {
                        "event_id": event_id,
                        "event_type": EventType.TARGET_REGISTERED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "test",
                        "payload": {
                            "target_id": "radix",
                            "node_id": "radix",
                            "node_type": "Target",
                            "name": "radix",
                            "repo_url": "git@github.com:test/radix.git",
                            "default_branch": "main",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 1
        assert data["bundle_id"] == bundle_id
        assert data["status"] == "ok"
    
    def test_ingest_multiple_events(self):
        """Should ingest multiple events in one bundle."""
        bundle_id = str(uuid.uuid4())
        
        events = []
        for i in range(3):
            events.append({
                "event_id": str(uuid.uuid4()),
                "event_type": EventType.TASK_CREATED,
                "timestamp": datetime.utcnow().isoformat(),
                "actor_id": "test",
                "payload": {
                    "task_id": f"task-{i}",
                    "node_id": f"task-{i}",
                    "node_type": "Task",
                    "target_id": "radix",
                    "title": f"Task {i}",
                    "scope": "test",
                    "priority": "high",
                    "estimated_size": "small",
                    "allowed_paths": [],
                    "acceptance_criteria": [],
                    "status": "pending",
                    "created_at": datetime.utcnow().isoformat()
                }
            })
        
        response = self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": bundle_id,
                "events": events
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 3
    
    def test_ingest_with_artifacts(self):
        """Should accept event bundle with artifact references."""
        bundle_id = str(uuid.uuid4())
        
        response = self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": bundle_id,
                "events": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": EventType.ARTIFACT_CREATED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "executor",
                        "payload": {
                            "artifact_id": "artifact-001",
                            "node_id": "artifact-001",
                            "node_type": "Artifact",
                            "sha256": "a" * 64,
                            "artifact_type": "log",
                            "size_bytes": 1024,
                            "storage_path": "/path/to/artifact",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    }
                ],
                "artifacts": [
                    {
                        "sha256": "a" * 64,
                        "kind": "log",
                        "uri": "file:///path/to/artifact",
                        "size": 1024
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 1


class TestGraphSummary:
    """Test graph summary endpoint."""
    
    def setup_method(self):
        """Create test client."""
        self.client = TestClient(app)
    
    def test_summary_empty_graph(self):
        """Summary should work with empty graph."""
        response = self.client.get(
            "/v1/graph/summary",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "nodes_by_type" in data
        assert "edges_by_type" in data
        assert "recent_events" in data
        assert isinstance(data["recent_events"], list)
    
    def test_summary_after_ingestion(self):
        """Summary should reflect ingested events."""
        # Ingest some events
        self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": str(uuid.uuid4()),
                "events": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": EventType.TARGET_REGISTERED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "test",
                        "payload": {
                            "target_id": "radix",
                            "node_id": "radix",
                            "node_type": "Target",
                            "name": "radix",
                            "repo_url": "test",
                            "default_branch": "main",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        # Get summary
        response = self.client.get(
            "/v1/graph/summary",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "Target" in data["nodes_by_type"]
        assert data["nodes_by_type"]["Target"] >= 1
        assert len(data["recent_events"]) >= 1
    
    def test_summary_recent_events_format(self):
        """Recent events should have correct format."""
        # Ingest event
        event_id = str(uuid.uuid4())
        self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": str(uuid.uuid4()),
                "events": [
                    {
                        "event_id": event_id,
                        "event_type": EventType.TASK_CREATED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "test-actor",
                        "payload": {
                            "task_id": "task-001",
                            "node_id": "task-001",
                            "node_type": "Task",
                            "target_id": "radix",
                            "title": "Test",
                            "scope": "test",
                            "priority": "high",
                            "estimated_size": "small",
                            "allowed_paths": [],
                            "acceptance_criteria": [],
                            "status": "pending",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        # Get summary
        response = self.client.get(
            "/v1/graph/summary",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        data = response.json()
        events = data["recent_events"]
        
        # Find our event
        our_event = next((e for e in events if e["event_id"] == event_id), None)
        assert our_event is not None
        assert our_event["event_type"] == EventType.TASK_CREATED
        assert our_event["actor_id"] == "test-actor"
        assert "timestamp" in our_event


class TestAttemptEndpoint:
    """Test attempt details endpoint."""
    
    def setup_method(self):
        """Create test client."""
        self.client = TestClient(app)
    
    def test_get_nonexistent_attempt(self):
        """Should return null node for nonexistent attempt."""
        response = self.client.get(
            "/v1/attempts/nonexistent",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["attempt_node"] is None
        assert data["events"] == []
        assert data["artifacts"] == []
    
    def test_get_attempt_with_events(self):
        """Should return attempt with related events."""
        attempt_id = "attempt-test-001"
        
        # Ingest attempt creation event
        self.client.post(
            "/v1/events/ingest",
            json={
                "target": "radix",
                "bundle_id": str(uuid.uuid4()),
                "events": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": EventType.ATTEMPT_CREATED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "scheduler",
                        "payload": {
                            "attempt_id": attempt_id,
                            "node_id": attempt_id,
                            "node_type": "Attempt",
                            "task_id": "task-001",
                            "attempt_number": 1,
                            "status": "created",
                            "created_at": datetime.utcnow().isoformat()
                        }
                    },
                    {
                        "event_id": str(uuid.uuid4()),
                        "event_type": EventType.ATTEMPT_STARTED,
                        "timestamp": datetime.utcnow().isoformat(),
                        "actor_id": "executor",
                        "payload": {
                            "attempt_id": attempt_id,
                            "status": "running",
                            "started_at": datetime.utcnow().isoformat()
                        }
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        # Get attempt
        response = self.client.get(
            f"/v1/attempts/{attempt_id}",
            headers={"Authorization": "Bearer test-token-12345"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["attempt_node"] is not None
        assert data["attempt_node"]["node_id"] == attempt_id
        assert len(data["events"]) >= 2
