# Topographic Intelligence v1

## Overview

Topographic Intelligence provides deterministic analysis of repository structure to derive:
- **Repository Areas**: High-level organizational zones (docs, ci, services, infra, tools, tests)
- **Subsystems**: Directory-based boundaries representing logical components
- **Dependencies**: Static analysis of imports and references between subsystems
- **Data Flows**: (Future) Deterministic signals of data movement

All operations are **deterministic** and **read-only**. No LLM calls. No modifications to target repositories.

## Purpose

Topology analysis enables:
- Understanding repository structure at scale
- Identifying subsystem boundaries and dependencies
- Detecting architectural patterns
- Supporting impact analysis for changes
- Providing context for task planning

## Determinism Guarantee

Given the same `(target_id, commit_sha)`, topology analysis produces **identical results** every time:
- Same areas discovered
- Same subsystems identified
- Same dependencies detected
- Same JSON artifacts (byte-for-byte identical)

This is achieved by:
- No LLM calls during topology analysis
- Deterministic path classification rules
- Sorted output in all JSON artifacts
- Fixed rules version (`topo_rules_v1`)

## Architecture

### Topology Indexer

**Module**: `leviathan/topology/indexer.py`

**Input**:
- Repository path
- Target ID
- Commit SHA

**Output**:
- Events (topo.started, topo.area.discovered, topo.subsystem.discovered, topo.dependency.discovered, topo.indexed, topo.completed)
- Artifacts (topo_areas.json, topo_subsystems.json, topo_deps.json, topo_summary.json)

### Classification Rules (v1)

**Areas** (path-based):
- `area/docs`: `docs/**`, `**/*.md`
- `area/ci`: `.github/workflows/**`
- `area/infra`: `infra/**`, `ops/**`, `cloudformation/**`, `terraform/**`
- `area/services`: `services/**`
- `area/tools`: `tools/**`, `scripts/**`
- `area/tests`: `tests/**`, `test/**`, `**/*_test.py`, `**/test_*.py`

**Subsystems** (directory boundaries):
- `services/**` → `subsystem/services/<child>`
- `ops/k8s/**` → `subsystem/ops/k8s/<child>`
- `charts/**` → `subsystem/charts/<child>`
- `tools/**` → `subsystem/tools/<child>`
- Fallback: top-level directory as subsystem

**Dependencies** (static analysis):
- **Python**: AST parse `import` and `from` statements
- **JS/TS**: Regex parse `import ... from '...'` statements
- **Config**: Scan for URL references (`http://<service>`, `<service>.svc`)

Evidence objects record:
```json
{
  "kind": "py_import",
  "from_file": "services/api/main.py",
  "to_module": "services.shared.db",
  "mapped_subsystem": "subsystem/services/shared"
}
```

## Local Execution

For local testing of topology tasks without K8s:

```bash
# Set workspace directory for local runs
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

# Set other required env vars
export TARGET_NAME=my-target
export TARGET_REPO_URL=https://github.com/owner/repo.git
export TASK_ID=topology-my-target
export ATTEMPT_ID=attempt-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=your-token

# Run worker
python3 -m leviathan.executor.worker
```

**Note**: `LEVIATHAN_WORKSPACE_DIR` is optional. If not set, worker will use `/workspace` (K8s) or fall back to `/tmp/leviathan-workspace` (local).

## Event Types

Topology emits these event types (append-only):

- `topo.started`: Topology analysis begins
- `topo.area.discovered`: One area discovered (payload includes area_id, path_prefixes, file_count)
- `topo.subsystem.discovered`: One subsystem discovered (payload includes subsystem_id, root_path, languages, area_id)
- `topo.dependency.discovered`: One dependency discovered (payload includes from_subsystem_id, to_subsystem_id, evidence list)
- `topo.indexed`: Summary of topology analysis (payload includes counts)
- `topo.completed`: Topology analysis complete

All events include:
- `target_id`: Target identifier
- `commit_sha`: Git commit SHA analyzed
- `rules_version`: `topo_rules_v1`

## Artifacts

Topology produces content-addressed JSON artifacts:

### `topo_areas.json`
```json
{
  "target_id": "radix",
  "commit_sha": "abc123...",
  "rules_version": "topo_rules_v1",
  "areas": [
    {
      "area_id": "area/services",
      "path_prefixes": ["services"],
      "file_count": 150,
      "rules_version": "topo_rules_v1",
      "target_id": "radix",
      "commit_sha": "abc123..."
    }
  ]
}
```

### `topo_subsystems.json`
```json
{
  "target_id": "radix",
  "commit_sha": "abc123...",
  "rules_version": "topo_rules_v1",
  "subsystems": [
    {
      "subsystem_id": "subsystem/services/api",
      "area_id": "area/services",
      "root_path": "services/api",
      "languages": {".py": 0.85, ".yaml": 0.15},
      "file_count": 45,
      "rules_version": "topo_rules_v1",
      "target_id": "radix",
      "commit_sha": "abc123..."
    }
  ]
}
```

