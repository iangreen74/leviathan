#!/usr/bin/env python3
"""
Task Worker: Executes tasks from backlog by generating/modifying files.

Invoked by DEV Autonomy Scheduler as a Kubernetes Job.
Fetches task from backlog, executes it, creates PR, posts events to control plane.

Environment variables required:
    GITHUB_TOKEN: GitHub personal access token
    TARGET_NAME: Target identifier (e.g., 'radix')
    TARGET_REPO_URL: Git repository URL
    TARGET_BRANCH: Target branch
    TASK_ID: Task ID to execute
    ATTEMPT_ID: Unique attempt identifier
    CONTROL_PLANE_URL: Control plane API URL
    CONTROL_PLANE_TOKEN: Control plane authentication token
    LEVIATHAN_WORKSPACE_DIR: Workspace directory
"""
import os
import sys
import uuid
import yaml
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional

import requests

from leviathan.executor.task_exec import execute_task, PathViolationError


def post_event_to_control_plane(event_type: str, payload: dict, control_plane_url: str, token: str, actor_id: str):
    """Post event to control plane."""
    bundle = {
        'target': payload.get('target_id', 'unknown'),
        'bundle_id': f"bundle-{payload.get('attempt_id', 'unknown')}",
        'events': [{
            'event_id': str(uuid.uuid4()),
            'event_type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            'actor_id': actor_id,
            'payload': payload
        }],
        'artifacts': []
    }
    
    response = requests.post(
        f"{control_plane_url}/v1/events/ingest",
        json=bundle,
        headers={'Authorization': f'Bearer {token}'},
        timeout=30
    )
    response.raise_for_status()
    print(f"✓ Posted {event_type} event to control plane")


def fetch_task_from_backlog(repo_path: Path, task_id: str) -> dict:
    """Fetch task spec from backlog."""
    backlog_path = repo_path / '.leviathan' / 'backlog.yaml'
    
    if not backlog_path.exists():
        raise ValueError(f"Backlog not found: {backlog_path}")
    
    with open(backlog_path, 'r') as f:
        backlog = yaml.safe_load(f)
    
    tasks = backlog.get('tasks', [])
    for task in tasks:
        if task.get('id') == task_id:
            return task
    
    raise ValueError(f"Task {task_id} not found in backlog")


def clone_repo(repo_url: str, branch: str, github_token: str, dest: Path) -> None:
    """Clone repository to destination."""
    # Build authenticated URL
    clone_url = repo_url
    if "https://" in clone_url:
        clone_url = clone_url.replace("https://", f"https://x-access-token:{github_token.strip()}@")
    
    print(f"Cloning {repo_url}...")
    subprocess.run(
        ['git', 'clone', '--branch', branch, '--depth', '1', clone_url, str(dest)],
        check=True,
        capture_output=True
    )
    print(f"✓ Cloned to {dest}")


def create_branch_and_commit(repo_path: Path, branch_name: str, task_title: str, changed_files: list) -> Optional[str]:
    """
    Create branch, commit changes, and return commit SHA.
    Returns None if no changes to commit.
    """
    os.chdir(repo_path)
    
    # Configure git user
    subprocess.run(['git', 'config', 'user.name', 'Leviathan Autonomy'], check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'leviathan@autonomy.local'], check=True, capture_output=True)
    
    # Create and checkout branch
    subprocess.run(['git', 'checkout', '-b', branch_name], check=True, capture_output=True)
    print(f"✓ Created branch: {branch_name}")
    
    # Check if there are changes
    status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
    if not status.stdout.strip():
        print("✓ No changes to commit (task is idempotent)")
        return None
    
    # Add changed files
    for file_path in changed_files:
        subprocess.run(['git', 'add', file_path], check=True, capture_output=True)
    
    # Commit
    commit_message = f"feat(leviathan): {task_title}"
    subprocess.run(['git', 'commit', '-m', commit_message], check=True, capture_output=True)
    
    # Get commit SHA
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True)
    commit_sha = result.stdout.strip()
    print(f"✓ Committed changes: {commit_sha[:8]}")
    
    return commit_sha


