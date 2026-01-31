"""
Unit tests for DEV Autonomy Scheduler.

Tests task selection, scope restrictions, and guardrails.
"""
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from leviathan.scheduler.dev_autonomy import DevAutonomyScheduler


class TestDevAutonomyScheduler:
    """Test DEV Autonomy Scheduler logic."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "dev.yaml"
        
        # Create minimal config
        config = {
            'autonomy_enabled': True,
            'target_id': 'test-target',
            'target_repo_url': 'https://github.com/test/repo.git',
            'target_branch': 'main',
            'allowed_path_prefixes': ['.leviathan/', 'docs/'],
            'max_open_prs': 1,
            'max_attempts_per_task': 2,
            'circuit_breaker_failures': 2,
            'control_plane_url': 'http://localhost:8000',
            'worker_image': 'leviathan-worker:local',
            'worker_namespace': 'leviathan',
            'workspace_dir': '/workspace'
        }
        
        with open(self.config_path, 'w') as f:
            yaml.dump(config, f)
    
    def test_select_task_with_ready_true(self):
        """Should select task with ready: true."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {'id': 'task-1', 'ready': False, 'allowed_paths': ['.leviathan/backlog.yaml']},
                {'id': 'task-2', 'ready': True, 'allowed_paths': ['.leviathan/backlog.yaml']},
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            assert selected is not None
            assert selected['id'] == 'task-2'
    
    def test_skip_task_without_ready(self):
        """Should skip tasks without ready: true."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {'id': 'task-1', 'ready': False, 'allowed_paths': ['.leviathan/backlog.yaml']},
                {'id': 'task-2', 'allowed_paths': ['.leviathan/backlog.yaml']},  # missing ready
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            assert selected is None
    
    def test_scope_restriction_allows_leviathan_paths(self):
        """Should allow tasks modifying .leviathan/ paths."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            allowed_paths = ['.leviathan/backlog.yaml', '.leviathan/contract.yaml']
            
            assert scheduler._is_scope_allowed(allowed_paths) is True
    
    def test_scope_restriction_allows_docs_paths(self):
        """Should allow tasks modifying docs/ paths."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            allowed_paths = ['docs/README.md', 'docs/architecture/design.md']
            
            assert scheduler._is_scope_allowed(allowed_paths) is True
    
    def test_scope_restriction_blocks_other_paths(self):
        """Should block tasks modifying paths outside allowed prefixes."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            # src/ is not in allowed_path_prefixes
            allowed_paths = ['src/main.py']
            
            assert scheduler._is_scope_allowed(allowed_paths) is False
    
    def test_scope_restriction_blocks_mixed_paths(self):
        """Should block tasks if ANY path is outside allowed prefixes."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            # Mix of allowed and disallowed
            allowed_paths = ['.leviathan/backlog.yaml', 'src/main.py']
            
            assert scheduler._is_scope_allowed(allowed_paths) is False
    
    def test_skip_tasks_with_unsatisfied_dependencies(self):
        """Should skip tasks when dependencies are not completed."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {
                    'id': 'task-0',
                    'ready': True,
                    'status': 'pending',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-1',
                    'ready': True,
                    'allowed_paths': ['.leviathan/backlog.yaml'],
                    'dependencies': ['task-0']
                },
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            # Should select task-0 (no deps), skip task-1 (dep not completed)
            assert selected is not None
            assert selected['id'] == 'task-0'
    
    def test_select_task_when_dependencies_completed(self):
        """Should select task when all dependencies are completed."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {
                    'id': 'task-0',
                    'ready': True,
                    'status': 'completed',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-1',
                    'ready': True,
                    'status': 'pending',
                    'allowed_paths': ['.leviathan/backlog.yaml'],
                    'dependencies': ['task-0']
                },
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            # Should select task-1 (dep completed)
            assert selected is not None
            assert selected['id'] == 'task-1'
    
    def test_skip_task_with_missing_dependency(self):
        """Should skip task when dependency doesn't exist in backlog."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {
                    'id': 'task-1',
                    'ready': True,
                    'allowed_paths': ['.leviathan/backlog.yaml'],
                    'dependencies': ['task-missing']
                },
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            # Should skip task-1 (dep doesn't exist)
            assert selected is None
    
    def test_select_task_with_multiple_dependencies_all_completed(self):
        """Should select task when all multiple dependencies are completed."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {
                    'id': 'task-0',
                    'ready': True,
                    'status': 'completed',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-1',
                    'ready': True,
                    'status': 'completed',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-2',
                    'ready': True,
                    'status': 'pending',
                    'allowed_paths': ['.leviathan/backlog.yaml'],
                    'dependencies': ['task-0', 'task-1']
                },
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            # Should select task-2 (all deps completed)
            assert selected is not None
            assert selected['id'] == 'task-2'
    
    def test_skip_task_with_multiple_dependencies_partial_completed(self):
        """Should skip task when only some dependencies are completed."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {
                    'id': 'task-0',
                    'ready': True,
                    'status': 'completed',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-1',
                    'ready': True,
                    'status': 'pending',
                    'allowed_paths': ['.leviathan/backlog.yaml']
                },
                {
                    'id': 'task-2',
                    'ready': True,
                    'status': 'pending',
                    'allowed_paths': ['.leviathan/backlog.yaml'],
                    'dependencies': ['task-0', 'task-1']
                },
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            # Should select task-1 (no deps), skip task-2 (task-1 not completed)
            assert selected is not None
            assert selected['id'] == 'task-1'
    
    def test_get_unsatisfied_dependencies(self):
        """Test _get_unsatisfied_dependencies helper."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            task_status_index = {
                'task-a': 'completed',
                'task-b': 'pending',
                'task-c': 'completed'
            }
            
            # All satisfied
            unsatisfied = scheduler._get_unsatisfied_dependencies(['task-a', 'task-c'], task_status_index)
            assert unsatisfied == []
            
            # Some unsatisfied
            unsatisfied = scheduler._get_unsatisfied_dependencies(['task-a', 'task-b'], task_status_index)
            assert unsatisfied == ['task-b']
            
            # Missing dependency
            unsatisfied = scheduler._get_unsatisfied_dependencies(['task-missing'], task_status_index)
            assert unsatisfied == ['task-missing']
    
    def test_skip_tasks_with_non_pending_status(self):
        """Should skip tasks with status other than pending."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            tasks = [
                {'id': 'task-1', 'ready': True, 'status': 'completed', 'allowed_paths': ['.leviathan/backlog.yaml']},
                {'id': 'task-2', 'ready': True, 'status': 'in_progress', 'allowed_paths': ['.leviathan/backlog.yaml']},
                {'id': 'task-3', 'ready': True, 'status': 'pending', 'allowed_paths': ['.leviathan/backlog.yaml']},
            ]
            
            selected = scheduler._select_next_task(tasks, set())
            
            assert selected is not None
            assert selected['id'] == 'task-3'
    
    def test_count_open_prs_with_agent_prefix(self):
        """Should count only PRs with agent/ branch prefix."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            mock_prs = [
                {'head': {'ref': 'agent/backlog-propose-123'}},
                {'head': {'ref': 'feature/new-feature'}},
                {'head': {'ref': 'agent/backlog-propose-456'}},
            ]
            
            with patch('requests.get') as mock_get:
                mock_response = Mock()
                mock_response.json.return_value = mock_prs
                mock_response.raise_for_status = Mock()
                mock_get.return_value = mock_response
                
                count = scheduler._count_open_prs()
                
                assert count == 2  # Only agent/ branches
    
    def test_count_open_prs_fails_safe(self):
        """Should return 0 if GitHub API fails (fail-safe behavior)."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            # Mock _get_open_agent_prs to return empty list (API error)
            with patch.object(scheduler, '_get_open_agent_prs', return_value=[]):
                count = scheduler._count_open_prs()
            
            # Should return 0 when API fails
            assert count == 0
    
    def test_build_authenticated_url_https(self):
        """Should build authenticated HTTPS URL."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            url = scheduler._build_authenticated_url(
                'https://github.com/test/repo.git',
                'test-token'
            )
            
            assert url == 'https://x-access-token:test-token@github.com/test/repo.git'
    
    def test_extract_repo_info(self):
        """Should extract owner and repo from URL."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(self.config_path))
            
            owner, repo = scheduler._extract_repo_info('https://github.com/iangreen74/radix.git')
            
            assert owner == 'iangreen74'
            assert repo == 'radix'


