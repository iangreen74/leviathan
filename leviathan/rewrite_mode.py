"""
Rewrite mode for Leviathan - reliable file writing for small tasks.

Instead of generating diffs (which often fail), this mode:
1. Prompts model to return strict JSON array with base64-encoded file contents
2. Validates JSON structure and path constraints
3. Validates file content syntax (Python, JSON, YAML)
4. Writes files atomically

This is more reliable for small tasks (<=5 files).
Base64 encoding prevents JSON parsing failures from special characters in file contents.
"""
import json
import base64
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from leviathan.content_validation import validate_file_content, ContentValidationError


class RewriteModeError(Exception):
    """Raised when rewrite mode fails validation."""
    pass


def _extract_json_candidate(raw_output: str) -> Tuple[str, List[str]]:
    """
    Extract JSON candidate from raw output, handling markdown fences.
    
    Returns:
        Tuple of (json_candidate, repairs_applied)
        - json_candidate: Extracted JSON string
        - repairs_applied: List of repair descriptions
    """
    repairs = []
    
    # Strip leading/trailing whitespace
    output = raw_output.strip()
    
    # Check for markdown code fences
    if '```' in output:
        # Extract content between first ``` fence
        fence_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        import re
        match = re.search(fence_pattern, output, re.DOTALL)
        if match:
            output = match.group(1).strip()
            repairs.append("stripped markdown code fence")
        else:
            # Try to extract between any ``` markers
            parts = output.split('```')
            if len(parts) >= 3:
                # Take the content between first pair of ```
                output = parts[1].strip()
                # Remove language identifier if present
                if output.startswith('json\n'):
                    output = output[5:].strip()
                repairs.append("stripped markdown code fence")
    
    # Try to extract strict envelope format first: {"files":[...]}
    if '{"files"' in output or '{\"files\"' in output:
        import re
        # Look for {"files":[...]} pattern
        match = re.search(r'\{\s*"files"\s*:\s*\[(.*?)\]\s*\}', output, re.DOTALL)
        if match:
            # Extract just the array part
            output = '[' + match.group(1) + ']'
            repairs.append("extracted files array from envelope")
    else:
        # Extract from first '[' or '{' to last ']' or '}'
        first_bracket = output.find('[')
        last_bracket = output.rfind(']')
        
        if first_bracket != -1 and last_bracket != -1 and first_bracket < last_bracket:
            output = output[first_bracket:last_bracket + 1]
            if first_bracket > 0 or last_bracket < len(output) - 1:
                repairs.append("extracted JSON array from surrounding text")
    
    return output, repairs


def _repair_base64_whitespace(json_text: str) -> Tuple[str, int]:
    """
    Remove whitespace inside content_b64 values.
    
    This handles cases where base64 strings are wrapped across lines.
    Only modifies content inside "content_b64" values, not paths or other fields.
    
    Returns:
        Tuple of (repaired_json, chars_removed)
    """
    import re
    
    chars_removed = 0
    
    # Pattern to match "content_b64": "..." with non-greedy capture
    # This ensures we only match the value, not spanning multiple objects
    pattern = r'"content_b64"\s*:\s*"([^"]*)"'
    
    def remove_whitespace(match):
        nonlocal chars_removed
        original_value = match.group(1)
        # Remove all whitespace characters (space, tab, newline, carriage return)
        cleaned_value = re.sub(r'[\s\n\r\t]+', '', original_value)
        chars_removed += len(original_value) - len(cleaned_value)
        return f'"content_b64": "{cleaned_value}"'
    
    repaired = re.sub(pattern, remove_whitespace, json_text)
    return repaired, chars_removed


def _salvage_partial_json(raw_text: str) -> Tuple[Optional[list], int]:
    """
    Salvage complete file entries from malformed/truncated JSON.
    
    Scans for complete {"path": "...", "content_b64": "..."} pairs.
    Ignores partial/truncated entries at the end.
    
    Args:
        raw_text: Raw JSON text that failed to parse
        
    Returns:
        Tuple of (salvaged_list, num_salvaged)
        - salvaged_list: List of complete file objects, or None if salvage failed
        - num_salvaged: Number of complete entries salvaged
    """
    import re
    
    # Pattern to match complete file entries with both path and content_b64
    # Must have closing quotes for both fields
    pattern = r'\{\s*"path"\s*:\s*"([^"]+)"\s*,\s*"content_b64"\s*:\s*"([^"]+)"\s*\}'
    
    matches = re.findall(pattern, raw_text, re.DOTALL)
    
    if not matches:
        return None, 0
    
    salvaged = []
    for path, content_b64 in matches:
        # Remove whitespace from content_b64 (common issue)
        content_b64_clean = re.sub(r'[\s\n\r\t]+', '', content_b64)
        salvaged.append({
            "path": path,
            "content_b64": content_b64_clean
        })
    
    return salvaged, len(salvaged)


