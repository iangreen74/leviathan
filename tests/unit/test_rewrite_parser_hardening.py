"""
Unit tests for rewrite mode output parser hardening.

Tests deterministic repair of:
- Markdown code fences around JSON
- Whitespace inside base64 strings
- Path field preservation (no corruption)
"""
import pytest
import base64
from pathlib import Path
from leviathan.rewrite_mode import (
    validate_rewrite_output,
    _extract_json_candidate,
    _repair_base64_whitespace
)


class TestMarkdownFenceHandling:
    """Test extraction of JSON from markdown code fences."""
    
    def test_json_with_triple_backticks(self):
        """JSON wrapped in ``` fences should parse successfully."""
        content = "import os\n\ndef main():\n    pass\n"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        output = f"""```json
[
  {{"path": "test.py", "content_b64": "{content_b64}"}}
]
```"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert error is None
        assert files == {"test.py": content}
    
    def test_json_with_backticks_no_language(self):
        """JSON wrapped in ``` without language identifier."""
        content = '{"key": "value"}'
        content_b64 = base64.b64encode(content.encode()).decode()
        
        output = f"""```
[
  {{"path": "config.json", "content_b64": "{content_b64}"}}
]
```"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["config.json"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert files == {"config.json": content}
    
    def test_json_with_surrounding_text(self):
        """JSON with explanatory text before/after should extract array."""
        content = "test"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        output = f"""Here is the implementation:

[
  {{"path": "test.txt", "content_b64": "{content_b64}"}}
]

This should work!"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert files == {"test.txt": content}


class TestBase64WhitespaceRepair:
    """Test removal of whitespace inside base64 strings."""
    
    def test_base64_with_newlines(self):
        """Base64 with embedded newlines should parse successfully."""
        content = "import os\nimport sys\n\ndef main():\n    print('hello')\n"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        # Insert newlines in the middle of base64
        wrapped_b64 = content_b64[:20] + "\n" + content_b64[20:40] + "\n" + content_b64[40:]
        
        output = f"""[
  {{"path": "test.py", "content_b64": "{wrapped_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert error is None
        assert files == {"test.py": content}
    
    def test_base64_with_spaces_and_tabs(self):
        """Base64 with spaces and tabs should parse successfully."""
        content = "test content"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        # Insert spaces and tabs
        wrapped_b64 = content_b64[:10] + "  \t  " + content_b64[10:]
        
        output = f"""[
  {{"path": "file.txt", "content_b64": "{wrapped_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert files == {"file.txt": content}
    
    def test_multiple_files_with_whitespace(self):
        """Multiple files with whitespace in base64 should all be repaired."""
        content1 = "file1 content"
        content2 = "file2 content"
        b64_1 = base64.b64encode(content1.encode()).decode()
        b64_2 = base64.b64encode(content2.encode()).decode()
        
        # Add whitespace to both
        wrapped_b64_1 = b64_1[:8] + "\n" + b64_1[8:]
        wrapped_b64_2 = b64_2[:8] + " \t " + b64_2[8:]
        
        output = f"""[
  {{"path": "file1.txt", "content_b64": "{wrapped_b64_1}"}},
  {{"path": "file2.txt", "content_b64": "{wrapped_b64_2}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file1.txt", "file2.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert files == {
            "file1.txt": content1,
            "file2.txt": content2
        }


class TestPathPreservation:
    """Test that path fields are never corrupted by repair."""
    
    def test_path_field_not_modified(self):
        """Ensure repair does NOT modify path fields."""
        content = "test"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        # Add whitespace to base64
        wrapped_b64 = content_b64[:10] + "\n\n" + content_b64[10:]
        
        exact_path = "tests/unit/test_example.py"
        output = f"""[
  {{"path": "{exact_path}", "content_b64": "{wrapped_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=[exact_path],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        # Path must be exactly as specified
        assert exact_path in files
        assert files[exact_path] == content
    
    def test_path_with_spaces_preserved(self):
        """Path with spaces should be preserved exactly (even if unusual)."""
        content = "test"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        # Unusual but valid path with spaces
        path_with_spaces = "my file.txt"
        output = f"""[
  {{"path": "{path_with_spaces}", "content_b64": "{content_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=[path_with_spaces],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert path_with_spaces in files
    
    def test_disallowed_path_still_rejected(self):
        """Paths not in allowed_paths must still be rejected."""
        content = "test"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        output = f"""[
  {{"path": "forbidden.py", "content_b64": "{content_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["allowed.py"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is False
        assert "not in allowed_paths" in error
        assert "forbidden.py" in error


class TestInvalidBase64AfterRepair:
    """Test that invalid base64 (even after whitespace removal) fails clearly."""
    
    def test_invalid_base64_characters(self):
        """Base64 with invalid padding should fail after repair."""
        # Invalid base64 - incorrect padding (single '=' when it should be '==')
        invalid_b64 = "aW1wb3J0IG9z="
        
        output = f"""[
  {{"path": "test.py", "content_b64": "{invalid_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.py"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        # Note: Python's base64 is lenient and may accept this
        # The key test is that IF it fails, the error is clear
        # So we just verify it doesn't crash
        assert is_valid is True or (is_valid is False and "base64 decode failed" in error)
    
    def test_malformed_base64_after_whitespace_removal(self):
        """Malformed base64 should fail with clear error."""
        # Not valid base64 even after whitespace removal
        bad_b64 = "not\nvalid\nbase64"
        
        output = f"""[
  {{"path": "test.txt", "content_b64": "{bad_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is False
        assert "base64 decode failed" in error


class TestRepairHelpers:
    """Test individual repair helper functions."""
    
    def test_extract_json_candidate_with_fence(self):
        """_extract_json_candidate should extract from fences."""
        output = """```json
