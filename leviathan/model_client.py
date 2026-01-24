"""
Model client for Leviathan runner.
Supports Claude API integration with fallback to local patch files.
"""
import os
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import requests

from leviathan.backlog import Task
from leviathan.rewrite_mode import (
    create_rewrite_prompt,
    read_existing_files,
    validate_rewrite_output,
    write_files,
    RewriteModeError
)


class PatchValidationError(Exception):
    """Raised when a generated patch violates constraints."""
    pass


class ModelClient:
    """
    Interface for model API calls with Claude integration.
    
    Supports two modes:
    1. Claude API mode (when LEVIATHAN_CLAUDE_API_KEY is set)
    2. Fallback mode (reads from leviathan_patch.txt)
    """
    
    def __init__(self, api_key: Optional[str] = None, repo_root: Optional[Path] = None):
        self.api_key = api_key or os.environ.get('LEVIATHAN_CLAUDE_API_KEY')
        self.repo_root = repo_root or Path.cwd()
        self.artifacts_dir = self.repo_root / '.leviathan'
        self.artifacts_dir.mkdir(exist_ok=True)
        
        # Fallback patch file
        self.patch_file = self.repo_root / 'leviathan_patch.txt'
        
        # Claude API configuration
        self.api_url = 'https://api.anthropic.com/v1/messages'
        self.model = os.environ.get('LEVIATHAN_CLAUDE_MODEL', 'claude-3-5-sonnet-latest')
        self.max_tokens = 4096
        self.temperature = 0.2  # Low for repeatability
    
    def _read_file_content(self, file_path: str, max_size_kb: int = 200) -> Tuple[str, bool]:
        """
        Read file content safely with size limits.
        
        Args:
            file_path: Path to file relative to repo root
            max_size_kb: Maximum file size in KB (default 200KB)
        
        Returns:
            Tuple of (content, was_truncated)
        """
        full_path = self.repo_root / file_path
        
        if not full_path.exists():
            return f"[FILE DOES NOT EXIST: {file_path}]", False
        
        try:
            # Check file size
            file_size = full_path.stat().st_size
            max_size_bytes = max_size_kb * 1024
            
            if file_size > max_size_bytes:
                # Read first 200 lines for large files
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= 200:
                            break
                        lines.append(line)
                    content = ''.join(lines)
                    content += f"\n\n[... TRUNCATED: File is {file_size} bytes, showing first 200 lines ...]"
                    return content, True
            else:
                # Read full file
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                    return content, False
        except Exception as e:
            return f"[ERROR READING FILE: {str(e)}]", False
    
    def _create_task_prompt(self, task: Task) -> str:
        """Create a prompt for the model from task details with file context."""
        # Read current file contents for all allowed paths
        file_contexts = []
        truncated_files = []
        
        for file_path in task.allowed_paths:
            content, was_truncated = self._read_file_content(file_path)
            
            file_contexts.append(f"""=== FILE: {file_path} (current content) ===
{content}
=== END FILE ===
""")
            
            if was_truncated:
                truncated_files.append(file_path)
        
        # Log truncation warnings
        truncation_note = ""
        if truncated_files:
            truncation_note = f"\n\nNOTE: The following files were truncated (>200KB): {', '.join(truncated_files)}"
        
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
6. Generate a unified diff patch that applies to the provided file contents above
7. Do not invent files outside allowed_paths{truncation_note}

OUTPUT FORMAT:
Generate a unified diff patch (git apply compatible format) that implements this task.
The patch MUST apply cleanly to the current file contents shown above.

