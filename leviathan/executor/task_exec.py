"""
Task Executor v1

Executes tasks from backlog by generating/modifying files according to task spec.
Enforces allowed_paths strictly and dispatches by scope.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any
import os


@dataclass
class ExecResult:
    """Result of task execution."""
    success: bool
    changed_files: List[str]  # Relative paths from repo root
    error: str = ""


class PathViolationError(Exception):
    """Raised when task attempts to write outside allowed_paths."""
    pass


def validate_output_path(file_path: str, allowed_paths: List[str], repo_root: str) -> None:
    """
    Validate that file_path is within allowed_paths.
    
    Args:
        file_path: Absolute or relative path to validate
        allowed_paths: List of allowed path prefixes (e.g., ["docs/", ".leviathan/"])
        repo_root: Absolute path to repository root
        
    Raises:
        PathViolationError: If file_path is outside allowed_paths
    """
    # Convert to relative path from repo root
    abs_path = Path(file_path)
    if not abs_path.is_absolute():
        abs_path = Path(repo_root) / file_path
    
    try:
        rel_path = abs_path.relative_to(repo_root)
    except ValueError:
        raise PathViolationError(f"Path {file_path} is outside repository root")
    
    # Check if path starts with any allowed prefix
    rel_path_str = str(rel_path)
    for allowed in allowed_paths:
        if rel_path_str.startswith(allowed.rstrip('/')):
            return
    
    raise PathViolationError(
        f"Path {rel_path_str} is outside allowed_paths: {allowed_paths}"
    )


def execute_docs_task(task_id: str, task_spec: Dict[str, Any], repo_path: str) -> ExecResult:
    """
    Execute a docs-scope task.
    
    Args:
        task_id: Task identifier
        task_spec: Task specification from backlog
        repo_path: Absolute path to repository
        
    Returns:
        ExecResult with success status and changed files
    """
    allowed_paths = task_spec.get('allowed_paths', [])
    
    # Task-specific execution
    if task_id == 'docs-leviathan-backlog-guide':
        return _execute_backlog_guide(task_spec, repo_path, allowed_paths)
    else:
        return ExecResult(
            success=False,
            changed_files=[],
            error=f"No executor implemented for docs task: {task_id}"
        )


def _execute_backlog_guide(task_spec: Dict[str, Any], repo_path: str, allowed_paths: List[str]) -> ExecResult:
    """Generate docs/27_RADIX_BACKLOG_AUTONOMY_GUIDE.md"""
    
    output_path = "docs/27_RADIX_BACKLOG_AUTONOMY_GUIDE.md"
    
    # Validate path
    try:
        validate_output_path(output_path, allowed_paths, repo_path)
    except PathViolationError as e:
        return ExecResult(success=False, changed_files=[], error=str(e))
    
    content = """# Radix Backlog Autonomy Guide

## Purpose

This document defines the backlog discipline for Leviathan autonomous execution in the Radix project. It ensures tasks are well-specified, bounded, and safe for autonomous agents to execute without human intervention.

## Required Task Fields

Every task in `.leviathan/backlog.yaml` must include:

### Core Fields
- **id**: Unique task identifier (kebab-case)
- **title**: Human-readable task description
- **scope**: Task category (see Scope Taxonomy below)
- **priority**: high | medium | low
- **ready**: true | false (whether task is executable)
- **allowed_paths**: List of path prefixes the task may modify
- **acceptance_criteria**: List of concrete success conditions
- **dependencies**: List of task IDs that must complete first
- **estimated_size**: xs | s | m | l | xl (rewrite threshold guidance)

### Optional Fields
- **status**: pending | in_progress | completed
- **pr_number**: GitHub PR number (if completed)
- **branch_name**: Git branch name (if in progress or completed)
- **commit**: Git commit SHA (if completed)

## Scope Taxonomy

Tasks are categorized by scope to enable targeted execution:

- **docs**: Documentation changes only
- **tests**: Test file changes only
- **ci**: CI/CD workflow changes
- **bootstrap**: Initial repository setup/indexing
- **tools**: Developer tooling and scripts
- **infra**: Infrastructure configuration

## allowed_paths Discipline

The `allowed_paths` field is **critical for safety**. It restricts what files a task may modify.

### Rules
1. **Empty list `[]`** means task can modify any file (use sparingly, requires review)
2. **Specific paths** limit task to those prefixes (e.g., `["docs/"]`)
3. **Multiple paths** allowed (e.g., `["docs/", "tests/schemas/"]`)
4. **Trailing slashes** recommended for directories
5. **Enforcement**: Executor validates all writes against allowed_paths before execution

### Examples

**Docs-only task:**
```yaml
- id: api-docs-update
  scope: docs
  allowed_paths:
    - docs/api/
  acceptance_criteria:
    - Update docs/api/endpoints.md with new /v2/search endpoint
```

