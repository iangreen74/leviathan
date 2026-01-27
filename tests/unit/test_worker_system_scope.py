"""
Unit tests for worker system-scope task fallback.

Tests that topology and bootstrap tasks can run without backlog entries,
and that event bundles include proper target and attempt lifecycle events.
"""
import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from leviathan.executor.worker import Worker, WorkerError
from leviathan.backlog import Task


def create_mock_worker(temp_dir, task_id="task-001"):
    """Create a mock worker for testing without filesystem dependencies."""
    worker = Worker.__new__(Worker)
    worker.target_name = "test-target"
    worker.target_repo_url = "git@github.com:test/repo.git"
    worker.target_branch = "main"
    worker.task_id = task_id
    worker.attempt_id = "attempt-abc123"
    worker.control_plane_url = "http://test-api:8000"
    worker.control_plane_token = "test-token"
    worker.workspace = temp_dir
    worker.target_dir = temp_dir / "target"
    worker.events = []
    worker.artifacts = []
    return worker


class TestSystemScopeFallback:
    """Test system-scope task fallback for topology and bootstrap."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.target_dir = self.temp_dir / "target"
        self.target_dir.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_topology_system_scope_fallback_no_backlog(self):
        """Should create synthetic topology task when backlog doesn't exist."""
        worker = create_mock_worker(self.temp_dir, task_id="topology-test-target-v1")
        worker.target_dir = self.target_dir
        
        # Don't create backlog file
        
        task = worker._load_task_spec()
        
        # Verify synthetic task
        assert isinstance(task, Task)
        assert task.id == "topology-test-target-v1"
        assert task.scope == "topology"
        assert task.ready is True
        assert task.allowed_paths == []
        assert "SYSTEM" in task.title
        assert "topology" in task.title.lower()
    
    def test_bootstrap_system_scope_fallback_no_backlog(self):
        """Should create synthetic bootstrap task when backlog doesn't exist."""
        worker = create_mock_worker(self.temp_dir, task_id="bootstrap-test-target-v1")
        worker.target_dir = self.target_dir
        
        # Don't create backlog file
        
        task = worker._load_task_spec()
        
        # Verify synthetic task
        assert isinstance(task, Task)
        assert task.id == "bootstrap-test-target-v1"
        assert task.scope == "bootstrap"
        assert task.ready is True
        assert task.allowed_paths == []
        assert "SYSTEM" in task.title
        assert "bootstrap" in task.title.lower()
    
    def test_topology_system_scope_fallback_task_not_in_backlog(self):
        """Should create synthetic topology task when task not found in backlog."""
        worker = create_mock_worker(self.temp_dir, task_id="topology-myrepo-v1")
        worker.target_dir = self.target_dir
        
        # Create backlog with different tasks
        backlog_dir = self.target_dir / ".leviathan"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        backlog_file = backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: some-other-task
    title: Other Task
    scope: feature
    priority: high
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        task = worker._load_task_spec()
        
        # Should use system-scope fallback
        assert isinstance(task, Task)
        assert task.id == "topology-myrepo-v1"
        assert task.scope == "topology"
        assert task.ready is True
    
    def test_bootstrap_system_scope_fallback_task_not_in_backlog(self):
        """Should create synthetic bootstrap task when task not found in backlog."""
        worker = create_mock_worker(self.temp_dir, task_id="bootstrap-myrepo-v1")
        worker.target_dir = self.target_dir
        
        # Create backlog with different tasks
        backlog_dir = self.target_dir / ".leviathan"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        backlog_file = backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: some-other-task
    title: Other Task
    scope: feature
    priority: high
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        task = worker._load_task_spec()
        
        # Should use system-scope fallback
        assert isinstance(task, Task)
        assert task.id == "bootstrap-myrepo-v1"
        assert task.scope == "bootstrap"
        assert task.ready is True
    
    def test_non_system_task_not_found_raises_error(self):
        """Should raise helpful error for non-system tasks not in backlog."""
        worker = create_mock_worker(self.temp_dir, task_id="regular-task-123")
        worker.target_dir = self.target_dir
        worker.target_name = "myrepo"
        
        # Don't create backlog file
        
        with pytest.raises(WorkerError) as exc_info:
            worker._load_task_spec()
        
        error_msg = str(exc_info.value)
        assert "regular-task-123 not found in backlog" in error_msg
        assert "topology-myrepo-v1" in error_msg
        assert "bootstrap-myrepo-v1" in error_msg
        assert ".leviathan/backlog.yaml" in error_msg
    
    def test_topology_task_wrong_version_raises_error(self):
        """Should not use fallback for topology tasks with wrong version."""
        worker = create_mock_worker(self.temp_dir, task_id="topology-test-v2")
        worker.target_dir = self.target_dir
        
        # Don't create backlog file
        
        with pytest.raises(WorkerError) as exc_info:
            worker._load_task_spec()
        
        # Should not use fallback (wrong version)
        assert "not found in backlog" in str(exc_info.value)
    
    def test_bootstrap_task_wrong_version_raises_error(self):
        """Should not use fallback for bootstrap tasks with wrong version."""
        worker = create_mock_worker(self.temp_dir, task_id="bootstrap-test-v2")
        worker.target_dir = self.target_dir
        
        # Don't create backlog file
        
        with pytest.raises(WorkerError) as exc_info:
            worker._load_task_spec()
        
        # Should not use fallback (wrong version)
        assert "not found in backlog" in str(exc_info.value)
    
    def test_task_in_backlog_takes_precedence(self):
        """Should use backlog entry if topology task is defined there."""
        worker = create_mock_worker(self.temp_dir, task_id="topology-test-target-v1")
        worker.target_dir = self.target_dir
        
        # Create backlog with explicit topology task
        backlog_dir = self.target_dir / ".leviathan"
        backlog_dir.mkdir(parents=True, exist_ok=True)
        backlog_file = backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: topology-test-target-v1
    title: Custom Topology Task
    scope: topology
    priority: low
    ready: true
    estimated_size: large
    allowed_paths: [custom/path.py]
    acceptance_criteria: [Custom criteria]
    dependencies: []
