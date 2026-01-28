> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# Target Bootstrap v1

## Overview

Target Bootstrap is a **deterministic, read-only** indexing system that populates Leviathan's graph with observable facts about a target repository's structure. It runs as a special type of attempt that does **not** use LLM interpretation and does **not** modify the target repository.

## Purpose

Bootstrap solves the cold-start problem: before Leviathan can operate on a repository, it needs to understand what files exist, where documentation lives, what workflows are configured, and what APIs are exposed. Bootstrap provides this foundational knowledge through pure observation.

## Key Principles

1. **Deterministic**: Same repository state always produces same events
2. **Read-Only**: Never modifies the target repository
3. **No LLM Calls**: Pure file system traversal and parsing
4. **Factual Only**: Records observable facts, no interpretation
5. **Auditable**: All discoveries logged as events in the graph

## What Bootstrap Discovers

### 1. Files
For every file in the repository:
- Path relative to repo root
- SHA256 hash
- Size in bytes
- File type (by extension)
- Language (for code files)

**Event**: `file.discovered`

**Payload**:
```json
{
  "target_id": "radix",
  "file_path": "services/api/main.py",
  "sha256": "abc123...",
  "size_bytes": 4096,
  "file_type": "python",
  "language": "python"
}
```

### 2. Documentation
For every markdown file:
- Path
- First heading (extracted as title)
- SHA256 hash

**Event**: `doc.discovered`

**Payload**:
```json
{
  "target_id": "radix",
  "doc_path": "docs/ARCHITECTURE.md",
  "doc_title": "Radix Architecture",
  "sha256": "def456..."
}
```

### 3. GitHub Actions Workflows
For every `.github/workflows/*.yml` file:
- Workflow name
- Triggers (on: push, pull_request, etc.)
- Path
- SHA256 hash

**Event**: `workflow.discovered`

**Payload**:
```json
{
  "target_id": "radix",
  "workflow_name": "CI",
  "workflow_path": ".github/workflows/ci.yml",
  "triggers": ["push", "pull_request"],
  "sha256": "ghi789..."
}
```

### 4. FastAPI Routes (Optional)
For Python files containing FastAPI routes:
- HTTP method (GET, POST, etc.)
- Path (/api/users, etc.)
- Source file
- Function name

**Event**: `api.route.discovered`

**Payload**:
```json
{
  "target_id": "radix",
  "method": "GET",
  "path": "/api/users",
  "source_file": "services/api/routes/users.py",
  "function_name": "list_users"
}
```

**Note**: Routes are extracted via AST parsing (deterministic). No code execution.

## Bootstrap Configuration

Repositories can provide a `.leviathan/bootstrap.yaml` file to control indexing:

```yaml
bootstrap:
  include:
    - "docs/**"
    - ".github/workflows/**"
    - "services/**"
    - "infra/**"
    - "*.md"
  
  exclude:
    - ".git/**"
    - "**/node_modules/**"
    - "**/.venv/**"
    - "**/__pycache__/**"
    - "**/dist/**"
    - "**/build/**"
  
  api_routes:
    enabled: true
```

**Defaults** (if no config file):
- Include: All files
- Exclude: `.git`, `node_modules`, `.venv`, `__pycache__`, `dist`, `build`
- API routes: Enabled

## Running Bootstrap

### Option 1: Via leviathanctl (Recommended)

```bash
leviathanctl bootstrap radix
```

This creates a synthetic bootstrap task and submits it to the executor.

### Option 2: Via Backlog Task

Add to target's `backlog.yaml`:

```yaml
tasks:
  - task_id: bootstrap-radix-v1
    title: "Bootstrap Radix repository"
    scope: bootstrap
    priority: high
    estimated_size: small
    allowed_paths: []  # Read-only, no modifications
    acceptance_criteria:
      - "Repository indexed"
      - "Files, docs, workflows discovered"
    status: pending
```

Then run scheduler:

```bash
kubectl create job leviathan-scheduler-run \
  --from=cronjob/leviathan-scheduler
```

## Execution Flow

