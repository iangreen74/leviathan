"""
Unit tests for graph-driven scheduler.
"""
import pytest
import uuid
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.artifacts.store import ArtifactStore
from leviathan.control_plane.scheduler import Scheduler, RetryPolicy
from leviathan.executors.base import Executor, AttemptResult, ArtifactRef


class MockExecutor(Executor):
    """Mock executor for testing."""
    
    def __init__(self, should_succeed=True):
        """
        Initialize mock executor.
        
        Args:
            should_succeed: Whether attempts should succeed or fail
        """
        self.should_succeed = should_succeed
        self.executed_attempts = []
    
    def run_attempt(self, target_id, task_id, attempt_id, task_spec, target_config):
        """Record execution and return result."""
        self.executed_attempts.append({
            'target_id': target_id,
            'task_id': task_id,
            'attempt_id': attempt_id
        })
        
        if self.should_succeed:
            return AttemptResult(
                success=True,
                branch_name=f"leviathan/{task_id}",
                artifacts=[],
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
        else:
            return AttemptResult(
                success=False,
                failure_type="test_failure",
                error_summary="Simulated test failure",
                artifacts=[],
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow()
            )
    
    def cleanup(self, attempt_id):
        """No-op cleanup."""
        pass


class TestScheduler:
    """Test scheduler functionality."""
    
    def setup_method(self):
        """Create test stores and scheduler."""
        # Create temporary directory for isolated event store
        self.temp_dir = Path(tempfile.mkdtemp())
        self.events_path = self.temp_dir / "events.ndjson"
        
        self.event_store = EventStore(backend="ndjson")
        self.event_store.ndjson_path = self.events_path
        self.event_store.ndjson_path.touch()
        
        self.graph_store = GraphStore(backend="memory")
        self.artifact_store = ArtifactStore(storage_root=self.temp_dir / "artifacts")
        self.executor = MockExecutor(should_succeed=True)
        self.retry_policy = RetryPolicy(max_attempts_per_task=3, backoff_seconds=60)
        
        self.scheduler = Scheduler(
            event_store=self.event_store,
            graph_store=self.graph_store,
            artifact_store=self.artifact_store,
            executor=self.executor,
            retry_policy=self.retry_policy
        )
    
    def teardown_method(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def _create_target(self, target_id="test-target"):
        """Helper to create a target in the graph."""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'target_id': target_id,
                'node_id': target_id,
                'node_type': 'Target',
                'name': target_id,
                'repo_url': f'git@github.com:test/{target_id}.git',
                'default_branch': 'main',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        self.event_store.append_event(event)
        self.graph_store.apply_event(event)
        return target_id
    
    def _create_task(self, target_id, task_id="test-task-001", status="pending"):
        """Helper to create a task in the graph."""
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'task_id': task_id,
                'node_id': task_id,
                'node_type': 'Task',
                'target_id': target_id,
                'title': 'Test task',
                'scope': 'test',
                'priority': 'high',
                'estimated_size': 'small',
                'allowed_paths': [],
                'acceptance_criteria': [],
                'status': status,
                'created_at': datetime.utcnow().isoformat()
            }
        )
        self.event_store.append_event(event)
        self.graph_store.apply_event(event)
        return task_id
    
    def test_select_next_task_with_pending_task(self):
        """Should select pending task."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.scheduler.select_next_task(target_id)
        
        assert task is not None
        assert task['node_id'] == task_id
        assert task['properties']['status'] == 'pending'
    
    def test_select_next_task_no_pending_tasks(self):
        """Should return None when no pending tasks."""
        target_id = self._create_target()
        self._create_task(target_id, status="completed")
        
        task = self.scheduler.select_next_task(target_id)
        
        assert task is None
    
    def test_create_attempt_emits_event(self):
        """Creating attempt should emit attempt.created event."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        attempt_id = self.scheduler.create_attempt(task)
        
        # Verify attempt node exists
        attempt_node = self.graph_store.get_node(attempt_id)
        assert attempt_node is not None
        assert attempt_node['properties']['task_id'] == task_id
        assert attempt_node['properties']['attempt_number'] == 1
    
    def test_run_attempt_success_emits_events(self):
        """Successful attempt should emit started and succeeded events."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        attempt_id = self.scheduler.create_attempt(task)
        
        target_config = {'target_id': target_id, 'repo_url': 'test'}
        result = self.scheduler.run_attempt(attempt_id, task, target_config)
        
        assert result.success is True
        
        # Verify executor was called
        assert len(self.executor.executed_attempts) == 1
        assert self.executor.executed_attempts[0]['attempt_id'] == attempt_id
        
        # Verify events were emitted
        events = self.event_store.get_events()
        event_types = [e.event_type for e in events]
        
        assert EventType.ATTEMPT_CREATED in event_types
        assert EventType.ATTEMPT_STARTED in event_types
        assert EventType.ATTEMPT_SUCCEEDED in event_types
    
    def test_run_attempt_failure_emits_failed_event(self):
        """Failed attempt should emit failed event."""
        # Use failing executor
        self.executor = MockExecutor(should_succeed=False)
        self.scheduler.executor = self.executor
        
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        attempt_id = self.scheduler.create_attempt(task)
        
        target_config = {'target_id': target_id, 'repo_url': 'test'}
        result = self.scheduler.run_attempt(attempt_id, task, target_config)
        
        assert result.success is False
        
        # Verify failed event emitted
        events = self.event_store.get_events()
        failed_events = [e for e in events if e.event_type == EventType.ATTEMPT_FAILED]
        
        assert len(failed_events) == 1
        assert failed_events[0].payload['failure_type'] == 'test_failure'
    
    def test_handle_retry_schedules_retry(self):
        """Should schedule retry when under max attempts."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        
        # Create one failed attempt
        attempt_id = self.scheduler.create_attempt(task)
        
        # Handle retry
        retry_scheduled = self.scheduler.handle_retry(task)
        
        assert retry_scheduled is True
        
        # Verify retry.scheduled event
        events = self.event_store.get_events()
        retry_events = [e for e in events if e.event_type == "retry.scheduled"]
        
        assert len(retry_events) == 1
        assert retry_events[0].payload['task_id'] == task_id
        assert retry_events[0].payload['retry_number'] == 2
    
    def test_handle_retry_max_attempts_reached(self):
        """Should not retry when max attempts reached."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        
        # Create 3 failed attempts (max)
        for i in range(3):
            attempt_id = self.scheduler.create_attempt(task)
        
        # Try to handle retry
        retry_scheduled = self.scheduler.handle_retry(task)
        
        assert retry_scheduled is False
        
        # Verify task marked as failed
        events = self.event_store.get_events()
        task_completed_events = [
            e for e in events 
            if e.event_type == EventType.TASK_COMPLETED 
            and e.payload.get('status') == 'failed'
        ]
        
        assert len(task_completed_events) == 1
    
    def test_run_once_executes_task(self):
        """run_once should select task, create attempt, and execute."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        target_config = {'target_id': target_id, 'repo_url': 'test'}
        executed = self.scheduler.run_once(target_id, target_config)
        
        assert executed is True
        
        # Verify executor was called
        assert len(self.executor.executed_attempts) == 1
        
        # Verify task marked as completed
        events = self.event_store.get_events()
        task_completed_events = [
            e for e in events 
            if e.event_type == EventType.TASK_COMPLETED
            and e.payload.get('status') == 'completed'
        ]
        
        assert len(task_completed_events) == 1
    
    def test_run_once_no_tasks_returns_false(self):
        """run_once should return False when no tasks ready."""
        target_id = self._create_target()
        
        target_config = {'target_id': target_id, 'repo_url': 'test'}
        executed = self.scheduler.run_once(target_id, target_config)
        
        assert executed is False
    
    def test_multiple_attempts_increment_attempt_number(self):
        """Multiple attempts should have incrementing attempt numbers."""
        target_id = self._create_target()
        task_id = self._create_task(target_id)
        
        task = self.graph_store.get_node(task_id)
        
        # Create 3 attempts
        attempt_ids = []
        for i in range(3):
            attempt_id = self.scheduler.create_attempt(task)
            attempt_ids.append(attempt_id)
        
        # Verify attempt numbers
        for i, attempt_id in enumerate(attempt_ids):
            attempt_node = self.graph_store.get_node(attempt_id)
            assert attempt_node['properties']['attempt_number'] == i + 1
    
    def test_retry_policy_configuration(self):
        """Retry policy should be configurable."""
        custom_policy = RetryPolicy(
            max_attempts_per_task=5,
            backoff_seconds=120,
            escalation_after=2
        )
        
        assert custom_policy.max_attempts_per_task == 5
        assert custom_policy.backoff_seconds == 120
        assert custom_policy.escalation_after == 2


class TestRetryPolicy:
    """Test retry policy."""
    
    def test_default_policy(self):
        """Default policy should have sensible defaults."""
        policy = RetryPolicy()
        
        assert policy.max_attempts_per_task == 3
        assert policy.backoff_seconds == 60
        assert policy.escalation_after == 3
    
    def test_custom_policy(self):
        """Should accept custom values."""
        policy = RetryPolicy(
            max_attempts_per_task=10,
            backoff_seconds=300,
            escalation_after=5
        )
        
        assert policy.max_attempts_per_task == 10
        assert policy.backoff_seconds == 300
        assert policy.escalation_after == 5
