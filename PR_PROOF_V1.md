# PR Proof v1: Backlog-Only PR Creation

## Overview

This document provides exact commands to create a **real GitHub PR** against Radix that modifies only `.leviathan/backlog.yaml`.

## Prerequisites

1. **GitHub Token** with `repo` scope for Radix
2. **Control Plane** running locally
3. **Radix Repository** accessible at `git@github.com:iangreen74/radix.git` or HTTPS equivalent

## Execution Commands

### Step 1: Start Control Plane

```bash
# Terminal 1: Control Plane
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

### Step 2: Run PR Proof Script

```bash
# Terminal 2: PR Proof Execution
export GITHUB_TOKEN=<your-github-token>
export TARGET_NAME=radix
export TARGET_REPO_URL=https://github.com/iangreen74/radix.git
export TARGET_BRANCH=main
export ATTEMPT_ID=attempt-pr-proof-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

# Run PR proof
python3 scripts/pr_proof_v1.py
```

## Expected Output

```
============================================================
PR Proof v1: Backlog-Only PR Creation
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git
Task: pr-proof-v1-backlog-only
Attempt: attempt-pr-proof-1738000000

✓ Posted attempt.created event to control plane
✓ Posted attempt.started event to control plane

Cloning https://github.com/iangreen74/radix.git...
✓ Cloned to /tmp/leviathan-workspace/attempt-pr-proof-1738000000/target
✓ Added task pr-proof-v1-backlog-only to backlog
Pushing branch agent/backlog-propose-attempt-pr-proof-1738000000...
✓ Branch pushed: agent/backlog-propose-attempt-pr-proof-1738000000
✓ Commit SHA: abc123def456...

Creating pull request...
✓ PR created: https://github.com/iangreen74/radix/pull/1
✓ PR number: 1
✓ Posted pr.created event to control plane
✓ Posted attempt.succeeded event to control plane

============================================================
✅ PR Proof v1 Complete
============================================================
PR URL: https://github.com/iangreen74/radix/pull/1
PR Number: 1
Branch: agent/backlog-propose-attempt-pr-proof-1738000000
Commit SHA: abc123def456...

Verify with:
  gh pr view 1 --repo https://github.com/iangreen74/radix.git
  curl -H 'Authorization: Bearer dev-token' \
    http://localhost:8000/v1/graph/summary
```

## Verification

### 1. Verify PR on GitHub

```bash
# Using GitHub CLI
gh pr view <PR_NUMBER> --repo iangreen74/radix

# Or visit URL directly
open https://github.com/iangreen74/radix/pull/<PR_NUMBER>
```

**Expected PR Content:**
- **Title**: `Leviathan: PR Proof v1: backlog-only change (Leviathan)`
- **Files Changed**: Only `.leviathan/backlog.yaml`
- **Diff**: Adds new task entry `pr-proof-v1-backlog-only`

### 2. Verify PR Diff

```bash
gh pr diff <PR_NUMBER> --repo iangreen74/radix
```

**Expected Output:**
```diff
diff --git a/.leviathan/backlog.yaml b/.leviathan/backlog.yaml
index abc123..def456 100644
--- a/.leviathan/backlog.yaml
+++ b/.leviathan/backlog.yaml
@@ -1,3 +1,15 @@
 tasks:
+- id: pr-proof-v1-backlog-only
+  title: 'PR Proof v1: backlog-only change (Leviathan)'
+  scope: docs
+  priority: high
+  ready: true
+  estimated_size: xs
+  allowed_paths:
+  - .leviathan/backlog.yaml
+  acceptance_criteria:
+  - PR modifies only .leviathan/backlog.yaml
+  - PR contains this new task entry
+  - No other files changed
+  dependencies: []
 - id: existing-task-001
   ...
```

### 3. Verify Control Plane Events

```bash
# Query graph summary
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/graph/summary | jq

