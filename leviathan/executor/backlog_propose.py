"""
Backlog propose mode: Create PR that adds task to .leviathan/backlog.yaml

This module implements a minimal PR creation flow that:
1. Clones target repo
2. Adds a new task entry to .leviathan/backlog.yaml
3. Creates a branch, commits, pushes
4. Opens a PR via GitHub API
5. Posts events to control plane

Used for PR Proof v1.
"""
import os
import re
import subprocess
import yaml
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

import requests

from leviathan.backlog import Task


class BacklogProposer:
    """Creates PRs that propose new tasks to target backlog."""
    
    def __init__(
        self,
        target_name: str,
        target_repo_url: str,
        target_branch: str,
        task_spec: Dict[str, Any],
        attempt_id: str,
        github_token: str,
        workspace: Path
    ):
        """
        Initialize backlog proposer.
        
        Args:
            target_name: Target identifier
            target_repo_url: Git repository URL
            target_branch: Target branch (usually 'main')
            task_spec: Task specification to add to backlog
            attempt_id: Unique attempt identifier
            github_token: GitHub personal access token
            workspace: Workspace directory
        """
        self.target_name = target_name
        self.target_repo_url = target_repo_url
        self.target_branch = target_branch
        self.task_spec = task_spec
        self.attempt_id = attempt_id
        self.github_token = github_token
        self.workspace = workspace
        self.target_dir = workspace / "target"
        
    def propose(self) -> Tuple[str, int, str]:
        """
        Propose task by creating PR to add it to backlog.yaml.
        
        Returns:
            Tuple of (pr_url, pr_number, commit_sha)
        """
        # Clone repo
        self._clone_repo()
        
        # Add task to backlog
        self._add_task_to_backlog()
        
        # Create branch and commit
        branch_name = f"agent/backlog-propose-{self.attempt_id}"
        commit_sha = self._commit_and_push(branch_name)
        
        # Create PR
        pr_url, pr_number = self._create_pr(branch_name)
        
        return pr_url, pr_number, commit_sha
    
    def _clone_repo(self):
        """Clone target repository."""
        print(f"\nCloning {self.target_repo_url}...")
        
        # For SSH URLs, use as-is (no token needed)
        # For HTTPS URLs, inject token
        if self.target_repo_url.startswith("git@"):
            clone_url = self.target_repo_url
        else:
            clone_url = self._build_authenticated_url(self.target_repo_url, self.github_token)
        
        subprocess.run(
            ["git", "clone", "--branch", self.target_branch, "--depth", "1", clone_url, str(self.target_dir)],
            check=True,
            capture_output=True  # Suppress token in output
        )
        
        print(f"✓ Cloned to {self.target_dir}")
    
    def _add_task_to_backlog(self):
        """Add task entry to .leviathan/backlog.yaml."""
        backlog_path = self.target_dir / ".leviathan" / "backlog.yaml"
        
        if not backlog_path.exists():
            raise ValueError(f"Backlog file not found: {backlog_path}")
        
        # Load existing backlog
        with open(backlog_path, 'r') as f:
            backlog_data = yaml.safe_load(f)
        
        # Ensure tasks list exists
        if 'tasks' not in backlog_data:
            backlog_data['tasks'] = []
        
        # Check if task already exists
        existing_ids = {task.get('id') for task in backlog_data['tasks']}
        if self.task_spec['id'] in existing_ids:
            print(f"Task {self.task_spec['id']} already exists in backlog")
            return
        
        # Add new task
        backlog_data['tasks'].append(self.task_spec)
        
        # Write back to file
        with open(backlog_path, 'w') as f:
            yaml.dump(backlog_data, f, default_flow_style=False, sort_keys=False)
        
        print(f"✓ Added task {self.task_spec['id']} to backlog")
    
    def _commit_and_push(self, branch_name: str) -> str:
        """
        Create branch, commit changes, and push.
        
        Args:
            branch_name: Branch name
            
        Returns:
            Commit SHA
        """
        # Configure git
        subprocess.run(
            ["git", "config", "user.email", "leviathan@example.com"],
            cwd=self.target_dir,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Leviathan"],
            cwd=self.target_dir,
            check=True
        )
        
        # Create branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=self.target_dir,
            check=True
        )
        
        # Stage and commit (use -f to force-add even if .leviathan is in .gitignore)
        subprocess.run(
            ["git", "add", "-f", ".leviathan/backlog.yaml"],
            cwd=self.target_dir,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Leviathan: Propose task {self.task_spec['id']}"],
            cwd=self.target_dir,
            check=True
        )
        
        # Get commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.target_dir,
            capture_output=True,
            text=True,
            check=True
        )
        commit_sha = result.stdout.strip()
        
        # Push with authentication
        # For SSH URLs, use as-is (relies on SSH keys)
        # For HTTPS URLs, inject token
        if self.target_repo_url.startswith("git@"):
            push_url = self.target_repo_url
        else:
            push_url = self._build_authenticated_url(self.target_repo_url, self.github_token)
        
        print(f"Pushing branch {branch_name}...")
        subprocess.run(
            ["git", "push", push_url, branch_name],
            cwd=self.target_dir,
            check=True,
            capture_output=True  # Suppress token in output
        )
        
        print(f"✓ Branch pushed: {branch_name}")
        print(f"✓ Commit SHA: {commit_sha}")
        return commit_sha
    
    def _create_pr(self, branch_name: str) -> Tuple[str, int]:
        """
        Create pull request using GitHub API.
        
        Args:
            branch_name: Branch name
            
        Returns:
            Tuple of (pr_url, pr_number)
        """
        print("\nCreating pull request...")
        
        # Extract repo info
        owner, repo = self._extract_repo_info(self.target_repo_url)
        
        # Build PR title and body
        title = f"Leviathan: {self.task_spec['title']}"
        body = f"""**PR Proof v1: Backlog-Only Change**

This PR proposes a new task for the Leviathan backlog.

**Task ID:** `{self.task_spec['id']}`
**Attempt ID:** `{self.attempt_id}`
**Scope:** `{self.task_spec.get('scope', 'unknown')}`
**Priority:** `{self.task_spec.get('priority', 'medium')}`

**Acceptance Criteria:**
{self._format_acceptance_criteria(self.task_spec.get('acceptance_criteria', []))}

**Changes:**
- Modified `.leviathan/backlog.yaml` only
- Added task entry: `{self.task_spec['id']}`

---
*This PR was automatically generated by Leviathan as part of PR Proof v1*
"""
        
        # Create PR
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        data = {
            "title": title,
            "body": body,
            "head": branch_name,
            "base": self.target_branch
        }
        
        response = requests.post(api_url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        
        pr_data = response.json()
        pr_url = pr_data['html_url']
        pr_number = pr_data['number']
        
        print(f"✓ PR created: {pr_url}")
        print(f"✓ PR number: {pr_number}")
        return pr_url, pr_number
    
    def _build_authenticated_url(self, repo_url: str, token: str) -> str:
        """Build authenticated GitHub URL with token."""
        # Sanitize token (strip whitespace/newlines)
        token = token.strip()
        
        # Convert SSH to HTTPS if needed
        if repo_url.startswith("git@github.com:"):
            repo_url = repo_url.replace("git@github.com:", "https://github.com/")
        
        # Inject token using x-access-token format (most compatible)
        if "https://" in repo_url:
            return repo_url.replace("https://", f"https://x-access-token:{token}@")
        
        return repo_url
    
    def _extract_repo_info(self, repo_url: str) -> Tuple[str, str]:
        """Extract owner and repo name from GitHub URL."""
        if "github.com" in repo_url:
            match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', repo_url)
            if match:
                return match.group(1), match.group(2)
        
        raise ValueError(f"Could not parse GitHub repo from URL: {repo_url}")
    
    def _format_acceptance_criteria(self, criteria: list) -> str:
        """Format acceptance criteria as markdown list."""
        if not criteria:
            return "- None specified"
        return "\n".join(f"- {c}" for c in criteria)
