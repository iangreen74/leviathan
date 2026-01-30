"""
Unit tests for task executor.
"""
import pytest
import tempfile
from pathlib import Path

from leviathan.executor.task_exec import (
    execute_task,
    execute_docs_task,
    validate_output_path,
    PathViolationError,
    ExecResult
)


def test_validate_output_path_allowed():
    """Test path validation allows paths within allowed_paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        validate_output_path(
            "docs/test.md",
            ["docs/"],
            tmpdir
        )
        # Should not raise


def test_validate_output_path_denied():
    """Test path validation rejects paths outside allowed_paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(PathViolationError):
            validate_output_path(
                "src/test.py",
                ["docs/"],
                tmpdir
            )


def test_validate_output_path_multiple_allowed():
    """Test path validation with multiple allowed paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Should allow docs/
        validate_output_path("docs/test.md", ["docs/", "tests/"], tmpdir)
        
        # Should allow tests/
        validate_output_path("tests/test.py", ["docs/", "tests/"], tmpdir)
        
        # Should reject src/
        with pytest.raises(PathViolationError):
            validate_output_path("src/test.py", ["docs/", "tests/"], tmpdir)


def test_validate_output_path_outside_repo():
    """Test path validation rejects paths outside repo root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(PathViolationError):
            validate_output_path(
                "../outside.txt",
                ["docs/"],
                tmpdir
            )


def test_execute_docs_task_backlog_guide():
    """Test execution of docs-leviathan-backlog-guide task."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'docs-leviathan-backlog-guide',
            'title': 'Document Radix backlog rules for Leviathan autonomy',
            'scope': 'docs',
            'allowed_paths': ['docs/']
        }
        
        result = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        
        assert result.success
        assert len(result.changed_files) == 1
        assert result.changed_files[0] == 'docs/27_RADIX_BACKLOG_AUTONOMY_GUIDE.md'
        assert result.error == ""
        
        # Verify file was created
        output_file = repo_path / 'docs' / '27_RADIX_BACKLOG_AUTONOMY_GUIDE.md'
        assert output_file.exists()
        
        content = output_file.read_text()
        assert 'Radix Backlog Autonomy Guide' in content
        assert 'allowed_paths' in content
        assert 'Scope Taxonomy' in content


def test_execute_docs_task_idempotent():
    """Test that executing same task twice is idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'docs-leviathan-backlog-guide',
            'title': 'Document Radix backlog rules for Leviathan autonomy',
            'scope': 'docs',
            'allowed_paths': ['docs/']
        }
        
        # First execution
        result1 = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        assert result1.success
        assert len(result1.changed_files) == 1
        
        # Second execution (file already exists with same content)
        result2 = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        assert result2.success
        assert len(result2.changed_files) == 0  # No changes


def test_execute_docs_task_path_violation():
    """Test that docs task respects allowed_paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'docs-leviathan-backlog-guide',
            'title': 'Document Radix backlog rules for Leviathan autonomy',
            'scope': 'docs',
            'allowed_paths': ['src/']  # Wrong path - should fail
        }
        
        result = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        
        assert not result.success
        assert 'outside allowed_paths' in result.error


def test_execute_docs_task_unknown():
    """Test that unknown docs task returns error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        task_spec = {
            'id': 'unknown-docs-task',
            'scope': 'docs',
            'allowed_paths': ['docs/']
        }
        
        result = execute_docs_task('unknown-docs-task', task_spec, str(tmpdir))
        
        assert not result.success
        assert 'No executor implemented' in result.error


def test_execute_task_docs_scope():
    """Test execute_task dispatches to docs executor."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'docs-leviathan-backlog-guide',
            'scope': 'docs',
            'allowed_paths': ['docs/']
        }
        
        result = execute_task(task_spec, str(repo_path))
        
        assert result.success
        assert len(result.changed_files) == 1


def test_execute_task_unknown_scope():
    """Test execute_task raises NotImplementedError for unknown scope."""
    with tempfile.TemporaryDirectory() as tmpdir:
        task_spec = {
            'id': 'test-task',
            'scope': 'unknown-scope',
            'allowed_paths': []
        }
        
        with pytest.raises(NotImplementedError):
            execute_task(task_spec, str(tmpdir))


def test_exec_result_dataclass():
    """Test ExecResult dataclass."""
    result = ExecResult(
        success=True,
        changed_files=['file1.txt', 'file2.txt'],
        error=""
    )
    
    assert result.success
    assert len(result.changed_files) == 2
    assert result.error == ""
    
    result_failed = ExecResult(
        success=False,
        changed_files=[],
        error="Test error"
    )
    
    assert not result_failed.success
    assert len(result_failed.changed_files) == 0
    assert result_failed.error == "Test error"