### `topo_deps.json`
```json
{
  "target_id": "radix",
  "commit_sha": "abc123...",
  "rules_version": "topo_rules_v1",
  "dependencies": [
    {
      "from_subsystem_id": "subsystem/services/api",
      "to_subsystem_id": "subsystem/services/db",
      "evidence": [
        {
          "kind": "py_import",
          "from_file": "services/api/main.py",
          "to_module": "services.db.client",
          "mapped_subsystem": "subsystem/services/db"
        }
      ]
    }
  ]
}
```

### `topo_summary.json`
```json
{
  "target_id": "radix",
  "commit_sha": "abc123...",
  "rules_version": "topo_rules_v1",
  "areas_count": 6,
  "subsystems_count": 12,
  "dependencies_count": 8,
  "flows_count": 0
}
```

## Control Plane API

Topology data is queryable via REST API:

### `GET /v1/topology/summary?target=<id>`
Returns topology summary with counts.

### `GET /v1/topology/areas?target=<id>`
Returns list of repository areas.

### `GET /v1/topology/subsystems?target=<id>`
Returns list of subsystems.

### `GET /v1/topology/dependencies?target=<id>`
Returns list of dependencies with evidence.

All endpoints require bearer token authentication.

## CLI Commands

Query topology via `leviathanctl`:

```bash
# Summary
leviathanctl topo-summary --target radix

# Areas
leviathanctl topo-areas --target radix

# Subsystems
leviathanctl topo-subsystems --target radix

# Dependencies
leviathanctl topo-deps --target radix

# GraphViz DOT output
leviathanctl topo-dot --target radix > topology.dot
dot -Tpng topology.dot -o topology.png
```

## Running Topology Analysis

### Local Execution

```bash
# Set environment variables
export TARGET_NAME=radix
export TARGET_REPO_URL=git@github.com:iangreen74/radix.git
export TARGET_BRANCH=main
export TASK_ID=topology-radix-v1
export ATTEMPT_ID=attempt-local-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=test-token

# Run worker
python3 -m leviathan.executor.worker
```

### Kubernetes Execution

```bash
# Create topology job
kubectl create job leviathan-topology-radix \
  --namespace=leviathan \
  --image=leviathan-worker:local \
  --env="TASK_ID=topology-radix-v1" \
  --env="ATTEMPT_ID=attempt-$(uuidgen)" \
  --env="TARGET_NAME=radix" \
  --env="TARGET_REPO_URL=git@github.com:iangreen74/radix.git" \
  --env="TARGET_BRANCH=main" \
  --env="CONTROL_PLANE_URL=http://leviathan-control-plane:8000"

# Watch job
kubectl logs -n leviathan job/leviathan-topology-radix -f
```

## Invariants

Topology is protected by invariants gate (`ops/invariants.yaml`):

- Artifact names: `topo_areas.json`, `topo_subsystems.json`, `topo_deps.json`, `topo_summary.json`
- Event types: `topo.started`, `topo.area.discovered`, `topo.subsystem.discovered`, `topo.dependency.discovered`, `topo.indexed`, `topo.completed`
- API endpoints: `/v1/topology/summary`, `/v1/topology/areas`, `/v1/topology/subsystems`, `/v1/topology/dependencies`

Validated by `tools/invariants_check.py` in CI.

## Testing

Unit tests in `tests/unit/test_topology_indexer.py`:

```bash
# Run topology tests
python3 -m pytest tests/unit/test_topology_indexer.py -v

# Run all tests
python3 -m pytest tests/unit -v
```

Tests verify:
- Basic indexing functionality
- Area discovery
- Subsystem discovery
- Dependency detection
- Artifact generation
- Deterministic output
- Event types
- Language distribution

## Limitations (v1)

**What topology v1 does**:
✅ Deterministic area classification  
✅ Directory-based subsystem boundaries  
✅ Static import analysis (Python, JS/TS)  
✅ Config reference scanning  
✅ Content-addressed artifacts  
✅ Append-only events  

**What topology v1 does NOT do**:
❌ Semantic code understanding  
❌ Dynamic dependency analysis  
❌ Performance profiling  
❌ Security analysis  
❌ LLM-based classification  
❌ Temporal analysis (changes over time)  

## Future Enhancements (v2+)

Planned improvements:
- **Temporal Intelligence**: Track topology changes over time
- **Data Flow Analysis**: Deterministic data flow detection
- **Critical Path Detection**: Identify high-impact subsystems
- **Soft Invariants**: ML-based pattern detection
- **Cross-Repository Topology**: Multi-repo dependency graphs
- **Performance Metrics**: Subsystem complexity scores

## Design Principles

1. **Determinism First**: Same input → same output, always
2. **No LLM Authority**: Topology is factual, not inferred
3. **Append-Only**: Events are immutable history
4. **Read-Only**: Never modifies target repositories
5. **Content-Addressed**: Artifacts referenced by SHA256
6. **Versioned Rules**: Rules version tracked for reproducibility

## Related Documentation

- [Leviathan Canonical Architecture](LEVIATHAN_CANONICAL.md)
- [Bootstrap v1](HOW_LEVIATHAN_OPERATES.md)
- [Invariants Gate](INVARIANTS.md)
- [Control Plane API](GRAPH_CONTROL_PLANE_API.md)