class TestSchedulerGuardrails:
    """Test scheduler guardrails and safety mechanisms."""
    
    def test_max_open_prs_enforced(self):
        """Should skip scheduling when max_open_prs reached."""
        temp_dir = Path(tempfile.mkdtemp())
        config_path = temp_dir / "dev.yaml"
        
        config = {
            'autonomy_enabled': True,
            'target_id': 'test',
            'target_repo_url': 'https://github.com/test/repo.git',
            'target_branch': 'main',
            'allowed_path_prefixes': ['.leviathan/'],
            'max_open_prs': 1,
            'max_attempts_per_task': 2,
            'circuit_breaker_failures': 2,
            'control_plane_url': 'http://localhost:8000',
            'worker_image': 'leviathan-worker:local',
            'worker_namespace': 'leviathan',
            'workspace_dir': '/workspace'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(config_path))
            
            # Mock to simulate max open PRs
            with patch.object(scheduler, '_get_open_agent_prs', return_value=[{'number': 1, 'branch': 'agent/test', 'url': 'url', 'title': 'test'}]):
                with patch.object(scheduler, '_fetch_target_backlog') as mock_fetch:
                    scheduler.run_schedule_cycle()
                    
                    # Should NOT fetch backlog (early exit)
                    mock_fetch.assert_not_called()
    
    def test_autonomy_disabled_exits_cleanly(self):
        """Should exit cleanly without submitting jobs when autonomy_enabled=false."""
        temp_dir = Path(tempfile.mkdtemp())
        config_path = temp_dir / "dev.yaml"
        
        config = {
            'autonomy_enabled': False,
            'target_id': 'test',
            'target_repo_url': 'https://github.com/test/repo.git',
            'target_branch': 'main',
            'allowed_path_prefixes': ['.leviathan/'],
            'max_open_prs': 1,
            'max_attempts_per_task': 2,
            'circuit_breaker_failures': 2,
            'control_plane_url': 'http://localhost:8000',
            'worker_image': 'leviathan-worker:local',
            'worker_namespace': 'leviathan',
            'workspace_dir': '/workspace'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(config_path))
            
            # Mock methods that would be called during scheduling
            with patch.object(scheduler, '_count_open_prs') as mock_count_prs:
                with patch.object(scheduler, '_fetch_target_backlog') as mock_fetch:
                    scheduler.run_schedule_cycle()
                    
                    # Should not call any scheduling methods when disabled
                    mock_count_prs.assert_not_called()
                    mock_fetch.assert_not_called()
    
    def test_autonomy_enabled_proceeds_normally(self):
        """Should proceed with normal scheduling when autonomy_enabled=true."""
        temp_dir = Path(tempfile.mkdtemp())
        config_path = temp_dir / "dev.yaml"
        
        config = {
            'autonomy_enabled': True,
            'target_id': 'test',
            'target_repo_url': 'https://github.com/test/repo.git',
            'target_branch': 'main',
            'allowed_path_prefixes': ['.leviathan/'],
            'max_open_prs': 1,
            'max_attempts_per_task': 2,
            'circuit_breaker_failures': 2,
            'control_plane_url': 'http://localhost:8000',
            'worker_image': 'leviathan-worker:local',
            'worker_namespace': 'leviathan',
            'workspace_dir': '/workspace'
        }
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f)
        
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'token', 'CONTROL_PLANE_TOKEN': 'token'}):
            scheduler = DevAutonomyScheduler(str(config_path))
            
            # Mock to simulate normal flow
            with patch.object(scheduler, '_get_open_agent_prs', return_value=[]):
                with patch.object(scheduler, '_fetch_target_backlog', return_value={'tasks': []}):
                    scheduler.run_schedule_cycle()
                    
                    # Should call scheduling methods (autonomy enabled)
                    scheduler._get_open_agent_prs.assert_called_once()
                    scheduler._fetch_target_backlog.assert_called_once()
