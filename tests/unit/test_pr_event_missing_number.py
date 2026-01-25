"""
Unit tests for PR events with missing pr_number field.
"""
import pytest
from datetime import datetime, timezone
from leviathan.graph.store import GraphStore
from leviathan.graph.events import Event, EventType


class TestPREventMissingNumber:
    """Test PR event handling with optional pr_number."""
    
    def test_pr_created_with_pr_number(self):
        """Should create PR node with pr_number in node_id."""
        store = GraphStore(backend="memory")
        
        event = Event(
            event_id="test-event-1",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "pr_number": 123,
                "pr_url": "https://github.com/org/repo/pull/123",
                "title": "Test PR",
                "state": "open"
            }
        )
        
        store.apply_event(event)
        
        # Verify PR node exists with expected node_id
        from leviathan.graph.schema import NodeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
        assert nodes[0]['node_id'] == "pr-123"
        assert nodes[0]['properties']['pr_number'] == 123
        assert nodes[0]['properties']['pr_url'] == "https://github.com/org/repo/pull/123"
    
    def test_pr_created_without_pr_number_with_url(self):
        """Should create PR node using hashed pr_url when pr_number missing."""
        store = GraphStore(backend="memory")
        
        pr_url = "https://github.com/org/repo/pull/placeholder"
        event = Event(
            event_id="test-event-2",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "pr_url": pr_url,
                "title": "Placeholder PR",
                "state": "open"
            }
        )
        
        store.apply_event(event)
        
        # Verify PR node exists
        from leviathan.graph.schema import NodeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
        assert nodes[0]['node_id'].startswith("pr-")
        assert len(nodes[0]['node_id']) == 15  # pr- + 12 hex chars
        assert 'pr_number' not in nodes[0]['properties'] or nodes[0]['properties']['pr_number'] is None
        assert nodes[0]['properties']['pr_url'] == pr_url
    
    def test_pr_created_without_pr_number_or_url(self):
        """Should create PR node using event_id when both pr_number and pr_url missing."""
        store = GraphStore(backend="memory")
        
        event_id = "test-event-fallback-123"
        event = Event(
            event_id=event_id,
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "title": "Minimal PR",
                "state": "open",
                "pr_url": ""  # Empty URL
            }
        )
        
        store.apply_event(event)
        
        # Verify PR node exists
        from leviathan.graph.schema import NodeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
        assert nodes[0]['node_id'] == f"pr-{event_id[:12]}"
    
    def test_pr_created_with_attempt_link(self):
        """Should link PR to attempt when attempt_id present."""
        store = GraphStore(backend="memory")
        
        # Create attempt first
        attempt_event = Event(
            event_id="attempt-event",
            event_type=EventType.ATTEMPT_STARTED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "attempt_id": "attempt-123",
                "task_id": "task-1"
            }
        )
        store.apply_event(attempt_event)
        
        # Create PR with attempt_id but no pr_number
        pr_event = Event(
            event_id="pr-event",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "pr_url": "https://github.com/org/repo/pull/placeholder",
                "title": "Test PR",
                "state": "open",
                "attempt_id": "attempt-123"
            }
        )
        store.apply_event(pr_event)
        
        # Verify PR node exists
        from leviathan.graph.schema import NodeType, EdgeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
        
        # Verify edge exists
        edges = store.query_edges(from_node="attempt-123", edge_type=EdgeType.PRODUCED)
        assert len(edges) >= 1
    
    def test_multiple_pr_events_same_url_deterministic(self):
        """Should create same node_id for same pr_url (deterministic hashing)."""
        store = GraphStore(backend="memory")
        
        pr_url = "https://github.com/org/repo/pull/test"
        
        # First event
        event1 = Event(
            event_id="event-1",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="actor-1",
            payload={
                "pr_url": pr_url,
                "title": "First",
                "state": "open"
            }
        )
        store.apply_event(event1)
        
        # Second event with same URL
        event2 = Event(
            event_id="event-2",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="actor-2",
            payload={
                "pr_url": pr_url,
                "title": "Updated",
                "state": "open"
            }
        )
        store.apply_event(event2)
        
        # Should have only 1 PR node (upserted)
        from leviathan.graph.schema import NodeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
        assert nodes[0]['node_id'].startswith("pr-")
    
    def test_pr_event_no_crash_on_missing_fields(self):
        """Should not crash when pr_number missing (regression test)."""
        store = GraphStore(backend="memory")
        
        # This should not raise KeyError
        event = Event(
            event_id="safe-event",
            event_type=EventType.PR_CREATED,
            timestamp=datetime.now(timezone.utc),
            actor_id="test-actor",
            payload={
                "pr_url": "https://github.com/org/repo/pull/safe",
                "title": "Safe PR",
                "state": "open"
                # pr_number intentionally missing
            }
        )
        
        # Should not raise exception
        store.apply_event(event)
        
        # Verify it worked
        from leviathan.graph.schema import NodeType
        nodes = store.query_nodes(node_type=NodeType.PULL_REQUEST)
        assert len(nodes) == 1
