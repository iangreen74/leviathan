"""
Safe command execution for Leviathan runner.
Enforces no-mutation rules for infrastructure commands.
"""
import subprocess
import re
from typing import List, Tuple, Optional
from pathlib import Path


def select_test_targets(allowed_paths: List[str]) -> List[str]:
    """
    Select test files to run based on allowed paths.
    
    Pure function that extracts test files from allowed_paths.
    If no test files are in allowed_paths, returns empty list.
    
    Args:
        allowed_paths: List of allowed file paths for a task
        
    Returns:
        List of test file paths to run (may be empty)
    
    Examples:
        >>> select_test_targets(['tests/unit/test_foo.py', 'src/foo.py'])
        ['tests/unit/test_foo.py']
        
        >>> select_test_targets(['src/foo.py', 'src/bar.py'])
        []
        
        >>> select_test_targets(['tests/unit/test_a.py', 'tests/unit/test_b.py'])
        ['tests/unit/test_a.py', 'tests/unit/test_b.py']
    """
    test_files = []
    
    for path in allowed_paths:
        # Check if path is a test file
        if path.startswith('tests/') and path.endswith('.py'):
            test_files.append(path)
    
    return test_files


class UnsafeCommandError(Exception):
    """Raised when attempting to execute an unsafe command."""
    pass


class CommandExecutor:
    """Executes commands with safety checks."""
    
    # Forbidden command patterns (infrastructure mutations)
    FORBIDDEN_PATTERNS = [
        r'\bterraform\s+(apply|destroy)',
        r'\baws\s+.*\s+(create|update|delete|put)',
        r'\bsam\s+(deploy|delete)',
        r'\bkubectl\s+(apply|create|delete|patch)',
        r'\bhelm\s+(install|upgrade|delete)',
        r'\bgcloud\s+.*\s+(create|update|delete)',
        r'\baz\s+.*\s+(create|update|delete)',
    ]
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
    
    def is_safe_command(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        Check if command is safe to execute.
        
        Returns:
            Tuple of (is_safe, reason_if_unsafe)
        """
        command_lower = command.lower()
        
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, command_lower):
                return False, f"Forbidden pattern detected: {pattern}"
        
        return True, None
    
    def run(self, command: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """
        Run a command safely.
        
        Args:
            command: Command string to execute
            cwd: Working directory (defaults to repo_root)
            check: Raise exception on non-zero exit
        
        Returns:
            CompletedProcess result
        
        Raises:
            UnsafeCommandError: If command is deemed unsafe
            subprocess.CalledProcessError: If command fails and check=True
        """
        is_safe, reason = self.is_safe_command(command)
        if not is_safe:
            raise UnsafeCommandError(f"Unsafe command blocked: {reason}\nCommand: {command}")
        
        if cwd is None:
            cwd = self.repo_root
        
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        
        return result
    
    def run_command(self, command: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """
        Run a command from list of arguments (safer than shell=True).
        
        Args:
            command: Command as list of arguments
            cwd: Working directory (defaults to repo_root)
            check: Raise exception on non-zero exit
        
        Returns:
            CompletedProcess result
        """
        # Check safety on joined command string
        command_str = ' '.join(command)
        is_safe, reason = self.is_safe_command(command_str)
        if not is_safe:
            raise UnsafeCommandError(f"Unsafe command blocked: {reason}\nCommand: {command_str}")
        
        if cwd is None:
            cwd = self.repo_root
        
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        
        return result
    
    def run_test_suite(self, scope: str, allowed_paths: List[str]) -> Tuple[bool, str]:
        """
        Run appropriate tests based on scope and allowed paths.
        
        Uses targeted testing: only runs test files explicitly in allowed_paths.
        This prevents unrelated test collection failures from blocking progress.
        
        Args:
            scope: Task scope (ci, docs, tools, test, services, infra)
            allowed_paths: Allowed file paths for this task
        
        Returns:
            Tuple of (success, output_message)
        """
        try:
            if scope == 'ci':
                # Validate bash scripts and YAML files
                bash_files = [p for p in allowed_paths if p.endswith('.sh')]
                yaml_files = [p for p in allowed_paths if p.endswith(('.yml', '.yaml'))]
                
                for bash_file in bash_files:
                    file_path = self.repo_root / bash_file
                    if file_path.exists():
                        result = self.run(f"bash -n {bash_file}", check=False)
                        if result.returncode != 0:
                            return False, f"Bash syntax error in {bash_file}: {result.stderr}"
                
                for yaml_file in yaml_files:
                    file_path = self.repo_root / yaml_file
                    if file_path.exists():
                        result = self.run(f"python3 -c \"import yaml; yaml.safe_load(open('{yaml_file}'))\"", check=False)
                        if result.returncode != 0:
                            return False, f"YAML syntax error in {yaml_file}: {result.stderr}"
                
                return True, "CI validation passed"
            
            elif scope == 'docs':
                # Ensure files exist
                for doc_path in allowed_paths:
                    file_path = self.repo_root / doc_path
                    if not file_path.exists():
                        return False, f"Expected doc file not found: {doc_path}"
                
                return True, "Docs validation passed"
            
            elif scope in ['test', 'tests', 'tools', 'services']:
                # Use targeted testing: only run test files in allowed_paths
                test_targets = select_test_targets(allowed_paths)
                
                if test_targets:
                    # Run pytest on specific test files only
                    test_args = ' '.join(test_targets)
                    print(f"Running targeted tests: {test_targets}")
                    result = self.run(f"python3 -m pytest {test_args} -v --tb=short", check=False)
                    
                    if result.returncode != 0:
                        return False, f"Tests failed:\n{result.stdout}\n{result.stderr}"
                    
                    return True, f"Tests passed:\n{result.stdout}"
                else:
                    # No test files in allowed_paths - skip testing
                    print("No test files in allowed_paths, skipping pytest")
                    return True, "No test files to run (skipped)"
            
            else:
                return True, f"No validation defined for scope: {scope}"
        
        except Exception as e:
            return False, f"Test execution error: {str(e)}"
