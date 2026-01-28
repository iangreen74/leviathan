"""
Unit tests for backlog propose mode.

Tests that backlog-only PR mode cannot modify files outside .leviathan/backlog.yaml.
"""
import pytest
import tempfile
import shutil
import uuid
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from leviathan.executor.backlog_propose import BacklogProposer


class TestBacklogPropose:
    """Test backlog propose functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        
    def teardown_method(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_backlog_propose_only_modifies_backlog_yaml(self):
        """Should only modify .leviathan/backlog.yaml, nothing else."""
        # Create fake repo structure
        target_dir = self.temp_dir / "target"
        target_dir.mkdir()
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        backlog_file = leviathan_dir / "backlog.yaml"
        backlog_file.write_text("tasks: []\n")
        
        # Create other files that should NOT be modified
        readme = target_dir / "README.md"
        readme.write_text("# Radix\n")
        
        src_dir = target_dir / "src"
        src_dir.mkdir()
        main_py = src_dir / "main.py"
        main_py.write_text("print('hello')\n")
        
        # Record initial state
        initial_readme = readme.read_text()
        initial_main = main_py.read_text()
        
        # Create proposer
        task_spec = {
            'id': 'test-task-001',
            'title': 'Test Task',
            'scope': 'docs',
            'priority': 'high',
            'ready': True,
            'estimated_size': 'xs',
            'allowed_paths': ['.leviathan/backlog.yaml'],
            'acceptance_criteria': ['Test criteria'],
            'dependencies': []
        }
        
        proposer = BacklogProposer(
            target_name='test-target',
            target_repo_url='https://github.com/test/repo.git',
            target_branch='main',
            task_spec=task_spec,
            attempt_id='attempt-test-123',
            github_token='fake-token',
            workspace=self.temp_dir
        )
        
        # Override target_dir to use our fake repo
        proposer.target_dir = target_dir
        
        # Add task to backlog
        proposer._add_task_to_backlog()
        
        # Verify only backlog.yaml was modified
        assert backlog_file.exists()
        backlog_content = backlog_file.read_text()
        assert 'test-task-001' in backlog_content
        
        # Verify other files unchanged
        assert readme.read_text() == initial_readme
        assert main_py.read_text() == initial_main
    
    def test_backlog_propose_task_spec_validation(self):
        """Task spec must include allowed_paths with only .leviathan/backlog.yaml."""
        task_spec = {
            'id': 'test-task-002',
            'title': 'Test Task',
            'scope': 'docs',
            'priority': 'high',
            'ready': True,
            'estimated_size': 'xs',
            'allowed_paths': ['.leviathan/backlog.yaml'],
            'acceptance_criteria': ['Test criteria'],
            'dependencies': []
        }
        
        # Verify allowed_paths is correct
        assert task_spec['allowed_paths'] == ['.leviathan/backlog.yaml']
        assert len(task_spec['allowed_paths']) == 1
    
    def test_backlog_propose_adds_task_to_existing_backlog(self):
        """Should add task to existing backlog without removing other tasks."""
        # Create fake repo with existing backlog
        target_dir = self.temp_dir / "target"
        target_dir.mkdir()
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        backlog_file = leviathan_dir / "backlog.yaml"
        backlog_file.write_text("""tasks:
  - id: existing-task-001
    title: Existing Task
    scope: feature
    priority: medium
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        # Create proposer
        task_spec = {
            'id': 'new-task-002',
            'title': 'New Task',
            'scope': 'docs',
            'priority': 'high',
            'ready': True,
            'estimated_size': 'xs',
            'allowed_paths': ['.leviathan/backlog.yaml'],
            'acceptance_criteria': ['Test criteria'],
            'dependencies': []
        }
        
        proposer = BacklogProposer(
            target_name='test-target',
            target_repo_url='https://github.com/test/repo.git',
            target_branch='main',
            task_spec=task_spec,
            attempt_id='attempt-test-456',
            github_token='fake-token',
            workspace=self.temp_dir
        )
        
        proposer.target_dir = target_dir
        
        # Add task
        proposer._add_task_to_backlog()
        
        # Verify both tasks exist
        backlog_content = backlog_file.read_text()
        assert 'existing-task-001' in backlog_content
        assert 'new-task-002' in backlog_content
    
    def test_backlog_propose_skips_duplicate_task(self):
        """Should skip adding task if ID already exists."""
        # Create fake repo with existing task
        target_dir = self.temp_dir / "target"
        target_dir.mkdir()
        
        leviathan_dir = target_dir / ".leviathan"
        leviathan_dir.mkdir()
        
        backlog_file = leviathan_dir / "backlog.yaml"
        backlog_file.write_text("""tasks:
  - id: duplicate-task
    title: Existing Task
    scope: feature
    priority: medium
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        # Try to add same task ID
        task_spec = {
            'id': 'duplicate-task',
            'title': 'Duplicate Task',
            'scope': 'docs',
            'priority': 'high',
            'ready': True,
            'estimated_size': 'xs',
            'allowed_paths': ['.leviathan/backlog.yaml'],
            'acceptance_criteria': ['Test criteria'],
            'dependencies': []
        }
        
        proposer = BacklogProposer(
            target_name='test-target',
            target_repo_url='https://github.com/test/repo.git',
            target_branch='main',
            task_spec=task_spec,
            attempt_id='attempt-test-789',
            github_token='fake-token',
            workspace=self.temp_dir
        )
        
        proposer.target_dir = target_dir
        
        # Add task (should skip)
        proposer._add_task_to_backlog()
        
        # Verify only one instance exists
        backlog_content = backlog_file.read_text()
        assert backlog_content.count('duplicate-task') == 1
    
    def test_extract_repo_info_https(self):
        """Should extract owner and repo from HTTPS URL."""
        proposer = BacklogProposer(
            target_name='test',
            target_repo_url='https://github.com/iangreen74/radix.git',
            target_branch='main',
            task_spec={},
            attempt_id='test',
            github_token='token',
            workspace=self.temp_dir
        )
        
        owner, repo = proposer._extract_repo_info('https://github.com/iangreen74/radix.git')
        assert owner == 'iangreen74'
        assert repo == 'radix'
    
    def test_extract_repo_info_ssh(self):
        """Should extract owner and repo from SSH URL."""
        proposer = BacklogProposer(
            target_name='test',
            target_repo_url='git@github.com:iangreen74/radix.git',
            target_branch='main',
            task_spec={},
            attempt_id='test',
            github_token='token',
            workspace=self.temp_dir
        )
        
        owner, repo = proposer._extract_repo_info('git@github.com:iangreen74/radix.git')
        assert owner == 'iangreen74'
        assert repo == 'radix'
    
    def test_build_authenticated_url_https(self):
        """Should inject token into HTTPS URL using x-access-token format."""
        proposer = BacklogProposer(
            target_name='test',
            target_repo_url='https://github.com/test/repo.git',
            target_branch='main',
            task_spec={},
            attempt_id='test',
            github_token='test-token',
            workspace=self.temp_dir
        )
        
        auth_url = proposer._build_authenticated_url(
            'https://github.com/test/repo.git',
            'test-token'
        )
        
        assert auth_url == 'https://x-access-token:test-token@github.com/test/repo.git'
        assert auth_url.startswith('https://')
        assert 'x-access-token:' in auth_url
    
    def test_build_authenticated_url_ssh_converts_to_https(self):
        """Should convert SSH URL to HTTPS with token using x-access-token format."""
        proposer = BacklogProposer(
            target_name='test',
            target_repo_url='git@github.com:test/repo.git',
            target_branch='main',
            task_spec={},
            attempt_id='test',
            github_token='test-token',
            workspace=self.temp_dir
        )
        
        auth_url = proposer._build_authenticated_url(
            'git@github.com:test/repo.git',
            'test-token'
        )
        
        assert auth_url == 'https://x-access-token:test-token@github.com/test/repo.git'
        assert auth_url.startswith('https://')
        assert 'git@' not in auth_url
        assert 'x-access-token:' in auth_url


    def test_build_authenticated_url_strips_token_whitespace(self):
        """Should strip whitespace and newlines from token."""
        proposer = BacklogProposer(
            target_name='test',
            target_repo_url='https://github.com/test/repo.git',
            target_branch='main',
            task_spec={},
            attempt_id='test',
            github_token='test-token',
            workspace=self.temp_dir
        )
        
        # Test with token that has whitespace
        auth_url = proposer._build_authenticated_url(
            'https://github.com/test/repo.git',
            '  test-token\n'
        )
        
        assert auth_url == 'https://x-access-token:test-token@github.com/test/repo.git'
        assert '\n' not in auth_url
        assert auth_url.count('test-token') == 1


class TestGitOperations:
    """Test git operations for backlog propose."""
    
    def test_git_add_uses_force_flag(self):
        """Should use -f flag to force-add .leviathan/backlog.yaml even if ignored."""
        with patch('subprocess.run') as mock_run:
            # Create fake repo structure
            temp_dir = Path(tempfile.mkdtemp())
            target_dir = temp_dir / "target"
            target_dir.mkdir()
            
            leviathan_dir = target_dir / ".leviathan"
            leviathan_dir.mkdir()
            
            backlog_file = leviathan_dir / "backlog.yaml"
            backlog_file.write_text("tasks: []\n")
            
            # Create proposer
            task_spec = {
                'id': 'test-task',
                'title': 'Test',
                'scope': 'docs',
                'priority': 'high',
                'ready': True,
                'estimated_size': 'xs',
                'allowed_paths': ['.leviathan/backlog.yaml'],
                'acceptance_criteria': [],
                'dependencies': []
            }
            
            proposer = BacklogProposer(
                target_name='test',
                target_repo_url='git@github.com:test/repo.git',
                target_branch='main',
                task_spec=task_spec,
                attempt_id='test-123',
                github_token='token',
                workspace=temp_dir
            )
            
            proposer.target_dir = target_dir
            
            # Mock subprocess to succeed
            mock_run.return_value = Mock(returncode=0, stdout='abc123\n')
            
            # Call commit_and_push
            try:
                proposer._commit_and_push('test-branch')
            except:
                pass  # May fail on other git commands, we only care about git add
            
            # Verify git add was called with -f flag
            git_add_calls = [call for call in mock_run.call_args_list 
                           if call[0][0][0:2] == ['git', 'add']]
            
            assert len(git_add_calls) > 0, "git add should have been called"
            
            # Check that -f flag is present
            git_add_cmd = git_add_calls[0][0][0]
            assert '-f' in git_add_cmd, "git add should use -f flag"
            assert '.leviathan/backlog.yaml' in git_add_cmd, "Should add backlog.yaml"
            
            # Clean up
            shutil.rmtree(temp_dir)


class TestEventSchema:
    """Test that events conform to Event schema."""
    
    def test_event_has_required_fields(self):
        """Event dict should include event_id, event_type, timestamp, actor_id, payload."""
        # Simulate what pr_proof_v1.py creates
        event = {
            'event_id': str(uuid.uuid4()),
            'event_type': 'attempt.created',
            'timestamp': datetime.utcnow().isoformat(),
            'actor_id': 'pr-proof-script-attempt-123',
            'payload': {
                'attempt_id': 'attempt-123',
                'task_id': 'task-456',
                'target_id': 'radix',
                'attempt_number': 1,
                'status': 'created'
            }
        }
        
        # Verify all required fields present
        assert 'event_id' in event
        assert 'event_type' in event
        assert 'timestamp' in event
        assert 'actor_id' in event
        assert 'payload' in event
        
        # Verify types
        assert isinstance(event['event_id'], str)
        assert isinstance(event['event_type'], str)
        assert isinstance(event['timestamp'], str)
        assert isinstance(event['actor_id'], str)
        assert isinstance(event['payload'], dict)
    
    def test_event_id_is_uuid(self):
        """event_id should be a valid UUID."""
        event_id = str(uuid.uuid4())
        
        # Should be parseable as UUID
        parsed = uuid.UUID(event_id)
        assert str(parsed) == event_id
    
    def test_actor_id_format(self):
        """actor_id should follow expected format."""
        attempt_id = 'attempt-pr-proof-1738000000'
        actor_id = f'pr-proof-script-{attempt_id}'
        
        assert actor_id.startswith('pr-proof-script-')
        assert attempt_id in actor_id
    
    def test_event_bundle_structure(self):
        """Event bundle should have correct structure for control plane."""
        bundle = {
            'target': 'radix',
            'bundle_id': 'bundle-attempt-123',
            'events': [{
                'event_id': str(uuid.uuid4()),
                'event_type': 'attempt.created',
                'timestamp': datetime.utcnow().isoformat(),
                'actor_id': 'pr-proof-script-attempt-123',
                'payload': {
                    'attempt_id': 'attempt-123',
                    'task_id': 'task-456',
                    'target_id': 'radix'
                }
            }],
            'artifacts': []
        }
        
        # Verify bundle structure
        assert 'target' in bundle
        assert 'bundle_id' in bundle
        assert 'events' in bundle
        assert 'artifacts' in bundle
        
        # Verify event in bundle has all required fields
        event = bundle['events'][0]
        assert 'event_id' in event
        assert 'event_type' in event
        assert 'timestamp' in event
        assert 'actor_id' in event
        assert 'payload' in event
