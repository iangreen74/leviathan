"""
Content validation for Leviathan rewrite mode.

Validates file contents BEFORE writing to disk to prevent syntax errors.
"""
import json
import yaml
from pathlib import Path
from typing import Tuple, Optional


class ContentValidationError(Exception):
    """Raised when file content validation fails."""
    pass


def validate_python_syntax(content: str, file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Python syntax by compiling the code.
    
    Args:
        content: Python source code
        file_path: Path for error reporting
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        compile(content, file_path, "exec")
        return True, None
    except SyntaxError as e:
        error_msg = f"Python syntax error in {file_path} at line {e.lineno}: {e.msg}"
        if e.text:
            error_msg += f"\n  {e.text.rstrip()}"
            if e.offset:
                error_msg += f"\n  {' ' * (e.offset - 1)}^"
        return False, error_msg
    except Exception as e:
        return False, f"Python compilation error in {file_path}: {str(e)}"


def validate_json_syntax(content: str, file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate JSON syntax.
    
    Args:
        content: JSON content
        file_path: Path for error reporting
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        json.loads(content)
        return True, None
    except json.JSONDecodeError as e:
        return False, f"JSON syntax error in {file_path} at line {e.lineno}, col {e.colno}: {e.msg}"
    except Exception as e:
        return False, f"JSON parsing error in {file_path}: {str(e)}"


def validate_yaml_syntax(content: str, file_path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate YAML syntax.
    
    Args:
        content: YAML content
        file_path: Path for error reporting
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        yaml.safe_load(content)
        return True, None
    except yaml.YAMLError as e:
        error_msg = f"YAML syntax error in {file_path}"
        if hasattr(e, 'problem_mark'):
            mark = e.problem_mark
            error_msg += f" at line {mark.line + 1}, col {mark.column + 1}"
        if hasattr(e, 'problem'):
            error_msg += f": {e.problem}"
        return False, error_msg
    except Exception as e:
        return False, f"YAML parsing error in {file_path}: {str(e)}"


def validate_file_content(file_path: str, content: str) -> Tuple[bool, Optional[str]]:
    """
    Validate file content based on file extension.
    
    Args:
        file_path: Path to file (used for extension detection and error reporting)
        content: File content to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == '.py':
        return validate_python_syntax(content, file_path)
    elif suffix == '.json':
        return validate_json_syntax(content, file_path)
    elif suffix in ('.yaml', '.yml'):
        return validate_yaml_syntax(content, file_path)
    else:
        # No validation for other file types
        return True, None
