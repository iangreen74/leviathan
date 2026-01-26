"""
Unit tests for bootstrap event ingestion via control plane API.
"""
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from leviathan.control_plane.api import app
from leviathan.control_plane.config import get_config
from leviathan.graph.events import EventStore
from leviathan.graph.store import GraphStore
from leviathan.artifacts.store import ArtifactStore


class TestBootstrapEventIngestion:
    """Test that bootstrap events are correctly ingested by the API."""
    
    @pytest.fixture
    def test_client(self, tmp_path, monkeypatch):
        """Create test client with temporary storage."""
        # Initialize stores with temporary directories
        ndjson_dir = tmp_path / "graph"
        ndjson_dir.mkdir()
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        
        # Set token in environment
        monkeypatch.setenv("LEVIATHAN_CONTROL_PLANE_TOKEN", "test-token")
        
        # Manually initialize stores for this test
        import leviathan.control_plane.api as api_module
        api_module.config = get_config()
        api_module.event_store = EventStore(backend="ndjson", ndjson_dir=str(ndjson_dir))
        api_module.graph_store = GraphStore(backend="memory")
        api_module.artifact_store = ArtifactStore(storage_root=artifacts_dir)
        
        client = TestClient(app)
        
        yield client, ndjson_dir
        
        # Clean up stores after test
        if api_module.event_store:
            api_module.event_store.close()
        if api_module.graph_store:
            api_module.graph_store.close()
        api_module.event_store = None
        api_module.graph_store = None
        api_module.artifact_store = None
    
    def test_bootstrap_events_ingested(self, test_client):
        """Test that bootstrap discovery events are ingested correctly."""
        client, ndjson_dir = test_client
        
        # Create event bundle with bootstrap events
        bundle = {
            "target": "test-target",
            "bundle_id": "bundle-test-123",
            "events": [
                {
                    "event_id": "attempt-started-123",
                    "event_type": "attempt.started",
                    "timestamp": "2026-01-25T23:00:00.000000",
                    "actor_id": "worker-123",
                    "payload": {
                        "attempt_id": "attempt-123",
                        "status": "running"
                    }
                },
                {
                    "event_id": "bootstrap-started-123",
                    "event_type": "bootstrap.started",
                    "timestamp": "2026-01-25T23:00:01.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "repo_url": "git@github.com:test/repo.git",
                        "commit_sha": "abc123",
                        "default_branch": "main"
                    }
                },
                {
                    "event_id": "file-abc123",
                    "event_type": "file.discovered",
                    "timestamp": "2026-01-25T23:00:02.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "file_path": "README.md",
                        "sha256": "abc123def456",
                        "size_bytes": 1024,
                        "file_type": "markdown",
                        "language": None
                    }
                },
                {
                    "event_id": "doc-readme",
                    "event_type": "doc.discovered",
                    "timestamp": "2026-01-25T23:00:03.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "doc_path": "README.md",
                        "doc_type": "markdown"
                    }
                },
                {
                    "event_id": "repo-indexed-123",
                    "event_type": "repo.indexed",
                    "timestamp": "2026-01-25T23:00:04.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "files_count": 1,
                        "docs_count": 1,
                        "workflows_count": 0,
                        "api_routes_count": 0
                    }
                },
                {
                    "event_id": "bootstrap-completed-123",
                    "event_type": "bootstrap.completed",
                    "timestamp": "2026-01-25T23:00:05.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "status": "completed",
                        "files_indexed": 1,
                        "docs_indexed": 1,
                        "workflows_indexed": 0,
                        "api_routes_indexed": 0
                    }
                },
                {
                    "event_id": "attempt-succeeded-123",
                    "event_type": "attempt.succeeded",
                    "timestamp": "2026-01-25T23:00:06.000000",
                    "actor_id": "worker-123",
                    "payload": {
                        "attempt_id": "attempt-123",
                        "status": "succeeded",
                        "completed_at": "2026-01-25T23:00:06.000000",
                        "artifacts_count": 2
                    }
                }
            ],
            "artifacts": []
        }
        
        # Post bundle to API
        response = client.post(
            "/v1/events/ingest",
            json=bundle,
            headers={"Authorization": "Bearer test-token"}
        )
        
        # Assert successful ingestion
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["ingested"] == 7  # All 7 events should be ingested
        
        # Verify events were written to NDJSON file
        events_file = ndjson_dir / "events.ndjson"
        assert events_file.exists()
        
        # Read and verify events
        with open(events_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 7
        
        # Parse event types
        import json
        event_types = [json.loads(line)['event_type'] for line in lines]
        
        # Verify all bootstrap event types are present
        assert 'attempt.started' in event_types
        assert 'bootstrap.started' in event_types
        assert 'file.discovered' in event_types
        assert 'doc.discovered' in event_types
        assert 'repo.indexed' in event_types
        assert 'bootstrap.completed' in event_types
        assert 'attempt.succeeded' in event_types
    
    def test_bootstrap_events_with_workflows(self, test_client):
        """Test bootstrap events including workflow.discovered."""
        client, ndjson_dir = test_client
        
        bundle = {
            "target": "test-target",
            "bundle_id": "bundle-test-456",
            "events": [
                {
                    "event_id": "bootstrap-started-456",
                    "event_type": "bootstrap.started",
                    "timestamp": "2026-01-25T23:10:00.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "repo_url": "git@github.com:test/repo.git",
                        "commit_sha": "def456",
                        "default_branch": "main"
                    }
                },
                {
                    "event_id": "workflow-ci",
                    "event_type": "workflow.discovered",
                    "timestamp": "2026-01-25T23:10:01.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "workflow_path": ".github/workflows/ci.yml",
                        "workflow_name": "CI",
                        "triggers": ["push", "pull_request"]
                    }
                },
                {
                    "event_id": "bootstrap-completed-456",
                    "event_type": "bootstrap.completed",
                    "timestamp": "2026-01-25T23:10:02.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "status": "completed",
                        "files_indexed": 1,
                        "docs_indexed": 0,
                        "workflows_indexed": 1,
                        "api_routes_indexed": 0
                    }
                }
            ],
            "artifacts": []
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=bundle,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 3
        
        # Verify workflow.discovered event was stored
        events_file = ndjson_dir / "events.ndjson"
        with open(events_file, 'r') as f:
            lines = f.readlines()
        
        import json
        event_types = [json.loads(line)['event_type'] for line in lines]
        assert 'workflow.discovered' in event_types
    
    def test_bootstrap_events_with_api_routes(self, test_client):
        """Test bootstrap events including api.route.discovered."""
        client, ndjson_dir = test_client
        
        bundle = {
            "target": "test-target",
            "bundle_id": "bundle-test-789",
            "events": [
                {
                    "event_id": "bootstrap-started-789",
                    "event_type": "bootstrap.started",
                    "timestamp": "2026-01-25T23:20:00.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "repo_url": "git@github.com:test/repo.git",
                        "commit_sha": "ghi789",
                        "default_branch": "main"
                    }
                },
                {
                    "event_id": "api-route-users",
                    "event_type": "api.route.discovered",
                    "timestamp": "2026-01-25T23:20:01.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "route_path": "/api/users",
                        "method": "GET",
                        "handler": "get_users",
                        "file_path": "api/routes.py"
                    }
                },
                {
                    "event_id": "bootstrap-completed-789",
                    "event_type": "bootstrap.completed",
                    "timestamp": "2026-01-25T23:20:02.000000",
                    "actor_id": "bootstrap-indexer",
                    "payload": {
                        "target_id": "test-target",
                        "status": "completed",
                        "files_indexed": 1,
                        "docs_indexed": 0,
                        "workflows_indexed": 0,
                        "api_routes_indexed": 1
                    }
                }
            ],
            "artifacts": []
        }
        
        response = client.post(
            "/v1/events/ingest",
            json=bundle,
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ingested"] == 3
        
        # Verify api.route.discovered event was stored
        events_file = ndjson_dir / "events.ndjson"
        with open(events_file, 'r') as f:
            lines = f.readlines()
        
        import json
        event_types = [json.loads(line)['event_type'] for line in lines]
        assert 'api.route.discovered' in event_types
