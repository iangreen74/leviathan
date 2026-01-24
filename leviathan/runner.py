#!/usr/bin/env python3
"""
Leviathan v0: Automated Agent Runner

Safe, semi-closed-loop runner for executing tasks from agent_backlog.yaml.
"""
import sys
import os
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import yaml
import subprocess

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from leviathan.backlog import Backlog, Task
from leviathan.console import Console
from leviathan.github import GitHubClient, compute_branch_name
from leviathan.exec import CommandExecutor
from leviathan.model_client import ModelClient, PatchValidationError
from leviathan.conflict_prevention import ConflictPrevention, ConflictPreventionError
from leviathan.rewrite_mode import RewriteModeError
from leviathan.target_config import TargetConfig
from leviathan.worktree_executor import WorktreeExecutor, WorktreeError


def sanitize_diff(diff_text: str) -> str:
    """
    Sanitize a diff by removing trailing whitespace from all lines.
    
    This prevents git apply failures caused by:
    - Trailing whitespace warnings
    - Whitespace-only lines (e.g., "+      " becomes "+")
    
    Args:
        diff_text: The raw diff text
    
    Returns:
        Sanitized diff text with trailing whitespace removed
    """
    lines = diff_text.split('\n')
    sanitized_lines = [line.rstrip() for line in lines]
    
    # Ensure final output ends with newline
    result = '\n'.join(sanitized_lines)
    if result and not result.endswith('\n'):
        result += '\n'
    
    return result


class ExecutionLogger:
    """Logs execution events to ~/.leviathan/logs/ (outside repo to avoid dirty tree)."""
    
    def __init__(self, log_path: Optional[Path] = None):
        # Always write to ~/.leviathan/logs/ to avoid dirtying repo
        if log_path is None:
            log_path = Path.home() / '.leviathan' / 'logs' / 'execution_log.yaml'
        self.log_path = log_path
        self._ensure_log_exists()
    
    def _ensure_log_exists(self):
        """Ensure log file exists with proper structure."""
        if not self.log_path.exists():
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {
                'version': 1,
                'entries': []
            }
            with open(self.log_path, 'w') as f:
                yaml.dump(initial_data, f, default_flow_style=False)
    
    def log_event(self, event_type: str, task_id: str, details: Dict[str, Any]):
        """
        Append an event to the execution log.
        
        Self-heals if log file is missing, empty, or corrupt.
        """
        # Load existing data with self-healing
        try:
            with open(self.log_path, 'r') as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            # File doesn't exist - initialize
            data = None
        except yaml.YAMLError:
            # Corrupt YAML - reinitialize
            data = None
        except Exception:
            # Any other error - reinitialize
            data = None
        
        # Self-heal: ensure data is a dict with 'entries' list
        if data is None or not isinstance(data, dict):
            data = {'version': 1, 'entries': []}
        
        if 'entries' not in data or not isinstance(data['entries'], list):
            data['entries'] = []
        
        # Append new entry
        entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'event_type': event_type,
            'task_id': task_id,
            **details
        }
        
        data['entries'].append(entry)
        
        # Write back to file
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


