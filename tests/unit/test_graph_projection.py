"""
Unit tests for graph projection determinism.
"""
import pytest
import uuid
from datetime import datetime

from leviathan.graph.events import Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.graph.schema import NodeType, EdgeType


class TestProjectionDeterminism:
    """Test that graph projection is deterministic."""
    
    def test_same_events_produce_same_graph(self):
        """Same events applied twice should produce identical graph."""
        # Create events
        events = [
            Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TARGET_REGISTERED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={
                    'target_id': 'radix',
                    'node_id': 'radix',
                    'node_type': 'Target',
                    'name': 'radix',
                    'repo_url': 'git@github.com:test/radix.git',
                    'default_branch': 'main',
                    'created_at': datetime.utcnow().isoformat()
                }
            ),
            Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={
                    'task_id': 'task-001',
                    'node_id': 'task-001',
                    'node_type': 'Task',
                    'target_id': 'radix',
                    'title': 'Test task',
                    'scope': 'test',
                    'priority': 'high',
                    'estimated_size': 'small',
                    'allowed_paths': [],
                    'acceptance_criteria': [],
                    'status': 'pending',
                    'created_at': datetime.utcnow().isoformat()
                }
            )
        ]
        
        # Build projection 1
        store1 = GraphStore(backend="memory")
        store1.rebuild_projection(events)
        
        # Build projection 2
        store2 = GraphStore(backend="memory")
        store2.rebuild_projection(events)
        
        # Should have same nodes
        assert len(store1.nodes) == len(store2.nodes)
        assert set(store1.nodes.keys()) == set(store2.nodes.keys())
        
        # Should have same edges
        assert len(store1.edges) == len(store2.edges)
        assert set(store1.edges.keys()) == set(store2.edges.keys())
    
    def test_target_registered_creates_node(self):
        """TARGET_REGISTERED event should create target node."""
        store = GraphStore(backend="memory")
        
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'target_id': 'radix',
                'node_id': 'radix',
                'node_type': 'Target',
                'name': 'radix',
                'repo_url': 'git@github.com:test/radix.git',
                'default_branch': 'main',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        
        store.apply_event(event)
        
        node = store.get_node('radix')
        assert node is not None
        assert node['node_type'] == NodeType.TARGET.value
        assert node['properties']['name'] == 'radix'
    
    def test_task_created_creates_node_and_edge(self):
        """TASK_CREATED event should create task node and edge to target."""
        store = GraphStore(backend="memory")
        
        # First create target
        target_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'target_id': 'radix',
                'node_id': 'radix',
                'node_type': 'Target',
                'name': 'radix',
                'repo_url': 'git@github.com:test/radix.git',
                'default_branch': 'main',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(target_event)
        
        # Create task
        task_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'task_id': 'task-001',
                'node_id': 'task-001',
                'node_type': 'Task',
                'target_id': 'radix',
                'title': 'Test task',
                'scope': 'test',
                'priority': 'high',
                'estimated_size': 'small',
                'allowed_paths': [],
                'acceptance_criteria': [],
                'status': 'pending',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(task_event)
        
        # Check node created
        node = store.get_node('task-001')
        assert node is not None
        assert node['node_type'] == NodeType.TASK.value
        
        # Check edge created
        edges = store.query_edges(from_node='task-001', edge_type=EdgeType.DEPENDS_ON)
        assert len(edges) == 1
        assert edges[0]['to_node'] == 'radix'
    
    def test_attempt_created_links_to_task(self):
        """ATTEMPT_CREATED event should create attempt node and link to task."""
        store = GraphStore(backend="memory")
        
        # Create task first
        task_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={
                'task_id': 'task-001',
                'node_id': 'task-001',
                'node_type': 'Task',
                'target_id': 'radix',
                'title': 'Test task',
                'scope': 'test',
                'priority': 'high',
                'estimated_size': 'small',
                'allowed_paths': [],
                'acceptance_criteria': [],
                'status': 'pending',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(task_event)
        
        # Create attempt
        attempt_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ATTEMPT_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="scheduler",
            payload={
                'attempt_id': 'attempt-001',
                'node_id': 'attempt-001',
                'node_type': 'Attempt',
                'task_id': 'task-001',
                'attempt_number': 1,
                'status': 'created',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(attempt_event)
        
        # Check attempt node
        node = store.get_node('attempt-001')
        assert node is not None
        assert node['node_type'] == NodeType.ATTEMPT.value
        
        # Check edge to task
        edges = store.query_edges(from_node='attempt-001', edge_type=EdgeType.DEPENDS_ON)
        assert len(edges) == 1
        assert edges[0]['to_node'] == 'task-001'
    
    def test_artifact_created_links_to_attempt(self):
        """ARTIFACT_CREATED event should create artifact and link to attempt."""
        store = GraphStore(backend="memory")
        
        # Create attempt first
        attempt_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ATTEMPT_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="scheduler",
            payload={
                'attempt_id': 'attempt-001',
                'node_id': 'attempt-001',
                'node_type': 'Attempt',
                'task_id': 'task-001',
                'attempt_number': 1,
                'status': 'created',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(attempt_event)
        
        # Create artifact
        artifact_event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ARTIFACT_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="executor",
            payload={
                'artifact_id': 'artifact-001',
                'node_id': 'artifact-001',
                'node_type': 'Artifact',
                'attempt_id': 'attempt-001',
                'sha256': 'a' * 64,
                'artifact_type': 'log',
                'size_bytes': 1024,
                'storage_path': '/path/to/artifact',
                'created_at': datetime.utcnow().isoformat()
            }
        )
        store.apply_event(artifact_event)
        
        # Check artifact node
        node = store.get_node('artifact-001')
        assert node is not None
        assert node['node_type'] == NodeType.ARTIFACT.value
        
        # Check PRODUCED edge from attempt to artifact
        edges = store.query_edges(from_node='attempt-001', edge_type=EdgeType.PRODUCED)
        assert len(edges) == 1
        assert edges[0]['to_node'] == 'artifact-001'
    
    def test_query_nodes_by_type(self):
        """Should be able to query nodes by type."""
        store = GraphStore(backend="memory")
        
        # Create multiple node types
        events = [
            Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TARGET_REGISTERED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={
                    'target_id': f'target-{i}',
                    'node_id': f'target-{i}',
                    'node_type': 'Target',
                    'name': f'target-{i}',
                    'repo_url': 'test',
                    'default_branch': 'main',
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            for i in range(3)
        ]
        
        events.extend([
            Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={
                    'task_id': f'task-{i}',
                    'node_id': f'task-{i}',
                    'node_type': 'Task',
                    'target_id': 'target-0',
                    'title': f'Task {i}',
                    'scope': 'test',
                    'priority': 'high',
                    'estimated_size': 'small',
                    'allowed_paths': [],
                    'acceptance_criteria': [],
                    'status': 'pending',
                    'created_at': datetime.utcnow().isoformat()
                }
            )
            for i in range(5)
        ])
        
        store.rebuild_projection(events)
        
        # Query by type
        targets = store.query_nodes(node_type=NodeType.TARGET)
        tasks = store.query_nodes(node_type=NodeType.TASK)
        
        assert len(targets) == 3
        assert len(tasks) == 5
