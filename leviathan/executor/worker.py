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
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

import requests

from leviathan.artifacts.store import ArtifactStore


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
            
            # Load task spec (placeholder - would load from .leviathan/backlog.yaml)
            task_spec = self._load_task_spec()
            
            # Execute task (placeholder - would integrate with runner.py)
            success = self._execute_task(task_spec)
            
            if success:
                # Commit and push
                branch_name = f"agent/{self.task_id}"
                self._commit_and_push(branch_name)
                
                # Create PR (placeholder)
                pr_url = self._create_pr(branch_name)
                
                # Emit success events
                self._emit_event("attempt.succeeded", {
                    'attempt_id': self.attempt_id,
                    'status': 'succeeded',
                    'completed_at': datetime.utcnow().isoformat(),
                    'branch_name': branch_name,
                    'pr_url': pr_url
                })
                
                if pr_url:
                    self._emit_event("pr.created", {
                        'attempt_id': self.attempt_id,
                        'pr_url': pr_url,
                        'title': f"Task {self.task_id}",
                        'state': 'open'
                        # pr_number omitted for placeholder PRs
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
    
    def _load_task_spec(self) -> Dict[str, Any]:
        """
        Load task specification from backlog.
        
        For now, returns placeholder. In full implementation, would:
        - Load .leviathan/backlog.yaml
        - Find task by task_id
        - Return task spec
        """
        return {
            'task_id': self.task_id,
            'title': 'Placeholder task',
            'scope': 'test',
            'priority': 'high',
            'estimated_size': 'small',
            'allowed_paths': [],
            'acceptance_criteria': []
        }
    
    def _execute_task(self, task_spec: Dict[str, Any]) -> bool:
        """
        Execute task.
        
        For now, creates a placeholder log artifact. In full implementation, would:
        - Use rewrite mode to generate code changes
        - Run targeted tests
        - Use repair loop to converge
        - Capture all artifacts (logs, test outputs, model outputs, diffs)
        
        Args:
            task_spec: Task specification
            
        Returns:
            True if successful
        """
        print(f"Executing task: {task_spec['title']}")
        
        # Create placeholder log artifact
        log_content = f"""Worker execution log for {self.attempt_id}

Task: {task_spec['title']}
Scope: {task_spec['scope']}

This is a placeholder execution.
In full implementation, this would:
1. Generate code changes using rewrite mode
2. Run targeted tests
3. Use repair loop to converge
4. Capture all artifacts

Status: Simulated success
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
            'node_id': f"artifact-{uuid.uuid4().hex[:8]}",
            'node_type': 'Artifact',
            'attempt_id': self.attempt_id,
            'sha256': log_artifact_meta['sha256'],
            'artifact_type': 'log',
            'size_bytes': log_artifact_meta['size_bytes'],
            'storage_path': log_artifact_meta['storage_path'],
            'created_at': datetime.utcnow().isoformat()
        })
        
        print("✓ Task execution completed")
        return True
    
    def _commit_and_push(self, branch_name: str):
        """
        Commit changes and push branch.
        
        Args:
            branch_name: Branch name to create
        """
        print(f"Committing and pushing branch: {branch_name}")
        
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
        
        # In full implementation, would have actual changes to commit
        # For now, create a placeholder file
        placeholder_file = self.target_dir / ".leviathan-attempt"
        placeholder_file.write_text(f"Attempt {self.attempt_id}\n")
        
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
        
        # Push (would use GitHub token in URL)
        # For now, skip actual push in placeholder
        print("✓ Branch created (push skipped in placeholder)")
    
    def _create_pr(self, branch_name: str) -> str:
        """
        Create pull request.
        
        Args:
            branch_name: Branch name
            
        Returns:
            PR URL
        """
        print("Creating pull request...")
        
        # In full implementation, would use GitHub API to create PR
        # For now, return placeholder URL
        pr_url = f"https://github.com/org/{self.target_name}/pull/123"
        
        print(f"✓ PR created: {pr_url}")
        return pr_url
    
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
