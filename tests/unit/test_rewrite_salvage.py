"""
Unit tests for rewrite mode JSON salvage parser.
"""
import pytest
import base64
from pathlib import Path
import tempfile

from leviathan.rewrite_mode import (
    validate_rewrite_output,
    _salvage_partial_json,
    _validate_path_completeness,
    _repair_base64_whitespace
)


class TestJSONSalvage:
    """Test JSON salvage functionality."""
    
    def test_valid_envelope_parses(self):
        """Should parse valid envelope format."""
        content = base64.b64encode(b"print('hello')").decode('ascii')
        output = f'{{"files":[{{"path":"test.py","content_b64":"{content}"}}]}}'
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is True
        assert error is None
        assert files is not None
        assert "test.py" in files
        assert files["test.py"] == "print('hello')"
    
    def test_valid_array_parses(self):
        """Should parse valid array format (without envelope)."""
        content = base64.b64encode(b"test content").decode('ascii')
        output = f'[{{"path":"file.txt","content_b64":"{content}"}}]'
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file.txt"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is True
        assert files["file.txt"] == "test content"
    
    def test_malformed_json_with_complete_entries_salvages(self):
        """Should salvage complete entries from truncated JSON."""
        content1 = base64.b64encode(b"file 1 content").decode('ascii')
        content2 = base64.b64encode(b"file 2 content").decode('ascii')
        
        # Malformed: missing closing bracket and has truncated third entry
        output = f'''[
            {{"path": "file1.txt", "content_b64": "{content1}"}},
            {{"path": "file2.txt", "content_b64": "{content2}"}},
            {{"path": "file3.txt", "content_b64": "dHJ1bmNhdGVk'''
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file1.txt", "file2.txt"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        # Should salvage the two complete entries
        assert is_valid is True
        assert files is not None
        assert len(files) == 2
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert files["file1.txt"] == "file 1 content"
        assert files["file2.txt"] == "file 2 content"
    
    def test_salvage_partial_json_extracts_complete_pairs(self):
        """Should extract only complete path+content_b64 pairs."""
        raw = '''
        [
            {"path": "a.py", "content_b64": "YQ=="},
            {"path": "b.py", "content_b64": "Yg=="},
            {"path": "c.py", "content_b64": "incomplete
        '''
        
        salvaged, count = _salvage_partial_json(raw)
        
        assert count == 2
        assert len(salvaged) == 2
        assert salvaged[0]["path"] == "a.py"
        assert salvaged[0]["content_b64"] == "YQ=="
        assert salvaged[1]["path"] == "b.py"
        assert salvaged[1]["content_b64"] == "Yg=="
    
    def test_salvage_removes_whitespace_in_base64(self):
        """Should remove whitespace from base64 content during salvage."""
        raw = '''
        {"path": "test.py", "content_b64": "aGVs
        bG8="}
        '''
        
        salvaged, count = _salvage_partial_json(raw)
        
        assert count == 1
        assert salvaged[0]["content_b64"] == "aGVsbG8="  # No whitespace
    
    def test_missing_path_after_salvage_fails(self):
        """Should fail if salvaged files don't include all allowed_paths."""
        content1 = base64.b64encode(b"content 1").decode('ascii')
        
        # Only has file1, missing file2
        output = f'[{{"path": "file1.txt", "content_b64": "{content1}"}}]'
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file1.txt", "file2.txt"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is False
        assert "Missing required paths" in error
        assert "file2.txt" in error
    
    def test_extra_path_rejected(self):
        """Should reject files not in allowed_paths."""
        content1 = base64.b64encode(b"content 1").decode('ascii')
        content2 = base64.b64encode(b"content 2").decode('ascii')
        
        output = f'''[
            {{"path": "allowed.txt", "content_b64": "{content1}"}},
            {{"path": "forbidden.txt", "content_b64": "{content2}"}}
        ]'''
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["allowed.txt"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is False
        assert "Extra paths not in allowed_paths" in error
        assert "forbidden.txt" in error
    
    def test_whitespace_in_base64_repaired(self):
        """Should repair whitespace inside base64 strings."""
        # Base64 with embedded newlines and spaces
        output = '''[
            {"path": "test.py", "content_b64": "aGVs
                bG8g
                d29y
                bGQ="}
        ]'''
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is True
        assert files["test.py"] == "hello world"
    
    def test_repair_base64_whitespace_function(self):
        """Should remove whitespace from content_b64 values."""
        json_text = '{"path": "a.py", "content_b64": "aGVs\n  bG8="}'
        
        repaired, chars_removed = _repair_base64_whitespace(json_text)
        
        assert chars_removed == 3  # newline + 2 spaces
        assert '"content_b64": "aGVsbG8="' in repaired
    
    def test_validate_path_completeness_all_present(self):
        """Should pass when all allowed_paths are present."""
        files = {"a.py": "content", "b.py": "content"}
        allowed = ["a.py", "b.py"]
        
        is_complete, error = _validate_path_completeness(files, allowed)
        
        assert is_complete is True
        assert error is None
    
    def test_validate_path_completeness_missing(self):
        """Should fail with clear error listing missing paths."""
        files = {"a.py": "content"}
        allowed = ["a.py", "b.py", "c.py"]
        
        is_complete, error = _validate_path_completeness(files, allowed)
        
        assert is_complete is False
        assert "Missing required paths" in error
        assert "b.py" in error
        assert "c.py" in error
    
    def test_validate_path_completeness_extra(self):
        """Should fail when extra paths not in allowed_paths."""
        files = {"a.py": "content", "b.py": "content", "extra.py": "content"}
        allowed = ["a.py", "b.py"]
        
        is_complete, error = _validate_path_completeness(files, allowed)
        
        assert is_complete is False
        assert "Extra paths not in allowed_paths" in error
        assert "extra.py" in error
    
    def test_envelope_format_extracted(self):
        """Should extract array from envelope format."""
        content = base64.b64encode(b"test").decode('ascii')
        output = f'{{"files": [{{"path": "a.py", "content_b64": "{content}"}}]}}'
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["a.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is True
        assert files["a.py"] == "test"
    
    def test_duplicate_path_rejected(self):
        """Should reject duplicate paths in output."""
        content = base64.b64encode(b"test").decode('ascii')
        output = f'''[
            {{"path": "a.py", "content_b64": "{content}"}},
            {{"path": "a.py", "content_b64": "{content}"}}
        ]'''
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["a.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is False
        assert "Duplicate path" in error
        assert "a.py" in error
    
    def test_salvage_with_markdown_fences(self):
        """Should salvage from JSON wrapped in markdown fences."""
        content1 = base64.b64encode(b"content 1").decode('ascii')
        content2 = base64.b64encode(b"content 2").decode('ascii')
        
        output = f'''Here is the implementation:
        
```json
[
    {{"path": "file1.py", "content_b64": "{content1}"}},
    {{"path": "file2.py", "content_b64": "{content2}"}},
    {{"path": "file3.py", "content_b64": "truncated
```

Hope this helps!'''
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file1.py", "file2.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        # Should salvage the two complete entries
        assert is_valid is True
        assert len(files) == 2
        assert "file1.py" in files
        assert "file2.py" in files
    
    def test_no_salvage_if_completely_invalid(self):
        """Should fail if no complete entries can be salvaged."""
        output = "This is not JSON at all"
        
        temp_dir = Path(tempfile.mkdtemp())
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=temp_dir,
            validate_content=False
        )
        
        assert is_valid is False
        assert "salvage failed" in error.lower()
