"""
Unit tests for backlog loader with format normalization.
"""
import pytest
import tempfile
import yaml
from pathlib import Path

from leviathan.backlog_loader import load_backlog_tasks, filter_ready_tasks


class TestBacklogLoader:
    """Test backlog loading with different YAML formats."""
    
    def setup_method(self):
        """Create temporary directory for test files."""
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_load_dict_format_with_tasks_key(self):
        """Should load backlog in dict{tasks:[...]} format."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'version': 1,
            'max_open_prs': 2,
            'tasks': [
                {
                    'id': 'task-001',
                    'title': 'Test task 1',
                    'ready': True,
                    'scope': 'test',
                    'priority': 'high'
                },
                {
                    'id': 'task-002',
                    'title': 'Test task 2',
                    'ready': False,
                    'scope': 'test',
                    'priority': 'medium'
                }
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        
        assert len(tasks) == 2
        assert tasks[0]['id'] == 'task-001'
        assert tasks[0]['title'] == 'Test task 1'
        assert tasks[1]['id'] == 'task-002'
    
    def test_load_top_level_list_format(self):
        """Should load backlog in top-level list format."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = [
            {
                'id': 'task-001',
                'title': 'Test task 1',
                'ready': True,
                'scope': 'test'
            },
            {
                'id': 'task-002',
                'title': 'Test task 2',
                'ready': True,
                'scope': 'test'
            }
        ]
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        
        assert len(tasks) == 2
        assert tasks[0]['id'] == 'task-001'
        assert tasks[1]['id'] == 'task-002'
    
    def test_filter_ready_tasks(self):
        """Should filter tasks to only those with ready=True."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {'id': 'task-001', 'ready': True, 'title': 'Ready task'},
                {'id': 'task-002', 'ready': False, 'title': 'Not ready'},
                {'id': 'task-003', 'ready': True, 'title': 'Also ready'}
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        ready_tasks = filter_ready_tasks(tasks)
        
        assert len(ready_tasks) == 2
        assert ready_tasks[0]['id'] == 'task-001'
        assert ready_tasks[1]['id'] == 'task-003'
    
    def test_invalid_format_not_dict_or_list(self):
        """Should raise ValueError for invalid root type."""
        backlog_file = self.temp_dir / "backlog.yaml"
        
        with open(backlog_file, 'w') as f:
            f.write("just a string")
        
        with pytest.raises(ValueError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "expected dict or list" in str(exc_info.value)
        assert "got str" in str(exc_info.value)
    
    def test_invalid_format_dict_without_tasks_key(self):
        """Should raise ValueError for dict without 'tasks' key."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'version': 1,
            'max_open_prs': 2,
            'items': []  # Wrong key
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        with pytest.raises(ValueError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "must contain 'tasks' key" in str(exc_info.value)
        assert "version" in str(exc_info.value)
        assert "max_open_prs" in str(exc_info.value)
    
    def test_invalid_tasks_not_list(self):
        """Should raise ValueError if 'tasks' is not a list."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': 'not a list'
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        with pytest.raises(ValueError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "'tasks' must be a list" in str(exc_info.value)
    
    def test_invalid_task_not_dict(self):
        """Should raise ValueError if task is not a dict."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {'id': 'task-001', 'ready': True},
                'not a dict',  # Invalid
                {'id': 'task-003', 'ready': True}
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        with pytest.raises(ValueError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "Invalid task at index 1" in str(exc_info.value)
        assert "expected dict" in str(exc_info.value)
    
    def test_missing_id_field(self):
        """Should raise ValueError if task missing 'id' field."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {'id': 'task-001', 'ready': True},
                {'title': 'No ID', 'ready': True}  # Missing 'id'
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        with pytest.raises(ValueError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "missing 'id' field" in str(exc_info.value)
        assert "index 1" in str(exc_info.value)
    
    def test_task_id_normalized_to_id(self):
        """Should normalize 'task_id' to 'id' for compatibility."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {'task_id': 'task-001', 'ready': True, 'title': 'Old format'}
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        
        assert len(tasks) == 1
        assert tasks[0]['id'] == 'task-001'
        assert tasks[0]['task_id'] == 'task-001'  # Original preserved
    
    def test_missing_backlog_file(self):
        """Should raise FileNotFoundError for missing file."""
        backlog_file = self.temp_dir / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            load_backlog_tasks(backlog_file)
        
        assert "Backlog not found" in str(exc_info.value)
    
    def test_estimated_size_not_filtered(self):
        """Should NOT filter tasks based on estimated_size."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {'id': 'task-001', 'ready': True, 'estimated_size': 'small'},
                {'id': 'task-002', 'ready': True, 'estimated_size': 'large'},
                {'id': 'task-003', 'ready': True, 'estimated_size': 'unknown'}
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        ready_tasks = filter_ready_tasks(tasks)
        
        # All ready tasks should be included regardless of estimated_size
        assert len(ready_tasks) == 3
        assert ready_tasks[0]['id'] == 'task-001'
        assert ready_tasks[1]['id'] == 'task-002'
        assert ready_tasks[2]['id'] == 'task-003'
    
    def test_empty_tasks_list(self):
        """Should handle empty tasks list."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {'tasks': []}
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        
        assert len(tasks) == 0
    
    def test_tasks_with_all_metadata(self):
        """Should preserve all task metadata fields."""
        backlog_file = self.temp_dir / "backlog.yaml"
        backlog_data = {
            'tasks': [
                {
                    'id': 'self-target-bootstrap',
                    'title': 'Bootstrap self-target',
                    'scope': 'infra',
                    'priority': 'high',
                    'ready': True,
                    'estimated_size': 'medium',
                    'allowed_paths': ['leviathan/'],
                    'acceptance_criteria': ['Tests pass'],
                    'dependencies': []
                }
            ]
        }
        
        with open(backlog_file, 'w') as f:
            yaml.dump(backlog_data, f)
        
        tasks = load_backlog_tasks(backlog_file)
        
        assert len(tasks) == 1
        task = tasks[0]
        assert task['id'] == 'self-target-bootstrap'
        assert task['title'] == 'Bootstrap self-target'
        assert task['scope'] == 'infra'
        assert task['priority'] == 'high'
        assert task['ready'] is True
        assert task['estimated_size'] == 'medium'
        assert task['allowed_paths'] == ['leviathan/']
        assert task['acceptance_criteria'] == ['Tests pass']
        assert task['dependencies'] == []
