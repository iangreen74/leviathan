> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# Target Contract Specification

## Overview

Each target repository must provide three files under `.leviathan/`:

1. **`contract.yaml`** - Repository metadata and configuration
2. **`backlog.yaml`** - Task backlog with priorities and dependencies  
3. **`policy.yaml`** - Allowed paths per scope and invariants

## contract.yaml

Defines repository metadata and Leviathan configuration.

```yaml
version: 1
repository:
  name: radix
  description: "Radix ML infrastructure platform"
  default_branch: main
  
leviathan:
  max_open_prs: 2
  rewrite_mode_threshold: 5  # Use rewrite mode for tasks with ≤5 files
  
scopes:
  - ci
  - docs
  - tests
  - tools
  - services
  - infra
```

## backlog.yaml

Defines the task backlog. Format:

```yaml
version: 1
max_open_prs: 2

tasks:
- id: task-id
  title: "Task title"
  scope: ci|docs|tests|tools|services|infra
  priority: high|medium|low
  ready: true|false
  allowed_paths:
  - path/to/file1.py
  - path/to/file2.py
  acceptance_criteria:
  - "Criterion 1"
  - "Criterion 2"
  dependencies:
  - other-task-id
  estimated_size: xs|s|m|l|xl
  status: completed  # Optional, set when done
  pr_number: 123     # Optional, set when PR created
  branch_name: fix/task-id  # Optional, set when branch created
```

### Field Descriptions

- **id**: Unique task identifier (kebab-case)
- **title**: Human-readable task description
- **scope**: Task category (determines test strategy)
- **priority**: Task priority for selection
- **ready**: Whether task is ready to execute (dependencies satisfied)
- **allowed_paths**: Files this task may modify (enforced)
- **acceptance_criteria**: Requirements for task completion
- **dependencies**: Task IDs that must complete first
- **estimated_size**: Rough size estimate
- **status**: Set to "completed" when done
- **pr_number**: GitHub PR number (set by Leviathan)
- **branch_name**: Git branch name (set by Leviathan)

## policy.yaml

Defines allowed paths per scope and invariants.

```yaml
version: 1

# Allowed path patterns per scope
scope_paths:
  ci:
    - .github/workflows/**
    - scripts/ci/**
  docs:
    - docs/**
    - README.md
  tests:
    - tests/**
  tools:
    - tools/**
  services:
    - services/**
  infra:
    - infra/**
    - cloudformation/**

# Invariants that must never be violated
invariants:
  - path: ops/invariants.yaml
    description: "Repository invariants checked by CI"
  
# Forbidden patterns (never allow)
forbidden:
  - "**/*.secret"
  - "**/*.key"
  - "**/credentials.json"
```

## Example: Radix Contract

### `.leviathan/contract.yaml`
```yaml
version: 1
repository:
  name: radix
  description: "Radix ML infrastructure platform"
  default_branch: main
  
leviathan:
  max_open_prs: 2
  rewrite_mode_threshold: 5
  
scopes:
  - ci
  - docs
  - tests
  - tools
  - services
  - infra
```

### `.leviathan/backlog.yaml`
```yaml
version: 1
max_open_prs: 2

tasks:
- id: geo-dataset-metadata-schema
  title: Define geophysics dataset metadata schema
  scope: tests
  priority: high
  ready: true
  allowed_paths:
  - tests/schemas/geophysics_dataset_schema.json
  - tests/unit/test_geophysics_dataset_schema.py
  acceptance_criteria:
  - Schema for seismic survey metadata (bounds, resolution, acquisition date)
  - Schema for well log metadata (depth range, measured properties)
  - Unit tests validate example metadata
  dependencies:
  - geo-domain-plugin-interface
  estimated_size: s
```

### `.leviathan/policy.yaml`
```yaml
version: 1

scope_paths:
  ci:
    - .github/workflows/**
    - scripts/ci/**
  docs:
    - docs/**
  tests:
    - tests/**
  tools:
    - tools/**
  services:
    - services/**
  infra:
    - infra/**

invariants:
  - path: ops/invariants.yaml
    description: "Repository invariants"

forbidden:
  - "**/*.secret"
  - "**/*.key"
```

## Target Configuration

Leviathan reads target configuration from `~/.leviathan/targets/{name}.yaml`:

```yaml
name: radix
repo_url: git@github.com:iangreen74/radix.git
default_branch: main
local_cache_dir: ~/.leviathan/targets/radix
contract_path: .leviathan/contract.yaml
backlog_path: .leviathan/backlog.yaml
policy_path: .leviathan/policy.yaml
```

## Validation

Leviathan validates:
1. All allowed_paths exist or will be created
2. All paths are within scope_paths for the task's scope
3. No forbidden patterns matched
4. Dependencies are satisfied (completed or don't exist)
5. ready=true before execution
6. max_open_prs limit not exceeded