**Tests-only task:**
```yaml
- id: smoke-artifact-schema
  scope: tests
  allowed_paths:
    - tests/unit/test_research_async_smoke_artifact.py
    - tests/schemas/smoke_artifact_schema.json
  acceptance_criteria:
    - JSON schema defined for smoke artifact structure
    - Unit test validates artifact against schema
```

## Rewrite Threshold Management

The `estimated_size` field helps keep tasks under Leviathan's rewrite threshold (~300 lines).

### Size Guidelines
- **xs**: < 50 lines (single file, small change)
- **s**: 50-150 lines (1-2 files, focused change)
- **m**: 150-300 lines (multiple files, moderate scope)
- **l**: 300-500 lines (large change, may need splitting)
- **xl**: > 500 lines (requires decomposition into smaller tasks)

### Best Practices
1. Prefer **s** and **m** sized tasks for autonomous execution
2. Split **l** and **xl** tasks into smaller subtasks with dependencies
3. Use acceptance criteria to bound scope explicitly
4. If a task grows beyond estimate, mark as blocked and decompose

## Autonomy Guardrails

Leviathan operates under strict guardrails defined in `.leviathan/policy.yaml` and autonomy config:

### DEV Environment Guardrails
- **allowed_path_prefixes**: `[.leviathan/, docs/]` (only these scopes executable)
- **max_open_prs**: 1 (prevents runaway PR creation)
- **max_running_attempts**: 1 (one task at a time)
- **max_attempts_per_task**: 2 (retry limit)
- **circuit_breaker_failures**: 2 (stops after consecutive failures)

### Execution Flow
1. Scheduler selects task with `ready: true`
2. Validates task scope matches `allowed_path_prefixes`
3. Creates worker job with task spec
4. Worker executes task, validates all writes against `allowed_paths`
5. Worker creates PR (no auto-merge)
6. Human reviews and merges PR
7. Scheduler continues with next ready task

### Safety Mechanisms
- **No direct pushes**: All changes via PR
- **No auto-merge**: Human approval required
- **Path enforcement**: Writes outside allowed_paths fail immediately
- **Event auditing**: All attempts logged to control plane
- **Deterministic**: Same task + same repo state = same output

## Task Readiness Checklist

Before setting `ready: true`:

- [ ] Task has clear, testable acceptance criteria
- [ ] `allowed_paths` is as narrow as possible
- [ ] `estimated_size` is ≤ m (or task is decomposed)
- [ ] Dependencies are satisfied or empty
- [ ] Scope matches current `allowed_path_prefixes` in autonomy config
- [ ] Task is idempotent (can be retried safely)

## Examples

### Example 1: Docs-Only Task

```yaml
- id: async-smoke-evidence-doc
  title: Add async smoke evidence documentation
  scope: docs
  priority: low
  ready: true
  allowed_paths:
    - docs/ci/ASYNC_SMOKE_EVIDENCE.md
  acceptance_criteria:
    - Documents smoke artifact JSON structure
    - Explains success vs failure artifacts
    - Shows example artifacts for each case
    - Links to workflow and script files
  dependencies:
    - smoke-artifact-schema
  estimated_size: xs
```

### Example 2: Tests-Only Task

```yaml
- id: api-base-normalization-test
  title: Add API base normalization unit test
  scope: tests
  priority: medium
  ready: false
  allowed_paths:
    - tests/unit/test_sentinel_api_base_normalization.py
  acceptance_criteria:
    - Test validates API base URL normalization logic
    - Covers missing stage path detection and correction
    - Covers trailing slash removal
    - Covers already-normalized URLs (no-op)
  dependencies:
    - smoke-trigger-tighten
  estimated_size: xs
```

## References

- Backlog format: `.leviathan/backlog.yaml`
- Autonomy policy: `.leviathan/policy.yaml`
- Autonomy config: `ops/autonomy/dev.yaml`
- Execution logs: Control plane event store

---

**Document Status**: Living document, updated as backlog discipline evolves.
"""
    
    # Write file
    abs_output_path = Path(repo_path) / output_path
    abs_output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file already exists with same content
    if abs_output_path.exists():
        existing_content = abs_output_path.read_text()
        if existing_content == content:
            # No changes needed
            return ExecResult(success=True, changed_files=[], error="")
    
    abs_output_path.write_text(content)
    
    return ExecResult(
        success=True,
        changed_files=[output_path],
        error=""
    )


def execute_task(task_spec: Dict[str, Any], repo_path: str) -> ExecResult:
    """
    Execute a task based on its scope.
    
    Args:
        task_spec: Task specification from backlog
        repo_path: Absolute path to repository
        
    Returns:
        ExecResult with execution outcome
        
    Raises:
        NotImplementedError: If scope executor not implemented
    """
    task_id = task_spec.get('id', 'unknown')
    scope = task_spec.get('scope', 'unknown')
    
    if scope == 'docs':
        return execute_docs_task(task_id, task_spec, repo_path)
    else:
        raise NotImplementedError(f"No executor implemented for scope: {scope}")
