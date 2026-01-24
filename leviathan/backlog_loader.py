"""
Backlog loader utility for normalizing backlog YAML formats.

Supports both formats:
1. Dict with 'tasks' key: {tasks: [...]}
2. Top-level list: [...]
"""
import yaml
from pathlib import Path
from typing import List, Dict, Any


def load_backlog_tasks(backlog_path: Path) -> List[Dict[str, Any]]:
    """
    Load and normalize backlog tasks from YAML file.
    
    Supports two formats:
    1. Dict with 'tasks' key: {version: 1, tasks: [...]}
    2. Top-level list: [...]
    
    Args:
        backlog_path: Path to backlog YAML file
        
    Returns:
        List of task dicts with normalized 'id' field
        
    Raises:
        FileNotFoundError: If backlog file doesn't exist
        ValueError: If backlog format is invalid
    """
    if not backlog_path.exists():
        raise FileNotFoundError(f"Backlog not found: {backlog_path}")
    
    with open(backlog_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Normalize to list of tasks
    if isinstance(data, dict):
        # Dict format: extract 'tasks' key
        if 'tasks' not in data:
            raise ValueError(
                f"Invalid backlog format in {backlog_path}: "
                f"dict must contain 'tasks' key. Found keys: {list(data.keys())}"
            )
        tasks = data['tasks']
    elif isinstance(data, list):
        # List format: use directly
        tasks = data
    else:
        raise ValueError(
            f"Invalid backlog format in {backlog_path}: "
            f"expected dict or list, got {type(data).__name__}"
        )
    
    # Validate tasks is a list
    if not isinstance(tasks, list):
        raise ValueError(
            f"Invalid backlog format in {backlog_path}: "
            f"'tasks' must be a list, got {type(tasks).__name__}"
        )
    
    # Normalize task dicts to ensure 'id' field exists
    normalized_tasks = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(
                f"Invalid task at index {i} in {backlog_path}: "
                f"expected dict, got {type(task).__name__}"
            )
        
        # Ensure 'id' field exists (some backlogs may use 'task_id')
        if 'id' not in task and 'task_id' in task:
            task['id'] = task['task_id']
        
        if 'id' not in task:
            raise ValueError(
                f"Invalid task at index {i} in {backlog_path}: "
                f"missing 'id' field. Found keys: {list(task.keys())}"
            )
        
        normalized_tasks.append(task)
    
    return normalized_tasks


def filter_ready_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter tasks to only those marked as ready.
    
    Args:
        tasks: List of task dicts
        
    Returns:
        List of ready tasks
    """
    return [task for task in tasks if task.get('ready', False)]
