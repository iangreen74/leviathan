# Local Topology Run Guide

## Overview

This guide provides exact, copy-paste-ready commands to run topology and bootstrap indexing locally without Kubernetes. This is useful for development, testing, and understanding how Leviathan workers operate.

## System-Scope Tasks

Leviathan supports **system-scope tasks** that can run without backlog entries:

- `topology-<target>-v1`: Deterministic topology analysis
- `bootstrap-<target>-v1`: Repository structure indexing

These tasks are recognized by the worker and execute even if `.leviathan/backlog.yaml` doesn't exist or doesn't contain the task.

## Prerequisites

1. **Control plane running locally**:
   ```bash
   python3 -m leviathan.control_plane.api
   ```
   Default: `http://localhost:8000`

2. **Authentication token**:
   ```bash
   export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
   ```

3. **Repository to analyze** (local path or remote URL)

## Complete Local Workflow

### Step 1: Start Control Plane

```bash
# Terminal 1: Start control plane
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

Control plane will start on `http://localhost:8000`.

### Step 2: Run Topology Worker

```bash
# Terminal 2: Run topology worker
export TARGET_NAME=leviathan
export TARGET_REPO_URL=file://$HOME/leviathan
export TARGET_BRANCH=main
export TASK_ID=topology-leviathan-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token

# Optional: Set workspace directory (defaults to /tmp/leviathan-workspace)
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

# Run worker
python3 -m leviathan.executor.worker
```

**Expected output**:
```
Leviathan Worker
Target: leviathan
Task: topology-leviathan-v1
Attempt: attempt-local-1738000000

Task not found in backlog, using system-scope fallback for topology task
Cloning file:///home/user/leviathan...
✓ Cloned to /tmp/leviathan-workspace/attempt-local-1738000000/target

=== Topology Indexing ===
Target: leviathan
Repository: file:///home/user/leviathan

Analyzing repository topology...

✓ Topology analysis complete
  - Areas: 6
  - Subsystems: 12
  - Dependencies: 8
  - Artifact: topo_areas.json (1234 bytes)
  - Artifact: topo_subsystems.json (2345 bytes)
  - Artifact: topo_deps.json (3456 bytes)
  - Artifact: topo_summary.json (456 bytes)

✓ Topology completed successfully

Posting event bundle to control plane...
✓ Posted 15 events, 4 artifacts

✅ Worker completed successfully
```

### Step 3: Query Topology Summary

```bash
# Terminal 3: Query topology data
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/topology/summary?target=leviathan | jq
```

**Expected response**:
```json
{
  "target_id": "leviathan",
  "commit_sha": "abc123...",
  "rules_version": "topo_rules_v1",
  "areas_count": 6,
  "subsystems_count": 12,
  "dependencies_count": 8,
  "flows_count": 0
}
```

### Step 4: Query Detailed Topology

```bash
# Get areas
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/topology/areas?target=leviathan | jq

# Get subsystems
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/topology/subsystems?target=leviathan | jq

# Or use leviathanctl CLI
python3 -m leviathan.cli.leviathanctl topo-summary --target leviathan
python3 -m leviathan.cli.leviathanctl topo-areas --target leviathan

## CLI Commands

Query topology via `leviathanctl`:

```bash
# Summary
python3 -m leviathan.cli.leviathanctl topo-summary --target radix

# Areas
python3 -m leviathan.cli.leviathanctl topo-areas --target radix

# Subsystems
python3 -m leviathan.cli.leviathanctl topo-subsystems --target radix

# Dependencies
python3 -m leviathan.cli.leviathanctl topo-deps --target radix

# GraphViz DOT output
python3 -m leviathan.cli.leviathanctl topo-dot --target radix > topology.dot
dot -Tpng topology.dot -o topology.png
```

## Bootstrap Run (Alternative)

To run bootstrap indexing instead of topology:

```bash
export TARGET_NAME=leviathan
export TARGET_REPO_URL=file://$HOME/leviathan
export TARGET_BRANCH=main
export TASK_ID=bootstrap-leviathan-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token

python3 -m leviathan.executor.worker
```

Bootstrap discovers:
- All files (with SHA256 hashes)
- Documentation (markdown files)
- GitHub Actions workflows
- FastAPI routes (Python only)

## Remote Repository Example

To analyze a remote repository:

```bash
export TARGET_NAME=radix
export TARGET_REPO_URL=https://github.com/iangreen74/radix.git
export TARGET_BRANCH=main
export TASK_ID=topology-radix-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token

# Optional: GitHub token for private repos
export GITHUB_TOKEN=ghp_your_token_here

