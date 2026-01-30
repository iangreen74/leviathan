"""
Unit tests for scheduler open PR latch functionality.

Tests that the scheduler correctly skips tasks with existing open agent PRs.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from leviathan.scheduler.dev_autonomy import DevAutonomyScheduler


@pytest.fixture
def mock_config(tmp_path):
    """Create mock config file."""
    config_path = tmp_path / "autonomy.yaml"
    config_content = """
target_id: test-target
target_repo_url: https://github.com/test/repo.git
target_branch: main
allowed_path_prefixes:
  - docs/
  - .leviathan/
max_open_prs: 3
max_attempts_per_task: 2
circuit_breaker_failures: 3
control_plane_url: http://localhost:8000
worker_image: leviathan-worker:local
worker_namespace: leviathan
workspace_dir: /workspace
autonomy_enabled: true
"""
    config_path.write_text(config_content)
    return str(config_path)


@pytest.fixture
def scheduler(mock_config, monkeypatch):
    """Create scheduler instance with mocked env vars."""
    monkeypatch.setenv('GITHUB_TOKEN', 'test-token')
    monkeypatch.setenv('CONTROL_PLANE_TOKEN', 'test-cp-token')
    return DevAutonomyScheduler(mock_config)


def test_extract_task_id_from_branch_standard_format(scheduler):
    """Test extracting task_id from standard agent branch format."""
    branch = "agent/task-exec-attempt-docs-leviathan-backlog-guide-1fa64a45"
    task_id = scheduler._extract_task_id_from_branch(branch)
    assert task_id == "docs-leviathan-backlog-guide"


def test_extract_task_id_from_branch_no_prefix(scheduler):
    """Test extracting task_id when branch doesn't have agent/ prefix."""
    branch = "feature/some-branch"
    task_id = scheduler._extract_task_id_from_branch(branch)
    assert task_id is None


def test_extract_task_id_from_branch_short_hash(scheduler):
    """Test extracting task_id with 8-char hash suffix."""
    branch = "agent/task-exec-attempt-simple-task-abc12345"
    task_id = scheduler._extract_task_id_from_branch(branch)
    assert task_id == "simple-task"


def test_extract_task_id_from_branch_no_hash(scheduler):
    """Test extracting task_id when no hash suffix present."""
    branch = "agent/task-exec-attempt-some-task"
    task_id = scheduler._extract_task_id_from_branch(branch)
    # Should return the whole suffix as fallback
    assert task_id == "some-task"


def test_extract_in_flight_tasks_single_pr(scheduler):
    """Test extracting in-flight tasks from single open PR."""
    open_prs = [
        {
            'number': 123,
            'url': 'https://github.com/test/repo/pull/123',
            'branch': 'agent/task-exec-attempt-docs-guide-abc12345',
            'title': 'Add docs guide'
        }
    ]
    
    in_flight = scheduler._extract_in_flight_tasks(open_prs)
    assert in_flight == {'docs-guide'}


def test_extract_in_flight_tasks_multiple_prs(scheduler):
    """Test extracting in-flight tasks from multiple open PRs."""
    open_prs = [
        {
            'number': 123,
            'url': 'https://github.com/test/repo/pull/123',
            'branch': 'agent/task-exec-attempt-docs-guide-abc12345',
            'title': 'Add docs guide'
        },
        {
            'number': 124,
            'url': 'https://github.com/test/repo/pull/124',
            'branch': 'agent/task-exec-attempt-fix-bug-def67890',
            'title': 'Fix bug'
        }
    ]
    
    in_flight = scheduler._extract_in_flight_tasks(open_prs)
    assert in_flight == {'docs-guide', 'fix-bug'}


def test_extract_in_flight_tasks_duplicate_task_ids(scheduler):
    """Test that duplicate task_ids result in single entry in set."""
    open_prs = [
        {
            'number': 123,
            'url': 'https://github.com/test/repo/pull/123',
            'branch': 'agent/task-exec-attempt-docs-guide-abc12345',
            'title': 'Add docs guide attempt 1'
        },
        {
            'number': 124,
            'url': 'https://github.com/test/repo/pull/124',
            'branch': 'agent/task-exec-attempt-docs-guide-def67890',
            'title': 'Add docs guide attempt 2'
        }
    ]
    
    in_flight = scheduler._extract_in_flight_tasks(open_prs)
    assert in_flight == {'docs-guide'}


def test_extract_in_flight_tasks_empty_list(scheduler):
    """Test extracting in-flight tasks from empty PR list."""
    in_flight = scheduler._extract_in_flight_tasks([])
    assert in_flight == set()


