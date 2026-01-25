"""
Unit tests for worker task loading and typed Task objects.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from leviathan.executor.worker import Worker, WorkerError
from leviathan.backlog import Task


class TestWorkerTaskLoading:
    """Test worker task loading with typed Task objects."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.target_dir = self.temp_dir / "target"
        self.target_dir.mkdir(parents=True, exist_ok=True)
        self.backlog_dir = self.target_dir / ".leviathan"
        self.backlog_dir.mkdir(parents=True, exist_ok=True)
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_load_task_spec_dict_format(self):
        """Should load task from dict format backlog and return Task object."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-001"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        # Create backlog with dict format
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
version: 1
max_open_prs: 2
tasks:
  - id: task-001
    title: Test Task
    scope: test
    priority: high
    ready: true
    estimated_size: small
    allowed_paths:
      - src/test.py
      - tests/test_test.py
    acceptance_criteria:
      - Tests pass
      - Code is clean
    dependencies: []
""")
        
        task = worker._load_task_spec()
        
        # Verify it's a Task object
        assert isinstance(task, Task)
        
        # Verify fields are accessible via attributes
        assert task.id == "task-001"
        assert task.title == "Test Task"
        assert task.scope == "test"
        assert task.priority == "high"
        assert task.ready is True
        assert task.estimated_size == "small"
        
        # Verify allowed_paths is a list
        assert isinstance(task.allowed_paths, list)
        assert len(task.allowed_paths) == 2
        assert "src/test.py" in task.allowed_paths
        
        # Verify acceptance_criteria is a list
        assert isinstance(task.acceptance_criteria, list)
        assert len(task.acceptance_criteria) == 2
        assert "Tests pass" in task.acceptance_criteria
    
    def test_load_task_spec_list_format(self):
        """Should load task from list format backlog and return Task object."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-002"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        # Create backlog with list format (no 'tasks' key)
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
- id: task-002
  title: Another Task
  scope: feature
  priority: medium
  ready: true
  estimated_size: medium
  allowed_paths:
    - lib/feature.py
  acceptance_criteria:
    - Feature works
  dependencies: []
""")
        
        task = worker._load_task_spec()
        
        # Verify it's a Task object
        assert isinstance(task, Task)
        assert task.id == "task-002"
        assert task.title == "Another Task"
        assert isinstance(task.allowed_paths, list)
        assert len(task.allowed_paths) == 1
    
    def test_load_task_spec_task_id_normalization(self):
        """Should normalize 'task_id' to 'id' field."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-003"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        # Create backlog with 'task_id' instead of 'id'
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - task_id: task-003
    title: Legacy Format Task
    scope: test
    priority: low
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        task = worker._load_task_spec()
        
        assert isinstance(task, Task)
        assert task.id == "task-003"
    
    def test_load_task_spec_not_found(self):
        """Should raise WorkerError if task not found."""
        worker = Mock(spec=Worker)
        worker.task_id = "nonexistent-task"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: task-001
    title: Test Task
    scope: test
    priority: high
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria: []
    dependencies: []
""")
        
        with pytest.raises(WorkerError, match="Task nonexistent-task not found"):
            worker._load_task_spec()
    
    def test_load_task_spec_backlog_not_found(self):
        """Should raise WorkerError if backlog file doesn't exist."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-001"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        # Don't create backlog file
        
        with pytest.raises(WorkerError, match="Backlog not found"):
            worker._load_task_spec()
    
    def test_load_task_spec_defaults(self):
        """Should use defaults for optional fields."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-004"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        # Create minimal backlog
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: task-004
""")
        
        task = worker._load_task_spec()
        
        assert isinstance(task, Task)
        assert task.id == "task-004"
        assert task.title == "Untitled"
        assert task.scope == "unknown"
        assert task.priority == "medium"
        assert task.ready is True
        assert task.allowed_paths == []
        assert task.acceptance_criteria == []
        assert task.dependencies == []
        assert task.estimated_size == "unknown"
    
    def test_allowed_paths_is_list(self):
        """Should ensure allowed_paths is always a list."""
        worker = Mock(spec=Worker)
        worker.task_id = "task-005"
        worker.target_dir = self.target_dir
        worker._load_task_spec = Worker._load_task_spec.__get__(worker)
        
        backlog_file = self.backlog_dir / "backlog.yaml"
        backlog_file.write_text("""
tasks:
  - id: task-005
    title: Test
    allowed_paths:
      - file1.py
      - file2.py
      - file3.py
