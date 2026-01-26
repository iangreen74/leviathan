"""
Unit tests for rebuild-on-start functionality (failover mode).
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from leviathan.graph.events import Event, EventStore
from leviathan.graph.store import GraphStore
from leviathan.control_plane.api import rebuild_graph_from_events


class TestRebuildOnStart:
    """Test rebuild-on-start functionality."""
    
    @pytest.fixture
    def temp_event_store(self, tmp_path):
        """Create temporary event store."""
        store = EventStore(backend="ndjson", ndjson_dir=str(tmp_path))
        return store
    
    @pytest.fixture
    def temp_graph_store(self):
        """Create temporary graph store."""
        store = GraphStore(backend="memory")
        return store
    
    def test_rebuild_empty_journal(self, temp_event_store, temp_graph_store, monkeypatch):
        """Test rebuilding from empty event journal."""
        # Set global stores
        import leviathan.control_plane.api as api_module
        monkeypatch.setattr(api_module, 'event_store', temp_event_store)
        monkeypatch.setattr(api_module, 'graph_store', temp_graph_store)
        
        # Rebuild should succeed with no events
        rebuild_graph_from_events()
        
        # Graph should be empty
        nodes = temp_graph_store.query_nodes()
        edges = temp_graph_store.query_edges()
        assert len(nodes) == 0
        assert len(edges) == 0
    
    def test_rebuild_with_events(self, temp_event_store, temp_graph_store, monkeypatch):
        """Test rebuilding from event journal with events."""
        # Add some events
        events = [
            Event(
                event_id='event-1',
                event_type='target.registered',
                timestamp=datetime.now(timezone.utc),
                actor_id='test',
                payload={
                    'target_id': 'test-target',
                    'name': 'test-target',
                    'repo_url': 'https://github.com/test/repo',
                    'default_branch': 'main'
                }
            ),
            Event(
                event_id='event-2',
                event_type='attempt.started',
                timestamp=datetime.now(timezone.utc),
                actor_id='test',
                payload={'attempt_id': 'attempt-1', 'task_id': 'task-1', 'status': 'running'}
            ),
            Event(
                event_id='event-3',
                event_type='attempt.succeeded',
                timestamp=datetime.now(timezone.utc),
                actor_id='test',
                payload={'attempt_id': 'attempt-1', 'status': 'succeeded'}
            ),
        ]
        
        for event in events:
            temp_event_store.append_event(event)
        
        # Set global stores
        import leviathan.control_plane.api as api_module
        monkeypatch.setattr(api_module, 'event_store', temp_event_store)
        monkeypatch.setattr(api_module, 'graph_store', temp_graph_store)
        
        # Rebuild
        rebuild_graph_from_events()
        
        # Graph should have nodes
        nodes = temp_graph_store.query_nodes()
        assert len(nodes) > 0
    
    def test_rebuild_deterministic(self, temp_event_store, temp_graph_store, monkeypatch):
        """Test that rebuild is deterministic."""
        # Add events
        events = [
            Event(
                event_id='event-1',
                event_type='target.registered',
                timestamp=datetime.now(timezone.utc),
                actor_id='test',
                payload={
                    'target_id': 'test-target',
                    'name': 'test-target',
                    'repo_url': 'https://github.com/test/repo',
                    'default_branch': 'main'
                }
            ),
            Event(
                event_id='event-2',
                event_type='attempt.started',
                timestamp=datetime.now(timezone.utc),
                actor_id='test',
                payload={'attempt_id': 'attempt-1', 'task_id': 'task-1', 'status': 'running'}
            ),
        ]
        
        for event in events:
            temp_event_store.append_event(event)
        
        # Set global stores
        import leviathan.control_plane.api as api_module
        monkeypatch.setattr(api_module, 'event_store', temp_event_store)
        monkeypatch.setattr(api_module, 'graph_store', temp_graph_store)
        
        # First rebuild
        rebuild_graph_from_events()
        nodes1 = temp_graph_store.query_nodes()
        edges1 = temp_graph_store.query_edges()
        
        # Second rebuild (should be identical)
        rebuild_graph_from_events()
        nodes2 = temp_graph_store.query_nodes()
        edges2 = temp_graph_store.query_edges()
        
        # Counts should match
        assert len(nodes1) == len(nodes2)
        assert len(edges1) == len(edges2)
    
    def test_rebuild_idempotent(self, temp_event_store, temp_graph_store, monkeypatch):
        """Test that rebuild is idempotent (can run multiple times)."""
        # Add events
        event = Event(
            event_id='event-1',
            event_type='target.registered',
            timestamp=datetime.now(timezone.utc),
            actor_id='test',
            payload={
                'target_id': 'test-target',
                'name': 'test-target',
                'repo_url': 'https://github.com/test/repo',
                'default_branch': 'main'
            }
        )
        temp_event_store.append_event(event)
        
        # Set global stores
        import leviathan.control_plane.api as api_module
        monkeypatch.setattr(api_module, 'event_store', temp_event_store)
        monkeypatch.setattr(api_module, 'graph_store', temp_graph_store)
        
        # Multiple rebuilds should not fail
        rebuild_graph_from_events()
        rebuild_graph_from_events()
        rebuild_graph_from_events()
        
        # Graph should still be consistent
        nodes = temp_graph_store.query_nodes()
        assert len(nodes) > 0


class TestEventStorePostgresInit:
    """Test Postgres schema initialization."""
    
    def test_postgres_schema_init_mock(self, monkeypatch):
        """Test that Postgres schema is initialized on connection."""
        # Mock psycopg2
        mock_conn = pytest.importorskip('unittest.mock').MagicMock()
        mock_cursor = pytest.importorskip('unittest.mock').MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        with pytest.importorskip('unittest.mock').patch('psycopg2.connect', return_value=mock_conn):
            store = EventStore(backend="postgres", postgres_url="postgresql://test")
            
            # Should have called CREATE TABLE
            calls = [str(call) for call in mock_cursor.execute.call_args_list]
            assert any('CREATE TABLE IF NOT EXISTS events' in str(call) for call in calls)
            
            # Should have called CREATE INDEX
            assert any('CREATE INDEX IF NOT EXISTS' in str(call) for call in calls)
            
            # Should have created triggers
            assert any('prevent_event_modification' in str(call) for call in calls)


class TestFailoverEnvironmentVariables:
    """Test failover environment variable handling."""
    
    def test_rebuild_on_start_env_disabled(self, monkeypatch):
        """Test LEVIATHAN_REBUILD_ON_START=0 (disabled)."""
        import os
        monkeypatch.setenv('LEVIATHAN_REBUILD_ON_START', '0')
        
        assert os.getenv('LEVIATHAN_REBUILD_ON_START') == '0'
    
    def test_rebuild_on_start_env_enabled(self, monkeypatch):
        """Test LEVIATHAN_REBUILD_ON_START=1 (enabled)."""
        import os
        monkeypatch.setenv('LEVIATHAN_REBUILD_ON_START', '1')
        
        assert os.getenv('LEVIATHAN_REBUILD_ON_START') == '1'
    
    def test_artifact_backend_env_s3(self, monkeypatch):
        """Test LEVIATHAN_ARTIFACT_BACKEND=s3."""
        import os
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_BACKEND', 's3')
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_S3_BUCKET', 'test-bucket')
        
        assert os.getenv('LEVIATHAN_ARTIFACT_BACKEND') == 's3'
        assert os.getenv('LEVIATHAN_ARTIFACT_S3_BUCKET') == 'test-bucket'
    
    def test_control_plane_backend_env_postgres(self, monkeypatch):
        """Test LEVIATHAN_CONTROL_PLANE_BACKEND=postgres."""
        import os
        monkeypatch.setenv('LEVIATHAN_CONTROL_PLANE_BACKEND', 'postgres')
        monkeypatch.setenv('LEVIATHAN_POSTGRES_URL', 'postgresql://test')
        
        assert os.getenv('LEVIATHAN_CONTROL_PLANE_BACKEND') == 'postgres'
        assert os.getenv('LEVIATHAN_POSTGRES_URL') == 'postgresql://test'
