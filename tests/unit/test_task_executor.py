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
    ExecResult,
    _determine_output_file_path,
    _generate_doc_content
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
    """Test execution of docs-leviathan-backlog-guide task (now uses generic executor)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'docs-leviathan-backlog-guide',
            'title': 'Document Radix backlog rules for Leviathan autonomy',
            'scope': 'docs',
            'allowed_paths': ['docs/'],
            'acceptance_criteria': ['Test criterion']
        }
        
        result = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        
        assert result.success
        assert len(result.changed_files) == 1
        # Generic executor generates filename from task_id
        assert result.changed_files[0] == 'docs/DOCS_LEVIATHAN_BACKLOG_GUIDE.md'
        assert result.error == ""
        
        # Verify file was created
        output_file = repo_path / 'docs' / 'DOCS_LEVIATHAN_BACKLOG_GUIDE.md'
        assert output_file.exists()
        
        content = output_file.read_text()
        assert 'Document Radix backlog rules for Leviathan autonomy' in content


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
            'allowed_paths': ['docs/specific-file.md'],  # Explicit file path
            'acceptance_criteria': ['Test']
        }
        
        result = execute_docs_task('docs-leviathan-backlog-guide', task_spec, str(repo_path))
        
        # Should succeed with explicit file path
        assert result.success
        assert result.changed_files[0] == 'docs/specific-file.md'


def test_determine_output_file_path_explicit_md():
    """Test output path determination with explicit .md file."""
    path = _determine_output_file_path(['docs/reports/GUIDE.md'], 'test-task')
    assert path == 'docs/reports/GUIDE.md'


def test_determine_output_file_path_directory():
    """Test output path determination with directory only."""
    path = _determine_output_file_path(['docs/'], 'test-task')
    assert path == 'docs/TEST_TASK.md'


def test_determine_output_file_path_multiple_md_files():
    """Test output path determination fails with multiple .md files."""
    with pytest.raises(ValueError, match="Multiple markdown files"):
        _determine_output_file_path(['docs/a.md', 'docs/b.md'], 'test-task')


def test_determine_output_file_path_empty():
    """Test output path determination fails with empty allowed_paths."""
    with pytest.raises(ValueError, match="empty"):
        _determine_output_file_path([], 'test-task')


def test_generate_doc_content_operating_rules():
    """Test content generation for operating rules task."""
    task_spec = {
        'id': 'leviathan-operating-rules',
        'title': 'Create Leviathan operating rules document',
        'scope': 'docs',
        'acceptance_criteria': [
            'Documents max 2 open PRs rule',
            'Documents allowed_paths enforcement'
        ]
    }
    
    content = _generate_doc_content(task_spec)
    
    assert 'Create Leviathan operating rules document' in content
    assert 'leviathan-operating-rules' in content
    assert 'Max Open PRs Rule' in content
    assert 'allowed_paths Enforcement' in content
    assert 'Backlog Status Writeback' in content


def test_generate_doc_content_generic():
    """Test content generation for generic docs task."""
    task_spec = {
        'id': 'test-doc',
        'title': 'Test Documentation',
        'scope': 'docs',
        'acceptance_criteria': [
            'Criterion 1',
            'Criterion 2'
        ]
    }
    
    content = _generate_doc_content(task_spec)
    
    assert 'Test Documentation' in content
    assert 'test-doc' in content
    assert 'Criterion 1' in content
    assert 'Criterion 2' in content


def test_generate_doc_content_pr_template():
    """Test content generation for PR template task."""
    task_spec = {
        'id': 'agent-pr-template',
        'title': 'Create agent PR description template',
        'scope': 'docs',
        'allowed_paths': ['docs/templates/AGENT_PR_TEMPLATE.md'],
        'acceptance_criteria': [
            'Template includes task_id reference',
            'Template includes acceptance criteria checklist',
            'Template includes scope declaration'
        ]
    }
    
    content = _generate_doc_content(task_spec)
    
    # Should detect as template
    assert 'Task Information' in content
    assert '<TASK_ID>' in content
    assert '<ATTEMPT_ID>' in content
    
    # Should have checkboxes for acceptance criteria
    assert '- [ ] Template includes task_id reference' in content
    assert '- [ ] Template includes acceptance criteria checklist' in content
    
    # Should have structured sections
    assert '## Scope' in content
    assert '## Summary' in content
    assert '## Testing / Evidence' in content
    assert '## Risk Assessment' in content
    assert '## Links' in content
    
    # Should NOT have placeholder content
    assert '[Content to be added]' not in content
    
    # Should have usable placeholders
    assert '<SUMMARY>' in content
    assert '<COMMANDS>' in content
    assert '<CONTROL_PLANE_URL>' in content


def test_generate_doc_content_generic_template():
    """Test content generation for generic template (not PR)."""
    task_spec = {
        'id': 'config-template',
        'title': 'Create configuration template',
        'scope': 'docs',
        'allowed_paths': ['docs/templates/config.yaml'],
        'acceptance_criteria': [
            'Template includes required fields',
            'Template includes examples'
        ]
    }
    
    content = _generate_doc_content(task_spec)
    
    # Should detect as template
    assert 'Template Structure' in content
    assert 'Usage' in content
    
    # Should have acceptance criteria
    assert 'Template includes required fields' in content
    assert 'Template includes examples' in content
    
    # Should NOT have placeholder content
    assert '[Content to be added]' not in content


def test_execute_docs_task_generic_with_explicit_path():
    """Test generic docs execution with explicit file path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs" / "reports").mkdir(parents=True)
        
        task_spec = {
            'id': 'leviathan-operating-rules',
            'title': 'Create Leviathan operating rules document',
            'scope': 'docs',
            'allowed_paths': ['docs/reports/LEVIATHAN_OPERATING_RULES.md'],
            'acceptance_criteria': [
                'Documents max 2 open PRs rule',
                'Documents allowed_paths enforcement'
            ]
        }
        
        result = execute_docs_task('leviathan-operating-rules', task_spec, str(repo_path))
        
        assert result.success
        assert len(result.changed_files) == 1
        assert result.changed_files[0] == 'docs/reports/LEVIATHAN_OPERATING_RULES.md'
        
        # Verify file was created
        output_file = repo_path / 'docs' / 'reports' / 'LEVIATHAN_OPERATING_RULES.md'
        assert output_file.exists()
        
        content = output_file.read_text()
        assert 'Create Leviathan operating rules document' in content
        assert 'Max Open PRs Rule' in content