class LeviathanRunner:
    """Main runner orchestrator."""
    
    def __init__(self, repo_root: Path, once: bool = False, sleep_seconds: int = 300, 
                 target_config: Optional[TargetConfig] = None, dry_run: bool = False):
        self.repo_root = repo_root
        self.once = once
        self.sleep_seconds = sleep_seconds
        self.target_config = target_config
        self.dry_run = dry_run
        
        # Determine backlog path: use target config if provided, else default
        if target_config:
            backlog_path = target_config.get_backlog_full_path()
        else:
            backlog_path = repo_root / 'docs/reports/agent_backlog.yaml'
        
        self.backlog = Backlog(backlog_path)
        self.github = GitHubClient(repo_root)
        self.executor = CommandExecutor(repo_root)
        self.model = ModelClient(repo_root=repo_root)
        self.logger = ExecutionLogger()  # Writes to ~/.leviathan/logs/
        self.conflict_prevention = ConflictPrevention(repo_root)
        
        # Initialize state tracking
        try:
            from leviathan.state import LeviathanState
            self.state = LeviathanState()
        except Exception:
            self.state = None
    
    def _preflight_checks(self) -> bool:
        """
        Run preflight checks before iteration.
        
        Returns:
            True if checks pass, False otherwise
        """
        # When using worktrees, we only need to check the cache repo is accessible
        # Individual tasks will run in ephemeral worktrees, so cache cleanliness doesn't matter
        if self.target_config:
            # For target mode, just ensure cache exists and can fetch
            Console.info("Using worktree mode - cache repo cleanliness not required")
            return True
        
        # Legacy mode: Check cache working tree (for backward compatibility)
        # Check 1: Clean working tree
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=self.repo_root
        )
        
        if result.stdout.strip():
            Console.error("❌ PREFLIGHT FAILED: Working tree is dirty")
            Console.error("Leviathan requires a clean working tree to operate safely.")
            Console.error("")
            Console.error("Dirty files:")
            for line in result.stdout.strip().split('\n'):
                Console.error(f"  {line}")
            Console.error("")
            Console.error("Action required:")
            Console.error("  1. Commit or stash changes in the Leviathan workspace")
            Console.error("  2. Or reset to clean state: git reset --hard origin/main")
            return False
        
        # Check 2: Dedicated clone path (warning only)
        expected_path = Path.home() / 'radix-leviathan'
        if self.repo_root.resolve() != expected_path.resolve():
            Console.warning(f"⚠️  Running from {self.repo_root}")
            Console.warning(f"⚠️  Expected dedicated clone at {expected_path}")
            Console.warning("⚠️  This may cause conflicts with human workspace")
        
        # Check 3: On main branch
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            cwd=self.repo_root
        )
        
        current_branch = result.stdout.strip()
        if current_branch != 'main':
            Console.error(f"❌ PREFLIGHT FAILED: Not on main branch (currently on {current_branch})")
            Console.error("Leviathan must run from main branch.")
            Console.error("")
            Console.error("Action required:")
            Console.error("  git checkout main")
            return False
        
        # Check 4: Try to sync with origin/main (ff-only)
        Console.info("Syncing with origin/main...")
        result = subprocess.run(
            ['git', 'pull', '--ff-only'],
            capture_output=True,
            text=True,
            cwd=self.repo_root
        )
        
        if result.returncode != 0:
            Console.error("❌ PREFLIGHT FAILED: Cannot fast-forward to origin/main")
            Console.error("")
            Console.error("Error output:")
            Console.error(result.stderr)
            Console.error("")
            Console.error("Action required:")
            Console.error("  1. Check for local commits that weren't pushed")
            Console.error("  2. Reset to origin/main: git reset --hard origin/main")
            Console.error("  3. Restart Leviathan service")
            return False
        
        Console.success("✅ Preflight checks passed")
        return True
    
    def run_iteration(self) -> bool:
        """
        Run one iteration of the runner.
        
        Returns:
            True if work was done, False if idle
        """
        Console.header("Leviathan v0 Runner Iteration")
        Console.timestamp()
        
        # Run preflight checks
        if not self._preflight_checks():
            return False
        
        # Check capacity using GitHub as source of truth
        open_pr_count = None
        github_available = False
        
        try:
            # Try to get count from GitHub first
            open_pr_count = self.github.get_open_pr_count()
            github_available = True
            
            # Sync backlog status with GitHub reality
            open_pr_branches = self.github.list_open_pr_branches()
            self.backlog.sync_pr_open_status(open_pr_branches)
            
        except Exception as e:
            # GitHub unavailable, fall back to backlog
            Console.warning(f"GitHub PR count unavailable; falling back to backlog status (may be stale).")
            Console.warning(f"Reason: {str(e)}")
            open_pr_count = self.backlog.get_open_pr_count()
        
        Console.capacity_status(open_pr_count, self.backlog.max_open_prs)
        
        if open_pr_count >= self.backlog.max_open_prs:
            Console.warning("Capacity limit reached. Waiting for PRs to merge.")
            return False
        
        # Select next task
        task = self.backlog.select_next_task()
        
        if not task:
            Console.info("No ready tasks available")
            return False
        
        # Display task info
        Console.task_info(task.id, task.title, task.scope, task.priority, task.estimated_size)
        Console.task_details(task.allowed_paths, task.acceptance_criteria)
        
        # Check for hot file conflicts BEFORE starting work
        Console.info("Checking for hot file conflicts...")
        is_safe, conflict_reason = self.conflict_prevention.check_hot_file_conflicts(task.allowed_paths)
        
        if not is_safe:
            Console.warning(f"Task blocked: {conflict_reason}")
            self.logger.log_event('task_blocked_hot_file', task.id, {
                'reason': conflict_reason
            })
            self.backlog.update_task_status(task.id, status='blocked')
            return False
        
        Console.success("No hot file conflicts detected")
        
        # Log task start
        self.logger.log_event('task_started', task.id, {
            'title': task.title,
            'scope': task.scope,
            'priority': task.priority
        })
        
        # Record in state DB
        if self.state:
            self.state.record_task_execution(
                task_id=task.id,
                status='started',
                metadata={'title': task.title, 'scope': task.scope}
            )
        
        try:
            # Execute task workflow
            success = self._execute_task(task)
            
            if success:
                Console.success(f"Task {task.id} completed successfully")
                return True
            else:
                Console.error(f"Task {task.id} failed")
                return False
        
        except Exception as e:
            Console.error(f"Task execution error: {str(e)}")
            self.logger.log_event('task_error', task.id, {
                'error': str(e)
            })
            
            # Record failure in state DB
            if self.state:
                self.state.record_task_execution(
                    task_id=task.id,
                    status='failed',
                    error_class=type(e).__name__,
                    error_message=str(e)
                )
            
            return False
    
    def _execute_task(self, task: Task) -> bool:
        """Execute a single task workflow."""
        
        # If using target config, execute in ephemeral worktree
        if self.target_config:
            return self._execute_task_in_worktree(task)
        else:
            # Legacy mode: execute directly in repo
            return self._execute_task_direct(task)
    
    def _execute_task_in_worktree(self, task: Task) -> bool:
        """Execute task in ephemeral worktree with guaranteed cleanup."""
        workspace_base = Path.home() / '.leviathan' / 'workspaces'
        
        # Create worktree executor
        worktree_exec = WorktreeExecutor(
            cache_dir=self.repo_root,
            workspace_base=workspace_base,
            target_name=self.target_config.name
        )
        
        try:
            # Create ephemeral worktree
            worktree_path = worktree_exec.create_worktree(
                task_id=task.id,
                base_branch=self.target_config.default_branch
            )
            
            # Execute task in worktree
            success = self._execute_task_direct(task, workspace_root=worktree_path)
            
            if success:
                # Push branch from worktree
                Console.info("Pushing branch from worktree...")
                push_result = subprocess.run(
                    ['git', 'push', '-u', 'origin', worktree_exec.branch_name],
                    cwd=worktree_path,
                    capture_output=True,
                    text=True
                )
                
                if push_result.returncode != 0:
                    Console.error(f"Failed to push: {push_result.stderr}")
                    return False
                
                Console.success("Branch pushed successfully")
            
            return success
            
        except WorktreeError as e:
            Console.error(f"Worktree error: {str(e)}")
            return False
        except Exception as e:
            Console.error(f"Task execution error: {str(e)}")
            return False
        finally:
            # ALWAYS cleanup worktree, even on failure
            worktree_exec.cleanup_worktree(force=True)
    
    def _execute_task_direct(self, task: Task, workspace_root: Optional[Path] = None) -> bool:
        """Execute task directly (legacy mode or within a worktree)."""
        
        # Use workspace_root if provided (worktree mode), else use repo_root
        work_root = workspace_root if workspace_root else self.repo_root
        
        # Determine mode: rewrite for small tasks (<=5 files), diff for larger
        use_rewrite_mode = len(task.allowed_paths) <= 5
        
        # Step 1: Generate implementation
        Console.step(1, 6, "Generating implementation")
        
        # Temporarily switch model client's repo_root to worktree if needed
        original_repo_root = self.model.repo_root
        if workspace_root:
            self.model.repo_root = workspace_root
        
        try:
            if use_rewrite_mode:
                Console.info(f"Using rewrite mode ({len(task.allowed_paths)} file(s))")
                try:
                    written_paths, source = self.model.generate_implementation_rewrite_mode(task)
                    Console.success(f"Implementation generated via {source} (rewrite mode)")
                    # Skip patch application step since files are already written
                    skip_patch_step = True
                except RewriteModeError as e:
                    Console.error(f"Rewrite mode failed: {str(e)}")
                    self.logger.log_event('rewrite_mode_failed', task.id, {
                        'error': str(e)
                    })
                    return False
                except Exception as e:
                    Console.error(f"Implementation generation failed: {str(e)}")
                    self.logger.log_event('generation_failed', task.id, {
                        'error': str(e)
                    })
                    return False
            else:
                Console.info(f"Using diff mode ({len(task.allowed_paths)} file(s))")
                try:
                    patch, source = self.model.generate_implementation(task)
                    Console.success(f"Implementation generated via {source}")
                    skip_patch_step = False
                except PatchValidationError as e:
                    Console.error(f"Patch validation failed: {str(e)}")
                    self.logger.log_event('patch_validation_failed', task.id, {
                        'error': str(e)
                    })
                    return False
                except FileNotFoundError as e:
                    Console.warning(str(e))
                    return False
                except Exception as e:
                    Console.error(f"Implementation generation failed: {str(e)}")
                    self.logger.log_event('generation_failed', task.id, {
                        'error': str(e)
                    })
                    return False
        finally:
            # Restore original repo_root
            self.model.repo_root = original_repo_root
        
        # Step 2: Create/verify branch
        Console.step(2, 6, "Preparing branch")
        
        if workspace_root:
            # In worktree mode, branch was already created by worktree executor
            # Just get the branch name from git
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                capture_output=True,
                text=True,
                cwd=workspace_root
            )
            branch_name = result.stdout.strip()
            Console.success(f"Using worktree branch: {branch_name}")
        else:
            # Legacy mode: create branch in current repo
            # Ensure we're branching from latest main
            Console.info("Ensuring fresh main branch...")
            if not self.conflict_prevention.ensure_fresh_main():
                Console.error("Failed to ensure fresh main")
                self.logger.log_event('fresh_main_failed', task.id, {})
                return False
            
            # Check for remote collision and compute branch name
            base_branch_name = f"agent/{task.id}"
            remote_exists = self.github.branch_exists_on_remote(base_branch_name)
            
            if remote_exists:
                Console.warning(f"Branch '{base_branch_name}' already exists on remote")
                Console.info("Using timestamp suffix to avoid collision...")
            
            branch_name = compute_branch_name(task.id, remote_exists)
            
            if remote_exists:
                Console.info(f"Computed unique branch name: {branch_name}")
            
            if not self.github.create_branch(branch_name):
                Console.error("Failed to create branch")
                self.logger.log_event('branch_creation_failed', task.id, {
                    'branch_name': branch_name,
                    'remote_existed': remote_exists
                })
                return False
            
            Console.success(f"Branch created: {branch_name}")
        
        # Step 3: Apply patch (skip if rewrite mode already wrote files)
        Console.step(3, 6, "Applying patch")
        
        if skip_patch_step:
            Console.info("Skipping patch application (rewrite mode already wrote files)")
        else:
            # Apply the generated patch using git apply
            patch_file = self.model.artifacts_dir / 'last_patch.diff'
            
            if not patch_file.exists():
                Console.error(f"Patch file not found: {patch_file}")
                self.logger.log_event('patch_file_missing', task.id, {})
                return False
            
            # Sanitize patch to remove trailing whitespace
            Console.info("Sanitizing patch (removing trailing whitespace)...")
            raw_patch = patch_file.read_text()
            sanitized_patch = sanitize_diff(raw_patch)
            
            # Save sanitized patch
            sanitized_patch_file = self.model.artifacts_dir / 'last_patch.sanitized.diff'
            sanitized_patch_file.write_text(sanitized_patch)
            
            Console.info(f"Applying sanitized patch from {sanitized_patch_file}")
            
            apply_result = self.executor.run_command(
                ['git', 'apply', '--whitespace=nowarn', str(sanitized_patch_file)],
                check=False
            )
            
            if apply_result.returncode != 0:
                Console.error(f"Failed to apply patch:\n{apply_result.stderr}")
                self.logger.log_event('patch_apply_failed', task.id, {
                    'error': apply_result.stderr
                })
                return False
            
            Console.success("Patch applied successfully")
        
        # Step 4: Run tests
        Console.step(4, 6, "Running tests")
        
        # Create executor for the work_root (worktree or repo_root)
        if workspace_root:
            test_executor = CommandExecutor(workspace_root)
        else:
            test_executor = self.executor
        
        test_success, test_output = test_executor.run_test_suite(task.scope, task.allowed_paths)
        
        if not test_success:
            Console.error(f"Tests failed:\n{test_output}")
            self.logger.log_event('tests_failed', task.id, {
                'output': test_output
            })
            return False
        
        Console.success("Tests passed")
        
        # Step 5: Commit (push happens in worktree cleanup for worktree mode)
        Console.step(5, 6, "Committing changes")
        
        # Check if there are changes to commit
        Console.info("Checking for changes...")
        
        if workspace_root:
            commit_executor = CommandExecutor(workspace_root)
        else:
            commit_executor = self.executor
        
        status_result = commit_executor.run_command(
            ['git', 'status', '--porcelain'],
            check=False
        )
        
        if not status_result.stdout.strip():
            Console.error("No changes to commit (patch may not have applied)")
            self.logger.log_event('no_changes_to_commit', task.id, {})
            return False
        
        Console.success(f"Changes detected: {len(status_result.stdout.strip().splitlines())} files")
        
        commit_prefix = {
            'ci': 'fix(ci)',
            'docs': 'docs',
            'tools': 'feat(tools)',
            'test': 'test',
            'services': 'feat',
            'infra': 'chore(infra)'
        }.get(task.scope, 'chore')
        
        # Include task ID in commit body
        commit_message = f"{commit_prefix}: {task.title}\n\nTask-ID: {task.id}"
        
        # Commit changes
        result = commit_executor.run_command(
            ['git', 'add', '.'],
            check=False
        )
        
        if result.returncode != 0:
            Console.error(f"Failed to stage changes: {result.stderr}")
            return False
        
        result = commit_executor.run_command(
            ['git', 'commit', '-m', commit_message],
            check=False
        )
        
        if result.returncode != 0:
            Console.error(f"Failed to commit: {result.stderr}")
            return False
        
        Console.success("Changes committed")
        
        # In legacy mode, push immediately. In worktree mode, push happens in caller
        if not workspace_root:
            # Check mergeability before pushing
            Console.info("Checking mergeability with main...")
            is_mergeable, conflict_reason = self.conflict_prevention.check_mergeability(branch_name)
            
            if not is_mergeable:
                Console.error(f"Merge conflict predicted: {conflict_reason}")
                self.logger.log_event('merge_conflict_predicted', task.id, {
                    'reason': conflict_reason,
                    'branch': branch_name
                })
                self.backlog.update_task_status(task.id, status='blocked')
                return False
            
            Console.success("Branch is mergeable")
            
            if not self.github.push_branch(branch_name):
                Console.error("Failed to push branch")
                return False
            
            Console.success("Changes pushed")
        
        # Step 6: Create pull request (using GitHub API from cache repo)
        Console.step(6, 6, "Creating pull request")
        
        pr_body = f"""## Task: {task.id}

{task.title}

### Acceptance Criteria
{chr(10).join(f'- [ ] {criterion}' for criterion in task.acceptance_criteria)}

### Scope
- **Type**: {task.scope}
- **Priority**: {task.priority}
- **Size**: {task.estimated_size}

### Allowed Paths
{chr(10).join(f'- `{path}`' for path in task.allowed_paths)}

---
*Generated by Leviathan v0 automated runner*

Task-ID: {task.id}
"""
        
        # Use auto-title generation based on file scope
        # GitHub client always uses self.repo_root (cache dir), which is correct
        try:
            pr_number, pr_url = self.github.create_pr_with_auto_title(
                task_id=task.id,
                task_title=task.title,
                body=pr_body
            )
        except Exception as e:
            Console.error(f"Failed to create PR: {str(e)}")
            self.logger.log_event('pr_creation_failed', task.id, {
                'error': str(e)
            })
            return False
        
        Console.pr_created(pr_number, pr_url)
        
        # Update backlog
        self.backlog.update_task_status(
            task.id,
            status='pr_opened',
            pr_number=pr_number,
            branch_name=branch_name
        )
        
        # Log PR creation
        self.logger.log_event('pr_created', task.id, {
            'pr_number': pr_number,
            'pr_url': pr_url,
            'branch_name': branch_name
        })
        
        # Record in state DB
        if self.state:
            self.state.record_task_execution(
                task_id=task.id,
                status='pr_opened',
                pr_number=pr_number,
                pr_url=pr_url,
                branch_name=branch_name
            )
        
        # Monitor CI (if PR number available)
        if pr_number and self.github.token:
            Console.section("Monitoring CI checks")
            final_state, details = self.github.monitor_pr_checks(pr_number, poll_interval=60, max_polls=10)
            
            Console.ci_status(final_state, details)
            
            self.logger.log_event('ci_completed', task.id, {
                'pr_number': pr_number,
                'state': final_state,
                'details': details
            })
            
            if final_state == 'success':
                self.backlog.update_task_status(task.id, status='ready_to_merge')
        
        return True
    
    def run_dry_run(self):
        """Run in dry-run mode: select and print next task without making changes."""
        Console.header("Leviathan v0 Dry Run Mode")
        Console.info(f"Repository: {self.repo_root}")
        
        if self.target_config:
            Console.info(f"Target: {self.target_config.name}")
            Console.info(f"Cache: {self.target_config.local_cache_dir}")
            
            # Ensure target repo is cloned/fetched
            self._ensure_target_repo()
        
        # Select next task
        task = self.backlog.select_next_task()
        
        if not task:
            Console.info("No ready tasks available")
            return
        
        # Print task details
        Console.header(f"Next Task: {task.id}")
        print(f"Title: {task.title}")
        print(f"Scope: {task.scope}")
        print(f"Priority: {task.priority}")
        print(f"Size: {task.estimated_size}")
        print(f"\nAllowed Paths:")
        for path in task.allowed_paths:
            print(f"  - {path}")
        print(f"\nAcceptance Criteria:")
        for criterion in task.acceptance_criteria:
            print(f"  - {criterion}")
    
    def _ensure_target_repo(self):
        """Ensure target repository is cloned and up-to-date."""
        if not self.target_config:
            return
        
        cache_dir = self.target_config.local_cache_dir
        
        if not cache_dir.exists():
            Console.info(f"Cloning target repo to {cache_dir}...")
            cache_dir.parent.mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                ['git', 'clone', self.target_config.repo_url, str(cache_dir)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                Console.error(f"Failed to clone target repo: {result.stderr}")
                sys.exit(1)
            
            Console.success("Target repo cloned")
        else:
            Console.info("Fetching latest from target repo...")
            
            result = subprocess.run(
                ['git', 'fetch', 'origin'],
                capture_output=True,
                text=True,
                cwd=cache_dir
            )
            
            if result.returncode != 0:
                Console.warning(f"Failed to fetch: {result.stderr}")
            else:
                Console.success("Target repo updated")
    
    def run(self):
        """Main run loop."""
        Console.header("Leviathan v0 Automated Runner")
        Console.info(f"Repository: {self.repo_root}")
        
        if self.target_config:
            Console.info(f"Target: {self.target_config.name}")
        
        if self.dry_run:
            Console.info("Mode: dry-run")
            self.run_dry_run()
            return
        
        Console.info(f"Mode: {'once' if self.once else 'loop'}")
        
        if self.once:
            self.run_iteration()
        else:
            while True:
                work_done = self.run_iteration()
                
                if not work_done:
                    Console.info(f"Sleeping for {self.sleep_seconds} seconds...")
                    time.sleep(self.sleep_seconds)


def main():
    parser = argparse.ArgumentParser(description='Leviathan v0 Automated Runner')
    parser.add_argument('--target', type=str, help='Path to target YAML config file')
    parser.add_argument('--dry-run', action='store_true', help='Select and print next task without making changes')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--loop', action='store_true', help='Run in continuous loop')
    parser.add_argument('--sleep-seconds', type=int, default=300, help='Sleep duration between iterations (default: 300)')
    
    args = parser.parse_args()
    
    # Load target config if provided
    target_config = None
    if args.target:
        target_path = Path(args.target).expanduser()
        try:
            target_config = TargetConfig.from_yaml(target_path)
        except (FileNotFoundError, ValueError) as e:
            Console.error(f"Failed to load target config: {e}")
            sys.exit(1)
    
    # Determine repo root: use target cache if available, else leviathan repo
    if target_config:
        repo_root = target_config.local_cache_dir
    else:
        repo_root = Path(__file__).parent.parent.parent
    
    # Default to once mode if neither specified
    once = args.once or not args.loop
    
    runner = LeviathanRunner(
        repo_root, 
        once=once, 
        sleep_seconds=args.sleep_seconds,
        target_config=target_config,
        dry_run=args.dry_run
    )
    
    try:
        runner.run()
    except KeyboardInterrupt:
        Console.info("\nRunner stopped by user")
        sys.exit(0)


if __name__ == '__main__':
    main()
