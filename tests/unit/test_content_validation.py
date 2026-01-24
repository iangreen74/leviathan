"""
Unit tests for content validation module.
"""
import pytest
from leviathan.content_validation import (
    validate_python_syntax,
    validate_json_syntax,
    validate_yaml_syntax,
    validate_file_content
)


class TestPythonValidation:
    """Test Python syntax validation."""
    
    def test_valid_python(self):
        """Valid Python code should pass."""
        code = """
import os

def hello():
    print("Hello, world!")
"""
        is_valid, error = validate_python_syntax(code, "test.py")
        assert is_valid is True
        assert error is None
    
    def test_invalid_python_literal_backslash_n(self):
        """Python with literal \\n outside strings should fail."""
        code = r"""
data = {\n
    "key": "value"\n
}
"""
        is_valid, error = validate_python_syntax(code, "test.py")
        assert is_valid is False
        assert error is not None
        assert "syntax error" in error.lower() or "unexpected character" in error.lower()
    
    def test_invalid_python_syntax_error(self):
        """Python with syntax errors should fail."""
        code = """
def broken(
    print("missing closing paren")
"""
        is_valid, error = validate_python_syntax(code, "test.py")
        assert is_valid is False
        assert error is not None
    
    def test_valid_python_with_strings(self):
        """Python with newlines in strings should pass."""
        code = """
text = "Line 1\\nLine 2"
data = {"key": "value"}
"""
        is_valid, error = validate_python_syntax(code, "test.py")
        assert is_valid is True
        assert error is None


class TestJSONValidation:
    """Test JSON syntax validation."""
    
    def test_valid_json(self):
        """Valid JSON should pass."""
        content = '{"key": "value", "number": 42}'
        is_valid, error = validate_json_syntax(content, "test.json")
        assert is_valid is True
        assert error is None
    
    def test_invalid_json_trailing_comma(self):
        """JSON with trailing comma should fail."""
        content = '{"key": "value",}'
        is_valid, error = validate_json_syntax(content, "test.json")
        assert is_valid is False
        assert error is not None
    
    def test_invalid_json_syntax(self):
        """Malformed JSON should fail."""
        content = '{"key": "value"'
        is_valid, error = validate_json_syntax(content, "test.json")
        assert is_valid is False
        assert error is not None
    
    def test_valid_json_array(self):
        """Valid JSON array should pass."""
        content = '[1, 2, 3, "test"]'
        is_valid, error = validate_json_syntax(content, "test.json")
        assert is_valid is True
        assert error is None


class TestYAMLValidation:
    """Test YAML syntax validation."""
    
    def test_valid_yaml(self):
        """Valid YAML should pass."""
        content = """
name: test
value: 42
items:
  - one
  - two
"""
        is_valid, error = validate_yaml_syntax(content, "test.yaml")
        assert is_valid is True
        assert error is None
    
    def test_invalid_yaml_indentation(self):
        """YAML with bad indentation should fail."""
        content = """
name: test
  bad_indent: value
"""
        is_valid, error = validate_yaml_syntax(content, "test.yaml")
        assert is_valid is False
        assert error is not None
    
    def test_valid_yaml_multiline(self):
        """YAML with multiline strings should pass."""
        content = """
description: |
  This is a
  multiline string
"""
        is_valid, error = validate_yaml_syntax(content, "test.yaml")
        assert is_valid is True
        assert error is None


class TestFileContentValidation:
    """Test file content validation dispatcher."""
    
    def test_python_file_validation(self):
        """Python files should be validated."""
        code = "import os\nprint('test')"
        is_valid, error = validate_file_content("test.py", code)
        assert is_valid is True
        assert error is None
    
    def test_json_file_validation(self):
        """JSON files should be validated."""
        content = '{"key": "value"}'
        is_valid, error = validate_file_content("test.json", content)
        assert is_valid is True
        assert error is None
    
    def test_yaml_file_validation(self):
        """YAML files should be validated."""
        content = "key: value"
        is_valid, error = validate_file_content("test.yaml", content)
        assert is_valid is True
        assert error is None
    
    def test_yml_extension(self):
        """Files with .yml extension should be validated as YAML."""
        content = "key: value"
        is_valid, error = validate_file_content("test.yml", content)
        assert is_valid is True
        assert error is None
    
    def test_unknown_file_type_passes(self):
        """Unknown file types should pass without validation."""
        content = "any content here"
        is_valid, error = validate_file_content("test.txt", content)
        assert is_valid is True
        assert error is None
    
    def test_invalid_python_file(self):
        """Invalid Python files should fail."""
        code = "def broken("
        is_valid, error = validate_file_content("test.py", code)
        assert is_valid is False
        assert error is not None
