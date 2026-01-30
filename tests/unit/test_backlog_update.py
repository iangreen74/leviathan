"""
Unit tests for backlog update functionality.

Tests marking tasks as completed in target repo backlog.
"""
import pytest
import tempfile
import yaml
from pathlib import Path
from datetime import datetime

from leviathan.executor.backlog_update import mark_task_completed, is_task_completed


@pytest.fixture
def sample_backlog():
    """Create sample backlog YAML content."""
    return {
        'version': '1.0',
        'tasks': [
            {
                'id': 'task-1',
                'title': 'First task',
                'ready': True,
                'status': 'pending',
                'allowed_paths': ['docs/']
            },
            {
                'id': 'task-2',
                'title': 'Second task',
                'ready': True,
                'status': 'pending',
                'allowed_paths': ['.leviathan/']
            },
            {
                'id': 'task-3',
                'title': 'Third task',
                'ready': False,
                'status': 'pending',
                'allowed_paths': ['src/']
            }
        ]
    }


@pytest.fixture
def backlog_file(sample_backlog):
    """Create temporary backlog file."""
    temp_dir = Path(tempfile.mkdtemp())
    backlog_path = temp_dir / 'backlog.yaml'
    
    with open(backlog_path, 'w') as f:
        yaml.dump(sample_backlog, f, default_flow_style=False, sort_keys=False)
    
    yield backlog_path
    
    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_mark_task_completed_success(backlog_file):
    """Test successfully marking a task as completed."""
    result = mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-abc123',
        'agent/task-exec-attempt-abc123',
        pr_number=42
    )
    
    assert result is True
    
    # Verify backlog was updated
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    task_1 = backlog['tasks'][0]
    assert task_1['id'] == 'task-1'
    assert task_1['status'] == 'completed'
    assert task_1['ready'] is False
    assert task_1['last_attempt_id'] == 'attempt-abc123'
    assert task_1['branch_name'] == 'agent/task-exec-attempt-abc123'
    assert task_1['pr_number'] == 42
    assert 'completed_at' in task_1
    
    # Verify timestamp is valid ISO format
    datetime.fromisoformat(task_1['completed_at'])


def test_mark_task_completed_null_pr_number(backlog_file):
    """Test marking task completed with null PR number."""
    result = mark_task_completed(
        backlog_file,
        'task-2',
        'attempt-def456',
        'agent/task-exec-attempt-def456',
        pr_number=None
    )
    
    assert result is True
    
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    task_2 = backlog['tasks'][1]
    assert task_2['status'] == 'completed'
    assert task_2['pr_number'] is None


def test_mark_task_completed_preserves_other_tasks(backlog_file):
    """Test that marking one task completed doesn't affect other tasks."""
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-abc123',
        'agent/task-exec-attempt-abc123',
        pr_number=42
    )
    
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    # Task 1 should be completed
    assert backlog['tasks'][0]['status'] == 'completed'
    assert backlog['tasks'][0]['ready'] is False
    
    # Task 2 should be unchanged
    assert backlog['tasks'][1]['status'] == 'pending'
    assert backlog['tasks'][1]['ready'] is True
    assert 'last_attempt_id' not in backlog['tasks'][1]
    
    # Task 3 should be unchanged
    assert backlog['tasks'][2]['status'] == 'pending'
    assert backlog['tasks'][2]['ready'] is False


def test_mark_task_completed_task_not_found(backlog_file):
    """Test marking a non-existent task returns False."""
    result = mark_task_completed(
        backlog_file,
        'nonexistent-task',
        'attempt-xyz789',
        'agent/task-exec-attempt-xyz789',
        pr_number=99
    )
    
    assert result is False
    
    # Verify backlog was not modified
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    for task in backlog['tasks']:
        assert task['status'] == 'pending'
        assert 'last_attempt_id' not in task


def test_mark_task_completed_file_not_found():
    """Test marking task in non-existent backlog raises ValueError."""
    nonexistent_path = Path('/tmp/nonexistent-backlog.yaml')
    
    with pytest.raises(ValueError, match="Backlog file not found"):
        mark_task_completed(
            nonexistent_path,
            'task-1',
            'attempt-abc123',
            'agent/task-exec-attempt-abc123'
        )


def test_mark_task_completed_invalid_backlog():
    """Test marking task in invalid backlog raises ValueError."""
    temp_dir = Path(tempfile.mkdtemp())
    backlog_path = temp_dir / 'invalid.yaml'
    
    # Create invalid backlog (missing 'tasks' key)
    with open(backlog_path, 'w') as f:
        yaml.dump({'version': '1.0'}, f)
    
    with pytest.raises(ValueError, match="Invalid backlog format"):
        mark_task_completed(
            backlog_path,
            'task-1',
            'attempt-abc123',
            'agent/task-exec-attempt-abc123'
        )
    
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_mark_task_completed_preserves_yaml_structure(backlog_file):
    """Test that YAML structure and formatting is preserved."""
    # Read original content
    with open(backlog_file, 'r') as f:
        original = yaml.safe_load(f)
    
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-abc123',
        'agent/task-exec-attempt-abc123',
        pr_number=42
    )
    
    with open(backlog_file, 'r') as f:
        updated = yaml.safe_load(f)
    
    # Verify version is preserved
    assert updated['version'] == original['version']
    
    # Verify task count is same
    assert len(updated['tasks']) == len(original['tasks'])
    
    # Verify task order is preserved
    for i, task in enumerate(updated['tasks']):
        assert task['id'] == original['tasks'][i]['id']


def test_is_task_completed_true(backlog_file):
    """Test checking if task is completed returns True."""
    # Mark task completed
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-abc123',
        'agent/task-exec-attempt-abc123'
    )
    
    # Check if completed
    assert is_task_completed(backlog_file, 'task-1') is True


def test_is_task_completed_false(backlog_file):
    """Test checking if pending task returns False."""
    assert is_task_completed(backlog_file, 'task-1') is False


def test_is_task_completed_task_not_found(backlog_file):
    """Test checking non-existent task returns False."""
    assert is_task_completed(backlog_file, 'nonexistent-task') is False


def test_is_task_completed_file_not_found():
    """Test checking task in non-existent backlog returns False."""
    nonexistent_path = Path('/tmp/nonexistent-backlog.yaml')
    assert is_task_completed(nonexistent_path, 'task-1') is False


def test_mark_task_completed_updates_existing_metadata(backlog_file):
    """Test that marking task completed twice updates metadata."""
    # First completion
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-first',
        'agent/task-exec-attempt-first',
        pr_number=10
    )
    
    # Second completion (should update)
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-second',
        'agent/task-exec-attempt-second',
        pr_number=20
    )
    
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    task_1 = backlog['tasks'][0]
    assert task_1['last_attempt_id'] == 'attempt-second'
    assert task_1['branch_name'] == 'agent/task-exec-attempt-second'
    assert task_1['pr_number'] == 20


def test_mark_task_completed_preserves_other_fields(backlog_file):
    """Test that marking task completed preserves other task fields."""
    mark_task_completed(
        backlog_file,
        'task-1',
        'attempt-abc123',
        'agent/task-exec-attempt-abc123'
    )
    
    with open(backlog_file, 'r') as f:
        backlog = yaml.safe_load(f)
    
    task_1 = backlog['tasks'][0]
    # Original fields should be preserved
    assert task_1['title'] == 'First task'
    assert task_1['allowed_paths'] == ['docs/']
    assert task_1['id'] == 'task-1'
