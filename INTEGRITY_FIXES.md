# Leviathan Local Topology Integrity Fixes

## Summary

Fixed three integrity issues discovered during local operational proof testing on VaultHub:

1. ✅ **AttemptNode validation error**: `attempt.created` events now include required `attempt_number` field
2. ✅ **Artifact store mismatch**: Worker now uses same artifact store location as control plane (`~/.leviathan/artifacts`)
3. ✅ **CLI module path**: Documentation updated with correct `python3 -m leviathan.cli.leviathanctl` invocation

## Changes Made

### 1. Worker Event Payload Fix

**File**: `leviathan/executor/worker.py`

**Change**: Added `attempt_number: 1` to `attempt.created` event payload

```python
# Before
self._emit_event("attempt.created", {
    'attempt_id': self.attempt_id,
    'task_id': self.task_id,
    'target_id': self.target_name,
    'status': 'created',
    'created_at': datetime.utcnow().isoformat()
})

# After
self._emit_event("attempt.created", {
    'attempt_id': self.attempt_id,
    'task_id': self.task_id,
    'target_id': self.target_name,
    'attempt_number': 1,  # For standalone/local runs, always 1
    'status': 'created',
    'created_at': datetime.utcnow().isoformat()
})
```

**Rationale**: `AttemptNode` schema requires `attempt_number: int` field. For standalone/local runs, we use `attempt_number=1` since there's no scheduler tracking attempt counts.

### 2. Artifact Store Consistency Fix

**File**: `leviathan/executor/worker.py`

**Change**: Worker now uses default artifact store location (same as control plane)

```python
# Before
self.artifact_store = ArtifactStore(storage_root=self.workspace / "artifacts")

# After
# Use default artifact store (same as control plane: ~/.leviathan/artifacts)
self.artifact_store = ArtifactStore()
```

**Rationale**: 
- Worker was storing artifacts in `<workspace>/artifacts`
- Control plane was looking in `~/.leviathan/artifacts` (default)
- This caused "artifact not found" warnings during event ingestion
- Now both use the same location for consistency

### 3. CLI Documentation Fix

**Files**: 
- `docs/LOCAL_TOPOLOGY_RUN.md`
- `QUICKSTART_LOCAL.md`

**Change**: Updated all CLI invocations to use correct module path

```bash
# Before (incorrect)
leviathanctl topo-summary --target radix

# After (correct)
python3 -m leviathan.cli.leviathanctl topo-summary --target radix
```

### 4. Test Updates

**Files**:
- `tests/unit/test_worker_system_scope.py`: Updated to assert `attempt_number` field
- `tests/unit/test_worker_workspace.py`: Updated to reflect new artifact store location

## Validation

All tests pass:
```bash
$ python3 -m pytest tests/unit -q
332 passed, 273 warnings in 2.49s

$ python3 tools/invariants_check.py
✅ SUCCESS: All invariants validated
```

## Reproduction Commands

### Start Control Plane
```bash
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

### Run Topology Worker
```bash
export TARGET_NAME=leviathan
export TARGET_REPO_URL=file://$HOME/leviathan
export TASK_ID=topology-leviathan-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token

python3 -m leviathan.executor.worker
```

### Query Results
```bash
# Via API
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/topology/summary?target=leviathan | jq

# Via CLI
python3 -m leviathan.cli.leviathanctl topo-summary --target leviathan
```

## Expected Behavior (After Fixes)

### Control Plane Logs
✅ No validation errors for `AttemptNode`
✅ No "artifact not found" warnings
✅ Events successfully ingested and projected to graph

### Worker Output
```
Leviathan Worker
Target: leviathan
Task: topology-leviathan-v1
Attempt: attempt-local-1738000000

Task not found in backlog, using system-scope fallback for topology task
...
✓ Topology analysis complete
  - Areas: 6
  - Subsystems: 12
  - Dependencies: 8

Posting event bundle to control plane...
✓ Posted 15 events, 4 artifacts

✅ Worker completed successfully
```

### Topology Query Response
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

## Diffstat

```
 INTEGRITY_FIXES.md                        | 201 ++++++++++++++++++++++++++++++
 QUICKSTART_LOCAL.md                       |   8 ++
 docs/LOCAL_TOPOLOGY_RUN.md                |  16 ++-
 leviathan/executor/worker.py              |   5 +-
 tests/unit/test_worker_system_scope.py    |   1 +
 tests/unit/test_worker_workspace.py       |   3 +-
 6 files changed, 227 insertions(+), 7 deletions(-)
```

## Architecture Notes

### Artifact Store Design
- **Content-addressed**: Artifacts stored by SHA256 hash
- **Deduplication**: Same content stored only once
- **Sharding**: Files stored in `<sha256[:2]>/<sha256>` structure
- **Pluggable backends**: File (default) or S3 for failover

### Default Locations
- **Events**: `~/.leviathan/graph/events.ndjson`
- **Artifacts**: `~/.leviathan/artifacts/`
- **Workspace**: `/workspace` (K8s) or `/tmp/leviathan-workspace` (local)

### Event Lifecycle
```
attempt.created (attempt_number=1)
  ↓
attempt.started
  ↓
topo.started
  ↓
topo.area.discovered (multiple)
  ↓
topo.subsystem.discovered (multiple)
  ↓
topo.dependency.discovered (multiple)
  ↓
topo.indexed
  ↓
topo.completed
  ↓
artifact.created (multiple)
  ↓
attempt.succeeded
```

## Related Documentation
- [Local Topology Run Guide](docs/LOCAL_TOPOLOGY_RUN.md)
- [Quickstart Local](QUICKSTART_LOCAL.md)
- [Target Bootstrap](docs/TARGET_BOOTSTRAP.md)
- [Topography](docs/TOPOGRAPHY.md)
