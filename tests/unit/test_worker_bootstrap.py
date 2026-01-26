"""
Unit tests for worker bootstrap execution.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml

from leviathan.executor.worker import Worker
from leviathan.backlog import Task


class TestWorkerBootstrapExecution:
    """Test worker bootstrap execution path."""
    
    @pytest.fixture
    def mock_env(self, tmp_path, monkeypatch):
        """Set up mock environment for worker."""
        # Set required environment variables
        monkeypatch.setenv("TARGET_NAME", "test-target")
        monkeypatch.setenv("TARGET_REPO_URL", "git@github.com:test/repo.git")
        monkeypatch.setenv("TARGET_BRANCH", "main")
        monkeypatch.setenv("TASK_ID", "bootstrap-test-v1")
        monkeypatch.setenv("ATTEMPT_ID", "attempt-bootstrap-123")
        monkeypatch.setenv("CONTROL_PLANE_URL", "http://test-control-plane:8000")
        monkeypatch.setenv("CONTROL_PLANE_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
        
        # Mock workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setattr("leviathan.executor.worker.Path", lambda x: workspace if x == "/workspace" else Path(x))
        
        return workspace
    
    @patch('leviathan.executor.worker.subprocess.run')
    @patch('leviathan.executor.worker.requests.post')
    def test_bootstrap_task_uses_indexer_not_model(self, mock_post, mock_subprocess, mock_env, tmp_path):
        """Bootstrap tasks should use indexer, not ModelClient."""
        # Create mock target repo with backlog
        target_dir = mock_env / "target"
        target_dir.mkdir(parents=True)
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        # Create backlog with bootstrap task
        backlog = {
            'tasks': [{
                'id': 'bootstrap-test-v1',
                'title': 'Bootstrap test repo',
                'scope': 'bootstrap',
                'priority': 'high',
                'allowed_paths': [],
                'acceptance_criteria': ['Repository indexed'],
                'status': 'pending'
            }]
        }
        
        with open(leviathan_dir / 'backlog.yaml', 'w') as f:
            yaml.dump(backlog, f)
        
        # Create some test files to index
        (target_dir / 'README.md').write_text('# Test Repo\n\nDescription')
        (target_dir / 'main.py').write_text('print("hello")')
        
        # Mock git operations
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if cmd[0] == 'git' and cmd[1] == 'clone':
                # Don't actually clone, files already created
                return Mock(returncode=0)
            elif cmd[0] == 'git' and cmd[1] == 'rev-parse':
                # Return mock commit SHA
                return Mock(stdout='abc123def456', returncode=0)
            return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_run_side_effect
        
        # Mock control plane response
        mock_post.return_value = Mock(status_code=200)
        
        # Create worker and run
        with patch('leviathan.executor.worker.ModelClient') as mock_model_client:
            worker = Worker()
            
            # Override target_dir to use our mock
            worker.target_dir = target_dir
            
            result = worker.run()
            
            # Assert ModelClient was never instantiated (no model calls for bootstrap)
            mock_model_client.assert_not_called()
            
            # Assert success
            assert result == 0
            
            # Assert events were posted
            assert mock_post.called
            call_args = mock_post.call_args
            bundle = call_args[1]['json']
            
            # Debug: print all event types
            event_types = [e['event_type'] for e in bundle['events']]
            print(f"\nDEBUG: Event types in bundle: {event_types}")
            print(f"DEBUG: Total events: {len(bundle['events'])}")
            
            # Check that bootstrap events are present
            assert 'bootstrap.started' in event_types
            assert 'bootstrap.completed' in event_types
            assert 'repo.indexed' in event_types
            assert 'file.discovered' in event_types
            
            # Check that artifacts were created
            assert len(bundle['artifacts']) > 0
            artifact_names = [a.get('name', '') for a in bundle['artifacts']]
            assert 'repo_tree.txt' in artifact_names
            assert 'repo_manifest.json' in artifact_names
    
    @patch('leviathan.executor.worker.subprocess.run')
    @patch('leviathan.executor.worker.requests.post')
    def test_bootstrap_task_no_pr_created(self, mock_post, mock_subprocess, mock_env, tmp_path):
        """Bootstrap tasks should not create PRs."""
        # Create mock target repo
        target_dir = mock_env / "target"
        target_dir.mkdir(parents=True)
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        # Create backlog with bootstrap task
        backlog = {
            'tasks': [{
                'id': 'bootstrap-test-v1',
                'title': 'Bootstrap test repo',
                'scope': 'bootstrap',
                'priority': 'high',
                'allowed_paths': [],
                'acceptance_criteria': ['Repository indexed'],
                'status': 'pending'
            }]
        }
        
        with open(leviathan_dir / 'backlog.yaml', 'w') as f:
            yaml.dump(backlog, f)
        
        # Create test file
        (target_dir / 'README.md').write_text('# Test')
        
        # Mock git operations
        def mock_run_side_effect(*args, **kwargs):
            cmd = args[0]
            if cmd[0] == 'git' and cmd[1] == 'clone':
                return Mock(returncode=0)
            elif cmd[0] == 'git' and cmd[1] == 'rev-parse':
                return Mock(stdout='abc123', returncode=0)
            # If we see git push or any PR-related commands, fail the test
            elif cmd[0] == 'git' and cmd[1] == 'push':
                pytest.fail("Bootstrap task should not push to git")
            return Mock(returncode=0)
        
        mock_subprocess.side_effect = mock_run_side_effect
        mock_post.return_value = Mock(status_code=200)
        
        # Create worker and run
        with patch('leviathan.executor.worker.requests.post') as mock_pr_post:
            worker = Worker()
            worker.target_dir = target_dir
            
            result = worker.run()
            
            # Assert success
            assert result == 0
            
            # Check that no PR was created (no github.com API calls)
            for call in mock_pr_post.call_args_list:
                url = call[0][0] if call[0] else call[1].get('url', '')
                assert 'api.github.com' not in url, "Bootstrap should not create PRs"
    
    @patch('leviathan.executor.worker.subprocess.run')
    @patch('leviathan.executor.worker.requests.post')
    @patch('leviathan.executor.worker.ArtifactStore')
    def test_bootstrap_by_task_id_prefix(self, mock_artifact_store, mock_post, mock_subprocess, tmp_path, monkeypatch):
        """Tasks with id starting with 'bootstrap-' should use bootstrap path."""
        # Set environment with bootstrap- prefixed task ID
        monkeypatch.setenv("TARGET_NAME", "test-target")
        monkeypatch.setenv("TARGET_REPO_URL", "git@github.com:test/repo.git")
        monkeypatch.setenv("TARGET_BRANCH", "main")
        monkeypatch.setenv("TASK_ID", "bootstrap-radix-v1")  # Match the task in backlog
        monkeypatch.setenv("ATTEMPT_ID", "attempt-bootstrap-456")
        monkeypatch.setenv("CONTROL_PLANE_URL", "http://test-control-plane:8000")
        monkeypatch.setenv("CONTROL_PLANE_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
        
        # Create mock target repo
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_dir = workspace / "target"
        target_dir.mkdir(parents=True)
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        # Create backlog with task that has bootstrap- prefix but different scope
        backlog = {
            'tasks': [{
                'id': 'bootstrap-radix-v1',
                'title': 'Bootstrap Radix',
                'scope': 'indexing',  # Different scope, but id starts with bootstrap-
                'priority': 'high',
                'allowed_paths': [],
                'acceptance_criteria': ['Repository indexed'],
                'status': 'pending'
            }]
        }
        
        with open(leviathan_dir / 'backlog.yaml', 'w') as f:
            yaml.dump(backlog, f)
        
        (target_dir / 'README.md').write_text('# Test')
        
        # Mock artifact store
        mock_store_instance = Mock()
        mock_store_instance.store.return_value = {
            'sha256': 'test-sha256',
            'storage_path': '/tmp/test',
            'size_bytes': 100
        }
        mock_artifact_store.return_value = mock_store_instance
        
        # Mock git operations
        mock_subprocess.side_effect = lambda *args, **kwargs: Mock(
            stdout='abc123' if args[0][1] == 'rev-parse' else '',
            returncode=0
        )
        mock_post.return_value = Mock(status_code=200)
        
        # Create worker and run
        with patch('leviathan.executor.worker.ModelClient') as mock_model_client:
            worker = Worker()
            worker.workspace = workspace
            worker.target_dir = target_dir
            
            result = worker.run()
            
            # Should use bootstrap path (no model calls)
            mock_model_client.assert_not_called()
            
            # Check events include bootstrap types
            call_args = mock_post.call_args
            bundle = call_args[1]['json']
            event_types = [e['event_type'] for e in bundle['events']]
            assert 'bootstrap.started' in event_types
    
    @patch('leviathan.executor.worker.subprocess.run')
    @patch('leviathan.executor.worker.requests.post')
    @patch('leviathan.executor.worker.ArtifactStore')
    def test_bootstrap_by_scope(self, mock_artifact_store, mock_post, mock_subprocess, tmp_path, monkeypatch):
        """Tasks with scope='bootstrap' should use bootstrap path."""
        # Set environment with non-bootstrap task ID
        monkeypatch.setenv("TARGET_NAME", "test-target")
        monkeypatch.setenv("TARGET_REPO_URL", "git@github.com:test/repo.git")
        monkeypatch.setenv("TARGET_BRANCH", "main")
        monkeypatch.setenv("TASK_ID", "index-repo-v1")  # Match the task in backlog
        monkeypatch.setenv("ATTEMPT_ID", "attempt-index-789")
        monkeypatch.setenv("CONTROL_PLANE_URL", "http://test-control-plane:8000")
        monkeypatch.setenv("CONTROL_PLANE_TOKEN", "test-token")
        monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
        
        # Create mock target repo
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target_dir = workspace / "target"
        target_dir.mkdir(parents=True)
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        # Create backlog with task that has scope=bootstrap
        backlog = {
            'tasks': [{
                'id': 'index-repo-v1',  # Different id pattern
                'title': 'Index repository',
                'scope': 'bootstrap',  # But scope is bootstrap
                'priority': 'high',
                'allowed_paths': [],
                'acceptance_criteria': ['Repository indexed'],
                'status': 'pending'
            }]
        }
        
        with open(leviathan_dir / 'backlog.yaml', 'w') as f:
            yaml.dump(backlog, f)
        
        (target_dir / 'README.md').write_text('# Test')
        
        # Mock artifact store
        mock_store_instance = Mock()
        mock_store_instance.store.return_value = {
            'sha256': 'test-sha256',
            'storage_path': '/tmp/test',
            'size_bytes': 100
        }
        mock_artifact_store.return_value = mock_store_instance
        
        # Mock git operations
        mock_subprocess.side_effect = lambda *args, **kwargs: Mock(
            stdout='abc123' if args[0][1] == 'rev-parse' else '',
            returncode=0
        )
        mock_post.return_value = Mock(status_code=200)
        
        # Create worker and run
        with patch('leviathan.executor.worker.ModelClient') as mock_model_client:
            worker = Worker()
            worker.workspace = workspace
            worker.target_dir = target_dir
            
            result = worker.run()
            
            # Should use bootstrap path (no model calls)
            mock_model_client.assert_not_called()
            
            # Check events include bootstrap types
            call_args = mock_post.call_args
            bundle = call_args[1]['json']
            event_types = [e['event_type'] for e in bundle['events']]
            assert 'bootstrap.completed' in event_types
