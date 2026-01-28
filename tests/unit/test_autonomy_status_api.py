"""
Unit tests for autonomy status API endpoint.

Tests that the control plane exposes autonomy status correctly.
"""
import pytest
import os
import tempfile
import yaml
from pathlib import Path
from fastapi.testclient import TestClient

from leviathan.control_plane.api import app, initialize_stores, reset_stores


class TestAutonomyStatusAPI:
    """Test autonomy status endpoint."""
    
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Set up test client with isolated storage."""
        # Set auth token BEFORE initializing stores
        os.environ["LEVIATHAN_CONTROL_PLANE_TOKEN"] = "test-token-12345"
        
        reset_stores()
        initialize_stores(ndjson_dir=str(tmp_path / "events"), artifacts_dir=str(tmp_path / "artifacts"))
        
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-12345"}
        
        yield
        
        # Cleanup
        reset_stores()
    
    def test_autonomy_status_unauthorized(self):
        """Should return 401 without valid token."""
        response = self.client.get("/v1/autonomy/status")
        assert response.status_code == 401
    
    def test_autonomy_status_with_auth(self):
        """Should return 200 with valid token."""
        response = self.client.get("/v1/autonomy/status", headers=self.headers)
        assert response.status_code == 200
    
    def test_autonomy_status_response_schema(self):
        """Should return correct response schema."""
        response = self.client.get("/v1/autonomy/status", headers=self.headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify schema
        assert 'autonomy_enabled' in data
        assert 'source' in data
        assert isinstance(data['autonomy_enabled'], bool)
        assert isinstance(data['source'], str)
    
    def test_autonomy_status_reads_from_config(self, tmp_path):
        """Should read autonomy_enabled from mounted config."""
        # Create a temporary config file
        config_path = tmp_path / "autonomy_config.yaml"
        config = {
            'autonomy_enabled': False,
            'target_id': 'test'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        # Set env var to point to our test config
        os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH'] = str(config_path)
        
        try:
            response = self.client.get("/v1/autonomy/status", headers=self.headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data['autonomy_enabled'] is False
            assert 'configmap' in data['source']
        finally:
            # Clean up env var
            if 'LEVIATHAN_AUTONOMY_CONFIG_PATH' in os.environ:
                del os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH']
    
    def test_autonomy_status_defaults_when_config_missing(self):
        """Should default to true when config not found."""
        # Set env var to non-existent path
        os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH'] = '/nonexistent/path.yaml'
        
        try:
            response = self.client.get("/v1/autonomy/status", headers=self.headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data['autonomy_enabled'] is True
            assert 'default' in data['source']
        finally:
            # Clean up env var
            if 'LEVIATHAN_AUTONOMY_CONFIG_PATH' in os.environ:
                del os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH']
    
    def test_autonomy_status_enabled_true(self, tmp_path):
        """Should return true when autonomy_enabled is true."""
        config_path = tmp_path / "autonomy_enabled.yaml"
        config = {
            'autonomy_enabled': True,
            'target_id': 'test'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH'] = str(config_path)
        
        try:
            response = self.client.get("/v1/autonomy/status", headers=self.headers)
            assert response.status_code == 200
            
            data = response.json()
            assert data['autonomy_enabled'] is True
        finally:
            if 'LEVIATHAN_AUTONOMY_CONFIG_PATH' in os.environ:
                del os.environ['LEVIATHAN_AUTONOMY_CONFIG_PATH']
