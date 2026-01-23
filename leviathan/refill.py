#!/usr/bin/env python3
"""
Leviathan Backlog Refill Helper

Ensures continuous work supply by maintaining target numbers of ready tasks
per scope, respecting dependencies.

Safety: Does NOT modify repo by default. Use --apply to create PR.
"""
import sys
import yaml
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Set


# Target number of ready tasks per scope
READY_TARGETS = {
    'docs': 2,
    'tests': 3,
    'services': 1
}

# Scopes that should never be auto-marked ready
EXCLUDED_SCOPES = {'infra', 'ci'}


def load_backlog(backlog_path: Path) -> Dict[str, Any]:
    """Load agent backlog YAML."""
    with open(backlog_path, 'r') as f:
        return yaml.safe_load(f)


def save_backlog(backlog_path: Path, backlog: Dict[str, Any]):
    """Save agent backlog YAML."""
    with open(backlog_path, 'w') as f:
        yaml.dump(backlog, f, default_flow_style=False, sort_keys=False)


def get_completed_task_ids(tasks: List[Dict[str, Any]]) -> Set[str]:
    """Get set of completed task IDs."""
    return {task['id'] for task in tasks if task.get('status') == 'completed'}


def dependencies_satisfied(task: Dict[str, Any], completed_ids: Set[str]) -> bool:
    """Check if all dependencies are satisfied."""
    dependencies = task.get('dependencies', [])
    if not dependencies:
        return True
    return all(dep in completed_ids for dep in dependencies)


def count_ready_by_scope(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count ready tasks by scope."""
    counts = {}
    for task in tasks:
        if task.get('ready', False) and task.get('status', '') not in ['completed', 'pr_opened']:
            scope = task.get('scope', 'unknown')
            counts[scope] = counts.get(scope, 0) + 1
    return counts


def calculate_refill_changes(backlog_path: Path) -> tuple[Dict[str, Any], List[str]]:
    """
    Calculate refill changes without modifying anything.
    
    Args:
        backlog_path: Path to agent_backlog.yaml
        
    Returns:
        Tuple of (modified_backlog, list_of_change_descriptions)
    """
    backlog = load_backlog(backlog_path)
    tasks = backlog.get('tasks', [])
    
    completed_ids = get_completed_task_ids(tasks)
    ready_counts = count_ready_by_scope(tasks)
    
    changes = []
    
    for scope, target in READY_TARGETS.items():
        current = ready_counts.get(scope, 0)
        needed = target - current
        
        if needed <= 0:
            continue
        
        print(f"📊 Scope '{scope}': {current}/{target} ready, need {needed} more")
        
        # Find eligible tasks for this scope
        eligible = []
        for task in tasks:
            if (task.get('scope') == scope and
                not task.get('ready', False) and
                task.get('status', '') not in ['completed', 'pr_opened', 'blocked'] and
                dependencies_satisfied(task, completed_ids)):
                eligible.append(task)
        
        # Sort by priority (high > medium > low)
        priority_order = {'high': 3, 'medium': 2, 'low': 1}
        eligible.sort(key=lambda t: priority_order.get(t.get('priority', 'medium'), 2), reverse=True)
        
        # Mark up to 'needed' tasks as ready
        for i, task in enumerate(eligible[:needed]):
            task['ready'] = True
            changes.append(f"  ✅ Marked ready: {task['id']} ({task['title']})")
    
    return backlog, changes


def apply_refill_via_pr(repo_root: Path, backlog_path: Path, modified_backlog: Dict[str, Any], changes: List[str]):
    """
    Apply refill changes via PR workflow.
    
    Creates branch, commits changes, pushes, and opens PR.
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    branch_name = f'agent/backlog-refill-{timestamp}'
    
    print(f"\n🔧 Creating branch: {branch_name}")
    
    # Create branch
    result = subprocess.run(
        ['git', 'checkout', '-b', branch_name],
        cwd=repo_root,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ Failed to create branch: {result.stderr}")
        sys.exit(1)
    
    # Save changes
    save_backlog(backlog_path, modified_backlog)
    print(f"✅ Applied {len(changes)} changes to backlog")
    
    # Commit
    subprocess.run(['git', 'add', str(backlog_path)], cwd=repo_root, check=True)
    
    commit_msg = f"chore(backlog): auto-refill ready tasks\n\nChanges:\n" + "\n".join(changes)
    subprocess.run(
        ['git', 'commit', '-m', commit_msg],
        cwd=repo_root,
        check=True
    )
    print("✅ Committed changes")
    
    # Push
    subprocess.run(
        ['git', 'push', '-u', 'origin', branch_name],
        cwd=repo_root,
        check=True
    )
    print("✅ Pushed branch")
    
    # Create PR using gh CLI or GitHub API
    try:
        from tools.leviathan.github import GitHubClient
        github = GitHubClient(repo_root)
        
        pr_title = f"chore(backlog): auto-refill ready tasks ({len(changes)} tasks)"
        pr_body = f"""Automated backlog refill to maintain target ready tasks per scope.

## Changes

{chr(10).join(changes)}

## Targets
- docs: 2 ready
- tests: 3 ready
- services: 1 ready

Generated by: `python3 tools/leviathan/refill.py --apply`
"""
        
        pr_number, pr_url = github.create_pr(branch_name, pr_title, pr_body)
        
        if pr_number:
            print(f"\n✅ PR created: #{pr_number}")
            print(f"   {pr_url}")
        else:
            print(f"\n⚠️  PR creation via API failed. Manual PR URL:")
            print(f"   {pr_url}")
    except Exception as e:
        print(f"\n⚠️  PR creation failed: {e}")
        print(f"   Create PR manually from branch: {branch_name}")


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent.parent
    backlog_path = repo_root / 'docs/reports/agent_backlog.yaml'
    
    if not backlog_path.exists():
        print(f"❌ Backlog not found: {backlog_path}")
        sys.exit(1)
    
    # Check for --apply flag
    apply_mode = '--apply' in sys.argv
    
    # Calculate changes
    modified_backlog, changes = calculate_refill_changes(backlog_path)
    
    if changes:
        print("\n📝 Proposed Changes:")
        for change in changes:
            print(change)
        
        if apply_mode:
            print("\n🚀 Applying changes via PR...")
            apply_refill_via_pr(repo_root, backlog_path, modified_backlog, changes)
        else:
            print("\n⚠️  No changes applied (dry-run mode)")
            print("\n💡 To apply these changes via PR, run:")
            print("   python3 tools/leviathan/refill.py --apply")
            sys.exit(2)  # Exit code 2 indicates changes available
    else:
        print("\n✅ No refill needed - all scopes at target")
        sys.exit(0)


if __name__ == '__main__':
    main()
