"""
Rewrite mode for Leviathan - reliable file writing for small tasks.

Instead of generating diffs (which often fail), this mode:
1. Prompts model to return strict JSON array with base64-encoded file contents
2. Validates JSON structure and path constraints
3. Writes files directly

This is more reliable for small tasks (<=5 files).
Base64 encoding prevents JSON parsing failures from special characters in file contents.
"""
import json
import base64
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class RewriteModeError(Exception):
    """Raised when rewrite mode fails validation."""
    pass


def validate_rewrite_output(
    output: str,
    allowed_paths: List[str],
    repo_root: Path
) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
    """
    Validate model output for rewrite mode.
    
    Supports two formats:
    1. New format (preferred): JSON array of {"path": "...", "content_b64": "..."}
    2. Legacy format: JSON object {"path": "raw content"}
    
    Args:
        output: Raw model output (should be JSON)
        allowed_paths: List of allowed file paths
        repo_root: Repository root path
        
    Returns:
        Tuple of (is_valid, error_message, parsed_files)
        - is_valid: True if validation passed
        - error_message: Error description if validation failed
        - parsed_files: Dict mapping file paths to contents (if valid)
    """
    # Try to parse JSON
    try:
        parsed = json.loads(output.strip())
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {str(e)}", None
    
    # Check if it's the new array format
    if isinstance(parsed, list):
        return _validate_array_format(parsed, allowed_paths)
    
    # Check if it's the legacy dict format
    elif isinstance(parsed, dict):
        print("⚠️  Using legacy dict format (consider upgrading to base64 array format)")
        return _validate_dict_format(parsed, allowed_paths)
    
    else:
        return False, f"Expected JSON array or object, got {type(parsed).__name__}", None


def _validate_array_format(
    parsed: list,
    allowed_paths: List[str]
) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
    """
    Validate new base64 array format.
    
    Expected format: [{"path": "file.py", "content_b64": "base64..."}]
    """
    if not parsed:
        return False, "Empty array", None
    
    files = {}
    
    for i, item in enumerate(parsed):
        # Each item must be a dict
        if not isinstance(item, dict):
            return False, f"Item {i} must be object, got {type(item).__name__}", None
        
        # Must have 'path' and 'content_b64'
        if 'path' not in item:
            return False, f"Item {i} missing 'path' field", None
        if 'content_b64' not in item:
            return False, f"Item {i} missing 'content_b64' field", None
        
        path = item['path']
        content_b64 = item['content_b64']
        
        # Both must be strings
        if not isinstance(path, str):
            return False, f"Item {i} 'path' must be string, got {type(path).__name__}", None
        if not isinstance(content_b64, str):
            return False, f"Item {i} 'content_b64' must be string, got {type(content_b64).__name__}", None
        
        # Decode base64
        try:
            content_bytes = base64.b64decode(content_b64)
            content = content_bytes.decode('utf-8')
        except Exception as e:
            return False, f"Item {i} ({path}): base64 decode failed: {str(e)}", None
        
        # Check path is allowed
        allowed = False
        for allowed_path in allowed_paths:
            if path == allowed_path or path.startswith(allowed_path.rstrip('/') + '/'):
                allowed = True
                break
        
        if not allowed:
            return False, f"Path not in allowed_paths: {path}", None
        
        files[path] = content
    
    print(f"✅ Validated base64 array format ({len(files)} file(s))")
    return True, None, files


def _validate_dict_format(
    parsed: dict,
    allowed_paths: List[str]
) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
    """
    Validate legacy dict format (backward compatibility).
    
    Expected format: {"file.py": "raw content"}
    """
    # All keys must be strings (file paths)
    for key in parsed.keys():
        if not isinstance(key, str):
            return False, f"File path must be string, got {type(key).__name__}: {key}", None
    
    # All values must be strings (file contents)
    for path, content in parsed.items():
        if not isinstance(content, str):
            return False, f"File content must be string for {path}, got {type(content).__name__}", None
    
    # All paths must be in allowed_paths
    forbidden_paths = []
    for file_path in parsed.keys():
        allowed = False
        for allowed_path in allowed_paths:
            if file_path == allowed_path or file_path.startswith(allowed_path.rstrip('/') + '/'):
                allowed = True
                break
        
        if not allowed:
            forbidden_paths.append(file_path)
    
    if forbidden_paths:
        return False, f"Paths not in allowed_paths: {', '.join(forbidden_paths)}", None
    
    return True, None, parsed