""")
        
        task = worker._load_task_spec()
        
        assert isinstance(task.allowed_paths, list)
        assert len(task.allowed_paths) == 3
        
        # Verify we can iterate over it
        for path in task.allowed_paths:
            assert isinstance(path, str)


class TestWorkerTaskExecution:
    """Test worker task execution with typed Task objects."""
    
    def test_execute_task_validates_allowed_paths(self):
        """Should validate that allowed_paths is a list."""
        worker = Mock(spec=Worker)
        worker.target_dir = Path("/tmp/test")
        worker.attempt_id = "attempt-123"
        worker.task_id = "task-001"
        worker.artifact_store = Mock()
        worker.artifacts = []
        worker.events = []
        worker._emit_event = Mock()
        worker._execute_task = Worker._execute_task.__get__(worker)
        
        # Create task with invalid allowed_paths
        task = Task(
            id="task-001",
            title="Test",
            scope="test",
            priority="high",
            ready=True,
            allowed_paths="not-a-list",  # Invalid!
            acceptance_criteria=[],
            dependencies=[],
            estimated_size="small"
        )
        
        with pytest.raises(WorkerError, match="allowed_paths must be a list"):
            worker._execute_task(task)
    
    @patch('leviathan.executor.worker.ModelClient')
    def test_execute_task_uses_task_attributes(self, mock_model_client):
        """Should access task fields via attributes, not dict keys."""
        worker = Mock(spec=Worker)
        worker.target_dir = Path("/tmp/test")
        worker.attempt_id = "attempt-123"
        worker.task_id = "task-001"
        worker.artifact_store = Mock()
        worker.artifact_store.store = Mock(return_value={
            'sha256': 'a' * 64,
            'size_bytes': 1024,
            'storage_path': '/tmp/log.txt'
        })
        worker.artifacts = []
        worker.events = []
        worker._emit_event = Mock()
        worker._execute_task = Worker._execute_task.__get__(worker)
        
        # Mock model client to return success
        mock_instance = Mock()
        mock_instance.generate_implementation_rewrite_mode = Mock(
            return_value=(['file1.py'], 'test-source')
        )
        mock_model_client.return_value = mock_instance
        
        # Create valid task
        task = Task(
            id="task-001",
            title="Test Task",
            scope="test",
            priority="high",
            ready=True,
            allowed_paths=["file1.py", "file2.py"],
            acceptance_criteria=["Tests pass"],
            dependencies=[],
            estimated_size="small"
        )
        
        # Should not raise AttributeError
        result = worker._execute_task(task)
        
        assert result is True
        
        # Verify model was called with task object
        mock_instance.generate_implementation_rewrite_mode.assert_called_once_with(
            task,
            retry_context=None
        )
    
    @patch('leviathan.executor.worker.ModelClient')
    def test_execute_task_accesses_title_scope_allowed_paths(self, mock_model_client):
        """Should access task.title, task.scope, task.allowed_paths without errors."""
        worker = Mock(spec=Worker)
        worker.target_dir = Path("/tmp/test")
        worker.attempt_id = "attempt-456"
        worker.task_id = "task-002"
        worker.artifact_store = Mock()
        worker.artifact_store.store = Mock(return_value={
            'sha256': 'b' * 64,
            'size_bytes': 2048,
            'storage_path': '/tmp/log2.txt'
        })
        worker.artifacts = []
        worker.events = []
        worker._emit_event = Mock()
        worker._execute_task = Worker._execute_task.__get__(worker)
        
        mock_instance = Mock()
        mock_instance.generate_implementation_rewrite_mode = Mock(
            return_value=(['output.py'], 'claude')
        )
        mock_model_client.return_value = mock_instance
        
        task = Task(
            id="task-002",
            title="Feature Implementation",
            scope="feature",
            priority="medium",
            ready=True,
            allowed_paths=["src/feature.py", "tests/test_feature.py"],
            acceptance_criteria=["Feature works", "Tests pass"],
            dependencies=[],
            estimated_size="medium"
        )
        
        result = worker._execute_task(task)
        
        assert result is True
        
        # Verify artifact log contains task attributes
        log_call = worker.artifact_store.store.call_args
        log_content = log_call[0][0].decode('utf-8')
        
        assert "Feature Implementation" in log_content
        assert "feature" in log_content
        assert "src/feature.py" in log_content or "allowed_paths" in log_content