def push_branch(repo_path: Path, branch_name: str) -> None:
    """Push branch to remote."""
    os.chdir(repo_path)
    subprocess.run(['git', 'push', 'origin', branch_name], check=True, capture_output=True)
    print(f"✓ Pushed branch: {branch_name}")


def create_pr(repo_url: str, branch_name: str, task_spec: dict, github_token: str) -> Tuple[str, int]:
    """Create pull request and return (pr_url, pr_number)."""
    # Extract owner/repo from URL
    parts = repo_url.replace('https://github.com/', '').replace('.git', '').split('/')
    owner, repo = parts[0], parts[1]
    
    task_id = task_spec.get('id', 'unknown')
    task_title = task_spec.get('title', 'Unknown task')
    scope = task_spec.get('scope', 'unknown')
    
    pr_title = f"feat({scope}): {task_title}"
    pr_body = f"""## Task Execution

**Task ID:** `{task_id}`  
**Scope:** `{scope}`  
**Executor:** Leviathan Task Worker v1

## Changes

This PR was autonomously generated by Leviathan to execute task `{task_id}` from the backlog.

### Acceptance Criteria

"""
    
    for criterion in task_spec.get('acceptance_criteria', []):
        pr_body += f"- {criterion}\n"
    
    pr_body += """
## Review Notes

- All changes are within task's `allowed_paths`
- Task execution is deterministic and auditable
- No auto-merge; human review required

---

*Generated by Leviathan Autonomy v1*
"""
    
    # Create PR via GitHub API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    response = requests.post(
        api_url,
        json={
            'title': pr_title,
            'head': branch_name,
            'base': 'main',
            'body': pr_body
        },
        headers={
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        },
        timeout=30
    )
    response.raise_for_status()
    
    pr_data = response.json()
    pr_url = pr_data['html_url']
    pr_number = pr_data['number']
    
    print(f"✓ Created PR #{pr_number}: {pr_url}")
    return pr_url, pr_number


