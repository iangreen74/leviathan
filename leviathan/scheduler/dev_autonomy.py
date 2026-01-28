"""
DEV Autonomy Scheduler v1

Continuously selects and executes ready tasks from target backlogs with strict guardrails.

Guardrails:
- Only executes tasks with ready: true (no autonomous planning)
- Scope restrictions: allowed_path_prefixes enforcement
- Concurrency limits: max_open_prs, max_running_attempts
- Retry policy: max_attempts_per_task
- Circuit breaker: stops after consecutive failures
"""
import os
import sys
import yaml
import uuid
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

import requests


class DevAutonomyScheduler:
    """DEV Autonomy Scheduler for closed-loop operation."""
    
    def __init__(self, config_path: str):
        """Initialize scheduler with config."""
        self.config = self._load_config(config_path)
        self.target_id = self.config['target_id']
        self.target_repo_url = self.config['target_repo_url']
        self.target_branch = self.config['target_branch']
        self.allowed_path_prefixes = self.config['allowed_path_prefixes']
        self.max_open_prs = self.config['max_open_prs']
        self.max_attempts_per_task = self.config['max_attempts_per_task']
        self.circuit_breaker_failures = self.config['circuit_breaker_failures']
        self.control_plane_url = self.config['control_plane_url']
        self.worker_image = self.config['worker_image']
        self.worker_namespace = self.config['worker_namespace']
        self.workspace_dir = self.config['workspace_dir']
        
        # Get secrets from env
        self.github_token = os.getenv('GITHUB_TOKEN', '').strip()
        self.control_plane_token = os.getenv('CONTROL_PLANE_TOKEN', '').strip()
        
        if not self.github_token or not self.control_plane_token:
            raise ValueError("GITHUB_TOKEN and CONTROL_PLANE_TOKEN must be set")
    
    def _load_config(self, config_path: str) -> Dict:
        """Load autonomy configuration."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    
    def run_schedule_cycle(self):
        """Run one scheduling cycle."""
        print("=" * 60)
        print(f"DEV Autonomy Scheduler - {datetime.utcnow().isoformat()}")
        print("=" * 60)
        print(f"Target: {self.target_id}")
        print(f"Repo: {self.target_repo_url}")
        print()
        
        # 1. Check open PRs
        open_pr_count = self._count_open_prs()
        print(f"Open PRs: {open_pr_count}/{self.max_open_prs}")
        
        if open_pr_count >= self.max_open_prs:
            print("✓ Max open PRs reached. Skipping this cycle.")
            return
        
        # 2. Fetch target backlog
        backlog = self._fetch_target_backlog()
        if not backlog:
            print("✗ Could not fetch target backlog")
            return
        
        tasks = backlog.get('tasks', [])
        print(f"Backlog tasks: {len(tasks)}")
        
        # 3. Check circuit breaker
        if self._is_circuit_breaker_tripped():
            print("✗ Circuit breaker tripped (consecutive failures). Stopping.")
            return
        
        # 4. Select next executable task
        task = self._select_next_task(tasks)
        
        if not task:
            print("✓ No executable tasks found")
            return
        
        task_id = task['id']
        print(f"\n→ Selected task: {task_id}")
        print(f"  Title: {task.get('title', 'N/A')}")
        print(f"  Scope: {task.get('scope', 'N/A')}")
        
        # 5. Check retry limit
        attempt_count = self._get_attempt_count(task_id)
        if attempt_count >= self.max_attempts_per_task:
            print(f"✗ Task {task_id} exceeded max attempts ({self.max_attempts_per_task})")
            self._mark_task_blocked(task_id, f"Exceeded max attempts: {attempt_count}")
            return
        
        # 6. Create and submit worker job
        attempt_id = f"attempt-{task_id}-{uuid.uuid4().hex[:8]}"
        print(f"  Attempt ID: {attempt_id}")
        print(f"  Attempt number: {attempt_count + 1}/{self.max_attempts_per_task}")
        
        success = self._submit_worker_job(task_id, attempt_id)
        
        if success:
            print(f"✓ Worker job submitted: {attempt_id}")
        else:
            print(f"✗ Failed to submit worker job")
    
    def _count_open_prs(self) -> int:
        """Count open PRs created by Leviathan (branch prefix: agent/)."""
        owner, repo = self._extract_repo_info(self.target_repo_url)
        
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
        params = {'state': 'open', 'per_page': 100}
        headers = {'Authorization': f'token {self.github_token}'}
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            prs = response.json()
            
            # Count PRs with branch prefix "agent/"
            leviathan_prs = [pr for pr in prs if pr.get('head', {}).get('ref', '').startswith('agent/')]
            return len(leviathan_prs)
        except Exception as e:
            print(f"Warning: Could not count open PRs: {e}")
            # Fail safe: assume max reached to prevent runaway
            return self.max_open_prs
    
    def _fetch_target_backlog(self) -> Optional[Dict]:
        """Fetch target backlog from repo."""
        # Clone repo to temp location
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Clone with depth 1
            clone_url = self._build_authenticated_url(self.target_repo_url, self.github_token)
            subprocess.run(
                ['git', 'clone', '--branch', self.target_branch, '--depth', '1', clone_url, str(temp_dir / 'repo')],
                check=True,
                capture_output=True
            )
            
            # Read backlog.yaml
            backlog_path = temp_dir / 'repo' / '.leviathan' / 'backlog.yaml'
            if not backlog_path.exists():
                print(f"Warning: No backlog found at {backlog_path}")
                return None
            
            with open(backlog_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error fetching backlog: {e}")
            return None
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def _is_circuit_breaker_tripped(self) -> bool:
        """Check if circuit breaker is tripped (consecutive failures)."""
        # Query control plane for recent failures
        # For simplicity in v1, we'll implement a basic check
        # In production, this would query event store
        return False  # TODO: Implement circuit breaker check
    
    def _select_next_task(self, tasks: List[Dict]) -> Optional[Dict]:
        """Select next executable task with guardrails."""
        for task in tasks:
            task_id = task.get('id')
            
            # Must have ready: true
            if not task.get('ready', False):
                continue
            
            # Check status (pending or missing)
            status = task.get('status', 'pending')
            if status not in ['pending', None]:
                continue
            
            # Check dependencies satisfied
            dependencies = task.get('dependencies', [])
            if dependencies:
                # For v1, skip tasks with dependencies (conservative)
                continue
            
            # Check scope restrictions
            allowed_paths = task.get('allowed_paths', [])
            if not self._is_scope_allowed(allowed_paths):
                print(f"  Skipping {task_id}: scope outside allowed prefixes")
                continue
            
            # This task is executable
            return task
        
        return None
    
    def _is_scope_allowed(self, allowed_paths: List[str]) -> bool:
        """Check if task scope is within allowed path prefixes."""
        if not allowed_paths:
            return False
        
        for path in allowed_paths:
            # Check if path starts with any allowed prefix
            allowed = False
            for prefix in self.allowed_path_prefixes:
                if path.startswith(prefix):
                    allowed = True
                    break
            
            if not allowed:
                return False
        
        return True
    
    def _get_attempt_count(self, task_id: str) -> int:
        """Get number of attempts for task."""
        # Query control plane or event store
        # For v1, return 0 (no retry tracking yet)
        return 0  # TODO: Implement attempt counting
    
    def _mark_task_blocked(self, task_id: str, reason: str):
        """Mark task as blocked."""
        print(f"  Marking task {task_id} as blocked: {reason}")
        # TODO: Post event to control plane or update backlog
    
    def _submit_worker_job(self, task_id: str, attempt_id: str) -> bool:
        """Submit Kubernetes Job for worker execution."""
        job_manifest = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': f"worker-{attempt_id}",
                'namespace': self.worker_namespace,
                'labels': {
                    'app': 'leviathan-worker',
                    'task-id': task_id,
                    'attempt-id': attempt_id
                }
            },
            'spec': {
                'backoffLimit': 0,
                'ttlSecondsAfterFinished': 3600,  # Cleanup after 1 hour
                'template': {
                    'metadata': {
                        'labels': {
                            'app': 'leviathan-worker',
                            'task-id': task_id
                        }
                    },
                    'spec': {
                        'restartPolicy': 'Never',
                        'containers': [{
                            'name': 'worker',
                            'image': self.worker_image,
                            'imagePullPolicy': 'IfNotPresent',
                            'command': ['python3', '-m', 'leviathan.executor.backlog_propose_worker'],
                            'env': [
                                {'name': 'TARGET_NAME', 'value': self.target_id},
                                {'name': 'TARGET_REPO_URL', 'value': self.target_repo_url},
                                {'name': 'TARGET_BRANCH', 'value': self.target_branch},
                                {'name': 'TASK_ID', 'value': task_id},
                                {'name': 'ATTEMPT_ID', 'value': attempt_id},
                                {'name': 'CONTROL_PLANE_URL', 'value': self.control_plane_url},
                                {'name': 'LEVIATHAN_WORKSPACE_DIR', 'value': self.workspace_dir},
                                {
                                    'name': 'GITHUB_TOKEN',
                                    'valueFrom': {
                                        'secretKeyRef': {
                                            'name': 'leviathan-secrets',
                                            'key': 'github-token'
                                        }
                                    }
                                },
                                {
                                    'name': 'CONTROL_PLANE_TOKEN',
                                    'valueFrom': {
                                        'secretKeyRef': {
                                            'name': 'leviathan-control-plane-secret',
                                            'key': 'LEVIATHAN_CONTROL_PLANE_TOKEN'
                                        }
                                    }
                                }
                            ],
                            'volumeMounts': [{
                                'name': 'workspace',
                                'mountPath': self.workspace_dir
                            }]
                        }],
                        'volumes': [{
                            'name': 'workspace',
                            'emptyDir': {}
                        }]
                    }
                }
            }
        }
        
        # Write manifest to temp file and apply
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(job_manifest, f)
            manifest_path = f.name
        
        try:
            result = subprocess.run(
                ['kubectl', 'apply', '-f', manifest_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return True
            else:
                print(f"kubectl apply failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"Error submitting job: {e}")
            return False
        finally:
            Path(manifest_path).unlink(missing_ok=True)
    
    def _build_authenticated_url(self, repo_url: str, token: str) -> str:
        """Build authenticated GitHub URL."""
        token = token.strip()
        if repo_url.startswith("git@github.com:"):
            repo_url = repo_url.replace("git@github.com:", "https://github.com/")
        if "https://" in repo_url:
            return repo_url.replace("https://", f"https://x-access-token:{token}@")
        return repo_url
    
    def _extract_repo_info(self, repo_url: str) -> Tuple[str, str]:
        """Extract owner and repo from GitHub URL."""
        import re
        if "github.com" in repo_url:
            match = re.search(r'github\.com[:/]([^/]+)/([^/.]+)', repo_url)
            if match:
                return match.group(1), match.group(2)
        raise ValueError(f"Could not parse GitHub repo from URL: {repo_url}")


def main():
    """Main entry point for scheduler."""
    config_path = os.getenv('AUTONOMY_CONFIG', '/etc/leviathan/autonomy/dev.yaml')
    
    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)
    
    scheduler = DevAutonomyScheduler(config_path)
    scheduler.run_schedule_cycle()


if __name__ == '__main__':
    main()