python3 -m leviathan.executor.worker
```

## Environment Variables Reference

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `TARGET_NAME` | Target identifier | `leviathan` |
| `TARGET_REPO_URL` | Git repository URL | `file://$HOME/leviathan` or `https://github.com/user/repo.git` |
| `TASK_ID` | Task identifier | `topology-<target>-v1` or `bootstrap-<target>-v1` |
| `ATTEMPT_ID` | Unique attempt ID | `attempt-local-$(date +%s)` |
| `CONTROL_PLANE_URL` | Control plane API URL | `http://localhost:8000` |
| `CONTROL_PLANE_TOKEN` | Auth token | `dev-token` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `TARGET_BRANCH` | Git branch to checkout | `main` |
| `LEVIATHAN_WORKSPACE_DIR` | Workspace directory | `/tmp/leviathan-workspace` |
| `GITHUB_TOKEN` | GitHub token for private repos | None |

## Troubleshooting

### Worker Error: Task not found in backlog

**Cause**: Task ID doesn't match system-scope pattern.

**Fix**: Use exact format `topology-<target>-v1` or `bootstrap-<target>-v1`:
```bash
# ✅ Correct
export TASK_ID=topology-leviathan-v1

# ❌ Wrong (will fail)
export TASK_ID=topology-leviathan-v2
export TASK_ID=topo-leviathan-v1
```

### Worker Error: Missing required env vars

**Cause**: One or more required environment variables not set.

**Fix**: Verify all required variables are exported:
```bash
env | grep -E "TARGET_|TASK_|ATTEMPT_|CONTROL_PLANE_"
```

### Topology API Returns: No topology data found

**Cause**: Worker events not yet processed by graph projection, or target name mismatch.

**Fix**:
1. Check worker completed successfully
2. Verify target name matches exactly:
   ```bash
   # Worker uses TARGET_NAME
   export TARGET_NAME=leviathan
   
   # Query uses same name
   curl "http://localhost:8000/v1/topology/summary?target=leviathan"
   ```
3. Check graph summary to verify events were ingested:
   ```bash
   curl -H "Authorization: Bearer dev-token" \
     http://localhost:8000/v1/graph/summary | jq
   ```

### Worker Events Have "target": null

**Cause**: This was a bug in earlier versions (now fixed).

**Fix**: Ensure you're using the latest worker code. Event bundles now include `target` field at the top level.

### Graph Projection Shows Empty Nodes

**Cause**: Missing `attempt.created` event (required for graph projection).

**Fix**: This is now fixed. Worker emits events in correct order:
1. `attempt.created` (with `task_id`, `target_id`)
2. `attempt.started`
3. Topology/bootstrap events
4. `attempt.succeeded` or `attempt.failed`

## Event Lifecycle

The worker emits events in this order:

```
1. attempt.created
   - attempt_id
   - task_id
   - target_id
   - status: created

2. attempt.started
   - attempt_id
   - task_id
   - target_id
   - status: running

3. topo.started (or bootstrap.started)
   - target_id
   - commit_sha
   - rules_version

4. topo.area.discovered (multiple)
   - area_id
   - path_prefixes
   - file_count

5. topo.subsystem.discovered (multiple)
   - subsystem_id
   - root_path
   - languages

6. topo.dependency.discovered (multiple)
   - from_subsystem_id
   - to_subsystem_id
   - evidence

7. topo.indexed
   - target_id
   - counts

8. topo.completed
   - target_id
   - status: completed

9. artifact.created (multiple)
   - artifact_id
   - sha256
   - artifact_type

10. attempt.succeeded
    - attempt_id
    - task_id
    - target_id
    - status: succeeded
```

All events are posted to control plane in a single bundle with top-level `target` field.

## Advanced: Custom Workspace

For debugging or artifact inspection:

```bash
# Use custom workspace
export LEVIATHAN_WORKSPACE_DIR=$HOME/leviathan-debug

# Run worker
python3 -m leviathan.executor.worker

# Inspect artifacts after run
ls -lh $HOME/leviathan-debug/attempt-*/artifacts/
cat $HOME/leviathan-debug/attempt-*/artifacts/topo_summary.json
```

## Integration with Backlog

System-scope tasks can also be defined in backlog for scheduling:

```yaml
# .leviathan/backlog.yaml
tasks:
  - id: topology-leviathan-v1
    title: "Topology analysis for Leviathan"
    scope: topology
    priority: high
    ready: true
    estimated_size: small
    allowed_paths: []
    acceptance_criteria:
      - "Topology indexed successfully"
    dependencies: []
```

If defined in backlog, the backlog entry takes precedence over system-scope fallback.

## Determinism Guarantee

Both topology and bootstrap are **deterministic**:
- Same `(target_id, commit_sha)` → identical results
- No LLM calls
- No random behavior
- Sorted JSON output

You can run the same analysis multiple times and get byte-for-byte identical artifacts.

## Summary

Local topology/bootstrap runs enable:
- ✅ Development without Kubernetes
- ✅ Fast iteration on indexer code
- ✅ Understanding worker behavior
- ✅ Debugging graph projection issues
- ✅ Testing with local repositories

**Key insight**: System-scope tasks (`topology-*-v1`, `bootstrap-*-v1`) work without backlog entries, making local execution simple and deterministic.