def validate_rewrite_output(
    output: str,
    allowed_paths: List[str],
    repo_root: Path,
    validate_content: bool = True
) -> Tuple[bool, Optional[str], Optional[Dict[str, str]]]:
    """
    Validate model output for rewrite mode with deterministic repair and salvage.
    
    Supports two formats:
    1. New format (preferred): JSON array of {"path": "...", "content_b64": "..."}
    2. Envelope format: {"files": [{"path": "...", "content_b64": "..."}]}
    3. Legacy format: JSON object {"path": "raw content"}
    
    Handles common LLM output issues:
    - Markdown code fences around JSON
    - Whitespace inside base64 strings
    - Truncated/malformed JSON (salvages complete entries)
    
    Args:
        output: Raw model output (should be JSON)
        allowed_paths: List of allowed file paths
        repo_root: Repository root path
        validate_content: If True, validate file syntax (Python, JSON, YAML)
        
    Returns:
        Tuple of (is_valid, error_message, parsed_files)
        - is_valid: True if validation passed
        - error_message: Error description if validation failed
        - parsed_files: Dict mapping file paths to contents (if valid)
    """
    # Step 1: Extract JSON candidate (handle fences, extract array)
    json_candidate, extraction_repairs = _extract_json_candidate(output)
    
    # Step 2: Try to parse JSON
    parsed = None
    salvaged = False
    
    try:
        parsed = json.loads(json_candidate)
    except json.JSONDecodeError as e:
        # Step 3: Apply base64 whitespace repair and retry
        repaired_json, chars_removed = _repair_base64_whitespace(json_candidate)
        
        if chars_removed > 0:
            try:
                parsed = json.loads(repaired_json)
                print(f"🔧 rewrite_mode: repaired base64 whitespace; removed {chars_removed} chars")
            except json.JSONDecodeError as e2:
                # Step 4: Attempt salvage of complete entries
                salvaged_list, num_salvaged = _salvage_partial_json(repaired_json)
                if salvaged_list and num_salvaged > 0:
                    parsed = salvaged_list
                    salvaged = True
                    print(f"🔧 rewrite_mode: salvaged {num_salvaged} complete file entries from malformed JSON")
                else:
                    return False, f"Invalid JSON and salvage failed: {str(e2)}", None
        else:
            # Try salvage without whitespace repair
            salvaged_list, num_salvaged = _salvage_partial_json(json_candidate)
            if salvaged_list and num_salvaged > 0:
                parsed = salvaged_list
                salvaged = True
                print(f"🔧 rewrite_mode: salvaged {num_salvaged} complete file entries from malformed JSON")
            else:
                return False, f"Invalid JSON and salvage failed: {str(e)}", None
    
    # Log extraction repairs if any were applied
    if extraction_repairs:
        print(f"🔧 rewrite_mode: applied repairs: {', '.join(extraction_repairs)}")
    
    # Check if it's the new array format
    if isinstance(parsed, list):
        is_valid, error_msg, files = _validate_array_format(parsed, allowed_paths)
    # Check if it's the legacy dict format
    elif isinstance(parsed, dict):
        print("⚠️  Using legacy dict format (consider upgrading to base64 array format)")
        is_valid, error_msg, files = _validate_dict_format(parsed, allowed_paths)
    else:
        return False, f"Expected JSON array or object, got {type(parsed).__name__}", None
    
    # If structure validation failed, return early
    if not is_valid:
        return is_valid, error_msg, files
    
    # Step 5: Enforce allowed_paths completeness (all must be present exactly once)
    if files:
        is_complete, completeness_error = _validate_path_completeness(files, allowed_paths)
        if not is_complete:
            return False, completeness_error, None
    
    # Validate file contents if requested
    if validate_content and files:
        for file_path, content in files.items():
            content_valid, content_error = validate_file_content(file_path, content)
            if not content_valid:
                return False, content_error, None
    
    return is_valid, error_msg, files