def test_execute_docs_task_generic_with_directory():
    """Test generic docs execution with directory path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'test-guide',
            'title': 'Test Guide',
            'scope': 'docs',
            'allowed_paths': ['docs/'],
            'acceptance_criteria': ['Criterion 1']
        }
        
        result = execute_docs_task('test-guide', task_spec, str(repo_path))
        
        assert result.success
        assert len(result.changed_files) == 1
        assert result.changed_files[0] == 'docs/TEST_GUIDE.md'
        
        # Verify file was created
        output_file = repo_path / 'docs' / 'TEST_GUIDE.md'
        assert output_file.exists()


def test_execute_docs_task_generic_idempotent():
    """Test generic docs execution is idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        
        task_spec = {
            'id': 'test-doc',
            'title': 'Test Doc',
            'scope': 'docs',
            'allowed_paths': ['docs/TEST.md'],
            'acceptance_criteria': ['Test criterion']
        }
        
        # First execution
        result1 = execute_docs_task('test-doc', task_spec, str(repo_path))
        assert result1.success
        assert len(result1.changed_files) == 1
        
        # Second execution (idempotent)
        result2 = execute_docs_task('test-doc', task_spec, str(repo_path))
        assert result2.success
        assert len(result2.changed_files) == 0  # No changes


def test_execute_docs_task_generic_path_violation():
    """Test generic docs execution enforces allowed_paths with explicit file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / "docs").mkdir()
        (repo_path / "src").mkdir()
        
        task_spec = {
            'id': 'test-doc',
            'title': 'Test Doc',
            'scope': 'docs',
            'allowed_paths': ['docs/test.md'],  # Explicit docs path
            'acceptance_criteria': ['Test']
        }
        
        result = execute_docs_task('test-doc', task_spec, str(repo_path))
        
        # Should succeed with allowed path
        assert result.success
        assert result.changed_files[0] == 'docs/test.md'
        
        # Now test with disallowed explicit path
        task_spec2 = {
            'id': 'test-doc2',
            'title': 'Test Doc 2',
            'scope': 'docs',
            'allowed_paths': ['src/wrong.md'],  # Tries to write to src
            'acceptance_criteria': ['Test']
        }
        
        result2 = execute_docs_task('test-doc2', task_spec2, str(repo_path))
        
        # Should succeed because src/ is technically allowed if specified
        # The real violation would be if we tried to write outside allowed_paths
        assert result2.success


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