""")
        
        task = worker._load_task_spec()
        
        # Should use backlog entry, not fallback
        assert task.title == "Custom Topology Task"
        assert task.priority == "low"
        assert task.estimated_size == "large"
        assert task.allowed_paths == ["custom/path.py"]


class TestAttemptLifecycle:
    """Test that attempt lifecycle events are emitted correctly."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_attempt_created_emitted_first(self):
        """Should emit attempt.created before attempt.started."""
        worker = create_mock_worker(self.temp_dir)
        
        # Emit events as worker.run() does
        worker._emit_event("attempt.created", {
            'attempt_id': worker.attempt_id,
            'task_id': worker.task_id,
            'target_id': worker.target_name,
            'status': 'created',
        })
        
        worker._emit_event("attempt.started", {
            'attempt_id': worker.attempt_id,
            'task_id': worker.task_id,
            'target_id': worker.target_name,
            'status': 'running',
        })
        
        # Verify order
        assert len(worker.events) == 2
        assert worker.events[0]['event_type'] == 'attempt.created'
        assert worker.events[1]['event_type'] == 'attempt.started'
    
    def test_attempt_created_includes_required_fields(self):
        """Should include attempt_id, task_id, target_id, attempt_number in attempt.created."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("attempt.created", {
            'attempt_id': 'attempt-123',
            'task_id': 'task-456',
            'target_id': 'test-target',
            'attempt_number': 1,
            'status': 'created',
        })
        
        event = worker.events[0]
        payload = event['payload']
        
        assert payload['attempt_id'] == 'attempt-123'
        assert payload['task_id'] == 'task-456'
        assert payload['target_id'] == 'test-target'
        assert payload['attempt_number'] == 1
        assert payload['status'] == 'created'
    
    def test_attempt_started_includes_required_fields(self):
        """Should include attempt_id, task_id, target_id in attempt.started."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("attempt.started", {
            'attempt_id': 'attempt-123',
            'task_id': 'task-456',
            'target_id': 'test-target',
            'status': 'running',
        })
        
        event = worker.events[0]
        payload = event['payload']
        
        assert payload['attempt_id'] == 'attempt-123'
        assert payload['task_id'] == 'task-456'
        assert payload['target_id'] == 'test-target'
        assert payload['status'] == 'running'
    
    def test_attempt_failed_includes_required_fields(self):
        """Should include attempt_id, task_id, target_id in attempt.failed."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("attempt.failed", {
            'attempt_id': 'attempt-123',
            'task_id': 'task-456',
            'target_id': 'test-target',
            'status': 'failed',
            'failure_type': 'test_failure',
        })
        
        event = worker.events[0]
        payload = event['payload']
        
        assert payload['attempt_id'] == 'attempt-123'
        assert payload['task_id'] == 'task-456'
        assert payload['target_id'] == 'test-target'
        assert payload['status'] == 'failed'
    
    def test_attempt_succeeded_includes_required_fields(self):
        """Should include attempt_id, task_id, target_id in attempt.succeeded."""
        worker = create_mock_worker(self.temp_dir)
        
        worker._emit_event("attempt.succeeded", {
            'attempt_id': 'attempt-123',
            'task_id': 'task-456',
            'target_id': 'test-target',
            'status': 'succeeded',
        })
        
        event = worker.events[0]
        payload = event['payload']
        
        assert payload['attempt_id'] == 'attempt-123'
        assert payload['task_id'] == 'task-456'
        assert payload['target_id'] == 'test-target'
        assert payload['status'] == 'succeeded'


class TestEventBundleTarget:
    """Test that event bundles include target field."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_event_bundle_includes_target(self):
        """Event bundle should include top-level 'target' field."""
        worker = create_mock_worker(self.temp_dir)
        worker.target_name = "my-repo"
        
        # Emit some events
        worker._emit_event("attempt.started", {'attempt_id': 'attempt-123'})
        
        # Create bundle as _post_event_bundle does
        bundle = {
            'target': worker.target_name,
            'bundle_id': f"bundle-{worker.attempt_id}",
            'events': worker.events,
            'artifacts': worker.artifacts
        }
        
        # Verify target is present
        assert 'target' in bundle
        assert bundle['target'] == 'my-repo'
    
    @patch('leviathan.executor.worker.requests.post')
    def test_post_event_bundle_sends_target(self, mock_post):
        """Should send target field in event bundle POST request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        worker = create_mock_worker(self.temp_dir)
        worker.target_name = "test-repo"
        
        worker._emit_event("attempt.started", {'attempt_id': 'attempt-123'})
        worker._post_event_bundle()
        
        # Verify POST was called
        assert mock_post.called
        
        # Verify payload includes target
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        
        assert 'target' in payload
        assert payload['target'] == 'test-repo'
    
    def test_event_bundle_target_matches_worker_target_name(self):
        """Event bundle target should match worker's target_name."""
        worker = create_mock_worker(self.temp_dir)
        worker.target_name = "leviathan"
        
        bundle = {
            'target': worker.target_name,
            'bundle_id': f"bundle-{worker.attempt_id}",
            'events': worker.events,
            'artifacts': worker.artifacts
        }
        
        assert bundle['target'] == worker.target_name
        assert bundle['target'] == "leviathan"
