"""
Backlog update utilities for marking tasks completed.

Updates target repo's .leviathan/backlog.yaml to mark tasks as completed
after successful execution, preventing infinite reruns.
"""
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional


def mark_task_completed(
    backlog_path: Path,
    task_id: str,
    attempt_id: str,
    branch_name: str,
    pr_number: Optional[int] = None
) -> bool:
    """
    Mark task as completed in backlog YAML.
    
    Updates:
    - status: completed
    - ready: false
    - last_attempt_id: <attempt_id>
    - branch_name: <branch_name>
    - pr_number: <pr_number> (if provided, else null)
    - completed_at: <ISO timestamp>
    
    Args:
        backlog_path: Path to .leviathan/backlog.yaml
        task_id: Task ID to mark completed
        attempt_id: Attempt ID that completed the task
        branch_name: Branch name where changes were made
        pr_number: PR number (optional, can be null initially)
    
    Returns:
        True if task was found and updated, False if task not found
    
    Raises:
        ValueError: If backlog file doesn't exist or is invalid
    """
    if not backlog_path.exists():
        raise ValueError(f"Backlog file not found: {backlog_path}")
    
    # Load backlog
    with open(backlog_path, 'r') as f:
        backlog = yaml.safe_load(f)
    
    if not backlog or 'tasks' not in backlog:
        raise ValueError(f"Invalid backlog format: missing 'tasks' key")
    
    # Find and update task
    tasks = backlog['tasks']
    task_found = False
    
    for task in tasks:
        if task.get('id') == task_id:
            task_found = True
            task['status'] = 'completed'
            task['ready'] = False
            task['last_attempt_id'] = attempt_id
            task['branch_name'] = branch_name
            task['pr_number'] = pr_number
            task['completed_at'] = datetime.utcnow().isoformat()
            break
    
    if not task_found:
        return False
    
    # Write updated backlog
    with open(backlog_path, 'w') as f:
        yaml.dump(backlog, f, default_flow_style=False, sort_keys=False)
    
    return True


def is_task_completed(backlog_path: Path, task_id: str) -> bool:
    """
    Check if task is already marked as completed in backlog.
    
    Args:
        backlog_path: Path to .leviathan/backlog.yaml
        task_id: Task ID to check
    
    Returns:
        True if task status is 'completed', False otherwise
    """
    if not backlog_path.exists():
        return False
    
    try:
        with open(backlog_path, 'r') as f:
            backlog = yaml.safe_load(f)
        
        tasks = backlog.get('tasks', [])
        for task in tasks:
            if task.get('id') == task_id:
                return task.get('status') == 'completed'
        
        return False
    except Exception:
        return False
