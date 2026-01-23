"""
GitHub operations for Leviathan runner.
Handles PR creation, CI monitoring, and status checks.
"""
import os
import subprocess
import time
import requests
from typing import Optional, Dict, Any, Tuple, Set, List
from pathlib import Path
from datetime import datetime


class ScopeMismatchError(Exception):
    """Raised when PR has mixed scopes that should be split."""
    pass


def compute_branch_name(task_id: str, remote_exists: bool) -> str:
    """
    Compute branch name with collision avoidance.
    
    Deterministic behavior:
    - If no remote collision: use agent/{task_id}
    - If remote collision: append -{UTCYYYYMMDDHHMMSS}
    
    Args:
        task_id: Task identifier
        remote_exists: Whether branch already exists on remote
        
    Returns:
        Branch name string
    """
    base_name = f"agent/{task_id}"
    
    if not remote_exists:
        return base_name
    
    # Remote collision detected - add timestamp suffix
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"{base_name}-{timestamp}"


class GitHubClient:
    """Handles GitHub API operations."""
    
    def __init__(self, repo_root: Path, repo_owner: str = "iangreen74", repo_name: str = "radix"):
        self.repo_root = repo_root
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.token = os.environ.get('GITHUB_TOKEN')
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    
    def get_changed_files(self, base: str = 'origin/main') -> List[str]:
        """
        Get list of changed files compared to base branch.
        
        Args:
            base: Base branch to compare against
            
        Returns:
            List of changed file paths
        """
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'{base}...HEAD'],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
                check=True
            )
            files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            return files
        except subprocess.CalledProcessError:
            return []
    
    def infer_scope_from_files(self, files: List[str]) -> Set[str]:
        """
        Infer scope(s) from changed file paths using sentinel rules.
        
        Args:
            files: List of changed file paths
            
        Returns:
            Set of inferred scopes (docs, test, ci, services, infra)
        """
        scopes = set()
        
        for file_path in files:
            if file_path.startswith('docs/'):
                scopes.add('docs')
            elif file_path.startswith('tests/'):
                scopes.add('test')
            elif file_path.startswith('.github/workflows/') or file_path.startswith('scripts/ci/'):
                scopes.add('ci')
            elif file_path.startswith('services/'):
                scopes.add('services')
            elif file_path.startswith('infra/'):
                scopes.add('infra')
            elif file_path.startswith('tools/'):
                scopes.add('tools')
        
        return scopes
    
    def generate_pr_title(self, task_id: str, task_title: str, scope: str) -> str:
        """
        Generate PR title based on scope and task.
        
        Args:
            task_id: Task identifier
            task_title: Human-readable task title
            scope: Inferred scope (docs, test, ci, services, infra, tools)
            
        Returns:
            Formatted PR title
        """
        # Map scope to conventional commit prefix
        if scope == 'docs':
            prefix = 'docs(mvp)'
        elif scope == 'test':
            prefix = 'test(mvp)'
        elif scope == 'ci':
            prefix = 'fix(ci)'
        elif scope == 'tools':
            prefix = 'fix(tools)'
        elif scope == 'services':
            # Geophysics tasks get feat(geo), others get feat(research)
            if task_id.startswith('geo-'):
                prefix = 'feat(geo)'
            else:
                prefix = 'feat(research)'
        elif scope == 'infra':
            prefix = 'feat(infra)'
        else:
            # Fallback
            prefix = 'feat'
        
        return f"{prefix}: {task_title}"
    
    def is_authenticated(self) -> bool:
        """Check if GitHub CLI is authenticated."""
        try:
            result = subprocess.run(
                ['gh', 'auth', 'status'],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def get_open_pr_count(self) -> int:
        """Get count of open PRs using GitHub API or gh CLI."""
        if self.token:
            # Use GitHub API
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f"{self.api_base}/pulls?state=open",
                headers=headers
            )
            if response.status_code == 200:
                return len(response.json())
        
        # Fallback to gh CLI
        if self.is_authenticated():
            try:
                result = subprocess.run(
                    ['gh', 'pr', 'list', '--json', 'number'],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root
                )
                if result.returncode == 0:
                    import json
                    prs = json.loads(result.stdout)
                    return len(prs)
            except Exception:
                pass
        
        return 0
    
    def list_open_pr_branches(self) -> set[str]:
        """
        Get set of branch names for all open PRs.
        
        Returns:
            Set of branch names (head refs) for open PRs
        """
        branches = set()
        
        if self.token:
            # Use GitHub API
            headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            response = requests.get(
                f"{self.api_base}/pulls?state=open",
                headers=headers
            )
            if response.status_code == 200:
                prs = response.json()
                for pr in prs:
                    if 'head' in pr and 'ref' in pr['head']:
                        branches.add(pr['head']['ref'])
                return branches
        
        # Fallback to gh CLI
        if self.is_authenticated():
            try:
                result = subprocess.run(
                    ['gh', 'pr', 'list', '--json', 'headRefName'],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root
                )
                if result.returncode == 0:
                    import json
                    prs = json.loads(result.stdout)
                    for pr in prs:
                        if 'headRefName' in pr:
                            branches.add(pr['headRefName'])
                    return branches
            except Exception:
                pass
        
        return branches
    
    def branch_exists_locally(self, branch_name: str) -> bool:
        """Check if branch exists locally."""
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', branch_name],
            cwd=self.repo_root,
            capture_output=True
        )
        return result.returncode == 0
    
    def branch_exists_on_remote(self, branch_name: str) -> bool:
        """Check if branch exists on remote."""
        result = subprocess.run(
            ['git', 'ls-remote', '--heads', 'origin', branch_name],
            cwd=self.repo_root,
            capture_output=True,
            text=True
        )
        return bool(result.stdout.strip())
    
    def delete_local_branch(self, branch_name: str) -> bool:
        """Delete local branch (force)."""
        result = subprocess.run(
            ['git', 'branch', '-D', branch_name],
            cwd=self.repo_root,
            capture_output=True
        )
        return result.returncode == 0
    
    def create_branch(self, branch_name: str) -> bool:
        """
        Create and checkout a new branch with self-healing.
        
        Self-heals:
        - If branch exists locally, deletes it and retries
        - Logs actual git command errors for debugging
        
        Args:
            branch_name: Name of branch to create
            
        Returns:
            True if successful, False otherwise
        """
        # First attempt
        result = subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            cwd=self.repo_root,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            return True
        
        # Log the error
        print(f"⚠️  Branch creation failed for '{branch_name}'")
        print(f"   Command: git checkout -b {branch_name}")
        if result.stderr:
            print(f"   Error: {result.stderr.strip()}")
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
        
        # Self-heal: check if branch exists locally
        if self.branch_exists_locally(branch_name):
            print(f"   Self-healing: Branch exists locally, deleting and retrying...")
            if self.delete_local_branch(branch_name):
                print(f"   Deleted local branch '{branch_name}'")
                
                # Retry
                result = subprocess.run(
                    ['git', 'checkout', '-b', branch_name],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"   ✅ Branch created successfully after self-heal")
                    return True
                else:
                    print(f"   ❌ Retry failed: {result.stderr.strip() if result.stderr else 'unknown error'}")
            else:
                print(f"   ❌ Failed to delete local branch")
        
        return False
    
    def commit_changes(self, message: str, files: list) -> bool:
        """Stage and commit changes."""
        try:
            # Stage files
            subprocess.run(
                ['git', 'add'] + files,
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            
            # Commit
            subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def push_branch(self, branch_name: str) -> bool:
        """Push branch to origin."""
        try:
            subprocess.run(
                ['git', 'push', '-u', 'origin', branch_name],
                cwd=self.repo_root,
                check=True,
                capture_output=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def create_pr_with_auto_title(self, task_id: str, task_title: str, body: str, base: str = 'main') -> Tuple[Optional[int], str]:
        """
        Create a pull request with auto-generated title based on file scope.
        
        Args:
            task_id: Task identifier
            task_title: Human-readable task title
            body: PR body (should include Task-ID)
            base: Base branch
            
        Returns:
            Tuple of (pr_number, pr_url)
            
        Raises:
            ScopeMismatchError: If PR has mixed scopes that should be split
        """
        # Get changed files and infer scope
        changed_files = self.get_changed_files(base=f'origin/{base}')
        
        if not changed_files:
            raise ValueError("No changed files detected")
        
        scopes = self.infer_scope_from_files(changed_files)
        
        # Check for mixed scopes
        if len(scopes) > 1:
            raise ScopeMismatchError(
                f"PR has mixed scopes: {', '.join(sorted(scopes))}. "
                f"Please split into separate PRs. Changed files: {', '.join(changed_files)}"
            )
        
        if len(scopes) == 0:
            raise ValueError(f"Could not infer scope from changed files: {', '.join(changed_files)}")
        
        # Generate title from scope
        scope = list(scopes)[0]
        title = self.generate_pr_title(task_id, task_title, scope)
        
        # Print title for visibility
        print(f"📝 Auto-generated PR title: {title}")
        
        if self.is_authenticated():
            try:
                result = subprocess.run(
                    ['gh', 'pr', 'create', '--base', base, '--title', title, '--body', body],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root,
                    check=True
                )
                pr_url = result.stdout.strip()
                
                # Extract PR number from URL
                pr_number = None
                if '/pull/' in pr_url:
                    pr_number = int(pr_url.split('/pull/')[-1])
                
                return pr_number, pr_url
            except subprocess.CalledProcessError as e:
                # Return URL for manual creation
                branch_result = subprocess.run(
                    ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                    capture_output=True,
                    text=True,
                    cwd=self.repo_root
                )
                branch_name = branch_result.stdout.strip()
                pr_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/new/{branch_name}"
                print(f"⚠️  gh CLI failed, use this title: {title}")
                return None, pr_url
        else:
            # Return URL for manual creation
            branch_result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )
            branch_name = branch_result.stdout.strip()
            pr_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/pull/new/{branch_name}"
            return None, pr_url
    
    def get_pr_status(self, pr_number: int) -> Dict[str, Any]:
        """
        Get PR check status.
        
        Returns:
            Dict with 'state' (pending/success/failure) and 'details'
        """
        if not self.token:
            return {'state': 'unknown', 'details': 'No GitHub token available'}
        
        headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # Get PR details
        response = requests.get(
            f"{self.api_base}/pulls/{pr_number}",
            headers=headers
        )
        
        if response.status_code != 200:
            return {'state': 'error', 'details': f'Failed to fetch PR: {response.status_code}'}
        
        pr_data = response.json()
        sha = pr_data['head']['sha']
        
        # Get check runs
        response = requests.get(
            f"{self.api_base}/commits/{sha}/check-runs",
            headers=headers
        )
        
        if response.status_code != 200:
            return {'state': 'error', 'details': f'Failed to fetch checks: {response.status_code}'}
        
        check_data = response.json()
        check_runs = check_data.get('check_runs', [])
        
        if not check_runs:
            return {'state': 'pending', 'details': 'No checks started yet'}
        
        # Analyze check statuses
        statuses = [check['status'] for check in check_runs]
        conclusions = [check.get('conclusion') for check in check_runs if check['status'] == 'completed']
        
        if any(s != 'completed' for s in statuses):
            return {'state': 'pending', 'details': f'{len([s for s in statuses if s != "completed"])} checks pending'}
        
        if any(c == 'failure' for c in conclusions):
            failed_checks = [check['name'] for check in check_runs if check.get('conclusion') == 'failure']
            return {'state': 'failure', 'details': f'Failed checks: {", ".join(failed_checks)}'}
        
        if all(c == 'success' for c in conclusions):
            return {'state': 'success', 'details': 'All checks passed'}
        
        return {'state': 'unknown', 'details': f'Mixed conclusions: {conclusions}'}
    
    def monitor_pr_checks(self, pr_number: int, poll_interval: int = 60, max_polls: int = 30) -> Tuple[str, str]:
        """
        Monitor PR checks until completion or timeout.
        
        Returns:
            Tuple of (final_state, details)
        """
        for i in range(max_polls):
            status = self.get_pr_status(pr_number)
            state = status['state']
            details = status['details']
            
            if state in ['success', 'failure', 'error']:
                return state, details
            
            if i < max_polls - 1:
                time.sleep(poll_interval)
        
        return 'timeout', f'Checks did not complete after {max_polls * poll_interval} seconds'
