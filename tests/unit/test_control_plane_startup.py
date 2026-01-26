"""
Unit tests for control plane startup and initialization.
"""
import pytest
import os
from pathlib import Path
from leviathan.control_plane.api import initialize_stores, reset_stores


class TestControlPlaneStartup:
    """Test control plane startup scenarios."""
    
    def setup_method(self):
        """Reset stores before each test."""
        reset_stores()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_stores()
    
    def test_initialize_stores_ndjson_default(self, tmp_path, monkeypatch):
        """Test initialize_stores with ndjson backend using defaults."""
        # Set required token
        monkeypatch.setenv('LEVIATHAN_CONTROL_PLANE_TOKEN', 'test-token')
        monkeypatch.setenv('LEVIATHAN_BACKEND', 'ndjson')
        
        # Override artifacts dir to avoid polluting home directory
        monkeypatch.setenv('LEVIATHAN_ARTIFACTS_DIR', str(tmp_path / 'artifacts'))
        
        # Should not crash - EventStore will use its default path
        initialize_stores()
        
        # Verify stores are initialized
        from leviathan.control_plane.api import event_store, graph_store, artifact_store
        assert event_store is not None
        assert graph_store is not None
        assert artifact_store is not None
    
    def test_initialize_stores_ndjson_with_override(self, tmp_path, monkeypatch):
        """Test initialize_stores with ndjson backend and test override."""
        # Set required token
        monkeypatch.setenv('LEVIATHAN_CONTROL_PLANE_TOKEN', 'test-token')
        monkeypatch.setenv('LEVIATHAN_BACKEND', 'ndjson')
        
        # Use override for tests
        ndjson_dir = str(tmp_path / 'events')
        artifacts_dir = str(tmp_path / 'artifacts')
        
        initialize_stores(ndjson_dir=ndjson_dir, artifacts_dir=artifacts_dir)
        
        # Verify stores are initialized
        from leviathan.control_plane.api import event_store, graph_store, artifact_store
        assert event_store is not None
        assert graph_store is not None
        assert artifact_store is not None
        
        # Verify ndjson file was created in override directory
        ndjson_path = Path(ndjson_dir) / "events.ndjson"
        assert ndjson_path.exists()
    
    def test_initialize_stores_idempotent(self, tmp_path, monkeypatch):
        """Test that initialize_stores is idempotent."""
        # Set required token
        monkeypatch.setenv('LEVIATHAN_CONTROL_PLANE_TOKEN', 'test-token')
        monkeypatch.setenv('LEVIATHAN_BACKEND', 'ndjson')
        monkeypatch.setenv('LEVIATHAN_ARTIFACTS_DIR', str(tmp_path / 'artifacts'))
        
        # First call
        initialize_stores()
        from leviathan.control_plane.api import event_store as store1
        
        # Second call should return early (already initialized)
        initialize_stores()
        from leviathan.control_plane.api import event_store as store2
        
        # Should be the same instance
        assert store1 is store2
    
    def test_initialize_stores_missing_token(self, monkeypatch):
        """Test that initialize_stores fails without token."""
        # Remove token
        monkeypatch.delenv('LEVIATHAN_CONTROL_PLANE_TOKEN', raising=False)
        
        # Should exit with error
        with pytest.raises(SystemExit):
            initialize_stores()
