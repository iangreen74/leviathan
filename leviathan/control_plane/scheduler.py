"""
Graph-driven scheduler for Leviathan task attempts.

Selects ready tasks, creates attempts, and orchestrates execution.
"""
import uuid
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.graph.schema import NodeType, EdgeType
from leviathan.artifacts.store import ArtifactStore
from leviathan.executors.base import Executor, AttemptResult
from leviathan.backlog_loader import load_backlog_tasks, filter_ready_tasks


class RetryPolicy:
    """Retry policy for failed attempts."""
    
    def __init__(
        self,
        max_attempts_per_task: int = 3,
        backoff_seconds: int = 60,
        escalation_after: int = 3
    ):
        """
        Initialize retry policy.
        
        Args:
            max_attempts_per_task: Maximum attempts before giving up
            backoff_seconds: Seconds to wait between retries
            escalation_after: Number of failures before escalation
        """
        self.max_attempts_per_task = max_attempts_per_task
        self.backoff_seconds = backoff_seconds
        self.escalation_after = escalation_after


class Scheduler:
    """
    Graph-driven scheduler for task attempts.
    
    Responsibilities:
    1. Select next ready task from graph
    2. Create Attempt node with relationships
    3. Execute attempt via executor
    4. Emit events for lifecycle
    5. Handle retries with backoff
    """
    
    def __init__(
        self,
        event_store: EventStore,
        graph_store: GraphStore,
        artifact_store: ArtifactStore,
        executor: Executor,
        retry_policy: Optional[RetryPolicy] = None
    ):
        """
        Initialize scheduler.
        
        Args:
            event_store: Event store for emitting events
            graph_store: Graph store for querying tasks
            artifact_store: Artifact store for storing outputs
            executor: Executor for running attempts
            retry_policy: Retry policy (default: RetryPolicy())
        """
        self.event_store = event_store
        self.graph_store = graph_store
        self.artifact_store = artifact_store
        self.executor = executor
        self.retry_policy = retry_policy or RetryPolicy()
    
    def select_next_task(self, target_id: str) -> Optional[Dict[str, Any]]:
        """
        Select next ready task for execution.
        
        A task is ready if:
        1. Status is 'pending'
        2. All dependencies are satisfied
        3. Not exceeded max attempts
        
        Args:
            target_id: Target identifier
            
        Returns:
            Task node or None if no tasks ready
        """
        # Get all pending tasks for target
        all_tasks = self.graph_store.query_nodes(node_type=NodeType.TASK)
        
        pending_tasks = [
            task for task in all_tasks
            if task['properties'].get('target_id') == target_id
            and task['properties'].get('status') == 'pending'
        ]
        
        for task in pending_tasks:
            task_id = task['node_id']
            
            # Check if exceeded max attempts
            attempts = self._get_task_attempts(task_id)
            if len(attempts) >= self.retry_policy.max_attempts_per_task:
                continue
            
            # Check if dependencies satisfied
            # (For now, we don't have dependency tracking, so all tasks are ready)
            # In future, check DEPENDS_ON edges and verify dependency tasks are completed
            
            return task
        
        return None
    
    def _get_task_attempts(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all attempts for a task."""
        all_attempts = self.graph_store.query_nodes(node_type=NodeType.ATTEMPT)
        return [
            attempt for attempt in all_attempts
            if attempt['properties'].get('task_id') == task_id
        ]
    
    def create_attempt(self, task: Dict[str, Any]) -> str:
        """
        Create attempt for task.
        
        Args:
            task: Task node
            
        Returns:
            Attempt ID
        """
        task_id = task['node_id']
        target_id = task['properties'].get('target_id')
        
        # Generate attempt ID
        attempt_id = f"attempt-{uuid.uuid4().hex[:8]}"
        
        # Count existing attempts
        attempts = self._get_task_attempts(task_id)
        attempt_number = len(attempts) + 1
        
        # Emit attempt.created event
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ATTEMPT_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="scheduler",
            payload={
                'attempt_id': attempt_id,
                'node_id': attempt_id,
                'node_type': 'Attempt',
                'task_id': task_id,
                'target_id': target_id,
                'attempt_number': attempt_number,
                'status': 'created',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        
        self.event_store.append_event(event)
        self.graph_store.apply_event(event)
        
        return attempt_id
    
    def run_attempt(
        self,
        attempt_id: str,
        task: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """
        Run attempt via executor.
        
        Args:
            attempt_id: Attempt identifier
            task: Task node
            target_config: Target configuration
            
        Returns:
            AttemptResult
        """
        task_id = task['node_id']
        target_id = task['properties'].get('target_id')
        
        # Emit attempt.started event
        started_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ATTEMPT_STARTED,
            timestamp=datetime.utcnow(),
            actor_id="scheduler",
            payload={
                'attempt_id': attempt_id,
                'status': 'running',
                'started_at': datetime.utcnow().isoformat()
            }
        )
        
        self.event_store.append_event(started_event)
        self.graph_store.apply_event(started_event)
        
        # Execute via executor
        result = self.executor.run_attempt(
            target_id=target_id,
            task_id=task_id,
            attempt_id=attempt_id,
            task_spec=task['properties'],
            target_config=target_config
        )
        
        # Emit completion event
        if result.success:
            completion_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.ATTEMPT_SUCCEEDED,
                timestamp=datetime.utcnow(),
                actor_id="executor",
                payload={
                    'attempt_id': attempt_id,
                    'status': 'succeeded',
                    'completed_at': datetime.utcnow().isoformat(),
                    'branch_name': result.branch_name,
                    'pr_url': result.pr_url,
                    'commit_sha': result.commit_sha
                }
            )
        else:
            completion_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.ATTEMPT_FAILED,
                timestamp=datetime.utcnow(),
                actor_id="executor",
                payload={
                    'attempt_id': attempt_id,
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'failure_type': result.failure_type,
                    'error_summary': result.error_summary
                }
            )
        
        self.event_store.append_event(completion_event)
        self.graph_store.apply_event(completion_event)
        
        # Store artifacts
        for artifact_ref in result.artifacts:
            artifact_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.ARTIFACT_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="executor",
                payload={
                    'artifact_id': f"artifact-{uuid.uuid4().hex[:8]}",
                    'node_id': f"artifact-{uuid.uuid4().hex[:8]}",
                    'node_type': 'Artifact',
                    'attempt_id': attempt_id,
                    'sha256': artifact_ref.sha256,
                    'artifact_type': artifact_ref.artifact_type,
                    'size_bytes': artifact_ref.size_bytes,
                    'storage_path': artifact_ref.path,
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            
            self.event_store.append_event(artifact_event)
            self.graph_store.apply_event(artifact_event)
        
        return result
    
    def handle_retry(self, task: Dict[str, Any]) -> bool:
        """
        Determine if task should be retried.
        
        Args:
            task: Task node
            
        Returns:
            True if retry scheduled, False if max attempts reached
        """
        task_id = task['node_id']
        attempts = self._get_task_attempts(task_id)
        
        if len(attempts) >= self.retry_policy.max_attempts_per_task:
            # Max attempts reached, mark task as failed
            task_failed_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_COMPLETED,
                timestamp=datetime.utcnow(),
                actor_id="scheduler",
                payload={
                    'task_id': task_id,
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'reason': f'Max attempts ({self.retry_policy.max_attempts_per_task}) exceeded'
                }
            )
            
            self.event_store.append_event(task_failed_event)
            self.graph_store.apply_event(task_failed_event)
            
            return False
        
        # Schedule retry
        retry_event = Event(
            event_id=str(uuid.uuid4()),
            event_type="retry.scheduled",
            timestamp=datetime.utcnow(),
            actor_id="scheduler",
            payload={
                'task_id': task_id,
                'retry_number': len(attempts) + 1,
                'backoff_seconds': self.retry_policy.backoff_seconds,
                'scheduled_at': (datetime.utcnow() + timedelta(seconds=self.retry_policy.backoff_seconds)).isoformat()
            }
        )
        
        self.event_store.append_event(retry_event)
        
        return True
    
    def load_backlog_into_graph(self, target_id: str, backlog_path: Path):
        """
        Load tasks from backlog YAML file into graph.
        
        Args:
            target_id: Target identifier
            backlog_path: Path to backlog YAML file
        """
        # Load and normalize backlog tasks
        tasks = load_backlog_tasks(backlog_path)
        
        # Filter to ready tasks only
        ready_tasks = filter_ready_tasks(tasks)
        
        # Create TASK_CREATED events for each ready task
        for task_data in ready_tasks:
            task_id = task_data['id']
            
            # Check if task already exists in graph
            existing_task = self.graph_store.get_node(task_id)
            if existing_task:
                # Task already in graph, skip
                continue
            
            # Create task event
            event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="scheduler",
                payload={
                    'task_id': task_id,
                    'node_id': task_id,
                    'node_type': 'Task',
                    'target_id': target_id,
                    'title': task_data.get('title', 'Unknown'),
                    'scope': task_data.get('scope', 'unknown'),
                    'priority': task_data.get('priority', 'medium'),
                    'estimated_size': task_data.get('estimated_size', 'unknown'),
                    'allowed_paths': task_data.get('allowed_paths', []),
                    'acceptance_criteria': task_data.get('acceptance_criteria', []),
                    'status': 'pending',
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            
            self.event_store.append_event(event)
            self.graph_store.apply_event(event)
    
    def run_once(self, target_id: str, target_config: Dict[str, Any]) -> bool:
        """
        Run scheduler once: select task, create attempt, execute.
        
        Args:
            target_id: Target identifier
            target_config: Target configuration
            
        Returns:
            True if task was executed, False if no tasks ready
        """
        # Load backlog tasks into graph if backlog_path provided
        if 'backlog_path' in target_config:
            backlog_path = Path(target_config['backlog_path'])
            if backlog_path.exists():
                self.load_backlog_into_graph(target_id, backlog_path)
        
        # Select next ready task
        task = self.select_next_task(target_id)
        
        if not task:
            print(f"No ready tasks for target {target_id}")
            return False
        
        task_id = task['node_id']
        task_title = task['properties'].get('title', 'Unknown')
        
        print(f"Selected task: {task_id} - {task_title}")
        
        # Create attempt
        attempt_id = self.create_attempt(task)
        print(f"Created attempt: {attempt_id}")
        
        # Run attempt
        result = self.run_attempt(attempt_id, task, target_config)
        
        if result.success:
            print(f"Attempt succeeded: {attempt_id}")
            
            # Mark task as completed
            task_completed_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_COMPLETED,
                timestamp=datetime.utcnow(),
                actor_id="scheduler",
                payload={
                    'task_id': task_id,
                    'status': 'completed',
                    'completed_at': datetime.utcnow().isoformat()
                }
            )
            
            self.event_store.append_event(task_completed_event)
            self.graph_store.apply_event(task_completed_event)
        else:
            print(f"Attempt failed: {attempt_id} - {result.failure_type}")
            
            # Handle retry
            retry_scheduled = self.handle_retry(task)
            
            if retry_scheduled:
                print(f"Retry scheduled for task {task_id}")
            else:
                print(f"Max attempts reached for task {task_id}")
        
        return True
