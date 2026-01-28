#!/usr/bin/env python3
"""
PR Proof v1: Create a real GitHub PR against Radix that modifies only .leviathan/backlog.yaml

This script:
1. Creates a task entry for PR proof
2. Uses BacklogProposer to add it to Radix's backlog.yaml
3. Creates a PR via GitHub API
4. Posts events to control plane
5. Returns PR URL and metadata
"""
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from leviathan.executor.backlog_propose import BacklogProposer
import requests


def post_event_to_control_plane(event_type: str, payload: dict, control_plane_url: str, token: str, actor_id: str):
    """Post event to control plane."""
    bundle = {
        'target': payload.get('target_id', 'radix'),
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


def main():
    """Run PR Proof v1."""
    # Required env vars
    required_vars = [
        'GITHUB_TOKEN',
        'TARGET_NAME',
        'TARGET_REPO_URL',
        'CONTROL_PLANE_URL',
        'CONTROL_PLANE_TOKEN',
        'ATTEMPT_ID'
    ]
    
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        print(f"Error: Missing required env vars: {', '.join(missing)}")
        sys.exit(1)
    
    # Get env vars
    github_token = os.getenv('GITHUB_TOKEN')
    target_name = os.getenv('TARGET_NAME', 'radix')
    target_repo_url = os.getenv('TARGET_REPO_URL')
    target_branch = os.getenv('TARGET_BRANCH', 'main')
    attempt_id = os.getenv('ATTEMPT_ID')
    control_plane_url = os.getenv('CONTROL_PLANE_URL')
    control_plane_token = os.getenv('CONTROL_PLANE_TOKEN')
    workspace_dir = Path(os.getenv('LEVIATHAN_WORKSPACE_DIR', '/tmp/leviathan-workspace'))
    
    # Task spec for PR proof
    task_id = 'pr-proof-v1-backlog-only'
    task_spec = {
        'id': task_id,
        'title': 'PR Proof v1: backlog-only change (Leviathan)',
        'scope': 'docs',
        'priority': 'high',
        'ready': True,
        'estimated_size': 'xs',
        'allowed_paths': ['.leviathan/backlog.yaml'],
        'acceptance_criteria': [
            'PR modifies only .leviathan/backlog.yaml',
            'PR contains this new task entry',
            'No other files changed'
        ],
        'dependencies': []
    }
    
    # Create workspace
    workspace = workspace_dir / attempt_id
    workspace.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("PR Proof v1: Backlog-Only PR Creation")
    print("=" * 60)
    print(f"Target: {target_name}")
    print(f"Repo: {target_repo_url}")
    print(f"Task: {task_id}")
    print(f"Attempt: {attempt_id}")
    print()
    
    actor_id = f"pr-proof-script-{attempt_id}"
    
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
        print("✅ PR Proof v1 Complete")
        print("=" * 60)
        print(f"PR URL: {pr_url}")
        print(f"PR Number: {pr_number}")
        print(f"Branch: agent/backlog-propose-{attempt_id}")
        print(f"Commit SHA: {commit_sha}")
        print()
        print("Verify with:")
        print(f"  gh pr view {pr_number} --repo {target_repo_url}")
        print(f"  curl -H 'Authorization: Bearer {control_plane_token}' \\")
        print(f"    {control_plane_url}/v1/graph/summary")
        
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
        sys.exit(1)


if __name__ == '__main__':
    main()
