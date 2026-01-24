"""
Base executor interface for running task attempts.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ArtifactRef:
    """Reference to an artifact produced during attempt execution."""
    path: str
    sha256: str
    artifact_type: str  # log, test_output, diff, model_output, patch
    size_bytes: int


@dataclass
class AttemptResult:
    """Result of executing a task attempt."""
    success: bool
    
    # Success fields
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    artifacts: List[ArtifactRef] = None
    
    # Failure fields
    failure_type: Optional[str] = None  # setup_failed, tests_failed, model_error, timeout
    error_summary: Optional[str] = None
    
    # Common fields
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = []


class Executor(ABC):
    """
    Abstract base class for task attempt executors.
    
    Executors are responsible for:
    1. Setting up execution environment (worktree, container, K8s job, etc.)
    2. Running the task attempt
    3. Collecting artifacts (logs, test outputs, diffs, etc.)
    4. Returning structured result
    """
    
    @abstractmethod
    def run_attempt(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """
        Execute a task attempt.
        
        Args:
            target_id: Target identifier
            task_id: Task identifier
            attempt_id: Attempt identifier
            task_spec: Task specification (title, scope, acceptance_criteria, etc.)
            target_config: Target configuration (repo_url, branch, etc.)
            
        Returns:
            AttemptResult with success/failure and artifacts
        """
        pass
    
    @abstractmethod
    def cleanup(self, attempt_id: str):
        """
        Clean up resources for an attempt.
        
        Args:
            attempt_id: Attempt identifier
        """
        pass
