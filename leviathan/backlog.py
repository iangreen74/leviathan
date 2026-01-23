"""
Backlog management for Leviathan agent runner.
Handles loading, parsing, and updating agent_backlog.yaml.
"""
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class Task:
    """Represents a single task from the backlog."""
    id: str
    title: str
    scope: str
    priority: str
    ready: bool
    allowed_paths: List[str]
    acceptance_criteria: List[str]
    dependencies: List[str]
    estimated_size: str
    status: Optional[str] = None  # pr_opened, ready_to_merge, blocked, completed
    pr_number: Optional[int] = None
    branch_name: Optional[str] = None
    
    @property
    def priority_value(self) -> int:
        """Convert priority to numeric value for sorting."""
        return {'high': 3, 'medium': 2, 'low': 1}.get(self.priority, 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for YAML serialization."""
        data = {
            'id': self.id,
            'title': self.title,
            'scope': self.scope,
            'priority': self.priority,
            'ready': self.ready,
            'allowed_paths': self.allowed_paths,
            'acceptance_criteria': self.acceptance_criteria,
            'dependencies': self.dependencies,
            'estimated_size': self.estimated_size,
        }
        if self.status:
            data['status'] = self.status
        if self.pr_number:
            data['pr_number'] = self.pr_number
        if self.branch_name:
            data['branch_name'] = self.branch_name
        return data


class Backlog:
    """Manages the agent backlog."""
    
    def __init__(self, backlog_path: Path):
        self.backlog_path = backlog_path
        self.version: int = 1
        self.max_open_prs: int = 2
        self.tasks: List[Task] = []
        self._load()
    
    def _load(self):
        """Load backlog from YAML file."""
        if not self.backlog_path.exists():
            raise FileNotFoundError(f"Backlog not found: {self.backlog_path}")
        
        with open(self.backlog_path, 'r') as f:
            data = yaml.safe_load(f)
        
        self.version = data.get('version', 1)
        self.max_open_prs = data.get('max_open_prs', 2)
        
        for task_data in data.get('tasks', []):
            task = Task(
                id=task_data['id'],
                title=task_data['title'],
                scope=task_data['scope'],
                priority=task_data['priority'],
                ready=task_data['ready'],
                allowed_paths=task_data['allowed_paths'],
                acceptance_criteria=task_data['acceptance_criteria'],
                dependencies=task_data.get('dependencies', []),
                estimated_size=task_data['estimated_size'],
                status=task_data.get('status'),
                pr_number=task_data.get('pr_number'),
                branch_name=task_data.get('branch_name'),
            )
            self.tasks.append(task)
    
    def save(self):
        """Save backlog to YAML file."""
        data = {
            'version': self.version,
            'max_open_prs': self.max_open_prs,
            'tasks': [task.to_dict() for task in self.tasks]
        }
        
        with open(self.backlog_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_open_pr_count(self) -> int:
        """Count tasks with open PRs."""
        return sum(1 for task in self.tasks if task.status == 'pr_opened')
    
    def sync_pr_open_status(self, open_pr_branches: set[str]):
        """
        Sync task statuses based on actual open PR branches from GitHub.
        
        For any task with status 'pr_opened' whose branch is not in the open PR list,
        mark it as 'completed' (PR was merged or closed).
        
        Args:
            open_pr_branches: Set of branch names that have open PRs
        """
        changed = False
        
        for task in self.tasks:
            if task.status == 'pr_opened':
                # Check if task has a branch name and if it's still open
                if hasattr(task, 'branch_name') and task.branch_name:
                    if task.branch_name not in open_pr_branches:
                        # PR was merged or closed, mark as completed
                        task.status = 'completed'
                        changed = True
        
        # Save if any changes were made
        if changed:
            self.save()
    
    def get_ready_tasks(self) -> List[Task]:
        """Get tasks that are ready to be worked on."""
        ready_tasks = []
        
        for task in self.tasks:
            # Skip if not marked ready
            if not task.ready:
                continue
            
            # Skip if already has a PR or is completed
            if task.status in ['pr_opened', 'ready_to_merge', 'completed']:
                continue
            
            # Check if all dependencies are satisfied
            dependencies_satisfied = True
            for dep_id in task.dependencies:
                dep_task = self.get_task(dep_id)
                if not dep_task or dep_task.status != 'completed':
                    dependencies_satisfied = False
                    break
            
            if dependencies_satisfied:
                ready_tasks.append(task)
        
        # Sort by priority (high to low)
        ready_tasks.sort(key=lambda t: t.priority_value, reverse=True)
        
        return ready_tasks
    
    def select_next_task(self) -> Optional[Task]:
        """Select the next task to work on, respecting max_open_prs."""
        # Check capacity
        if self.get_open_pr_count() >= self.max_open_prs:
            return None
        
        # Get ready tasks
        ready_tasks = self.get_ready_tasks()
        
        # Return highest priority task
        return ready_tasks[0] if ready_tasks else None
    
    def update_task_status(self, task_id: str, status: str, pr_number: Optional[int] = None, branch_name: Optional[str] = None):
        """Update task status and save."""
        task = self.get_task(task_id)
        if task:
            task.status = status
            if pr_number:
                task.pr_number = pr_number
            if branch_name:
                task.branch_name = branch_name
            self.save()
