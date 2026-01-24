"""
Worktree executor for Leviathan - ephemeral per-task workspaces.

Creates isolated git worktrees for each task to prevent dirty working tree issues.
"""
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime


class WorktreeError(Exception):
    """Raised when worktree operations fail."""
    pass


class WorktreeExecutor:
    """
    Manages ephemeral git worktrees for task execution.
    
    Each task runs in an isolated worktree created from the cache clone.
    On failure, the worktree is always cleaned up to keep the cache clean.
    """
    
    def __init__(self, cache_dir: Path, workspace_base: Path, target_name: str):
        """
        Initialize worktree executor.
        
        Args:
            cache_dir: Path to target repo cache (bare or normal clone)
            workspace_base: Base directory for ephemeral workspaces
            target_name: Name of target (for workspace organization)
        """
        self.cache_dir = cache_dir
        self.workspace_base = workspace_base
        self.target_name = target_name
        self.worktree_path: Optional[Path] = None
        self.branch_name: Optional[str] = None
    
    def create_worktree(self, task_id: str, base_branch: str = "main") -> Path:
        """
        Create ephemeral worktree for a task.
        
        Args:
            task_id: Task ID (used for branch and workspace naming)
            base_branch: Branch to base the worktree on (default: main)
            
        Returns:
            Path to created worktree
            
        Raises:
            WorktreeError: If worktree creation fails
        """
        # Generate unique workspace path with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        workspace_dir = self.workspace_base / self.target_name / f"{task_id}-{timestamp}"
        workspace_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Branch name for this task
        branch_name = f"agent/{task_id}"
        
        # Fetch latest from origin to ensure we have up-to-date refs
        print(f"📥 Fetching latest from origin in cache...")
        fetch_result = subprocess.run(
            ['git', 'fetch', 'origin'],
            cwd=self.cache_dir,
            capture_output=True,
            text=True
        )
        
        if fetch_result.returncode != 0:
            raise WorktreeError(f"Failed to fetch from origin: {fetch_result.stderr}")
        
        # Create worktree on new branch from origin/base_branch
        print(f"🌳 Creating worktree at {workspace_dir}")
        print(f"   Branch: {branch_name} (from origin/{base_branch})")
        
        worktree_result = subprocess.run(
            ['git', 'worktree', 'add', '-b', branch_name, str(workspace_dir), f'origin/{base_branch}'],
            cwd=self.cache_dir,
            capture_output=True,
            text=True
        )
        
        if worktree_result.returncode != 0:
            # If branch already exists, try without -b flag
            if 'already exists' in worktree_result.stderr:
                print(f"⚠️  Branch {branch_name} exists, using unique name...")
                branch_name = f"agent/{task_id}-{timestamp}"
                
                worktree_result = subprocess.run(
                    ['git', 'worktree', 'add', '-b', branch_name, str(workspace_dir), f'origin/{base_branch}'],
                    cwd=self.cache_dir,
                    capture_output=True,
                    text=True
                )
                
                if worktree_result.returncode != 0:
                    raise WorktreeError(f"Failed to create worktree: {worktree_result.stderr}")
            else:
                raise WorktreeError(f"Failed to create worktree: {worktree_result.stderr}")
        
        print(f"✅ Worktree created successfully")
        
        self.worktree_path = workspace_dir
        self.branch_name = branch_name
        
        return workspace_dir
    
    def cleanup_worktree(self, force: bool = True):
        """
        Clean up worktree and delete local branch.
        
        This is called in finally blocks to ensure cleanup even on failure.
        
        Args:
            force: If True, force removal even if worktree is dirty
        """
        if not self.worktree_path:
            return
        
        print(f"🧹 Cleaning up worktree: {self.worktree_path}")
        
        # Remove worktree
        if self.worktree_path.exists():
            remove_args = ['git', 'worktree', 'remove']
            if force:
                remove_args.append('--force')
            remove_args.append(str(self.worktree_path))
            
            result = subprocess.run(
                remove_args,
                cwd=self.cache_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"⚠️  Failed to remove worktree: {result.stderr}")
                # Try manual cleanup as fallback
                try:
                    shutil.rmtree(self.worktree_path)
                    print(f"✅ Manually removed worktree directory")
                except Exception as e:
                    print(f"⚠️  Manual cleanup failed: {e}")
            else:
                print(f"✅ Worktree removed")
        
        # Delete local branch (best effort)
        if self.branch_name:
            result = subprocess.run(
                ['git', 'branch', '-D', self.branch_name],
                cwd=self.cache_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ Deleted local branch: {self.branch_name}")
            else:
                # Branch might not exist or already deleted - not critical
                pass
        
        self.worktree_path = None
        self.branch_name = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always cleanup."""
        self.cleanup_worktree(force=True)
        return False