```
1. Worker starts bootstrap task
2. Clone target repository
3. Load bootstrap.yaml (if present)
4. Walk file tree (respecting excludes)
5. For each file:
   - Compute SHA256
   - Classify type
   - Emit file.discovered event
   - If markdown: extract title, emit doc.discovered
   - If workflow: parse YAML, emit workflow.discovered
   - If Python: extract routes, emit api.route.discovered
6. Emit repo.indexed event (summary counts)
7. Generate artifacts:
   - repo_tree.txt (file listing)
   - repo_manifest.json (summary stats)
   - workflows_manifest.json (workflow details)
   - api_routes.json (API route details)
8. Upload artifacts to artifact store
9. Post event bundle to control plane
10. Mark attempt.succeeded (no PR created)
```

## Artifacts Generated

### repo_tree.txt
Plain text listing of all discovered files:

```
.github/workflows/ci.yml
.github/workflows/release.yml
README.md
docs/ARCHITECTURE.md
services/api/main.py
services/api/routes/users.py
...
```

### repo_manifest.json
Summary statistics:

```json
{
  "target_id": "radix",
  "repo_url": "git@github.com:owner/radix.git",
  "commit_sha": "abc123...",
  "default_branch": "main",
  "indexed_at": "2024-01-01T00:00:00Z",
  "counts": {
    "total_files": 247,
    "by_type": {
      "python": 89,
      "markdown": 12,
      "yaml": 8,
      "javascript": 45,
      ...
    },
    "docs": 12,
    "workflows": 3,
    "api_routes": 24
  }
}
```

### workflows_manifest.json
Detailed workflow information:

```json
[
  {
    "target_id": "radix",
    "workflow_name": "CI",
    "workflow_path": ".github/workflows/ci.yml",
    "triggers": ["push", "pull_request"],
    "sha256": "..."
  },
  ...
]
```

### api_routes.json
Discovered API routes:

```json
[
  {
    "target_id": "radix",
    "method": "GET",
    "path": "/api/users",
    "source_file": "services/api/routes/users.py",
    "function_name": "list_users"
  },
  ...
]
```

## Local Execution

For local testing of bootstrap/topology tasks without K8s:

```bash
# Set workspace directory for local runs
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

# Set other required env vars
export TARGET_NAME=my-target
export TARGET_REPO_URL=https://github.com/owner/repo.git
export TASK_ID=bootstrap-my-target
export ATTEMPT_ID=attempt-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=your-token

# Run worker
python3 -m leviathan.executor.worker
```

**Note**: `LEVIATHAN_WORKSPACE_DIR` is optional. If not set, worker will use `/workspace` (K8s) or fall back to `/tmp/leviathan-workspace` (local).

## Querying Bootstrap Results

### Graph Summary

```bash
leviathanctl graph-summary
```

Output includes bootstrap counts:

```json
{
  "nodes_by_type": {
    "Target": 1,
    "File": 247,
    "Doc": 12,
    "Workflow": 3,
    "APIRoute": 24,
    ...
  },
  ...
}
```

### View Attempt

```bash
leviathanctl attempts-show attempt-bootstrap-radix-123
```

Shows:
- Attempt status
- Artifacts generated
- Event count
- Indexing statistics

### Download Artifacts

Artifacts are stored in the artifact store and can be retrieved via the control plane API:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  $CONTROL_PLANE_URL/v1/artifacts/$SHA256 \
  -o repo_manifest.json
```

## Use Cases

### 1. Initial Target Onboarding

When adding a new target repository to Leviathan:

```bash
# Register target
kubectl create configmap leviathan-target-radix \
  --from-file=contract.yaml \
  --from-file=backlog.yaml \
  --from-file=policy.yaml

# Bootstrap to populate graph
leviathanctl bootstrap radix

# Verify
leviathanctl graph-summary
```

### 2. Periodic Re-indexing

Re-run bootstrap after major repository changes:

```bash
# After large refactor or migration
leviathanctl bootstrap radix

# Compare with previous bootstrap
leviathanctl attempts-list --target radix --limit 2
```

### 3. Documentation Discovery

Find all documentation in a repository:

```bash
# Bootstrap if not already done
leviathanctl bootstrap radix

# Query for docs (via graph API)
curl -H "Authorization: Bearer $TOKEN" \
  $CONTROL_PLANE_URL/v1/graph/nodes?type=Doc
```

### 4. API Surface Analysis

Understand what APIs a service exposes:

```bash
# Bootstrap to discover routes
leviathanctl bootstrap radix

