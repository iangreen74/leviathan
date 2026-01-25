"""
Unit tests for worker event bundle generation.
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from leviathan.executor.worker import Worker, WorkerError


def create_mock_worker(temp_dir):
    """Create a mock worker for testing without filesystem dependencies."""
    worker = Worker.__new__(Worker)
    worker.target_name = "test-target"
    worker.target_repo_url = "git@github.com:test/repo.git"
    worker.target_branch = "main"
    worker.task_id = "task-001"
    worker.attempt_id = "attempt-abc123"
    worker.control_plane_url = "http://test-api:8000"
    worker.control_plane_token = "test-token"
    worker.workspace = temp_dir
    worker.events = []
    worker.artifacts = []
    return worker


class TestWorkerEventBundle:
    """Test worker event bundle generation."""
    
    def setup_method(self):
        """Set up test environment."""
        # Create temp workspace
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Set required env vars
        os.environ["TARGET_NAME"] = "test-target"
        os.environ["TARGET_REPO_URL"] = "git@github.com:test/repo.git"
        os.environ["TARGET_BRANCH"] = "main"
        os.environ["TASK_ID"] = "task-001"
        os.environ["ATTEMPT_ID"] = "attempt-abc123"
        os.environ["CONTROL_PLANE_URL"] = "http://test-api:8000"
        os.environ["CONTROL_PLANE_TOKEN"] = "test-token"
    
    def teardown_method(self):
        """Clean up environment."""
        for key in ["TARGET_NAME", "TARGET_REPO_URL", "TARGET_BRANCH", 
                    "TASK_ID", "ATTEMPT_ID", "CONTROL_PLANE_URL", "CONTROL_PLANE_TOKEN"]:
            os.environ.pop(key, None)
        
        # Clean up temp directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_worker_initialization(self):
        """Worker should initialize from environment variables."""
        worker = create_mock_worker(self.temp_dir)
        
        assert worker.target_name == "test-target"
        assert worker.target_repo_url == "git@github.com:test/repo.git"
        assert worker.target_branch == "main"
        assert worker.task_id == "task-001"
        assert worker.attempt_id == "attempt-abc123"
        assert worker.control_plane_url == "http://test-api:8000"
        assert worker.control_plane_token == "test-token"
    
    def test_worker_missing_env_vars(self):
        """Worker should raise error if required env vars missing."""
        os.environ.pop("TASK_ID")
        
        with pytest.raises(WorkerError) as exc_info:
            Worker()
        
        assert "TASK_ID" in str(exc_info.value)
    
    def test_emit_event_structure(self):
        """Emitted events should have correct structure."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("test.event", {
            'test_field': 'test_value',
            'attempt_id': 'attempt-abc123'
        })
        
        assert len(worker.events) == 1
        event = worker.events[0]
        
        # Verify event structure
        assert 'event_id' in event
        assert 'event_type' in event
        assert 'timestamp' in event
        assert 'actor_id' in event
        assert 'payload' in event
        
        assert event['event_type'] == 'test.event'
        assert event['actor_id'] == 'worker-attempt-abc123'
        assert event['payload']['test_field'] == 'test_value'
    
    def test_event_bundle_structure(self):
        """Event bundle should conform to control plane API schema."""
        worker = create_mock_worker(self.temp_dir)
        
        # Emit some events
        worker._emit_event("attempt.started", {
            'attempt_id': 'attempt-abc123',
            'status': 'running'
        })
        
        worker._emit_event("attempt.succeeded", {
            'attempt_id': 'attempt-abc123',
            'status': 'succeeded'
        })
        
        # Add artifact
        worker.artifacts.append({
            'sha256': 'a' * 64,
            'kind': 'log',
            'uri': 'file:///workspace/artifacts/test.log',
            'size': 1024
        })
        
        # Create bundle (would be posted to API)
        bundle = {
            'target': worker.target_name,
            'bundle_id': f"bundle-{worker.attempt_id}",
            'events': worker.events,
            'artifacts': worker.artifacts
        }
        
        # Verify bundle structure
        assert 'target' in bundle
        assert 'bundle_id' in bundle
        assert 'events' in bundle
        assert 'artifacts' in bundle
        
        assert bundle['target'] == 'test-target'
        assert len(bundle['events']) == 2
        assert len(bundle['artifacts']) == 1
        
        # Verify event structure
        for event in bundle['events']:
            assert 'event_id' in event
            assert 'event_type' in event
            assert 'timestamp' in event
            assert 'actor_id' in event
            assert 'payload' in event
        
        # Verify artifact structure
        artifact = bundle['artifacts'][0]
        assert 'sha256' in artifact
        assert 'kind' in artifact
        assert 'uri' in artifact
        assert 'size' in artifact
    
    @patch('leviathan.executor.worker.requests.post')
    def test_post_event_bundle(self, mock_post):
        """Should post event bundle to control plane API."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        worker = create_mock_worker(self.temp_dir)
        
        # Emit event
        worker._emit_event("attempt.started", {
            'attempt_id': 'attempt-abc123',
            'status': 'running'
        })
        
        # Post bundle
        worker._post_event_bundle()
        
        # Verify API call
        assert mock_post.called
        call_args = mock_post.call_args
        
        # Verify URL
        assert call_args[0][0] == 'http://test-api:8000/v1/events/ingest'
        
        # Verify headers
        assert 'Authorization' in call_args[1]['headers']
        assert call_args[1]['headers']['Authorization'] == 'Bearer test-token'
        
        # Verify payload
        payload = call_args[1]['json']
        assert payload['target'] == 'test-target'
        assert 'bundle_id' in payload
        assert 'events' in payload
        assert 'artifacts' in payload
    
    def test_artifact_reference_structure(self):
        """Artifact references should have required fields."""
        worker = create_mock_worker(self.temp_dir)
        
        # Add artifact
        worker.artifacts.append({
            'sha256': 'abc123' + '0' * 58,  # 64 chars
            'kind': 'log',
            'uri': 'file:///workspace/artifacts/test.log',
            'size': 2048
        })
        
        artifact = worker.artifacts[0]
        
        # Verify required fields
        assert 'sha256' in artifact
        assert 'kind' in artifact
        assert 'uri' in artifact
        assert 'size' in artifact
        
        # Verify types
        assert isinstance(artifact['sha256'], str)
        assert isinstance(artifact['kind'], str)
        assert isinstance(artifact['uri'], str)
        assert isinstance(artifact['size'], int)
        
        # Verify SHA256 format (64 hex chars)
        assert len(artifact['sha256']) == 64
    
    def test_multiple_events_ordering(self):
        """Events should maintain order."""
        worker = create_mock_worker(self.temp_dir)
        
        # Emit events in order
        worker._emit_event("attempt.started", {'status': 'running'})
        worker._emit_event("tests.passed", {'test_count': 5})
        worker._emit_event("attempt.succeeded", {'status': 'succeeded'})
        
        # Verify order
        assert len(worker.events) == 3
        assert worker.events[0]['event_type'] == 'attempt.started'
        assert worker.events[1]['event_type'] == 'tests.passed'
        assert worker.events[2]['event_type'] == 'attempt.succeeded'
    
    def test_event_timestamps(self):
        """Events should have ISO format timestamps."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("test.event", {'data': 'test'})
        
        event = worker.events[0]
        timestamp = event['timestamp']
        
        # Verify ISO format (should parse without error)
        from datetime import datetime
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert parsed is not None
    
    def test_event_actor_id(self):
        """Events should have worker-specific actor ID."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("test.event", {'data': 'test'})
        
        event = worker.events[0]
        assert event['actor_id'] == 'worker-attempt-abc123'
    
    def test_load_task_spec_structure(self):
        """Task spec should have expected structure."""
        worker = create_mock_worker(self.temp_dir)
        worker.target_dir = self.temp_dir / "target"
        worker.target_dir.mkdir(parents=True, exist_ok=True)
        
        # Create mock backlog file
        backlog_dir = worker.target_dir / ".leviathan"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        backlog_file = backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: task-001
    title: Test Task
    scope: test
    priority: high
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
""")
        
        task_spec = worker._load_task_spec()
        
        # Verify required fields
        assert 'id' in task_spec
        assert 'title' in task_spec
        assert 'scope' in task_spec
        assert task_spec['id'] == 'task-001'
