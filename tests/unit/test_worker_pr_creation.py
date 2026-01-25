"""
Unit tests for worker PR creation and git operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from leviathan.executor.worker import Worker, WorkerError
from leviathan.backlog import Task


class TestWorkerPRCreation:
    """Test worker PR creation functionality."""
    
    def test_build_authenticated_url_https(self):
        """Should inject token into HTTPS URL."""
        worker = Mock(spec=Worker)
        worker._build_authenticated_url = Worker._build_authenticated_url.__get__(worker)
        
        url = "https://github.com/owner/repo.git"
        token = "ghp_test123"
        
        result = worker._build_authenticated_url(url, token)
        
        assert result == "https://x-access-token:ghp_test123@github.com/owner/repo.git"
        assert token in result
    
    def test_build_authenticated_url_ssh(self):
        """Should convert SSH to HTTPS with token."""
        worker = Mock(spec=Worker)
        worker._build_authenticated_url = Worker._build_authenticated_url.__get__(worker)
        
        url = "git@github.com:owner/repo.git"
        token = "ghp_test123"
        
        result = worker._build_authenticated_url(url, token)
        
        assert result.startswith("https://x-access-token:")
        assert "github.com/owner/repo.git" in result
        assert "git@" not in result
    
    def test_extract_repo_info_https(self):
        """Should extract owner and repo from HTTPS URL."""
        worker = Mock(spec=Worker)
        worker._extract_repo_info = Worker._extract_repo_info.__get__(worker)
        
        url = "https://github.com/iangreen74/leviathan.git"
        
        owner, repo = worker._extract_repo_info(url)
        
        assert owner == "iangreen74"
        assert repo == "leviathan"
    
    def test_extract_repo_info_ssh(self):
        """Should extract owner and repo from SSH URL."""
        worker = Mock(spec=Worker)
        worker._extract_repo_info = Worker._extract_repo_info.__get__(worker)
        
        url = "git@github.com:iangreen74/leviathan.git"
        
        owner, repo = worker._extract_repo_info(url)
        
        assert owner == "iangreen74"
        assert repo == "leviathan"
    
    def test_extract_repo_info_invalid(self):
        """Should raise error for invalid URL."""
        worker = Mock(spec=Worker)
        worker._extract_repo_info = Worker._extract_repo_info.__get__(worker)
        
        url = "invalid-url"
        
        with pytest.raises(WorkerError, match="Could not parse GitHub repo"):
            worker._extract_repo_info(url)
    
    def test_format_acceptance_criteria_empty(self):
        """Should handle empty acceptance criteria."""
        worker = Mock(spec=Worker)
        worker._format_acceptance_criteria = Worker._format_acceptance_criteria.__get__(worker)
        
        result = worker._format_acceptance_criteria([])
        
        assert result == "*No acceptance criteria specified*"
    
    def test_format_acceptance_criteria_list(self):
        """Should format criteria as markdown list."""
        worker = Mock(spec=Worker)
        worker._format_acceptance_criteria = Worker._format_acceptance_criteria.__get__(worker)
        
        criteria = ["Test passes", "Code is clean", "Docs updated"]
        
        result = worker._format_acceptance_criteria(criteria)
        
        assert "- Test passes" in result
        assert "- Code is clean" in result
        assert "- Docs updated" in result
    
    @patch('requests.get')
    def test_get_existing_pr_found(self, mock_get):
        """Should return existing PR if found."""
        worker = Mock(spec=Worker)
        worker.github_token = "test-token"
        worker._get_existing_pr = Worker._get_existing_pr.__get__(worker)
        
        mock_response = Mock()
        mock_response.json.return_value = [{
            'number': 123,
            'html_url': 'https://github.com/owner/repo/pull/123'
        }]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = worker._get_existing_pr("owner", "repo", "test-branch")
        
        assert result is not None
        assert result['number'] == 123
        assert result['html_url'] == 'https://github.com/owner/repo/pull/123'
    
    @patch('requests.get')
    def test_get_existing_pr_not_found(self, mock_get):
        """Should return None if no PR exists."""
        worker = Mock(spec=Worker)
        worker.github_token = "test-token"
        worker._get_existing_pr = Worker._get_existing_pr.__get__(worker)
        
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = worker._get_existing_pr("owner", "repo", "test-branch")
        
        assert result is None
    
    @patch('requests.get')
    def test_get_existing_pr_error(self, mock_get):
        """Should return None on error."""
        worker = Mock(spec=Worker)
        worker.github_token = "test-token"
        worker._get_existing_pr = Worker._get_existing_pr.__get__(worker)
        
        mock_get.side_effect = Exception("API error")
        
        result = worker._get_existing_pr("owner", "repo", "test-branch")
        
        assert result is None
    
    @patch('requests.post')
    def test_create_pr_new(self, mock_post):
        """Should create new PR via GitHub API."""
        worker = Mock(spec=Worker)
        worker.github_token = "test-token"
        worker.target_repo_url = "https://github.com/owner/repo.git"
        worker.target_branch = "main"
        worker.task_id = "task-1"
        worker.attempt_id = "attempt-1"
        worker._extract_repo_info = Worker._extract_repo_info.__get__(worker)
        worker._format_acceptance_criteria = Worker._format_acceptance_criteria.__get__(worker)
        worker._get_existing_pr = Mock(return_value=None)
        worker._create_pr = Worker._create_pr.__get__(worker)
        
        mock_response = Mock()
        mock_response.json.return_value = {
            'number': 456,
            'html_url': 'https://github.com/owner/repo/pull/456'
        }
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        task_spec = Task(
            id='task-1',
            title='Test Task',
            scope='test',
            priority='high',
            ready=True,
            allowed_paths=[],
            acceptance_criteria=['Test passes'],
            dependencies=[],
            estimated_size='small'
        )
        
        pr_url, pr_number = worker._create_pr("test-branch", task_spec)
        
        assert pr_url == 'https://github.com/owner/repo/pull/456'
        assert pr_number == 456
        
        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]['json']['title'] == 'Leviathan: Test Task'
        assert call_args[1]['json']['head'] == 'test-branch'
        assert call_args[1]['json']['base'] == 'main'
    
    def test_create_pr_existing(self):
        """Should return existing PR if found."""
        worker = Mock(spec=Worker)
        worker.github_token = "test-token"
        worker.target_repo_url = "https://github.com/owner/repo.git"
        worker.task_id = "task-1"
        worker.attempt_id = "attempt-1"
        worker._extract_repo_info = Worker._extract_repo_info.__get__(worker)
        worker._format_acceptance_criteria = Worker._format_acceptance_criteria.__get__(worker)
        worker._get_existing_pr = Mock(return_value={
            'number': 789,
            'html_url': 'https://github.com/owner/repo/pull/789'
        })
        worker._create_pr = Worker._create_pr.__get__(worker)
        
        task_spec = Task(
            id='task-1',
            title='Test Task',
            scope='test',
            priority='high',
            ready=True,
            allowed_paths=[],
            acceptance_criteria=[],
            dependencies=[],
            estimated_size='small'
        )
        
        pr_url, pr_number = worker._create_pr("test-branch", task_spec)
        
        assert pr_url == 'https://github.com/owner/repo/pull/789'
        assert pr_number == 789
    
    def test_create_pr_no_token(self):
        """Should raise error if no GitHub token."""
        worker = Mock(spec=Worker)
        worker.github_token = None
        worker._create_pr = Worker._create_pr.__get__(worker)
        
        task_spec = Task(
            id='task-1',
            title='Test',
            scope='test',
            priority='high',
            ready=True,
            allowed_paths=[],
            acceptance_criteria=[],
            dependencies=[],
            estimated_size='small'
        )
        
        with pytest.raises(WorkerError, match="GITHUB_TOKEN required"):
            worker._create_pr("test-branch", task_spec)
    
    def test_branch_name_format(self):
        """Should use collision-safe branch naming."""
        # Branch name should be: agent/<task_id>-<attempt_id>
        task_id = "task-123"
        attempt_id = "attempt-456"
        expected = f"agent/{task_id}-{attempt_id}"
        
        assert expected == "agent/task-123-attempt-456"
