"""
Conflict prevention mechanisms for Leviathan runner.
Prevents merge conflicts through hot-file locking and mergeability checks.
"""
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Set
import requests
import os


# Hot files that should not be modified by multiple PRs simultaneously
HOT_FILES = [
    'tools/leviathan/runner.py',
    'tools/leviathan/README.md',
    'tools/leviathan/github.py',
    'tools/leviathan/backlog.py',
]


class ConflictPreventionError(Exception):
    """Raised when conflict prevention mechanisms block a task."""
    pass


class ConflictPrevention:
    """Handles conflict prevention checks."""
    
    def __init__(self, repo_root: Path, github_token: Optional[str] = None):
        self.repo_root = repo_root
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN')
        self.repo_owner = "iangreen74"
        self.repo_name = "radix"
    
    def ensure_fresh_main(self) -> bool:
        """
        Ensure we're branching from fresh main.
        
        Steps:
        1. Fetch latest from origin
        2. Checkout main
        3. Pull with fast-forward only
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch latest
            subprocess.run(
                ['git', 'fetch', 'origin'],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            # Checkout main
            subprocess.run(
                ['git', 'checkout', 'main'],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            # Pull with fast-forward only
            subprocess.run(
                ['git', 'pull', '--ff-only'],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            return True
        
        except subprocess.CalledProcessError as e:
            print(f"Failed to ensure fresh main: {e}")
            return False
    
    def get_open_pr_files(self) -> List[Tuple[int, List[str]]]:
        """
        Get list of files modified in all open PRs.
        
        Returns:
            List of tuples: (pr_number, list_of_modified_files)
        """
        if not self.github_token:
            print("⚠️  No GITHUB_TOKEN available, skipping hot file check")
            return []
        
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get open PRs
        api_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/pulls"
        response = requests.get(api_url, headers=headers, params={'state': 'open'})
        
        if response.status_code != 200:
            print(f"⚠️  Failed to fetch open PRs: {response.status_code}")
            return []
        
        prs = response.json()
        pr_files = []
        
        for pr in prs:
            pr_number = pr['number']
            
            # Get files for this PR
            files_url = f"{api_url}/{pr_number}/files"
            files_response = requests.get(files_url, headers=headers)
            
            if files_response.status_code == 200:
                files = files_response.json()
                modified_files = [f['filename'] for f in files]
                pr_files.append((pr_number, modified_files))
        
        return pr_files
    
    def check_hot_file_conflicts(self, task_allowed_paths: List[str]) -> Tuple[bool, Optional[str]]:
        """
        Check if task would modify hot files that are already in open PRs.
        
        Args:
            task_allowed_paths: List of paths the task is allowed to modify
        
        Returns:
            Tuple of (is_safe, blocking_reason)
            - is_safe: True if no conflicts, False if blocked
            - blocking_reason: Description of conflict if blocked
        """
        # Check if task touches any hot files
        task_hot_files = set()
        for path in task_allowed_paths:
            if path in HOT_FILES:
                task_hot_files.add(path)
        
        if not task_hot_files:
            # Task doesn't touch hot files, safe to proceed
            return True, None
        
        # Get open PR files
        pr_files = self.get_open_pr_files()
        
        if not pr_files:
            # No open PRs or couldn't fetch, allow task
            return True, None
        
        # Check for conflicts
        for pr_number, modified_files in pr_files:
            pr_hot_files = set(modified_files) & set(HOT_FILES)
            
            # Check if there's overlap
            conflict_files = task_hot_files & pr_hot_files
            
            if conflict_files:
                return False, f"PR #{pr_number} is modifying hot files: {', '.join(conflict_files)}"
        
        return True, None
    
    def check_mergeability(self, branch_name: str) -> Tuple[bool, Optional[str]]:
        """
        Check if branch can merge cleanly with origin/main.
        
        Args:
            branch_name: Name of the branch to check
        
        Returns:
            Tuple of (is_mergeable, conflict_reason)
        """
        try:
            # Save current branch
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()
            
            # Checkout the branch to test
            subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            # Fetch latest main
            subprocess.run(
                ['git', 'fetch', 'origin', 'main'],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            # Try merge without committing
            result = subprocess.run(
                ['git', 'merge', '--no-commit', '--no-ff', 'origin/main'],
                cwd=self.repo_root,
                capture_output=True,
                text=True
            )
            
            # Check result
            if result.returncode != 0:
                # Merge would conflict
                # Abort the merge
                subprocess.run(
                    ['git', 'merge', '--abort'],
                    cwd=self.repo_root,
                    capture_output=True
                )
                
                # Return to original branch
                subprocess.run(
                    ['git', 'checkout', current_branch],
                    cwd=self.repo_root,
                    capture_output=True
                )
                
                return False, "Branch would conflict with origin/main"
            
            # Abort the merge (we just wanted to test)
            subprocess.run(
                ['git', 'merge', '--abort'],
                cwd=self.repo_root,
                capture_output=True
            )
            
            # Return to original branch
            subprocess.run(
                ['git', 'checkout', current_branch],
                cwd=self.repo_root,
                capture_output=True
            )
            
            return True, None
        
        except subprocess.CalledProcessError as e:
            return False, f"Mergeability check failed: {str(e)}"
    
    def get_hot_files_list(self) -> List[str]:
        """Get list of hot files."""
        return HOT_FILES.copy()
