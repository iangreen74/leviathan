"""
Unit tests for worker workspace directory selection.
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from leviathan.executor.worker import Worker, WorkerError


class TestWorkerWorkspace:
    """Test worker workspace directory selection logic."""
    
    def setup_method(self):
        """Set up test environment."""
        # Set required env vars for Worker initialization
        self.env_vars = {
            'TARGET_NAME': 'test-target',
            'TARGET_REPO_URL': 'https://github.com/test/repo.git',
            'TASK_ID': 'task-123',
            'ATTEMPT_ID': 'attempt-456',
            'CONTROL_PLANE_URL': 'http://localhost:8000',
            'CONTROL_PLANE_TOKEN': 'test-token'
        }
    
    def test_workspace_explicit_override(self, tmp_path, monkeypatch):
        """Test LEVIATHAN_WORKSPACE_DIR explicit override."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Set workspace override
        workspace_dir = str(tmp_path / "custom-workspace")
        monkeypatch.setenv('LEVIATHAN_WORKSPACE_DIR', workspace_dir)
        
        # Initialize worker
        worker = Worker()
        
        # Should use override with attempt_id subdirectory
        expected_workspace = Path(workspace_dir) / self.env_vars['ATTEMPT_ID']
        assert worker.workspace == expected_workspace
        assert worker.workspace.exists()
        assert worker.workspace.is_dir()
    
    def test_workspace_k8s_default_writable(self, tmp_path, monkeypatch):
        """Test /workspace when writable (K8s scenario)."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Remove workspace override
        monkeypatch.delenv('LEVIATHAN_WORKSPACE_DIR', raising=False)
        
        # Mock /workspace as writable
        fake_workspace = tmp_path / "workspace"
        fake_workspace.mkdir()
        
        with patch('leviathan.executor.worker.Path') as mock_path:
            # Make Path("/workspace") return our fake workspace
            def path_side_effect(arg):
                if arg == "/workspace":
                    return fake_workspace
                return Path(arg)
            
            mock_path.side_effect = path_side_effect
            
            # Initialize worker
            worker = Worker()
            
            # Should use /workspace with attempt_id subdirectory
            expected_workspace = fake_workspace / self.env_vars['ATTEMPT_ID']
            assert worker.workspace == expected_workspace
    
    def test_workspace_fallback_to_tmp(self, tmp_path, monkeypatch):
        """Test fallback to /tmp when /workspace not writable."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Remove workspace override
        monkeypatch.delenv('LEVIATHAN_WORKSPACE_DIR', raising=False)
        
        # Mock /workspace as non-writable
        with patch.object(Worker, '_is_writable', return_value=False):
            # Mock /tmp/leviathan-workspace to use tmp_path
            fake_tmp = tmp_path / "tmp-leviathan-workspace"
            
            with patch('leviathan.executor.worker.Path') as mock_path:
                def path_side_effect(arg):
                    if arg == "/workspace":
                        return Path("/nonexistent/workspace")
                    elif arg == "/tmp/leviathan-workspace":
                        return fake_tmp
                    return Path(arg)
                
                mock_path.side_effect = path_side_effect
                
                # Initialize worker
                worker = Worker()
                
                # Should use /tmp fallback with attempt_id subdirectory
                expected_workspace = fake_tmp / self.env_vars['ATTEMPT_ID']
                assert worker.workspace == expected_workspace
                assert worker.workspace.exists()
    
    def test_workspace_creates_subdirectory(self, tmp_path, monkeypatch):
        """Test that workspace creates attempt_id subdirectory."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        
        # Set workspace override
        workspace_dir = str(tmp_path / "workspace")
        monkeypatch.setenv('LEVIATHAN_WORKSPACE_DIR', workspace_dir)
        
        # Initialize worker
        worker = Worker()
        
        # Subdirectory should exist
        assert worker.workspace.exists()
        assert worker.workspace.name == self.env_vars['ATTEMPT_ID']
        
        # Target dir should be under workspace
        assert worker.target_dir == worker.workspace / "target"
        # ArtifactStore now uses default location (~/.leviathan/artifacts) for consistency with control plane
        assert worker.artifact_store.backend.storage_root == Path.home() / ".leviathan" / "artifacts"
    
    def test_is_writable_success(self, tmp_path, monkeypatch):
        """Test _is_writable with writable directory."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv('LEVIATHAN_WORKSPACE_DIR', str(tmp_path))
        
        worker = Worker()
        
        # tmp_path should be writable
        assert worker._is_writable(tmp_path) is True
    
    def test_is_writable_nonexistent(self, tmp_path, monkeypatch):
        """Test _is_writable with non-existent directory."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv('LEVIATHAN_WORKSPACE_DIR', str(tmp_path))
        
        worker = Worker()
        
        # Non-existent directory should return False
        nonexistent = tmp_path / "nonexistent"
        assert worker._is_writable(nonexistent) is False
    
    def test_is_writable_permission_denied(self, tmp_path, monkeypatch):
        """Test _is_writable with permission denied."""
        # Set env vars
        for key, value in self.env_vars.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv('LEVIATHAN_WORKSPACE_DIR', str(tmp_path))
        
        worker = Worker()
        
        # Mock permission error
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        
        with patch.object(Path, 'touch', side_effect=PermissionError("Permission denied")):
            assert worker._is_writable(readonly_dir) is False