def write_files(
    files: Dict[str, str],
    repo_root: Path,
    ensure_trailing_newline: bool = True
) -> List[str]:
    """
    Write files to disk.
    
    Args:
        files: Dict mapping file paths to contents
        repo_root: Repository root path
        ensure_trailing_newline: Add trailing newline if missing
        
    Returns:
        List of written file paths
    """
    written_paths = []
    
    for file_path, content in files.items():
        full_path = repo_root / file_path
        
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ensure trailing newline for text files
        if ensure_trailing_newline and content and not content.endswith('\n'):
            content += '\n'
        
        # Write file
        full_path.write_text(content, encoding='utf-8')
        written_paths.append(file_path)
    
    return written_paths


def read_existing_files(
    allowed_paths: List[str],
    repo_root: Path
) -> Dict[str, Optional[str]]:
    """
    Read current contents of allowed files.
    
    Args:
        allowed_paths: List of allowed file paths
        repo_root: Repository root path
        
    Returns:
        Dict mapping file paths to contents (None if file doesn't exist)
    """
    existing_files = {}
    
    for file_path in allowed_paths:
        full_path = repo_root / file_path
        
        if full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding='utf-8')
                existing_files[file_path] = content
            except Exception as e:
                # If we can't read it, mark as None
                existing_files[file_path] = None
        else:
            existing_files[file_path] = None
    
    return existing_files


def create_rewrite_prompt(
    task,
    existing_files: Dict[str, Optional[str]]
) -> str:
    """
    Create prompt for rewrite mode.
    
    Args:
        task: Task object with id, title, scope, etc.
        existing_files: Dict of current file contents
        
    Returns:
        Prompt string for model
    """
    # Build file context section
    file_contexts = []
    for file_path, content in existing_files.items():
        if content is None:
            file_contexts.append(f"""=== FILE: {file_path} (does not exist yet) ===
[File will be created]
=== END FILE ===
""")
        else:
            file_contexts.append(f"""=== FILE: {file_path} (current content) ===
{content}=== END FILE ===
""")
    
    prompt = f"""You are implementing a task from the Leviathan agent backlog.

TASK DETAILS:
ID: {task.id}
Title: {task.title}
Scope: {task.scope}
Priority: {task.priority}
Size: {task.estimated_size}

ALLOWED PATHS (you may ONLY modify these files):
{chr(10).join(f'- {path}' for path in task.allowed_paths)}

ACCEPTANCE CRITERIA (all must be satisfied):
{chr(10).join(f'{i}. {criterion}' for i, criterion in enumerate(task.acceptance_criteria, 1))}

CURRENT FILE CONTENTS:
{chr(10).join(file_contexts)}

HARD CONSTRAINTS:
1. Only modify files within the allowed paths listed above
2. No infrastructure mutations (no terraform apply, aws create/update/delete, etc)
3. Follow the scope constraints ({task.scope})
4. Write clean, tested, documented code
5. Ensure all acceptance criteria are met

OUTPUT FORMAT - CRITICAL:
You MUST output ONLY a JSON array where each element has:
- "path": file path (must be from allowed_paths above)
- "content_b64": base64-encoded COMPLETE file contents

RULES:
- NO markdown code fences (no ```)
- NO explanatory text before or after the JSON
- NO comments
- Include ALL files that need to be written (even if only slightly modified)
- Use base64 encoding to avoid JSON escaping issues

Example (output ONLY this format, nothing else):
[
  {{"path": "path/to/file1.py", "content_b64": "aW1wb3J0IG9zCgpkZWYgbWFpbigpOgogICAgcGFzcwo="}},
  {{"path": "path/to/file2.json", "content_b64": "eyJrZXkiOiAidmFsdWUifQo="}}
]

Generate the implementation now as pure JSON array with base64-encoded contents:"""
    
    return prompt
