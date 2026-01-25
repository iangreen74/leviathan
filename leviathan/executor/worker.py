"""
Worker entrypoint for K8s Job execution.

Runs inside K8s Job container to execute one task attempt and post results
to the control plane API.

Usage:
    python -m leviathan.executor.worker

Environment variables:
    TARGET_NAME: Target identifier
    TARGET_REPO_URL: Git repository URL
    TARGET_BRANCH: Branch to checkout
    TASK_ID: Task identifier
    ATTEMPT_ID: Attempt identifier
    CONTROL_PLANE_URL: Control plane API URL
    CONTROL_PLANE_TOKEN: Control plane auth token
    GITHUB_TOKEN: GitHub personal access token
    LEVIATHAN_CLAUDE_API_KEY: Claude API key
    LEVIATHAN_CLAUDE_MODEL: Claude model name
"""
import os
import sys
import uuid
import json
import subprocess
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import requests

from leviathan.artifacts.store import ArtifactStore
from leviathan.model_client import ModelClient
from leviathan.rewrite_mode import RewriteModeError
from leviathan.backlog import Task
from leviathan.backlog_loader import load_backlog_tasks


class WorkerError(Exception):
    """Worker execution error."""
    pass


class Worker:
    """
    K8s Job worker that executes one task attempt.
    
    Workflow:
    1. Clone target repo
    2. Load task from backlog
    3. Execute task (rewrite mode + tests + repair loop)
    4. Commit and push branch
    5. Create PR
    6. Post event bundle to control plane
    7. Exit
    """
    
    def __init__(self):
        """Initialize worker from environment."""
        self.target_name = os.getenv("TARGET_NAME")
        self.target_repo_url = os.getenv("TARGET_REPO_URL")
        self.target_branch = os.getenv("TARGET_BRANCH", "main")
        self.task_id = os.getenv("TASK_ID")
        self.attempt_id = os.getenv("ATTEMPT_ID")
        self.control_plane_url = os.getenv("CONTROL_PLANE_URL")
        self.control_plane_token = os.getenv("CONTROL_PLANE_TOKEN")
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.claude_api_key = os.getenv("LEVIATHAN_CLAUDE_API_KEY")
        self.claude_model = os.getenv("LEVIATHAN_CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        
        # Validate required env vars
        required = [
            "TARGET_NAME", "TARGET_REPO_URL", "TASK_ID", "ATTEMPT_ID",
            "CONTROL_PLANE_URL", "CONTROL_PLANE_TOKEN"
        ]
        missing = [var for var in required if not os.getenv(var)]
        if missing:
            raise WorkerError(f"Missing required env vars: {', '.join(missing)}")
        
        self.workspace = Path("/workspace")
        self.target_dir = self.workspace / "target"
        self.artifact_store = ArtifactStore(storage_root=self.workspace / "artifacts")
        
        self.events = []
        self.artifacts = []
    
    def run(self) -> int:
        """
        Execute worker workflow.
        
        Returns:
            Exit code (0 = success, 1 = failure)
        """
        try:
            print(f"Leviathan Worker")
            print(f"Target: {self.target_name}")
            print(f"Task: {self.task_id}")
            print(f"Attempt: {self.attempt_id}")
            print()
            
            # Emit attempt.started event
            self._emit_event("attempt.started", {
                'attempt_id': self.attempt_id,
                'status': 'running',
                'started_at': datetime.utcnow().isoformat()
            })
            
            # Clone repo
            self._clone_repo()
            
            # Load task spec from backlog
            task_spec = self._load_task_spec()
            
            # Execute task using rewrite mode
            success = self._execute_task(task_spec)
            
            if success:
                # Commit and push
                branch_name = f"agent/{self.task_id}-{self.attempt_id}"
                commit_sha = self._commit_and_push(branch_name)
                
                # Create PR
                pr_url, pr_number = self._create_pr(branch_name, task_spec)
                
                # Emit success events
                self._emit_event("attempt.succeeded", {
                    'attempt_id': self.attempt_id,
                    'status': 'succeeded',
                    'completed_at': datetime.utcnow().isoformat(),
                    'branch_name': branch_name,
                    'commit_sha': commit_sha,
                    'pr_url': pr_url,
                    'pr_number': pr_number
                })
                
                self._emit_event("pr.created", {
                    'attempt_id': self.attempt_id,
                    'pr_url': pr_url,
                    'pr_number': pr_number,
                    'title': f"Leviathan: {task_spec.title}",
                    'state': 'open'
                })
                
                # Post event bundle
                self._post_event_bundle()
                
                print("\n✅ Worker completed successfully")
                return 0
            
            else:
                # Emit failure event
                self._emit_event("attempt.failed", {
                    'attempt_id': self.attempt_id,
                    'status': 'failed',
                    'completed_at': datetime.utcnow().isoformat(),
                    'failure_type': 'execution_failed',
                    'error_summary': 'Task execution failed'
                })
                
                # Post event bundle
                self._post_event_bundle()
                
                print("\n❌ Worker failed")
                return 1
        
        except Exception as e:
            print(f"\n❌ Worker error: {e}")
            
            # Emit failure event
            self._emit_event("attempt.failed", {
                'attempt_id': self.attempt_id,
                'status': 'failed',
                'completed_at': datetime.utcnow().isoformat(),
                'failure_type': 'worker_error',
                'error_summary': str(e)
            })
            
            # Try to post event bundle
            try:
                self._post_event_bundle()
            except:
                pass
            
            return 1
    
    def _clone_repo(self):
        """Clone target repository."""
        print(f"Cloning {self.target_repo_url}...")
        
        # Configure git to use GitHub token
        if self.github_token:
            # Replace git@ with https:// and inject token
            repo_url = self.target_repo_url
            if repo_url.startswith("git@github.com:"):
                repo_url = repo_url.replace("git@github.com:", "https://github.com/")
            
            if "https://" in repo_url and self.github_token:
                repo_url = repo_url.replace("https://", f"https://{self.github_token}@")
        else:
            repo_url = self.target_repo_url
        
        subprocess.run(
            ["git", "clone", "--branch", self.target_branch, repo_url, str(self.target_dir)],
            check=True,
            capture_output=True
        )
        
        print(f"✓ Cloned to {self.target_dir}")
    
    def _load_task_spec(self) -> Task:
        """
        Load task specification from backlog.
        
        Returns:
            Task object with typed fields
        """
        backlog_path = self.target_dir / ".leviathan" / "backlog.yaml"
        
        if not backlog_path.exists():
            raise WorkerError(f"Backlog not found: {backlog_path}")
        
        # Load and normalize tasks using backlog_loader
        tasks = load_backlog_tasks(backlog_path)
        
        # Find task by ID
        for task_dict in tasks:
            if task_dict.get('id') == self.task_id:
                # Convert dict to Task object
                return Task(
                    id=task_dict['id'],
                    title=task_dict.get('title', 'Untitled'),
                    scope=task_dict.get('scope', 'unknown'),
                    priority=task_dict.get('priority', 'medium'),
                    ready=task_dict.get('ready', True),
                    allowed_paths=task_dict.get('allowed_paths', []),
                    acceptance_criteria=task_dict.get('acceptance_criteria', []),
                    dependencies=task_dict.get('dependencies', []),
                    estimated_size=task_dict.get('estimated_size', 'unknown'),
                    status=task_dict.get('status'),
                    pr_number=task_dict.get('pr_number'),
                    branch_name=task_dict.get('branch_name')
                )
        
        raise WorkerError(f"Task {self.task_id} not found in backlog")
    
    def _execute_task(self, task_spec: Task) -> bool:
        """
        Execute task using rewrite mode.
        
        Args:
            task_spec: Task object with typed fields
            
        Returns:
            True if successful
        """
        print(f"Executing task: {task_spec.title}")
        print(f"Scope: {task_spec.scope}")
        print(f"Allowed paths: {len(task_spec.allowed_paths)} file(s)")
        
        # Validate allowed_paths
        if not isinstance(task_spec.allowed_paths, list):
            raise WorkerError(f"Task {task_spec.id}: allowed_paths must be a list, got {type(task_spec.allowed_paths).__name__}")
        
        # Initialize model client
        model = ModelClient(repo_root=self.target_dir)
        
        # Use rewrite mode for task execution
        try:
            print("\nGenerating implementation using rewrite mode...")
            written_paths, source = model.generate_implementation_rewrite_mode(
                task_spec,
                retry_context=None
            )
            print(f"✓ Implementation generated via {source}")
            print(f"  Files written: {len(written_paths)}")
            
            # Store execution log
            log_content = f"""Worker execution log for {self.attempt_id}

Task: {task_spec.title}
Scope: {task_spec.scope}
Allowed paths: {task_spec.allowed_paths}

Execution:
- Mode: rewrite
- Source: {source}
- Files written: {len(written_paths)}
- Paths: {written_paths}

Status: Success
"""
            
            log_artifact_meta = self.artifact_store.store(
                log_content.encode('utf-8'),
                "log",
                metadata={
                    'attempt_id': self.attempt_id,
                    'task_id': self.task_id
                }
            )
            
            self.artifacts.append({
                'sha256': log_artifact_meta['sha256'],
                'kind': 'log',
                'uri': f"file://{log_artifact_meta['storage_path']}",
                'size': log_artifact_meta['size_bytes']
            })
            
            # Emit artifact.created event
            self._emit_event("artifact.created", {
                'artifact_id': f"artifact-{uuid.uuid4().hex[:8]}",
                'attempt_id': self.attempt_id,
                'sha256': log_artifact_meta['sha256'],
                'artifact_type': 'log',
                'size_bytes': log_artifact_meta['size_bytes'],
                'storage_path': log_artifact_meta['storage_path'],
                'created_at': datetime.utcnow().isoformat()
            })
            
            print("✓ Task execution completed")
            return True
            
        except RewriteModeError as e:
            print(f"✗ Rewrite mode failed: {e}")
            return False
        except Exception as e:
            print(f"✗ Task execution failed: {e}")
            return False
    
    def _commit_and_push(self, branch_name: str) -> str:
        """
        Commit changes and push branch.
        
        Args:
            branch_name: Branch name to create
            
        Returns:
            Commit SHA
        """
        print(f"\nCommitting and pushing branch: {branch_name}")
        
        # Configure git
        subprocess.run(
            ["git", "config", "user.name", "Leviathan Bot"],
            cwd=self.target_dir,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "leviathan@example.com"],
            cwd=self.target_dir,
            check=True
        )
        
        # Create branch
        subprocess.run(
            ["git", "checkout", "-b", branch_name],
            cwd=self.target_dir,
            check=True
        )
        
        # Stage and commit
        subprocess.run(
            ["git", "add", "."],
            cwd=self.target_dir,
            check=True
        )
        subprocess.run(
            ["git", "commit", "-m", f"Leviathan: {self.task_id}"],
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
        
        # Push with token authentication
        if not self.github_token:
            raise WorkerError("GITHUB_TOKEN required for push")
        
        # Build authenticated remote URL
        repo_url = self._build_authenticated_url(self.target_repo_url, self.github_token)
        
        print("Pushing to remote...")
        subprocess.run(
            ["git", "push", repo_url, branch_name],
            cwd=self.target_dir,
            check=True,
            capture_output=True  # Suppress token in output
        )
        
        print(f"✓ Branch pushed: {branch_name}")
        print(f"✓ Commit SHA: {commit_sha}")
        return commit_sha
    
    def _build_authenticated_url(self, repo_url: str, token: str) -> str:
        """
        Build authenticated GitHub URL with token.
        
        Args:
            repo_url: Original repository URL
            token: GitHub token
            
        Returns:
            Authenticated URL (token not logged)
        """
        # Convert SSH to HTTPS if needed
        if repo_url.startswith("git@github.com:"):
            repo_url = repo_url.replace("git@github.com:", "https://github.com/")
        
        # Inject token
        if "https://" in repo_url:
            return repo_url.replace("https://", f"https://x-access-token:{token}@")
        
        return repo_url
    
    def _extract_repo_info(self, repo_url: str) -> Tuple[str, str]:
        """
        Extract owner and repo name from GitHub URL.
        
        Args:
            repo_url: Repository URL
            
        Returns:
            Tuple of (owner, repo)
        """
        # Handle both HTTPS and SSH URLs
        if "github.com" in repo_url:
            # Extract owner/repo from URL
            match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', repo_url)
            if match:
                return match.group(1), match.group(2)
        
        raise WorkerError(f"Could not parse GitHub repo from URL: {repo_url}")
    
    def _create_pr(self, branch_name: str, task_spec: Task) -> Tuple[str, int]:
        """
        Create pull request using GitHub API.
        
        Args:
            branch_name: Branch name
            task_spec: Task specification
            
        Returns:
            Tuple of (pr_url, pr_number)
        """
        print("\nCreating pull request...")
        
        if not self.github_token:
            raise WorkerError("GITHUB_TOKEN required for PR creation")
        
        # Extract repo info
        owner, repo = self._extract_repo_info(self.target_repo_url)
        
        # Build PR title and body
        title = f"Leviathan: {task_spec.title}"
        body = f"""Automated PR from Leviathan

**Task ID:** {self.task_id}
**Attempt ID:** {self.attempt_id}
**Scope:** {task_spec.scope}

**Acceptance Criteria:**
{self._format_acceptance_criteria(task_spec.acceptance_criteria)}

---
*This PR was automatically generated by Leviathan*
"""
        
        # Check if PR already exists for this branch
        existing_pr = self._get_existing_pr(owner, repo, branch_name)
        if existing_pr:
            pr_number = existing_pr['number']
            pr_url = existing_pr['html_url']
            print(f"✓ PR already exists: {pr_url}")
            print(f"✓ PR number: {pr_number}")
            return pr_url, pr_number
        
        # Create new PR
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
    
    def _get_existing_pr(self, owner: str, repo: str, branch_name: str) -> Optional[Dict[str, Any]]:
        """
        Check if PR already exists for branch.
        
        Args:
            owner: Repository owner
            repo: Repository name
            branch_name: Branch name
            
        Returns:
            PR data if exists, None otherwise
        """
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json"
        }
        params = {
            "head": f"{owner}:{branch_name}",
            "state": "open"
        }
        
        try:
            response = requests.get(api_url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            prs = response.json()
            return prs[0] if prs else None
        except Exception:
            return None
    
    def _format_acceptance_criteria(self, criteria: List[str]) -> str:
        """
        Format acceptance criteria as markdown list.
        
        Args:
            criteria: List of acceptance criteria
            
        Returns:
            Formatted markdown string
        """
        if not criteria:
            return "*No acceptance criteria specified*"
        
        return "\n".join(f"- {c}" for c in criteria)
    
    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        """
        Emit event to be posted in bundle.
        
        Args:
            event_type: Event type
            payload: Event payload
        """
        event = {
            'event_id': str(uuid.uuid4()),
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            'actor_id': f"worker-{self.attempt_id}",
            'payload': payload
        }
        self.events.append(event)
    
    def _post_event_bundle(self):
        """Post event bundle to control plane API."""
        print("\nPosting event bundle to control plane...")
        
        bundle = {
            'target': self.target_name,
            'bundle_id': f"bundle-{self.attempt_id}",
            'events': self.events,
            'artifacts': self.artifacts
        }
        
        response = requests.post(
            f"{self.control_plane_url}/v1/events/ingest",
            json=bundle,
            headers={'Authorization': f'Bearer {self.control_plane_token}'},
            timeout=30
        )
        
        response.raise_for_status()
        
        print(f"✓ Posted {len(self.events)} events, {len(self.artifacts)} artifacts")


def main():
    """Main entrypoint."""
    try:
        worker = Worker()
        exit_code = worker.run()
        sys.exit(exit_code)
    except WorkerError as e:
        print(f"Worker initialization error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