# Query attempts (if API supports it)
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/attempts | jq
```

**Expected Events:**
- `attempt.created` with `attempt_number: 1`
- `attempt.started`
- `pr.created` with `pr_number` and `pr_url`
- `attempt.succeeded`

### 4. Verify Event Journal

```bash
# Check events.ndjson
cat ~/.leviathan/graph/events.ndjson | grep pr-proof-v1-backlog-only | jq
```

## Task Specification

The PR adds this task to Radix's backlog:

```yaml
id: pr-proof-v1-backlog-only
title: 'PR Proof v1: backlog-only change (Leviathan)'
scope: docs
priority: high
ready: true
estimated_size: xs
allowed_paths:
  - .leviathan/backlog.yaml
acceptance_criteria:
  - PR modifies only .leviathan/backlog.yaml
  - PR contains this new task entry
  - No other files changed
dependencies: []
```

## Implementation Details

### Components

1. **BacklogProposer** (`leviathan/executor/backlog_propose.py`)
   - Clones target repo
   - Adds task to `.leviathan/backlog.yaml`
   - Creates branch, commits, pushes
   - Opens PR via GitHub API

2. **PR Proof Script** (`scripts/pr_proof_v1.py`)
   - Orchestrates the flow
   - Posts lifecycle events to control plane
   - Returns PR metadata

3. **Unit Tests** (`tests/unit/test_backlog_propose.py`)
   - Verifies only backlog.yaml is modified
   - Tests duplicate task handling
   - Tests URL parsing and authentication

### Event Lifecycle

```
attempt.created (attempt_number=1, task_id, target_id)
  ↓
attempt.started (task_id, target_id)
  ↓
[Clone repo, modify backlog.yaml, commit, push]
  ↓
pr.created (pr_number, pr_url, branch_name, commit_sha)
  ↓
attempt.succeeded (pr_number, pr_url)
```

### Allowed Paths Enforcement

The task spec includes:
```yaml
allowed_paths:
  - .leviathan/backlog.yaml
```

The BacklogProposer implementation:
- Only modifies `.leviathan/backlog.yaml`
- Uses `git add .leviathan/backlog.yaml` (not `git add .`)
- Unit tests verify no other files are touched

## Test Results

```bash
$ python3 -m pytest tests/unit/test_backlog_propose.py -v
8 passed in 0.04s

$ python3 -m pytest tests/unit -q
340 passed, 273 warnings in 2.40s

$ python3 tools/invariants_check.py
✅ SUCCESS: All invariants validated
```

## Troubleshooting

### Error: Authentication failed

**Cause**: Invalid or missing GitHub token

**Fix**: Ensure `GITHUB_TOKEN` has `repo` scope:
```bash
gh auth status
# Or create new token at https://github.com/settings/tokens
```

### Error: Backlog file not found

**Cause**: Radix doesn't have `.leviathan/backlog.yaml`

**Fix**: Verify Radix repo structure or create initial backlog file

### Error: PR already exists

**Cause**: Branch already has an open PR

**Fix**: The script will detect and return existing PR URL

## Architecture Notes

### Why Backlog-Only?

1. **Governance**: Tasks are proposed via PR to backlog.yaml
2. **Minimal Risk**: No product code changes
3. **Deterministic**: Single file modification is easy to verify
4. **Proof of Concept**: Demonstrates full PR creation flow

### PR Creation Flow

1. Clone target repo with token auth
2. Create branch `agent/backlog-propose-<attempt_id>`
3. Modify only `.leviathan/backlog.yaml`
4. Commit with message: `Leviathan: Propose task <task_id>`
5. Push to origin with token auth
6. Create PR via GitHub API
7. Post events to control plane

### Event Posting

Events are posted as bundles to `/v1/events/ingest`:
```json
{
  "target": "radix",
  "bundle_id": "bundle-attempt-pr-proof-1738000000",
  "events": [...],
  "artifacts": []
}
```

## Related Documentation

- [Worker Implementation](leviathan/executor/worker.py) - PR creation logic
- [Backlog Proposer](leviathan/executor/backlog_propose.py) - Backlog-only PR mode
- [Integrity Fixes](INTEGRITY_FIXES.md) - Event payload fixes
- [Local Topology Run](docs/LOCAL_TOPOLOGY_RUN.md) - Local execution guide
