"""
Local worktree executor - runs attempts in git worktrees.

Reuses existing worktree and runner logic.
"""
import os
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from leviathan.executors.base import Executor, AttemptResult, ArtifactRef
from leviathan.artifacts.store import ArtifactStore


class LocalWorktreeExecutor(Executor):
    """
    Executor that runs attempts in local git worktrees.
    
    Reuses existing runner logic but wraps it in the Executor interface.
    """
    
    def __init__(self, worktree_base: Path = None, artifact_store: ArtifactStore = None):
        """
        Initialize local worktree executor.
        
        Args:
            worktree_base: Base directory for worktrees (default: ~/.leviathan/worktrees)
            artifact_store: Artifact store for storing logs/outputs
        """
        if worktree_base is None:
            worktree_base = Path.home() / ".leviathan" / "worktrees"
        
        self.worktree_base = worktree_base
        self.worktree_base.mkdir(parents=True, exist_ok=True)
        
        if artifact_store is None:
            artifact_store = ArtifactStore()
        
        self.artifact_store = artifact_store
    
    def run_attempt(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """
        Execute task attempt in local worktree.
        
        For now, this is a simplified implementation that:
        1. Creates a worktree directory
        2. Simulates execution (actual runner integration in future PR)
        3. Collects artifacts
        4. Returns result
        
        Args:
            target_id: Target identifier
            task_id: Task identifier
            attempt_id: Attempt identifier
            task_spec: Task specification
            target_config: Target configuration
            
        Returns:
            AttemptResult
        """
        started_at = datetime.utcnow()
        
        # Create worktree directory
        worktree_path = self.worktree_base / attempt_id
        worktree_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # TODO: Integrate with existing runner.py logic
            # For now, create a simple log artifact
            log_content = f"""Attempt {attempt_id} for task {task_id}
Target: {target_id}
Task: {task_spec.get('title', 'Unknown')}
Scope: {task_spec.get('scope', 'Unknown')}

This is a placeholder execution.
In PR #4, this will integrate with the full runner logic.
"""
            
            # Store log artifact
            log_artifact_meta = self.artifact_store.store(
                log_content.encode('utf-8'),
                "log",
                metadata={
                    'attempt_id': attempt_id,
                    'task_id': task_id,
                    'target_id': target_id
                }
            )
            
            artifacts = [
                ArtifactRef(
                    path=log_artifact_meta['storage_path'],
                    sha256=log_artifact_meta['sha256'],
                    artifact_type='log',
                    size_bytes=log_artifact_meta['size_bytes']
                )
            ]
            
            completed_at = datetime.utcnow()
            
            # Simulate success for now
            return AttemptResult(
                success=True,
                branch_name=f"leviathan/{task_id}",
                artifacts=artifacts,
                started_at=started_at,
                completed_at=completed_at
            )
        
        except Exception as e:
            completed_at = datetime.utcnow()
            
            # Store error log
            error_log = f"Execution failed: {str(e)}"
            error_artifact_meta = self.artifact_store.store(
                error_log.encode('utf-8'),
                "log",
                metadata={
                    'attempt_id': attempt_id,
                    'task_id': task_id,
                    'error': True
                }
            )
            
            return AttemptResult(
                success=False,
                failure_type="execution_error",
                error_summary=str(e),
                artifacts=[
                    ArtifactRef(
                        path=error_artifact_meta['storage_path'],
                        sha256=error_artifact_meta['sha256'],
                        artifact_type='log',
                        size_bytes=error_artifact_meta['size_bytes']
                    )
                ],
                started_at=started_at,
                completed_at=completed_at
            )
    
    def cleanup(self, attempt_id: str):
        """
        Clean up worktree for attempt.
        
        Args:
            attempt_id: Attempt identifier
        """
        worktree_path = self.worktree_base / attempt_id
        
        if worktree_path.exists():
            import shutil
            shutil.rmtree(worktree_path)