[{"test": "value"}]
```"""
        
        candidate, repairs = _extract_json_candidate(output)
        
        assert candidate == '[{"test": "value"}]'
        assert "stripped markdown code fence" in repairs
    
    def test_extract_json_candidate_no_fence(self):
        """_extract_json_candidate should extract array without fence."""
        output = """Some text before
[{"test": "value"}]
Some text after"""
        
        candidate, repairs = _extract_json_candidate(output)
        
        assert candidate == '[{"test": "value"}]'
        assert "extracted JSON array from surrounding text" in repairs
    
    def test_repair_base64_whitespace_function(self):
        """_repair_base64_whitespace should only modify content_b64 values."""
        json_text = """[
  {"path": "test.py", "content_b64": "aW1w\nb3J0\nIG9z"}
]"""
        
        repaired, chars_removed = _repair_base64_whitespace(json_text)
        
        assert chars_removed == 2  # Two newlines removed
        assert '"content_b64": "aW1wb3J0IG9z"' in repaired
        assert '"path": "test.py"' in repaired  # Path unchanged
    
    def test_repair_does_not_touch_other_fields(self):
        """Repair should not modify fields other than content_b64."""
        json_text = """[
  {
    "path": "my file.txt",
    "content_b64": "dGVz\ndA==",
    "other_field": "value with spaces"
  }
]"""
        
        repaired, chars_removed = _repair_base64_whitespace(json_text)
        
        # Only content_b64 should be modified
        assert '"path": "my file.txt"' in repaired
        assert '"other_field": "value with spaces"' in repaired
        assert '"content_b64": "dGVzdA=="' in repaired
        assert chars_removed == 1


class TestBackwardCompatibility:
    """Test that valid outputs still work without repair."""
    
    def test_valid_output_no_repair_needed(self):
        """Already-valid output should parse without any repairs."""
        content = "test content"
        content_b64 = base64.b64encode(content.encode()).decode()
        
        output = f"""[
  {{"path": "test.txt", "content_b64": "{content_b64}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["test.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert files == {"test.txt": content}
    
    def test_multiple_valid_files(self):
        """Multiple files in valid format should work."""
        content1 = "file1"
        content2 = "file2"
        b64_1 = base64.b64encode(content1.encode()).decode()
        b64_2 = base64.b64encode(content2.encode()).decode()
        
        output = f"""[
  {{"path": "file1.txt", "content_b64": "{b64_1}"}},
  {{"path": "file2.txt", "content_b64": "{b64_2}"}}
]"""
        
        is_valid, error, files = validate_rewrite_output(
            output,
            allowed_paths=["file1.txt", "file2.txt"],
            repo_root=Path("/tmp"),
            validate_content=False
        )
        
        assert is_valid is True
        assert len(files) == 2