# Download API routes artifact
# (artifact SHA from attempt details)
curl -H "Authorization: Bearer $TOKEN" \
  $CONTROL_PLANE_URL/v1/artifacts/$SHA256 \
  -o api_routes.json

# Analyze routes
jq '.[] | select(.path | startswith("/api/v2"))' api_routes.json
```

## Safety Guarantees

### What Bootstrap DOES

✅ Read files from repository
✅ Compute hashes and metadata
✅ Parse YAML and Python AST
✅ Emit events to control plane
✅ Upload artifacts to artifact store

### What Bootstrap DOES NOT DO

❌ Modify any files in the repository
❌ Create branches or commits
❌ Create pull requests
❌ Call LLM APIs
❌ Execute any code from the repository
❌ Make network requests (except to control plane)

## Limitations

### 1. Language Support

FastAPI route extraction only works for Python. Other languages require custom parsers.

**Workaround**: Add route discovery for other frameworks as needed (e.g., Express.js, Go Gin).

### 2. Large Repositories

Very large repositories (>10k files) may take several minutes to index.

**Workaround**: Use `bootstrap.yaml` to exclude unnecessary directories.

### 3. Binary Files

Binary files are indexed (path, hash, size) but content is not analyzed.

**Workaround**: This is intentional. Bootstrap is for structure, not content analysis.

### 4. Dynamic Routes

Routes defined dynamically (e.g., via loops or config) are not discovered.

**Workaround**: Only statically-defined routes with decorators are found. This is a feature, not a bug—dynamic routes require runtime analysis.

## Troubleshooting

### Bootstrap Fails with "No such file or directory"

**Cause**: Repository clone failed or bootstrap.yaml has invalid paths.

**Fix**: Check repository URL and credentials. Verify bootstrap.yaml paths exist.

### No API Routes Discovered

**Cause**: `api_routes.enabled: false` in bootstrap.yaml, or no FastAPI decorators found.

**Fix**: Enable API route discovery in bootstrap.yaml. Verify Python files use `@app.get()` style decorators.

### Too Many Files Indexed

**Cause**: Default excludes not sufficient for your repository.

**Fix**: Add custom excludes to `.leviathan/bootstrap.yaml`:

```yaml
bootstrap:
  exclude:
    - ".git/**"
    - "**/node_modules/**"
    - "**/vendor/**"  # Add custom excludes
    - "**/tmp/**"
```

### Bootstrap Attempt Shows as Failed

**Cause**: Exception during indexing (permissions, encoding, etc.).

**Fix**: Check attempt logs:

```bash
leviathanctl attempts-show attempt-bootstrap-radix-123
```

Look for error in failure_type and error_summary.

## Future Enhancements

### Planned

- [ ] Support for Express.js route discovery (JavaScript/TypeScript)
- [ ] Support for Go Gin route discovery
- [ ] Database schema discovery (SQL files, migrations)
- [ ] Dependency graph extraction (imports, requires)
- [ ] Test coverage mapping (test files → source files)

### Not Planned

- ❌ LLM-based code understanding (violates determinism principle)
- ❌ Execution-based discovery (violates read-only principle)
- ❌ External API calls (violates isolation principle)

## Comparison with Other Approaches

### vs. GitHub Code Search

- **Bootstrap**: Indexes into Leviathan's graph, queryable via control plane
- **GitHub Search**: External service, not integrated with Leviathan

### vs. LLM-based Analysis

- **Bootstrap**: Deterministic, fast, no API costs
- **LLM Analysis**: Non-deterministic, slow, expensive, can hallucinate

### vs. Manual Documentation

- **Bootstrap**: Automated, always up-to-date
- **Manual Docs**: Requires human maintenance, often stale

## Summary

Target Bootstrap v1 provides a **deterministic, read-only, auditable** way to populate Leviathan's graph with observable facts about a repository's structure. It runs as a special attempt that:

1. Walks the file tree
2. Computes hashes and metadata
3. Parses configuration files (YAML)
4. Extracts API routes (Python AST)
5. Emits events to the graph
6. Generates artifacts for later analysis

Bootstrap is the foundation for Leviathan's understanding of a target repository. It provides the "what exists" knowledge that enables intelligent task execution.

**Key Takeaway**: Bootstrap is boring by design—no LLMs, no interpretation, just facts.