def _validate_path_completeness(
    files: Dict[str, str],
    allowed_paths: List[str]
) -> Tuple[bool, Optional[str]]:
    """
    Validate that all allowed_paths are present exactly once.
    
    Args:
        files: Dict of parsed files
        allowed_paths: List of required paths
        
    Returns:
        Tuple of (is_complete, error_message)
    """
    file_paths = set(files.keys())
    allowed_set = set(allowed_paths)
    
    # Check for extra paths first (not in allowed_paths) - security check
    extra = file_paths - allowed_set
    if extra:
        extra_list = sorted(extra)
        return False, f"Extra paths not in allowed_paths: {', '.join(extra_list)}"
    
    # Check for missing paths
    missing = allowed_set - file_paths
    if missing:
        missing_list = sorted(missing)
        return False, f"Missing required paths: {', '.join(missing_list)}"
    
    return True, None


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
        
        # Check for duplicate paths
        if path in files:
            return False, f"Duplicate path: {path}", None
        
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
    Write files to disk atomically using temp files.
    
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
        
        # Write atomically: write to temp file in same directory, then replace
        # This ensures we never have partially-written files
        temp_fd, temp_path = tempfile.mkstemp(
            dir=full_path.parent,
            prefix=f".{full_path.name}.",
            suffix=".tmp"
        )
        
        try:
            # Write content to temp file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Atomically replace target file
            os.replace(temp_path, full_path)
            written_paths.append(file_path)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise
    
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
    existing_files: Dict[str, Optional[str]],
    retry_context: Optional[Dict[str, str]] = None
) -> str:
    """
    Create prompt for rewrite mode with filetype-aware instructions.
    
    Args:
        task: Task object with id, title, scope, etc.
        existing_files: Dict of current file contents
        retry_context: Optional dict with 'test_output' and 'failure_type' for retries
        
    Returns:
        Prompt string for model
    """
    # Analyze file types in allowed paths
    has_python = any(path.endswith('.py') for path in task.allowed_paths)
    has_json = any(path.endswith('.json') for path in task.allowed_paths)
    has_yaml = any(path.endswith(('.yaml', '.yml')) for path in task.allowed_paths)
    
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
    
    # Build filetype-specific instructions
    filetype_instructions = []
    
    if has_python:
        filetype_instructions.append("""
PYTHON FILES (.py):
- MUST decode to valid Python 3.10+ source code
- NO JSON-like escaped fragments (no literal \\n, \\t outside Python strings)
- Use Python dict/list literals directly: {{"key": "value"}}, not {{\\"key\\": \\"value\\"}}
- If you need JSON data in Python, use triple-quoted strings with json.loads():
  
  import json
  data = json.loads('''
  {{
      "key": "value"
  }}
  ''')
  
- Write idiomatic Python, not JSON masquerading as Python""")
    
    if has_json:
        filetype_instructions.append("""
JSON FILES (.json):
- MUST decode to valid JSON (strict RFC 8259)
- Use proper JSON syntax with escaped quotes inside strings""")
    
    if has_yaml:
        filetype_instructions.append("""
YAML FILES (.yaml, .yml):
- MUST decode to valid YAML
- Use proper YAML indentation and syntax""")
    
    filetype_section = "".join(filetype_instructions) if filetype_instructions else ""
    
    # Build retry feedback section if this is a retry attempt
    retry_section = ""
    if retry_context:
        failure_type = retry_context.get('failure_type', 'unknown')
        test_output = retry_context.get('test_output', '')
        
        # Truncate test output to last 200 lines to keep prompt bounded
        test_lines = test_output.split('\n')
        if len(test_lines) > 200:
            test_output = '\n'.join(test_lines[-200:])
            test_output = f"[... truncated to last 200 lines ...]\n{test_output}"
        
        retry_section = f"""

⚠️  RETRY ATTEMPT - PREVIOUS IMPLEMENTATION FAILED ⚠️

Failure Type: {failure_type}

The previous implementation failed with the following test output:

```
{test_output}
```

CURRENT FILE CONTENTS (after previous attempt):
{chr(10).join(file_contexts)}

Your task is to FIX the implementation based on the test failure above.
Analyze the error carefully and generate corrected file contents.
"""
    
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
{retry_section}
{"" if retry_context else f'''
CURRENT FILE CONTENTS:
{chr(10).join(file_contexts)}'''}

HARD CONSTRAINTS:
1. Only modify files within the allowed paths listed above
2. No infrastructure mutations (no terraform apply, aws create/update/delete, etc)
3. Follow the scope constraints ({task.scope})
4. Write clean, tested, documented code
5. Ensure all acceptance criteria are met
{filetype_section}

OUTPUT FORMAT - CRITICAL:
You MUST output EXACTLY this format with NO extra text:

{{"files":[{{"path":"...","content_b64":"..."}},{{"path":"...","content_b64":"..."}}]}}

RULES:
1. EXACT envelope: {{"files":[...]}}
2. NO markdown code fences (no ```)
3. NO explanatory text before or after
4. NO comments or prose
5. Include ALL files from allowed_paths (even if only slightly modified)
6. Use base64 encoding to avoid JSON escaping issues
7. Each file object MUST have both "path" and "content_b64" fields

Example (Python test with dict literal, NOT escaped JSON):
{{"files":[
  {{"path":"tests/unit/test_example.py","content_b64":"aW1wb3J0IHB5dGVzdAoKZGVmIHRlc3RfZXhhbXBsZSgpOgogICAgZGF0YSA9IHsKICAgICAgICAibmFtZSI6ICJ0ZXN0IiwKICAgICAgICAidmFsdWUiOiA0MgogICAgfQogICAgYXNzZXJ0IGRhdGFbIm5hbWUiXSA9PSAidGVzdCIK"}},
  {{"path":"config.json","content_b64":"ewogICAgImtleSI6ICJ2YWx1ZSIKfQo="}}
]}}

Generate the implementation now as pure JSON envelope with base64-encoded contents:"""
    
    return prompt
