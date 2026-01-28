> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# Leviathan Architecture

## Overview

Leviathan is an autonomous AI agent system designed to execute tasks on target repositories through a contract-based interface. It operates externally to target repositories, using Git as the delivery mechanism.

## Core Principles

1. **External Operation**: Leviathan never runs inside target repositories
2. **Contract-Based**: Each target defines its own contract, backlog, and policies
3. **Ephemeral Execution**: Uses git worktrees for isolated, disposable workspaces
4. **Deterministic & Auditable**: Every action logged with timestamps
5. **No Self-Modification**: Leviathan code is separate from target code

## System Components

### Control Plane

**Orchestrator** (`leviathan/runner.py`)
- Reads target contract and backlog
- Selects next task based on priority, dependencies, and concurrency limits
- Coordinates execution through backend abstraction
- Manages state and logging

**Task Selector** (`leviathan/backlog.py`)
- Parses backlog YAML
- Filters ready tasks (dependencies satisfied, ready=true)
- Sorts by priority
- Enforces max_open_prs limit

**State Manager** (`leviathan/state.py`)
- Tracks execution history
- Prevents duplicate work
- Stores in `~/.leviathan/state.db` (SQLite)

### Executor Backends

**WorktreeExecutor** (default)
```
1. Clone/fetch target repository to ~/.leviathan/targets/{name}
2. Create git worktree in temporary directory
3. Execute task (rewrite mode or diff mode)
4. Commit changes in worktree
5. Push branch to origin
6. Create PR via GitHub API
7. Remove worktree
```

**K8sJobExecutor** (future)
```
1. Create Kubernetes Job with target repo mounted
2. Job executes task in isolated pod
3. Job pushes branch and creates PR
4. Job terminates
```

### Model Integration

**ModelClient** (`leviathan/model_client.py`)
- Interfaces with Claude API
- Supports two modes:
  - **Rewrite Mode**: For small tasks (≤5 files), generates base64-encoded file contents
  - **Diff Mode**: For larger tasks, generates unified diffs
- Validates output against allowed_paths
- Retries on validation failures

**Rewrite Mode** (`leviathan/rewrite_mode.py`)
- Prompts model for JSON array: `[{"path": "...", "content_b64": "..."}]`
- Base64 encoding prevents JSON parsing failures
- Validates paths against allowed_paths
- Writes files directly

### Safety & Validation

**Conflict Prevention** (`leviathan/conflict_prevention.py`)
- Ensures fresh main branch before creating task branch
- Prevents stale base branches
- Detects remote branch collisions

**Command Executor** (`leviathan/exec.py`)
- Blocks unsafe infrastructure commands (terraform apply, aws create, etc.)
- Runs tests based on task scope
- Targeted test selection (only tests in allowed_paths)

**GitHub Client** (`leviathan/github.py`)
- Creates branches with collision detection
- Creates PRs with task metadata
- Checks branch existence on remote

## Data Flow

```
1. Orchestrator reads target contract from ~/.leviathan/targets/{name}.yaml
2. Orchestrator fetches target repo to ~/.leviathan/targets/{name}/
3. Orchestrator reads .leviathan/backlog.yaml from target repo
4. Task Selector chooses next task
5. Executor creates worktree in /tmp/leviathan-{task-id}/
6. ModelClient generates implementation (rewrite or diff mode)
7. Executor applies changes in worktree
8. Executor runs tests (targeted to allowed_paths)
9. Executor commits and pushes branch
10. GitHub Client creates PR
11. Executor removes worktree
12. State Manager records execution
```

## Directory Structure

### Leviathan Repository
```
/home/ian/leviathan/
├── leviathan/           # Core package
│   ├── runner.py        # Main orchestrator
│   ├── backlog.py       # Task selection
│   ├── model_client.py  # Claude API integration
│   ├── rewrite_mode.py  # Base64 rewrite mode
│   ├── exec.py          # Command execution
│   ├── github.py        # GitHub API client
│   ├── state.py         # Execution state
│   ├── conflict_prevention.py
│   └── console.py       # Logging utilities
├── docs/                # Documentation
├── ops/                 # Deployment configs
│   ├── systemd/         # Systemd service
│   └── k8s/             # Kubernetes manifests
└── tests/               # Unit tests
```

### Runtime State
```
~/.leviathan/
├── env                  # Environment variables (secrets)
├── state.db             # Execution history (SQLite)
├── logs/                # Execution logs
│   └── leviathan.log
└── targets/             # Target repository caches
    ├── radix.yaml       # Target config
    └── radix/           # Cloned target repo
```

### Target Repository
```
target-repo/
└── .leviathan/
    ├── contract.yaml    # Repository metadata
    ├── backlog.yaml     # Task backlog
    └── policy.yaml      # Allowed paths & invariants
```

## Execution Modes

### Dry Run
```bash
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml --dry-run
```
- Reads backlog
- Selects next task
- Prints task details
- Does not execute

### Once Mode
```bash
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml --once
```
- Executes one task
- Creates PR
- Exits

### Continuous Mode (Daemon)
```bash
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml
```
- Runs continuously
- Executes tasks as they become ready
- Respects max_open_prs limit
- Sleeps between iterations

## Security Model

### Secrets Management
- API keys stored in `~/.leviathan/env` (never committed)
- Systemd service uses `EnvironmentFile=%h/.leviathan/env`
- Kubernetes uses Secret resources

### Path Isolation
- Leviathan never writes to target repo except via git commits
- All work happens in ephemeral worktrees
- Worktrees deleted after PR creation

### Auditability
- Every action logged with timestamp
- Execution history in state.db
- Git commits provide full audit trail

## Future Enhancements

1. **Multi-Target Support**: Run multiple targets concurrently
2. **K8s Job Backend**: Scalable execution in Kubernetes
3. **Webhook Integration**: Trigger on PR events
4. **Advanced Scheduling**: Time-based task execution
5. **Metrics & Monitoring**: Prometheus metrics, Grafana dashboards
