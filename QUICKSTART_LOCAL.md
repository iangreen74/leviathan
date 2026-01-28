# Leviathan Local Quickstart

## Run Topology Analysis Locally (3 Commands)

### 1. Start Control Plane
```bash
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

### 2. Run Topology Worker (New Terminal)
```bash
export TARGET_NAME=leviathan
export TARGET_REPO_URL=file://$HOME/leviathan
export TASK_ID=topology-leviathan-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token

python3 -m leviathan.executor.worker
```

### 3. Query Topology Summary
```bash
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/topology/summary?target=leviathan | jq
```

## What Changed

### System-Scope Tasks
Topology and bootstrap tasks now work **without backlog entries**:
- `topology-<target>-v1` → automatic topology indexing
- `bootstrap-<target>-v1` → automatic bootstrap indexing

### Fixed Issues
1. ✅ Worker creates synthetic TaskSpec for system-scope tasks
2. ✅ Event bundles include `target` field at top level
3. ✅ Worker emits `attempt.created` before `attempt.started`
4. ✅ All attempt events include `task_id` and `target_id`
5. ✅ Improved error messages for task not found scenarios

### Tests
All tests pass:
```bash
python3 -m pytest tests/unit -q                    # 332 passed
python3 tools/invariants_check.py                  # ✅ SUCCESS
```

## CLI Commands

Query topology using leviathanctl:
```bash
python3 -m leviathan.cli.leviathanctl topo-summary --target leviathan
python3 -m leviathan.cli.leviathanctl graph-summary
```

## Documentation
- Full guide: [docs/LOCAL_TOPOLOGY_RUN.md](docs/LOCAL_TOPOLOGY_RUN.md)
- Bootstrap: [docs/TARGET_BOOTSTRAP.md](docs/TARGET_BOOTSTRAP.md)
- Topology: [docs/TOPOGRAPHY.md](docs/TOPOGRAPHY.md)