CRITICAL OUTPUT REQUIREMENTS:
1. Output ONLY the unified diff between BEGIN_DIFF and END_DIFF markers
2. NO markdown code fences (no ```)
3. NO commentary or explanations
4. NO text before BEGIN_DIFF or after END_DIFF
5. Start with "diff --git" immediately after BEGIN_DIFF

Format:
BEGIN_DIFF
diff --git a/path/to/file.py b/path/to/file.py
index abc123..def456 100644
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,3 +10,4 @@ existing line
 existing line
+new line
 existing line
END_DIFF

Generate the implementation patch now:"""
        return prompt
    
    def _call_claude_api(self, prompt: str) -> str:
        """
        Call Claude API to generate implementation.
        
        Returns:
            Raw model output
        
        Raises:
            Exception: If API call fails
        """
        if not self.api_key:
            raise ValueError("LEVIATHAN_CLAUDE_API_KEY not set")
        
        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }
        
        payload = {
            'model': self.model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        }
        
        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            raise Exception(
                f"Claude API error {response.status_code} (model: {self.model}): {response.text}\n"
                f"If model not found, set LEVIATHAN_CLAUDE_MODEL to a supported model."
            )
        
        data = response.json()
        
        # Extract text from response
        if 'content' in data and len(data['content']) > 0:
            return data['content'][0]['text']
        else:
            raise Exception(f"Unexpected API response format: {data}")
    
    def _validate_diff_syntax(self, patch: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that patch is a valid unified diff.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        lines = patch.strip().split('\n')
        
        # Must contain at least one "diff --git" line
        has_diff_header = any(line.startswith('diff --git') for line in lines)
        if not has_diff_header:
            return False, "Missing 'diff --git' header"
        
        # Must contain matching "---" and "+++" lines
        has_minus_header = any(line.startswith('--- ') for line in lines)
        has_plus_header = any(line.startswith('+++ ') for line in lines)
        
        if not has_minus_header:
            return False, "Missing '--- a/...' header"
        if not has_plus_header:
            return False, "Missing '+++ b/...' header"
        
        # Must contain at least one hunk header (@@)
        has_hunk = any(line.startswith('@@') for line in lines)
        if not has_hunk:
            return False, "Missing '@@ ...' hunk header"
        
        return True, None
    
    def _extract_patch_from_output(self, output: str) -> str:
        """
        Extract patch from model output with strict validation.
        
        Prefers BEGIN_DIFF/END_DIFF markers, falls back to other methods.
        """
        # First, try to extract between BEGIN_DIFF and END_DIFF markers
        if 'BEGIN_DIFF' in output and 'END_DIFF' in output:
            match = re.search(r'BEGIN_DIFF\s*\n(.*?)\nEND_DIFF', output, re.DOTALL)
            if match:
                patch = match.group(1).strip()
                return patch
        
        # Fallback: Remove markdown code blocks if present
        if '```' in output:
            match = re.search(r'```(?:diff)?\n(.*?)\n```', output, re.DOTALL)
            if match:
                output = match.group(1)
        
        # Fallback: Find the start of the actual patch (diff --git)
        lines = output.split('\n')
        patch_start = None
        
        for i, line in enumerate(lines):
            if line.startswith('diff --git'):
                patch_start = i
                break
        
        if patch_start is not None:
            patch = '\n'.join(lines[patch_start:])
            return patch.strip()
        
        # If no diff header found, return as-is (will fail validation)
        return output.strip()
    
    def _validate_patch(self, patch: str, allowed_paths: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Validate that patch only touches allowed paths.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Extract file paths from patch
        modified_files = []
        
        for line in patch.split('\n'):
            if line.startswith('diff --git'):
                # Extract file path from: diff --git a/path/to/file b/path/to/file
                match = re.search(r'diff --git a/(.*?) b/', line)
                if match:
                    modified_files.append(match.group(1))
            elif line.startswith('--- ') or line.startswith('+++ '):
                # Extract from: --- a/path/to/file or +++ b/path/to/file
                match = re.search(r'[+-]{3} [ab]/(.*?)$', line)
                if match:
                    file_path = match.group(1)
                    if file_path != '/dev/null':  # Ignore /dev/null (new/deleted files)
                        modified_files.append(file_path)
        
        # Remove duplicates
        modified_files = list(set(modified_files))
        
        if not modified_files:
            return False, "No files found in patch"
        
        # Check each file against allowed paths
        forbidden_files = []
        
        for file_path in modified_files:
            allowed = False
            for allowed_path in allowed_paths:
                # Check if file is under allowed path
                if file_path.startswith(allowed_path) or file_path == allowed_path.rstrip('/'):
                    allowed = True
                    break
            
            if not allowed:
                forbidden_files.append(file_path)
        
        if forbidden_files:
            return False, f"Patch modifies forbidden files: {', '.join(forbidden_files)}"
        
        return True, None
    
    def _save_artifacts(self, raw_output: str, patch: str):
        """Save model output and patch to artifacts directory."""
        # Save raw model output
        output_file = self.artifacts_dir / 'last_model_output.txt'
        output_file.write_text(raw_output)
        
        # Save extracted patch
        patch_file = self.artifacts_dir / 'last_patch.diff'
        patch_file.write_text(patch)
    
    def generate_implementation_rewrite_mode(
        self, 
        task: Task, 
        max_retries: int = 1,
        retry_context: Optional[Dict[str, str]] = None
    ) -> Tuple[List[str], str]:
        """
        Generate implementation using rewrite mode (for small tasks).
        
        Returns JSON mapping file paths to complete contents, then writes files directly.
        More reliable than diff-based patching for small tasks.
        
        Args:
            task: Task to implement
            max_retries: Number of retries on validation failure
            retry_context: Optional dict with 'test_output' and 'failure_type' for repair loop
            
        Returns:
            Tuple of (written_paths, source)
            - written_paths: List of file paths that were written
            - source: 'claude_api' or 'local_file'
            
        Raises:
            RewriteModeError: If output validation fails after retries
            Exception: If API call fails
        """
        if not self.api_key:
            raise ValueError("Rewrite mode requires LEVIATHAN_CLAUDE_API_KEY")
        
        # Read existing files
        existing_files = read_existing_files(task.allowed_paths, self.repo_root)
        
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                # Create prompt
                if attempt == 0:
                    print("🤖 Calling Claude API (rewrite mode) to generate implementation...")
                    # Use retry_context if provided (for repair loop), otherwise fresh prompt
                    prompt = create_rewrite_prompt(task, existing_files, retry_context=retry_context)
                else:
                    print(f"🔄 Retry {attempt}/{max_retries} with stricter prompt...")
                    # Add extra emphasis on retry with specific error
                    prompt = create_rewrite_prompt(task, existing_files, retry_context=retry_context)
                    prompt += f"\n\nIMPORTANT: Previous attempt failed validation with error:\n{last_error}\n\nPlease fix this error and output ONLY pure JSON with no extra text."
                
                # Call API
                raw_output = self._call_claude_api(prompt)
                
                # Save raw output for debugging
                output_file = self.artifacts_dir / 'last_rewrite_output.txt'
                output_file.write_text(raw_output)
                
                # Validate output (includes content syntax validation)
                is_valid, error_msg, parsed_files = validate_rewrite_output(
                    raw_output,
                    task.allowed_paths,
                    self.repo_root,
                    validate_content=True
                )
                
                if not is_valid:
                    print(f"⚠️  Validation failed: {error_msg}")
                    if attempt < max_retries:
                        # Store error for next retry prompt
                        last_error = error_msg
                        continue
                    else:
                        raise RewriteModeError(
                            f"Rewrite mode validation failed after {max_retries + 1} attempts: {error_msg}\n"
                            f"See {output_file} for details"
                        )
                
                # Write files
                written_paths = write_files(parsed_files, self.repo_root)
                
                print(f"✅ Wrote {len(written_paths)} file(s) in rewrite mode")
                for path in written_paths:
                    print(f"   - {path}")
                
                return written_paths, 'claude_api'
                
            except RewriteModeError:
                raise
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠️  Attempt {attempt + 1} failed: {str(e)}")
                    continue
                else:
                    raise
        
        raise RewriteModeError("Rewrite mode failed after all retries")
    
    def generate_implementation(self, task: Task) -> Tuple[str, str]:
        """
        Generate implementation for a task.
        
        Returns:
            Tuple of (patch_content, source)
            - patch_content: The unified diff patch
            - source: 'claude_api' or 'local_file'
        
        Raises:
            PatchValidationError: If patch violates constraints
            Exception: If generation fails
        """
        # Try Claude API first if key is available
        if self.api_key:
            try:
                print("🤖 Calling Claude API to generate implementation...")
                
                prompt = self._create_task_prompt(task)
                raw_output = self._call_claude_api(prompt)
                
                # Extract patch
                patch = self._extract_patch_from_output(raw_output)
                
                # Validate diff syntax first
                is_valid_syntax, syntax_error = self._validate_diff_syntax(patch)
                
                if not is_valid_syntax:
                    # Save artifacts even on failure for debugging
                    self._save_artifacts(raw_output, patch)
                    raise PatchValidationError(
                        f"Model output did not contain a valid unified diff: {syntax_error}\n"
                        f"See {self.artifacts_dir / 'last_model_output.txt'} for details"
                    )
                
                # Validate patch constraints
                is_valid, error_msg = self._validate_patch(patch, task.allowed_paths)
                
                if not is_valid:
                    # Save artifacts even on failure for debugging
                    self._save_artifacts(raw_output, patch)
                    raise PatchValidationError(f"Generated patch validation failed: {error_msg}")
                
                # Save validated patch
                self._save_artifacts(raw_output, patch)
                
                print(f"✅ Generated patch ({len(patch)} bytes)")
                print(f"📁 Artifacts saved to {self.artifacts_dir}")
                
                return patch, 'claude_api'
            
            except PatchValidationError:
                raise  # Re-raise validation errors
            except Exception as e:
                print(f"⚠️  Claude API error: {str(e)}")
                print("⚠️  Falling back to local patch file...")
        
        # Fallback to local patch file
        if self.patch_file.exists():
            print(f"📄 Reading patch from {self.patch_file}")
            patch = self.patch_file.read_text()
            
            # Validate local patch too
            is_valid, error_msg = self._validate_patch(patch, task.allowed_paths)
            
            if not is_valid:
                raise PatchValidationError(f"Local patch validation failed: {error_msg}")
            
            return patch, 'local_file'
        else:
            raise FileNotFoundError(
                f"No patch available. Either:\n"
                f"1. Set LEVIATHAN_CLAUDE_API_KEY to use Claude API\n"
                f"2. Create {self.patch_file} with your patch"
            )
