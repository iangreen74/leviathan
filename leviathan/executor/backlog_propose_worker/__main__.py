#!/usr/bin/env python3
"""
Backlog Propose Worker: Executes a single task attempt.

Invoked by DEV Autonomy Scheduler as a Kubernetes Job.
Fetches task from backlog, creates PR, posts events to control plane.

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
from pathlib import Path
from datetime import datetime

import requests

from leviathan.executor.backlog_propose import BacklogProposer


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
    print("Backlog Propose Worker")
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
            'attempt_number': 1,  # TODO: Get actual attempt number
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
        import subprocess
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        repo_dir = temp_dir / 'repo'
        
        # Build authenticated URL
        clone_url = target_repo_url
        if "https://" in clone_url:
            clone_url = clone_url.replace("https://", f"https://x-access-token:{github_token.strip()}@")
        
        print(f"Cloning {target_repo_url}...")
        subprocess.run(
            ['git', 'clone', '--branch', target_branch, '--depth', '1', clone_url, str(repo_dir)],
            check=True,
            capture_output=True
        )
        print(f"✓ Cloned to {repo_dir}")
        
        # Fetch task spec
        task_spec = fetch_task_from_backlog(repo_dir, task_id)
        print(f"✓ Loaded task spec: {task_spec.get('title', 'N/A')}")
        
        # Cleanup temp clone
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Create proposer
        proposer = BacklogProposer(
            target_name=target_name,
            target_repo_url=target_repo_url,
            target_branch=target_branch,
            task_spec=task_spec,
            attempt_id=attempt_id,
            github_token=github_token,
            workspace=workspace
        )
        
        # Propose task (creates PR)
        pr_url, pr_number, commit_sha = proposer.propose()
        
        # Post pr.created event
        post_event_to_control_plane(
            'pr.created',
            {
                'attempt_id': attempt_id,
                'task_id': task_id,
                'target_id': target_name,
                'pr_number': pr_number,
                'pr_url': pr_url,
                'branch_name': f"agent/backlog-propose-{attempt_id}",
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
        print(f"Branch: agent/backlog-propose-{attempt_id}")
        print(f"Commit SHA: {commit_sha}")
        
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
