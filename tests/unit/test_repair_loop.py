"""
Unit tests for per-task repair loop functionality.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from leviathan.runner import LeviathanRunner


class MockTask:
    """Mock task object for testing."""
    def __init__(self, task_id="test-task", allowed_paths=None):
        self.id = task_id
        self.title = "Test Task"
        self.scope = "test"
        self.priority = "high"
        self.estimated_size = "small"
        self.allowed_paths = allowed_paths or ["test.py", "test.json"]
        self.acceptance_criteria = ["Tests pass", "Code is clean"]


class TestRepairLoop:
    """Test repair loop convergence behavior."""
    
    @patch('leviathan.runner.subprocess.run')
    @patch('leviathan.runner.CommandExecutor')
    @patch('leviathan.runner.ModelClient')
    @patch('leviathan.runner.GitHubClient')
    @patch('leviathan.runner.Backlog')
    def test_success_on_first_attempt(self, mock_backlog, mock_github, mock_model, mock_executor, mock_subprocess):
        """Task succeeds on first attempt - no retry needed."""
        # Setup mocks
        mock_model_instance = Mock()
        mock_model_instance.repo_root = Path("/tmp/test")
        mock_model_instance.generate_implementation_rewrite_mode.return_value = (["test.py"], "claude_api")
        mock_model.return_value = mock_model_instance
        
        mock_executor_instance = Mock()
        mock_executor_instance.run_test_suite.return_value = (True, "All tests passed")
        mock_executor_instance.run_command.return_value = Mock(returncode=0, stdout="M test.py", stderr="")
        mock_executor.return_value = mock_executor_instance
        
        mock_github_instance = Mock()
        mock_github_instance.create_pr_with_auto_title.return_value = (123, "https://github.com/test/pr/123")
        mock_github_instance.token = None  # Skip CI monitoring
        mock_github.return_value = mock_github_instance
        
        mock_backlog_instance = Mock()
        mock_backlog.return_value = mock_backlog_instance
        
        # Mock subprocess.run for git commands
        mock_subprocess.return_value = Mock(returncode=0, stdout="agent/test-task", stderr="")
        
        # Create runner (mocks are already patched)
        runner = LeviathanRunner(
            repo_root=Path("/tmp/test")
        )
        
        # Execute single attempt (simulating the loop)
        task = MockTask()
        success, failure_context = runner._execute_single_attempt(
            task=task,
            workspace_root=Path("/tmp/worktree"),
            use_rewrite_mode=True,
            attempt_number=1,
            retry_context=None
        )
        
        # Should succeed on first attempt
        assert success is True
        assert failure_context == {}
        
        # Model should be called once
        assert mock_model_instance.generate_implementation_rewrite_mode.call_count == 1
        
        # Tests should be run once
        assert mock_executor_instance.run_test_suite.call_count == 1
    
    @patch('leviathan.runner.subprocess.run')
    @patch('leviathan.runner.CommandExecutor')
    @patch('leviathan.runner.ModelClient')
    @patch('leviathan.runner.GitHubClient')
    @patch('leviathan.runner.Backlog')
    def test_success_on_second_attempt(self, mock_backlog, mock_github, mock_model, mock_executor, mock_subprocess):
        """Task fails first attempt, succeeds on second with retry feedback."""
        # Setup mocks
        mock_model_instance = Mock()
        mock_model_instance.repo_root = Path("/tmp/test")
        mock_model_instance.generate_implementation_rewrite_mode.return_value = (["test.py"], "claude_api")
        mock_model.return_value = mock_model_instance
        
        # First attempt: tests fail, second attempt: tests pass
        mock_executor_instance = Mock()
        mock_executor_instance.run_test_suite.side_effect = [
            (False, "FAILED test.py::test_example - AssertionError"),
            (True, "All tests passed")
        ]
        mock_executor_instance.run_command.return_value = Mock(returncode=0, stdout="M test.py", stderr="")
        mock_executor.return_value = mock_executor_instance
        
        mock_github_instance = Mock()
        mock_github_instance.create_pr_with_auto_title.return_value = (123, "https://github.com/test/pr/123")
        mock_github_instance.token = None
        mock_github.return_value = mock_github_instance
        
        mock_backlog_instance = Mock()
        mock_backlog.return_value = mock_backlog_instance
        
        # Mock subprocess.run for git commands
        mock_subprocess.return_value = Mock(returncode=0, stdout="agent/test-task", stderr="")
        
        # Create runner (mocks are already patched)
        runner = LeviathanRunner(
            repo_root=Path("/tmp/test")
        )
        
        # Attempt 1: Should fail with test failure
        task = MockTask()
        success1, failure_context1 = runner._execute_single_attempt(
            task=task,
            workspace_root=Path("/tmp/worktree"),
            use_rewrite_mode=True,
            attempt_number=1,
            retry_context=None
        )
        
        assert success1 is False
        assert failure_context1['failure_type'] == 'test_failure'
        assert 'AssertionError' in failure_context1['test_output']
        
        # Attempt 2: Should succeed with retry context
        success2, failure_context2 = runner._execute_single_attempt(
            task=task,
            workspace_root=Path("/tmp/worktree"),
            use_rewrite_mode=True,
            attempt_number=2,
            retry_context=failure_context1
        )
        
        assert success2 is True
        assert failure_context2 == {}
        
        # Model should be called twice (once per attempt)
        assert mock_model_instance.generate_implementation_rewrite_mode.call_count == 2
        
        # Second call should include retry_context
        second_call_kwargs = mock_model_instance.generate_implementation_rewrite_mode.call_args_list[1][1]
        assert second_call_kwargs['retry_context'] == failure_context1
    
    @patch('leviathan.runner.subprocess.run')
    @patch('leviathan.runner.CommandExecutor')
    @patch('leviathan.runner.ModelClient')
    @patch('leviathan.runner.GitHubClient')
    @patch('leviathan.runner.Backlog')
    def test_max_attempts_exhausted(self, mock_backlog, mock_github, mock_model, mock_executor, mock_subprocess):
        """Task fails all attempts - should stop after max_attempts."""
        # Setup mocks
        mock_model_instance = Mock()
        mock_model_instance.repo_root = Path("/tmp/test")
        mock_model_instance.generate_implementation_rewrite_mode.return_value = (["test.py"], "claude_api")
        mock_model.return_value = mock_model_instance
        
        # All attempts fail
        mock_executor_instance = Mock()
        mock_executor_instance.run_test_suite.return_value = (False, "FAILED test.py::test_example")
        mock_executor_instance.run_command.return_value = Mock(returncode=0, stdout="M test.py", stderr="")
        mock_executor.return_value = mock_executor_instance
        
        mock_backlog_instance = Mock()
        mock_backlog.return_value = mock_backlog_instance
        
        # Mock subprocess.run for git commands
        mock_subprocess.return_value = Mock(returncode=0, stdout="agent/test-task", stderr="")
        
        # Create runner (mocks are already patched)
        runner = LeviathanRunner(
            repo_root=Path("/tmp/test")
        )
        
        # Execute all 3 attempts
        task = MockTask()
        last_failure = None
        
        for attempt in range(1, 4):
            success, failure_context = runner._execute_single_attempt(
                task=task,
                workspace_root=Path("/tmp/worktree"),
                use_rewrite_mode=True,
                attempt_number=attempt,
                retry_context=last_failure
            )
            assert success is False
            assert failure_context['failure_type'] == 'test_failure'
            last_failure = failure_context
        
        # Model should be called 3 times
        assert mock_model_instance.generate_implementation_rewrite_mode.call_count == 3


class TestRetryPrompt:
    """Test that retry prompts include test output and file contents."""
    
    def test_retry_context_includes_test_output(self):
        """Verify retry context contains test output."""
        from leviathan.rewrite_mode import create_rewrite_prompt
        
        task = MockTask()
        existing_files = {"test.py": "def test(): pass"}
        retry_context = {
            'failure_type': 'test_failure',
            'test_output': 'FAILED test.py::test_example\nAssertionError: expected 42, got 0'
        }
        
        prompt = create_rewrite_prompt(task, existing_files, retry_context=retry_context)
        
        # Should include failure type
        assert 'test_failure' in prompt
        
        # Should include test output
        assert 'FAILED test.py::test_example' in prompt
        assert 'AssertionError' in prompt
        
        # Should include retry warning
        assert 'RETRY ATTEMPT' in prompt
        assert 'PREVIOUS IMPLEMENTATION FAILED' in prompt
    
    def test_retry_context_includes_file_contents(self):
        """Verify retry context shows current file contents."""
        from leviathan.rewrite_mode import create_rewrite_prompt
        
        task = MockTask()
        existing_files = {
            "test.py": "def broken_test():\n    assert False",
            "test.json": '{"key": "value"}'
        }
        retry_context = {
            'failure_type': 'test_failure',
            'test_output': 'Tests failed'
        }
        
        prompt = create_rewrite_prompt(task, existing_files, retry_context=retry_context)
        
        # Should include current file contents in retry section
        assert 'CURRENT FILE CONTENTS (after previous attempt)' in prompt
        assert 'def broken_test()' in prompt
        assert 'assert False' in prompt
    
    def test_retry_context_truncates_long_output(self):
        """Verify long test output is truncated to last 200 lines."""
        from leviathan.rewrite_mode import create_rewrite_prompt
        
        task = MockTask()
        existing_files = {"test.py": "pass"}
        
        # Create test output with 300 lines
        long_output = '\n'.join([f"Line {i}" for i in range(300)])
        retry_context = {
            'failure_type': 'test_failure',
            'test_output': long_output
        }
        
        prompt = create_rewrite_prompt(task, existing_files, retry_context=retry_context)
        
        # Should include truncation notice
        assert 'truncated to last 200 lines' in prompt
        
        # Should include last lines
        assert 'Line 299' in prompt
        
        # Should not include early lines
        assert 'Line 50' not in prompt