def main():
    """Run worker for single task attempt."""
    # Required env vars
    required_vars = [
        'GITHUB_TOKEN',
        'TARGET_NAME',
        'TARGET_REPO_URL',
        'TASK_ID',
        'ATTEMPT_ID',
        'CONTROL_PLANE_URL',
        'CONTROL_PLANE_TOKEN'
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"Error: Missing required env vars: {', '.join(missing)}")
        sys.exit(1)
    
    # Get env vars
    github_token = os.getenv('GITHUB_TOKEN')
    target_name = os.getenv('TARGET_NAME')
    target_repo_url = os.getenv('TARGET_REPO_URL')
    target_branch = os.getenv('TARGET_BRANCH', 'main')
    task_id = os.getenv('TASK_ID')
    attempt_id = os.getenv('ATTEMPT_ID')
    control_plane_url = os.getenv('CONTROL_PLANE_URL')
    control_plane_token = os.getenv('CONTROL_PLANE_TOKEN')
    workspace_dir = Path(os.getenv('LEVIATHAN_WORKSPACE_DIR', '/tmp/leviathan-workspace'))
    
    # Create workspace
    workspace = workspace_dir / attempt_id
    workspace.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("Leviathan Task Worker v1")
    print("=" * 60)
    print(f"Target: {target_name}")
    print(f"Repo: {target_repo_url}")
    print(f"Task: {task_id}")
    print(f"Attempt: {attempt_id}")
    print()
    
    actor_id = f"worker-{attempt_id}"
    
    # Post attempt.created
    post_event_to_control_plane(
        'attempt.created',
        {
            'attempt_id': attempt_id,
            'task_id': task_id,
            'target_id': target_name,
            'attempt_number': 1,
            'status': 'created'
        },
        control_plane_url,
        control_plane_token,
        actor_id
    )
    
    # Post attempt.started
    post_event_to_control_plane(
        'attempt.started',
        {
            'attempt_id': attempt_id,
            'task_id': task_id,
            'target_id': target_name,
            'status': 'running'
        },
        control_plane_url,
        control_plane_token,
        actor_id
    )
    
    try:
        # Clone repo to get task spec
        temp_dir = Path(tempfile.mkdtemp())
        spec_repo = temp_dir / 'spec_repo'
        clone_repo(target_repo_url, target_branch, github_token, spec_repo)
        
        # Fetch task spec
        task_spec = fetch_task_from_backlog(spec_repo, task_id)
        print(f"✓ Loaded task spec: {task_spec.get('title', 'N/A')}")
        
        # Cleanup temp clone
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Clone repo for execution
        repo_path = workspace / 'target'
        clone_repo(target_repo_url, target_branch, github_token, repo_path)
        
        # Execute task
        print(f"\nExecuting task: {task_id}")
        print(f"Scope: {task_spec.get('scope', 'unknown')}")
        print(f"Allowed paths: {task_spec.get('allowed_paths', [])}")
        print()
        
        exec_result = execute_task(task_spec, str(repo_path))
        
        if not exec_result.success:
            raise RuntimeError(f"Task execution failed: {exec_result.error}")
        
        print(f"✓ Task executed successfully")
        if exec_result.changed_files:
            print(f"  Changed files: {', '.join(exec_result.changed_files)}")
        else:
            print(f"  No files changed (idempotent)")
        
        # Create branch and commit
        branch_name = f"agent/task-exec-{attempt_id}"
        commit_sha = create_branch_and_commit(
            repo_path,
            branch_name,
            task_spec.get('title', 'Task execution'),
            exec_result.changed_files
        )
        
        # If no changes, succeed without creating PR
        if commit_sha is None:
            post_event_to_control_plane(
                'attempt.succeeded',
                {
                    'attempt_id': attempt_id,
                    'task_id': task_id,
                    'target_id': target_name,
                    'status': 'succeeded',
                    'note': 'No changes needed (task already satisfied)'
                },
                control_plane_url,
                control_plane_token,
                actor_id
            )
            
            print()
            print("=" * 60)
            print("✅ Worker Complete (No Changes)")
            print("=" * 60)
            print("Task already satisfied, no PR created")
            return
        
        # Push branch
        push_branch(repo_path, branch_name)
        
        # Create PR
        pr_url, pr_number = create_pr(target_repo_url, branch_name, task_spec, github_token)
        
        # Post pr.created event
        post_event_to_control_plane(
            'pr.created',
            {
                'attempt_id': attempt_id,
                'task_id': task_id,
                'target_id': target_name,
                'pr_number': pr_number,
                'pr_url': pr_url,
                'branch_name': branch_name,
                'commit_sha': commit_sha
            },
            control_plane_url,
            control_plane_token,
            actor_id
        )
        
        # Post attempt.succeeded
        post_event_to_control_plane(
            'attempt.succeeded',
            {
                'attempt_id': attempt_id,
                'task_id': task_id,
                'target_id': target_name,
                'status': 'succeeded',
                'pr_number': pr_number,
                'pr_url': pr_url
            },
            control_plane_url,
            control_plane_token,
            actor_id
        )
        
        print()
        print("=" * 60)
        print("✅ Worker Complete")
        print("=" * 60)
        print(f"PR URL: {pr_url}")
        print(f"PR Number: {pr_number}")
        print(f"Branch: {branch_name}")
        print(f"Commit SHA: {commit_sha}")
        
    except PathViolationError as e:
        # Post attempt.failed with path violation
        post_event_to_control_plane(
            'attempt.failed',
            {
                'attempt_id': attempt_id,
                'task_id': task_id,
                'target_id': target_name,
                'status': 'failed',
                'failure_type': 'path_violation',
                'error_summary': str(e)
            },
            control_plane_url,
            control_plane_token,
            actor_id
        )
        
        print(f"\n❌ Path Violation Error: {e}")
        sys.exit(1)
        
    except Exception as e:
        # Post attempt.failed
        post_event_to_control_plane(
            'attempt.failed',
            {
                'attempt_id': attempt_id,
                'task_id': task_id,
                'target_id': target_name,
                'status': 'failed',
                'failure_type': 'execution_error',
                'error_summary': str(e)
            },
            control_plane_url,
            control_plane_token,
            actor_id
        )
        
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