def test_select_next_task_skips_in_flight(scheduler):
    """Test that task selection skips tasks with open PRs."""
    tasks = [
        {
            'id': 'task-with-pr',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/guide.md']
        },
        {
            'id': 'task-without-pr',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/other.md']
        }
    ]
    
    in_flight_tasks = {'task-with-pr'}
    
    selected = scheduler._select_next_task(tasks, in_flight_tasks)
    assert selected is not None
    assert selected['id'] == 'task-without-pr'


def test_select_next_task_all_in_flight(scheduler):
    """Test that no task is selected when all ready tasks have open PRs."""
    tasks = [
        {
            'id': 'task-1',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/guide.md']
        },
        {
            'id': 'task-2',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/other.md']
        }
    ]
    
    in_flight_tasks = {'task-1', 'task-2'}
    
    selected = scheduler._select_next_task(tasks, in_flight_tasks)
    assert selected is None


def test_select_next_task_no_in_flight(scheduler):
    """Test that task selection works normally when no tasks are in-flight."""
    tasks = [
        {
            'id': 'task-1',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/guide.md']
        }
    ]
    
    in_flight_tasks = set()
    
    selected = scheduler._select_next_task(tasks, in_flight_tasks)
    assert selected is not None
    assert selected['id'] == 'task-1'


def test_select_next_task_respects_other_guardrails(scheduler):
    """Test that open PR latch works alongside other guardrails."""
    tasks = [
        {
            'id': 'not-ready',
            'ready': False,
            'status': 'pending',
            'allowed_paths': ['docs/guide.md']
        },
        {
            'id': 'wrong-scope',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['src/code.py']  # Not in allowed prefixes
        },
        {
            'id': 'has-open-pr',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/other.md']
        },
        {
            'id': 'valid-task',
            'ready': True,
            'status': 'pending',
            'allowed_paths': ['docs/final.md']
        }
    ]
    
    in_flight_tasks = {'has-open-pr'}
    
    selected = scheduler._select_next_task(tasks, in_flight_tasks)
    assert selected is not None
    assert selected['id'] == 'valid-task'


def test_get_open_agent_prs_filters_non_agent_branches(scheduler):
    """Test that _get_open_agent_prs only returns agent/ branches."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            'number': 123,
            'html_url': 'https://github.com/test/repo/pull/123',
            'head': {'ref': 'agent/task-exec-attempt-task1-abc12345'},
            'title': 'Agent PR'
        },
        {
            'number': 124,
            'html_url': 'https://github.com/test/repo/pull/124',
            'head': {'ref': 'feature/user-branch'},
            'title': 'User PR'
        },
        {
            'number': 125,
            'html_url': 'https://github.com/test/repo/pull/125',
            'head': {'ref': 'agent/task-exec-attempt-task2-def67890'},
            'title': 'Another agent PR'
        }
    ]
    mock_response.raise_for_status = Mock()
    
    with patch('requests.get', return_value=mock_response):
        agent_prs = scheduler._get_open_agent_prs()
    
    assert len(agent_prs) == 2
    assert agent_prs[0]['number'] == 123
    assert agent_prs[0]['branch'] == 'agent/task-exec-attempt-task1-abc12345'
    assert agent_prs[1]['number'] == 125
    assert agent_prs[1]['branch'] == 'agent/task-exec-attempt-task2-def67890'


def test_get_open_agent_prs_handles_api_error(scheduler):
    """Test that _get_open_agent_prs handles API errors gracefully."""
    with patch('requests.get', side_effect=Exception("API error")):
        agent_prs = scheduler._get_open_agent_prs()
    
    # Should return empty list on error (fail-safe)
    assert agent_prs == []


def test_count_open_prs_uses_get_open_agent_prs(scheduler):
    """Test that _count_open_prs correctly counts agent PRs."""
    mock_prs = [
        {'number': 123, 'branch': 'agent/task1', 'url': 'url1', 'title': 'PR 1'},
        {'number': 124, 'branch': 'agent/task2', 'url': 'url2', 'title': 'PR 2'}
    ]
    
    with patch.object(scheduler, '_get_open_agent_prs', return_value=mock_prs):
        count = scheduler._count_open_prs()
    
    assert count == 2


def test_count_open_prs_fail_safe_on_none(scheduler):
    """Test that _count_open_prs returns max_open_prs when API fails."""
    with patch.object(scheduler, '_get_open_agent_prs', return_value=None):
        count = scheduler._count_open_prs()
    
    assert count == scheduler.max_open_prs
