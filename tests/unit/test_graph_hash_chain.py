"""
Unit tests for event store hash chain integrity.
"""
import pytest
import uuid
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from leviathan.graph.events import EventStore, Event, EventType


class TestHashChain:
    """Test hash chain integrity."""
    
    def setup_method(self):
        """Create temporary directory for test events."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.ndjson_path = self.temp_dir / "events.ndjson"
    
    def teardown_method(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_first_event_has_no_prev_hash(self):
        """First event in chain should have prev_hash=None."""
        # Override default path
        import leviathan.graph.events
        original_path = Path.home() / ".leviathan" / "graph" / "events.ndjson"
        
        # Use temp path
        store = EventStore(backend="ndjson")
        store.ndjson_path = self.ndjson_path
        store.ndjson_path.touch()
        
        event = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={'target_id': 'test', 'node_id': 'test', 'node_type': 'Target', 'name': 'test', 'repo_url': 'test', 'default_branch': 'main', 'created_at': datetime.utcnow().isoformat()}
        )
        
        event = store.append_event(event)
        
        assert event.prev_hash is None
        assert event.hash is not None
        assert len(event.hash) == 64  # SHA256 hex
    
    def test_second_event_links_to_first(self):
        """Second event should have prev_hash pointing to first event."""
        store = EventStore(backend="ndjson")
        store.ndjson_path = self.ndjson_path
        store.ndjson_path.touch()
        
        event1 = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={'target_id': 'test', 'node_id': 'test', 'node_type': 'Target', 'name': 'test', 'repo_url': 'test', 'default_branch': 'main', 'created_at': datetime.utcnow().isoformat()}
        )
        event1 = store.append_event(event1)
        
        event2 = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={'task_id': 'task-1', 'node_id': 'task-1', 'node_type': 'Task', 'target_id': 'test', 'title': 'Test', 'scope': 'test', 'priority': 'high', 'estimated_size': 'small', 'allowed_paths': [], 'acceptance_criteria': [], 'status': 'pending', 'created_at': datetime.utcnow().isoformat()}
        )
        event2 = store.append_event(event2)
        
        assert event2.prev_hash == event1.hash
        assert event2.hash != event1.hash
    
    def test_hash_is_deterministic(self):
        """Same event data should produce same hash."""
        event_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()
        payload = {'target_id': 'test', 'node_id': 'test', 'node_type': 'Target', 'name': 'test', 'repo_url': 'test', 'default_branch': 'main', 'created_at': timestamp.isoformat()}
        
        event1 = Event(
            event_id=event_id,
            event_type=EventType.TARGET_REGISTERED,
            timestamp=timestamp,
            actor_id="test",
            payload=payload,
            prev_hash=None
        )
        hash1 = event1.compute_hash()
        
        event2 = Event(
            event_id=event_id,
            event_type=EventType.TARGET_REGISTERED,
            timestamp=timestamp,
            actor_id="test",
            payload=payload,
            prev_hash=None
        )
        hash2 = event2.compute_hash()
        
        assert hash1 == hash2
    
    def test_verify_chain_valid(self):
        """Verify chain should pass for valid chain."""
        store = EventStore(backend="ndjson")
        store.ndjson_path = self.ndjson_path
        store.ndjson_path.touch()
        
        # Add 3 events
        for i in range(3):
            event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={'task_id': f'task-{i}', 'node_id': f'task-{i}', 'node_type': 'Task', 'target_id': 'test', 'title': f'Task {i}', 'scope': 'test', 'priority': 'high', 'estimated_size': 'small', 'allowed_paths': [], 'acceptance_criteria': [], 'status': 'pending', 'created_at': datetime.utcnow().isoformat()}
            )
            store.append_event(event)
        
        is_valid, error = store.verify_chain()
        assert is_valid is True
        assert error is None
    
    def test_verify_chain_detects_tampering(self):
        """Verify chain should detect if event hash is modified."""
        store = EventStore(backend="ndjson")
        store.ndjson_path = self.ndjson_path
        store.ndjson_path.touch()
        
        # Add 2 events
        event1 = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TARGET_REGISTERED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={'target_id': 'test', 'node_id': 'test', 'node_type': 'Target', 'name': 'test', 'repo_url': 'test', 'default_branch': 'main', 'created_at': datetime.utcnow().isoformat()}
        )
        store.append_event(event1)
        
        event2 = Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            timestamp=datetime.utcnow(),
            actor_id="test",
            payload={'task_id': 'task-1', 'node_id': 'task-1', 'node_type': 'Task', 'target_id': 'test', 'title': 'Test', 'scope': 'test', 'priority': 'high', 'estimated_size': 'small', 'allowed_paths': [], 'acceptance_criteria': [], 'status': 'pending', 'created_at': datetime.utcnow().isoformat()}
        )
        store.append_event(event2)
        
        # Tamper with the file: change event2's payload
        import json
        lines = []
        with open(self.ndjson_path, 'r') as f:
            for line in f:
                data = json.loads(line)
                if data['event_id'] == event2.event_id:
                    # Modify payload but keep hash (simulating tampering)
                    data['payload']['title'] = 'TAMPERED'
                lines.append(json.dumps(data))
        
        with open(self.ndjson_path, 'w') as f:
            for line in lines:
                f.write(line + '\n')
        
        # Verify should fail
        is_valid, error = store.verify_chain()
        assert is_valid is False
        assert "hash mismatch" in error.lower()
    
    def test_chain_with_many_events(self):
        """Test chain with many events."""
        store = EventStore(backend="ndjson")
        store.ndjson_path = self.ndjson_path
        store.ndjson_path.touch()
        
        # Add 100 events
        for i in range(100):
            event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.TASK_CREATED,
                timestamp=datetime.utcnow(),
                actor_id="test",
                payload={'task_id': f'task-{i}', 'node_id': f'task-{i}', 'node_type': 'Task', 'target_id': 'test', 'title': f'Task {i}', 'scope': 'test', 'priority': 'high', 'estimated_size': 'small', 'allowed_paths': [], 'acceptance_criteria': [], 'status': 'pending', 'created_at': datetime.utcnow().isoformat()}
            )
            store.append_event(event)
        
        # Verify chain
        is_valid, error = store.verify_chain()
        assert is_valid is True
        
        # Check all events retrieved
        events = store.get_events()
        assert len(events) == 100
        
        # Verify chain links
        for i in range(1, len(events)):
            assert events[i].prev_hash == events[i-1].hash
