# Leviathan: Architecture, Operation, and Strategic Roadmap

**Version**: 1.0  
**Date**: 2026-01-25  
**Status**: Living Document

---

## 1. Executive Summary

### What Leviathan Is

Leviathan is a **platform engineering system** that ingests existing software repositories, builds a deterministic knowledge graph about them, and executes scoped engineering tasks through controlled AI-assisted agents. It serves as a long-term SRE and product evolution engine, operating repositories through explicit contracts, backlogs, and policies.

Leviathan is **not** an autonomous planning system. It does not invent work. It executes explicitly defined tasks, creates pull requests for human review, and maintains an append-only audit trail of all actions.

### What Problem It Solves

Modern software systems accumulate technical debt, lose institutional knowledge, and require ongoing maintenance that is tedious but critical. Traditional automation is brittle; pure AI autonomy is unsafe. Leviathan occupies the middle ground:

- **Deterministic ingestion**: Indexes repositories without LLMs to build a factual graph
- **Scoped execution**: AI agents work within explicit boundaries defined by humans
- **Human-in-the-loop**: All changes go through PR review before merge
- **Anti-forgetting**: Invariants and contracts prevent configuration drift
- **Auditability**: Append-only event log provides full history

Leviathan enables teams to maintain and evolve systems at scale while retaining human authority over all changes.

### Why It Exists Separately from Radix

**Radix** is a research platform and future product for evidence-based decision making. It is a *target* that Leviathan operates.

**Leviathan** is the *platform* that enables operating Radix (and other repositories) safely and deterministically. Separating these concerns allows:

- Radix to focus on its domain (research workflows, evidence synthesis)
- Leviathan to be a general-purpose platform for repository operation
- Clear boundaries between product code and platform infrastructure
- Leviathan to eventually operate multiple targets (Radix, VaultScaler infrastructure, etc.)

Leviathan is infrastructure. Radix is product. They are complementary but distinct.

---

## 2. Core Design Principles

### Determinism

Bootstrap and indexing processes produce identical results given identical inputs. No LLM calls during bootstrap. The graph is built from facts, not inferences.

### Auditability

Every action is logged to an append-only event store. Events include:
- `bootstrap.started`, `file.discovered`, `workflow.discovered`, `bootstrap.completed`
- `attempt.created`, `attempt.started`, `attempt.succeeded`, `attempt.failed`
- `pr.created`, `artifact.created`

The event log is the source of truth for "what happened and when."

### Anti-Forgetting

Configuration drift is prevented through:
- **Invariants gate**: `ops/invariants.yaml` defines canonical truths, validated in CI
- **Contracts**: Each target explicitly declares its configuration
- **Policies**: Allowed paths and forbidden patterns are enforced
- **Immutable artifacts**: Bootstrap outputs are stored and referenced by hash

### Explicit Configuration

No magic. No implicit behavior. Everything is declared:
- Targets opt-in via `.leviathan/contract.yaml`
- Tasks are defined in `.leviathan/backlog.yaml`
- Policies are enforced via `.leviathan/policy.yaml`
- Invariants are checked via `tools/invariants_check.py`

### Human Authority

Humans retain final control:
- Humans define tasks in the backlog
- Humans approve all PRs before merge
- Humans can invalidate attempts and retry
- Humans can pause/stop execution at any time

Leviathan proposes. Humans decide.

### Safety by Construction

Multiple layers of safety:
- **Scope enforcement**: Tasks can only modify files in `allowed_paths`
- **Invariant checks**: Quality gates must pass before PR creation
- **PR-based workflow**: No automatic merges
- **Ephemeral execution**: Work happens in isolated worktrees/pods
- **Blocked commands**: Infrastructure-mutating commands are rejected

---

## 3. System Architecture Overview

### Control Plane

The control plane is the orchestrator and state manager:

**Components**:
- **API Server** (`leviathan/control_plane/api.py`): FastAPI service exposing REST endpoints
- **Event Store** (`leviathan/graph/events.py`): Append-only NDJSON or Postgres backend
- **Graph Store** (`leviathan/graph/store.py`): In-memory or Postgres graph of nodes and edges
- **Artifact Store** (`leviathan/artifacts/store.py`): File-based storage for bootstrap outputs
- **Scheduler** (`leviathan/scheduler.py`): Selects next task and dispatches to executor

**Deployment**:
- Runs as Kubernetes Deployment in `leviathan` namespace
- Service name: `leviathan-control-plane` on port `8000`
- Container name: `control-plane`
- Image: `leviathan-control-plane:local` (dev) or immutable tag (prod)

**Responsibilities**:
- Ingest event bundles from workers
- Maintain graph of targets, attempts, artifacts, PRs
- Provide query API for operators (`leviathanctl`)
- Track execution history and failures

### Worker / Executor

The worker executes tasks in isolated environments:

**Components**:
- **Worker** (`leviathan/executor/worker.py`): Main execution loop
- **Model Client** (`leviathan/model_client.py`): Claude API integration
- **Git Client** (`leviathan/git_client.py`): Repository operations
- **GitHub Client** (`leviathan/github.py`): PR creation
- **Bootstrap Indexer** (`leviathan/bootstrap/indexer.py`): Deterministic repo analysis

**Deployment**:
- Runs as Kubernetes Job per attempt
- Container name: `worker`
- Image: `leviathan-worker:local` (dev) or immutable tag (prod)
- Ephemeral: Job terminates after task completion

**Responsibilities**:
- Clone target repository
- Execute bootstrap (if `scope=bootstrap`) or task (if normal task)
- Generate changes via LLM (for tasks) or deterministic indexing (for bootstrap)
- Validate changes against policy
- Create PR (for tasks) or upload artifacts (for bootstrap)
- Post event bundle to control plane

### Graph Store

The graph represents the system's knowledge:

**Node Types**:
- `Target`: A repository being operated (e.g., Radix)
- `Attempt`: A single execution of a task or bootstrap
- `Artifact`: An output file (repo_manifest.json, workflows_manifest.json, etc.)
- `PR`: A pull request created by Leviathan

**Edge Types**:
- `TARGETS`: Control plane → Target
- `EXECUTED`: Target → Attempt
- `PRODUCED`: Attempt → Artifact
- `CREATED`: Attempt → PR

**Properties**:
- Nodes have `node_type`, `node_id`, `properties` (dict)
- Edges have `edge_type`, `from_node`, `to_node`, `properties` (dict)
- Graph is built from events, not stored separately (event sourcing)

### Artifact Store

Stores immutable outputs from bootstrap:

**Artifacts**:
- `repo_tree.txt`: Directory tree of repository
- `repo_manifest.json`: File counts, types, sizes
- `workflows_manifest.json`: GitHub Actions workflows discovered
- `api_routes.json`: API endpoints discovered

**Storage**:
- File-based: `~/.leviathan/artifacts/{sha256}/filename`
- Artifacts referenced by SHA256 hash
- Immutable: Once written, never modified

### Kubernetes as Execution Substrate

Leviathan uses Kubernetes for:
- **Isolation**: Each attempt runs in its own pod
- **Scalability**: Multiple attempts can run concurrently
- **Resource limits**: CPU/memory constraints per job
- **Cleanup**: Jobs auto-delete after completion
- **Secrets management**: K8s Secrets for API keys

**Namespace**: `leviathan`

**Key Resources**:
- Deployment: `leviathan-control-plane`
- Service: `leviathan-control-plane` (ClusterIP, port 8000)
- Jobs: `leviathan-worker-{attempt-id}` (created per attempt)
- Secrets: `leviathan-secrets` (tokens, API keys)

### Separation of Concerns

**Control Plane**:
- Stateful
- Long-lived
- Manages graph and events
- Provides query API

**Worker**:
- Stateless
- Ephemeral
- Executes one task
- Posts results and terminates

**Graph**:
- Append-only
- Event-sourced
- Queryable
- Immutable history

**Artifacts**:
- Content-addressed
- Immutable
- Referenced by hash

---

## 4. The Graph Model

### What the Graph Represents

The graph is a **knowledge base** about targets and their evolution:

- **Facts about repositories**: Files, workflows, API routes, documentation
- **Execution history**: What tasks were attempted, when, by whom
- **Artifacts produced**: Bootstrap outputs, test results, build artifacts
- **PRs created**: What changes were proposed, what was merged

The graph is **not** a code analysis tool. It does not understand semantics. It records facts and relationships.

### Node and Event Types

**Nodes** (entities):
- `Target`: Repository being operated
- `Attempt`: Execution of a task or bootstrap
- `Artifact`: File produced by an attempt
- `PR`: Pull request created by an attempt

**Events** (state changes):
- `bootstrap.started`, `bootstrap.completed`: Bootstrap lifecycle
- `file.discovered`, `doc.discovered`, `workflow.discovered`, `api.route.discovered`: Discovery events
- `repo.indexed`: Summary of bootstrap results
- `attempt.created`, `attempt.started`, `attempt.succeeded`, `attempt.failed`: Attempt lifecycle
- `artifact.created`: Artifact uploaded
- `pr.created`: PR opened

### Why Append-Only

Append-only design provides:

1. **Auditability**: Full history is preserved, never overwritten
2. **Debugging**: Can replay events to understand failures
3. **Immutability**: Past events cannot be altered (integrity)
4. **Event sourcing**: Graph state is derived from events, not stored separately
5. **Concurrency**: No write conflicts (only appends)

### How Bootstrap Populates the Graph

Bootstrap is a **deterministic, LLM-free** process:

```
1. Clone target repository at specific commit SHA
2. Walk file tree, emit file.discovered events
3. Parse .github/workflows/*.yml, emit workflow.discovered events
4. Scan for API routes (FastAPI, Flask, etc.), emit api.route.discovered events
5. Identify documentation files, emit doc.discovered events
6. Generate repo_manifest.json with counts and statistics
7. Upload artifacts to artifact store
8. Emit artifact.created events
9. Emit bootstrap.completed event
10. Post event bundle to control plane
```

**Result**: Graph now contains facts about the repository at a specific point in time.

**No LLMs**: Bootstrap uses regex, AST parsing, and file system operations only. This ensures determinism and reproducibility.

### How Ongoing Execution Extends It

After bootstrap, tasks extend the graph:

```
1. Scheduler selects task from backlog
2. Creates attempt node
3. Worker executes task (may use LLM)
4. Worker creates PR
5. Worker emits pr.created event
6. Worker posts event bundle to control plane
7. Graph updated with new attempt and PR nodes
```

**Result**: Graph tracks what work was done, what PRs were created, what was merged.

### Why This Enables SRE-Like Behavior

The graph enables:

- **Failure analysis**: Query all failed attempts for a target
- **Trend detection**: Count bootstrap runs over time, track file growth
- **Dependency tracking**: See what artifacts were produced by which attempts
- **Audit trail**: Answer "who changed what and when"
- **Replay**: Re-run bootstrap at a specific commit to compare
- **Metrics**: Count attempts, success rate, PR merge rate

The graph is the foundation for observability and continuous improvement.

---

## 5. Target Model (Radix as Example)

### What It Means to "Ingest" a Repository

Ingesting a repository means:

1. **Registration**: Add target config to control plane
2. **Bootstrap**: Run deterministic indexing to populate graph
3. **Contract**: Target provides `.leviathan/contract.yaml`, `backlog.yaml`, `policy.yaml`
4. **Ongoing operation**: Scheduler selects tasks, workers execute, PRs are created

**Radix** is the first target. It is a research platform with:
- Python codebase
- FastAPI backend
- React frontend
- GitHub Actions CI/CD
- Documentation in Markdown

Leviathan ingests Radix by:
- Running bootstrap to index files, workflows, API routes
- Reading backlog from `.leviathan/backlog.yaml`
- Executing tasks within policy boundaries
- Creating PRs for human review

### Bootstrap Process

Bootstrap for Radix:

```bash
# Trigger bootstrap
kubectl create job leviathan-bootstrap-radix \
  --from=cronjob/leviathan-bootstrap

# Bootstrap worker:
1. Clones git@github.com:iangreen74/radix.git
2. Walks file tree (1481 files)
3. Discovers 21 GitHub workflows
4. Discovers 29 API routes
5. Identifies 367 documentation files
6. Generates repo_manifest.json
7. Uploads artifacts
8. Posts events to control plane
```

**Output**:
- `repo_tree.txt`: Full directory listing
- `repo_manifest.json`: `{"counts": {"total_files": 1481, "by_type": {"python": 450, ...}}}`
- `workflows_manifest.json`: List of workflows with triggers
- `api_routes.json`: List of API endpoints with methods

**Graph updated**:
- `bootstrap.started` event
- 1481 `file.discovered` events
- 367 `doc.discovered` events
- 21 `workflow.discovered` events
- 29 `api.route.discovered` events
- `repo.indexed` event
- `bootstrap.completed` event

### Backlog Synthesis

After bootstrap, Leviathan can **propose** (not execute) tasks:

```bash
leviathanctl backlog-suggest radix
```

**Process**:
1. Load bootstrap artifacts (repo_manifest, workflows, api_routes)
2. Load current backlog from Radix repo
3. Load policy constraints
4. Generate task proposals via LLM (or fallback to deterministic templates)
5. Validate proposals against policy
6. Create PR to Radix with updated `.leviathan/backlog.yaml`

**Proposed tasks** (example):
- `radix-dataset-schema-v1`: Define dataset registration schema
- `radix-dataset-api-stub-v1`: Create dataset API stub
- `radix-research-schema-v1`: Define research plan schema
- `radix-experiment-schema-v1`: Define experiment execution schema
- `radix-evidence-schema-v1`: Define evidence pack schema
- `radix-answer-schema-v1`: Define answer synthesis schema

**Governance**:
- Tasks only modify `.leviathan/backlog.yaml` (never product code)
- Human reviews and approves backlog PR
- Tasks remain `ready: false` until human sets `ready: true`

### Ongoing Task Execution

Once tasks are in the backlog:

```
1. Scheduler reads backlog.yaml from Radix repo
2. Filters tasks by status=pending, ready=true
3. Selects highest priority task
4. Creates attempt
5. Dispatches worker job
6. Worker executes task (may use LLM)
7. Worker validates changes against policy
8. Worker creates PR to Radix
9. Human reviews and merges PR
10. Scheduler updates task status to completed
```

**Example task**:
```yaml
- id: radix-dataset-schema-v1
  title: Define dataset registration schema
  scope: core
  priority: high
  ready: true
  allowed_paths:
    - .leviathan/schemas/dataset.yaml
  acceptance_criteria:
    - Schema defines required fields for dataset registration
    - Schema includes validation rules
    - Schema is documented with examples
  dependencies: []
  estimated_size: small
```

**Worker execution**:
1. Clones Radix repo
2. Reads task spec
3. Calls Claude API with prompt including acceptance criteria
4. Claude generates `.leviathan/schemas/dataset.yaml`
5. Worker validates: only `.leviathan/schemas/dataset.yaml` modified ✓
6. Worker creates PR
7. Human reviews schema, approves, merges

### How Leviathan Does NOT Magically "Understand Everything"

**What Leviathan knows**:
- File paths and types (from bootstrap)
- Workflow triggers (from parsing YAML)
- API endpoint paths (from regex/AST parsing)
- Documentation file locations (from file extensions)

**What Leviathan does NOT know**:
- Business logic or domain semantics
- Why code was written a certain way
- Architectural intent
- Performance characteristics
- Security implications

Leviathan is **not** a code understanding system. It indexes facts and executes scoped tasks. Understanding comes from:
- Human-written acceptance criteria
- Human-defined policies
- Human review of PRs

### What Guarantees It Does and Does Not Make

**Guarantees**:
✅ Bootstrap is deterministic (same repo → same artifacts)  
✅ Tasks only modify files in `allowed_paths`  
✅ All changes go through PR review  
✅ All actions are logged to event store  
✅ Invariants are checked before PR creation  

**Non-Guarantees**:
❌ Tasks will succeed (LLM may fail, tests may fail)  
❌ Generated code is correct (human review required)  
❌ PRs will be merged (human decision)  
❌ System will "understand" requirements (explicit criteria needed)  
❌ Autonomous planning (tasks must be explicitly defined)  

---

## 6. Execution Lifecycle

### Target Registration

**Step 1: Create target config**

```yaml
# ~/.leviathan/targets/radix.yaml
target_id: radix
name: Radix Research Platform
repo_url: git@github.com:iangreen74/radix.git
default_branch: main
description: Evidence-based research platform
owner: platform-team
```

**Step 2: Deploy to control plane**

```bash
kubectl create configmap leviathan-target-radix \
  --from-file=target.yaml=~/.leviathan/targets/radix.yaml
```

**Step 3: Trigger bootstrap**

```bash
kubectl create job leviathan-bootstrap-radix \
  --from=cronjob/leviathan-bootstrap
```

### Task Selection

**Scheduler logic**:

```python
1. Load backlog.yaml from target repo
2. Filter tasks:
   - status == "pending"
   - ready == true
   - dependencies satisfied
3. Sort by priority (high > medium > low)
4. Check concurrency limit (max_open_prs)
5. Select highest priority task
6. Create attempt record
7. Dispatch worker job
```

### Attempt Creation

**Attempt record**:

```json
{
  "attempt_id": "attempt-radix-abc123",
  "target_id": "radix",
  "task_id": "radix-dataset-schema-v1",
  "status": "created",
  "created_at": "2026-01-25T18:00:00Z"
}
```

**Event emitted**: `attempt.created`

### Worker Execution

**Worker job lifecycle**:

```
1. Job pod starts
2. Worker loads task spec from backlog
3. Worker loads policy from target repo
4. Worker clones target repo
5. Worker executes task:
   - For bootstrap: Run deterministic indexer
   - For normal task: Call LLM with prompt
6. Worker validates changes against policy
7. Worker runs invariant checks
8. If all pass: Create PR
9. If any fail: Mark attempt as failed
10. Worker posts event bundle to control plane
11. Job pod terminates
```

**Environment variables**:
- `TASK_ID`: Task identifier
- `ATTEMPT_ID`: Attempt identifier
- `TARGET_NAME`: Target name
- `TARGET_REPO_URL`: Git URL
- `TARGET_BRANCH`: Default branch
- `CONTROL_PLANE_URL`: API endpoint
- `CONTROL_PLANE_TOKEN`: Auth token
- `GITHUB_TOKEN`: GitHub PAT
- `LEVIATHAN_CLAUDE_API_KEY`: Claude API key
- `LEVIATHAN_CLAUDE_MODEL`: Model name

### Event Emission

**Events posted to control plane**:

```json
{
  "target": "radix",
  "bundle_id": "bundle-abc123",
  "events": [
    {
      "event_id": "attempt-started-abc123",
      "event_type": "attempt.started",
      "timestamp": "2026-01-25T18:00:01.000000",
      "actor_id": "worker-abc123",
      "payload": {"attempt_id": "attempt-abc123", "status": "running"}
    },
    {
      "event_id": "pr-created-xyz",
      "event_type": "pr.created",
      "timestamp": "2026-01-25T18:00:30.000000",
      "actor_id": "worker-abc123",
      "payload": {
        "pr_number": 42,
        "pr_url": "https://github.com/iangreen74/radix/pull/42",
        "branch_name": "leviathan/radix-dataset-schema-v1"
      }
    },
    {
      "event_id": "attempt-succeeded-abc123",
      "event_type": "attempt.succeeded",
      "timestamp": "2026-01-25T18:00:31.000000",
      "actor_id": "worker-abc123",
      "payload": {"attempt_id": "attempt-abc123", "status": "succeeded"}
    }
  ],
  "artifacts": []
}
```

### Artifact Storage

**For bootstrap attempts**:

```
1. Worker generates artifacts (repo_manifest.json, etc.)
2. Worker computes SHA256 hash of each artifact
3. Worker uploads to artifact store
4. Worker emits artifact.created events
5. Artifacts referenced by hash in graph
```

**Artifact metadata**:

```json
{
  "artifact_id": "artifact-repo-manifest-abc123",
  "artifact_name": "repo_manifest.json",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "size_bytes": 4096,
  "created_at": "2026-01-25T18:00:15Z"
}
```

### Optional PR Creation

**For normal tasks** (not bootstrap):

```
1. Worker creates branch: leviathan/{task-id}
2. Worker commits changes
3. Worker pushes branch to origin
4. Worker calls GitHub API to create PR
5. PR title: Task title
6. PR body: Acceptance criteria + metadata
7. Worker emits pr.created event
```

**For bootstrap tasks**:
- No PR created
- Artifacts uploaded instead
- Events posted to control plane

### Human Review

**Human workflow**:

```
1. Receive notification of new PR
2. Review changes against acceptance criteria
3. Check that only allowed_paths were modified
4. Verify tests pass
5. Approve and merge, or request changes
```

**If changes requested**:
- Human comments on PR
- Leviathan does NOT automatically retry
- Human can manually re-run task or modify backlog

**If approved and merged**:
- Scheduler detects merge (via GitHub webhook or polling)
- Scheduler updates backlog: task status → completed
- Scheduler commits updated backlog to target repo

---

## 7. Operational Model

### Running Leviathan Locally

**Prerequisites**:
- Python 3.10+
- Docker (for building images)
- kubectl (for K8s deployment)
- GitHub CLI (`gh`) authenticated

**Local development**:

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run control plane locally
export LEVIATHAN_CONTROL_PLANE_TOKEN=test-token
python3 -m leviathan.control_plane.api

# In another terminal, run worker for bootstrap
export TASK_ID=bootstrap-radix-v1
export ATTEMPT_ID=attempt-local-123
export TARGET_NAME=radix
export TARGET_REPO_URL=git@github.com:iangreen74/radix.git
export TARGET_BRANCH=main
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=test-token
python3 -m leviathan.executor.worker
```

### Running Leviathan in Kubernetes

**Build images**:

```bash
# Build control plane image
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .

# Build worker image
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .

# Load into kind cluster (if using kind)
kind load docker-image leviathan-control-plane:local
kind load docker-image leviathan-worker:local
```

**Deploy control plane**:

```bash
# Create namespace
kubectl create namespace leviathan

# Create secrets
kubectl create secret generic leviathan-secrets \
  --namespace=leviathan \
  --from-literal=control-plane-token=<token> \
  --from-literal=github-token=<github-pat> \
  --from-literal=claude-api-key=<claude-key>

# Deploy control plane
kubectl apply -f ops/k8s/control-plane.yaml

# Verify deployment
kubectl get pods -n leviathan
kubectl logs -n leviathan deployment/leviathan-control-plane
```

**Trigger bootstrap**:

```bash
# Create job from template
kubectl create job leviathan-bootstrap-radix \
  --namespace=leviathan \
  --from=cronjob/leviathan-bootstrap

# Watch job
kubectl get jobs -n leviathan -w

# View logs
kubectl logs -n leviathan job/leviathan-bootstrap-radix
```

### Secrets and Configuration

**Required secrets**:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: leviathan-secrets
  namespace: leviathan
type: Opaque
stringData:
  control-plane-token: <secure-random-token>
  github-token: <github-personal-access-token>
  claude-api-key: <anthropic-api-key>
  claude-model: claude-3-5-sonnet-20241022
```

**Control plane env vars**:
- `LEVIATHAN_CONTROL_PLANE_TOKEN`: Auth token for API
- `LEVIATHAN_CONTROL_PLANE_BACKEND`: `ndjson` or `postgres`
- `LEVIATHAN_POSTGRES_URL`: (if postgres backend)

**Worker env vars**:
- `CONTROL_PLANE_URL`: `http://leviathan-control-plane:8000`
- `CONTROL_PLANE_TOKEN`: Same as control plane token
- `GITHUB_TOKEN`: GitHub PAT with repo scope
- `LEVIATHAN_CLAUDE_API_KEY`: Claude API key
- `LEVIATHAN_CLAUDE_MODEL`: Model name
- `TASK_ID`: Injected by scheduler
- `ATTEMPT_ID`: Injected by scheduler
- `TARGET_NAME`: Injected by scheduler
- `TARGET_REPO_URL`: Injected by scheduler
- `TARGET_BRANCH`: Injected by scheduler

### Common Failure Modes

**1. No pods found**

```
Error: No resources found in leviathan namespace
```

**Cause**: Deployment not applied or wrong namespace

**Fix**:
```bash
kubectl apply -f ops/k8s/control-plane.yaml
kubectl get pods -n leviathan
```

**2. Image pull errors**

```
ImagePullBackOff: Failed to pull image "leviathan-control-plane:local"
```

**Cause**: Image not loaded into cluster (kind) or wrong tag

**Fix**:
```bash
# For kind
kind load docker-image leviathan-control-plane:local
kind load docker-image leviathan-worker:local

# For production, use immutable tags
docker tag leviathan-control-plane:local ghcr.io/iangreen74/leviathan-control-plane:v1.0.0
docker push ghcr.io/iangreen74/leviathan-control-plane:v1.0.0
```

**3. Secret not found**

```
Error: secret "leviathan-secrets" not found
```

**Cause**: Secrets not created in namespace

**Fix**:
```bash
kubectl create secret generic leviathan-secrets \
  --namespace=leviathan \
  --from-literal=control-plane-token=<token> \
  --from-literal=github-token=<github-pat> \
  --from-literal=claude-api-key=<claude-key>
```

**4. Worker job fails immediately**

```
Job status: Failed
```

**Cause**: Missing env vars or invalid task spec

**Fix**:
```bash
# Check job logs
kubectl logs -n leviathan job/leviathan-worker-{attempt-id}

# Common issues:
# - CONTROL_PLANE_URL not set
# - GITHUB_TOKEN invalid
# - Task not found in backlog
```

**5. Bootstrap events not persisted**

```
Worker posts 1907 events, but events.ndjson only has 7
```

**Cause**: Event ingestion silently failing (fixed in recent commit)

**Fix**:
- Check control plane logs for ingestion errors
- Verify event validation logic
- Ensure timestamp format is ISO8601

### How to Debug Safely and Deterministically

**1. Check invariants first**:

```bash
python3 tools/invariants_check.py
```

If invariants fail, fix configuration before debugging further.

**2. Query control plane**:

```bash
export LEVIATHAN_API_URL=http://localhost:8000
export LEVIATHAN_CONTROL_PLANE_TOKEN=<token>

# View graph summary
python3 -m leviathan.cli.leviathanctl graph-summary

# List recent attempts
python3 -m leviathan.cli.leviathanctl attempts-list --limit 10

# Show attempt details
python3 -m leviathan.cli.leviathanctl attempts-show <attempt-id>
```

**3. Inspect events**:

```bash
# For NDJSON backend
cat ~/.leviathan/graph/events.ndjson | jq '.event_type' | sort | uniq -c

# Check for bootstrap events
cat ~/.leviathan/graph/events.ndjson | jq 'select(.event_type | startswith("bootstrap"))'
```

**4. Replay bootstrap locally**:

```bash
# Set env vars
export TASK_ID=bootstrap-radix-v1
export ATTEMPT_ID=attempt-debug-123
export TARGET_NAME=radix
export TARGET_REPO_URL=git@github.com:iangreen74/radix.git
export TARGET_BRANCH=main
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=test-token

# Run worker
python3 -m leviathan.executor.worker

# Check artifacts
ls -la /tmp/leviathan-artifacts/
```

**5. Validate artifacts**:

```bash
# Check artifact store
ls -la ~/.leviathan/artifacts/

# Verify artifact content
cat ~/.leviathan/artifacts/{sha256}/repo_manifest.json | jq .
```

**6. Test event ingestion**:

```bash
# Post test event bundle
curl -X POST http://localhost:8000/v1/events/ingest \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "test",
    "bundle_id": "test-123",
    "events": [{
      "event_id": "test-1",
      "event_type": "test.event",
      "timestamp": "2026-01-25T18:00:00.000000",
      "actor_id": "test",
      "payload": {}
    }],
    "artifacts": []
  }'
```

---

## 8. Invariants and Anti-Forgetting Mechanisms

### Purpose of invariants.yaml

Configuration drift is a primary cause of operational failures. As systems evolve, manifests diverge, naming conventions change, and institutional knowledge is lost.

`ops/invariants.yaml` defines **canonical truths** that MUST NOT drift:

- Kubernetes namespace: `leviathan`
- Control plane service name: `leviathan-control-plane`
- Control plane port: `8000`
- Container names: `control-plane`, `worker`
- Image names: `leviathan-control-plane`, `leviathan-worker`
- Required labels and selectors
- Required environment variables
- Forbidden image tags (`:latest`)

### What Is Enforced

**Validated by `tools/invariants_check.py`**:

1. **K8s manifests** (`ops/k8s/*.yaml`):
   - Container names match invariants
   - Image names match invariants
   - No `:latest` tags
   - Labels and selectors match
   - Service names and ports match
   - Namespace is consistent

2. **CI workflows** (`.github/workflows/*.yml`):
   - Invariants check runs before tests
   - Required dependencies installed
   - No `:latest` tags in workflow images

3. **Requirements** (`requirements-dev.txt`):
   - Contains pytest, pyyaml, httpx

4. **Namespace consistency**:
   - All manifests use `leviathan` namespace

### Why This Is Critical for AI-Assisted Engineering

AI-assisted systems have no memory. Each interaction is stateless. Without explicit invariants:

- Configuration drifts over time
- Naming conventions diverge
- Required env vars are forgotten
- Image tags become inconsistent
- Deployment fails mysteriously

Invariants provide:

1. **Institutional memory**: Knowledge is codified, not tribal
2. **Drift prevention**: CI fails if configuration diverges
3. **Onboarding**: New engineers see canonical values
4. **Debugging**: Failures are caught early, not in production
5. **AI context**: Future AI agents can read invariants to understand system

### How CI Enforces Memory

**CI workflow** (`.github/workflows/ci.yml`):

```yaml
- name: Check invariants
  run: |
    python3 tools/invariants_check.py

- name: Run unit tests
  run: |
    python3 -m pytest tests/unit -v
```

**Enforcement**:
- Invariants check runs **before** tests
- If invariants fail, CI fails
- PR cannot be merged until invariants pass
- Forces explicit review of configuration changes

**Example failure**:

```
FAIL: Control plane container name must be 'control-plane', got 'api'
FAIL: Control plane image must start with 'leviathan-control-plane', got 'leviathan-worker:local'
```

Developer must fix configuration to match invariants, or update invariants with explicit justification.

---

## 9. Current State of the System

### What Is Implemented Today

**Core Infrastructure**:
✅ Control plane API (FastAPI)  
✅ Event store (NDJSON and Postgres backends)  
✅ Graph store (in-memory and Postgres)  
✅ Artifact store (file-based)  
✅ Worker execution framework  
✅ Bootstrap indexer (deterministic, no LLMs)  
✅ Model client (Claude API integration)  
✅ GitHub client (PR creation)  
✅ Git client (clone, branch, commit, push)  

**Deployment**:
✅ Kubernetes manifests (control plane, worker job template)  
✅ Docker images (control-plane, worker)  
✅ Secrets management (K8s Secrets)  
✅ Namespace isolation  
✅ CI/CD pipeline (GitHub Actions)  

**Governance**:
✅ Invariants gate (`ops/invariants.yaml`, `tools/invariants_check.py`)  
✅ Contract/backlog/policy model  
✅ Scope enforcement (allowed_paths)  
✅ PR-based workflow  

**Operator Tools**:
✅ `leviathanctl` CLI (graph-summary, attempts-list, failures-recent, invalidate, backlog-suggest)  
✅ Event ingestion API  
✅ Graph query API  

**Testing**:
✅ 277 unit tests passing  
✅ Bootstrap event ingestion tests  
✅ Backlog synthesis validation tests  
✅ API integration tests  

### What Is Stable

**Stable components** (production-ready):
- Event store append-only semantics
- Bootstrap determinism (same repo → same artifacts)
- Invariants validation in CI
- Worker job execution model
- Artifact storage and retrieval
- Graph node/edge model

**Stable workflows**:
- Bootstrap execution
- Event bundle posting
- Artifact upload
- PR creation
- Invariants checking

### What Is Still Rough or Manual

**Rough edges**:
- Scheduler is not automated (manual job creation)
- No webhook integration (polling required for PR merge detection)
- Backlog synthesis API is placeholder (full integration pending)
- No metrics/monitoring (Prometheus, Grafana)
- No alerting on failures
- Manual secret rotation

**Manual processes**:
- Target registration (kubectl create configmap)
- Bootstrap triggering (kubectl create job)
- Task execution (manual job creation)
- Backlog updates (manual PR to target repo)
- Failure investigation (manual log inspection)

### Known Gaps

**Missing features**:
- Automated scheduler (cron-based or event-driven)
- Webhook handlers for GitHub events
- Multi-target concurrency
- Resource quotas and limits
- Backup and restore for event store
- Disaster recovery procedures
- Performance benchmarks
- Load testing

**Documentation gaps**:
- Runbook for production incidents
- Disaster recovery playbook
- Performance tuning guide
- Security hardening checklist

**Testing gaps**:
- Integration tests for full execution lifecycle
- End-to-end tests with real GitHub API
- Performance tests for large repositories
- Chaos engineering tests

---

## 10. Roadmap

### Short-Term (Next 3 Months)

**Stability and Deployment Polish**:

1. **Automated scheduler**:
   - CronJob for periodic task selection
   - Event-driven scheduling via webhooks
   - Concurrency limits and backpressure

2. **Webhook integration**:
   - GitHub webhook receiver
   - PR merge detection
   - Automatic backlog updates

3. **Monitoring and alerting**:
   - Prometheus metrics (attempts, failures, latency)
   - Grafana dashboards
   - Alertmanager rules for critical failures

4. **Operational runbooks**:
   - Incident response procedures
   - Disaster recovery playbook
   - Backup and restore procedures

5. **Security hardening**:
   - Secret rotation automation
   - RBAC for control plane API
   - Network policies for pod isolation
   - Audit logging

### Medium-Term (3-12 Months)

**Radix Integration and GPU Orchestration Hooks**:

1. **Radix as primary target**:
   - Complete backlog synthesis integration
   - Execute first 10 tasks on Radix
   - Iterate on task quality and acceptance criteria
   - Build feedback loop for task refinement

2. **GPU orchestration hooks**:
   - Detect GPU-dependent tasks (e.g., model training)
   - Schedule tasks on GPU-enabled nodes
   - Resource quotas for GPU jobs
   - Cost tracking and optimization

3. **Multi-target support**:
   - Operate multiple repositories concurrently
   - Shared control plane, isolated workers
   - Per-target resource limits
   - Cross-target dependency tracking

4. **Advanced task types**:
   - Long-running tasks (model training, data processing)
   - Scheduled tasks (periodic maintenance)
   - Conditional tasks (trigger on events)

5. **Improved observability**:
   - Distributed tracing (OpenTelemetry)
   - Structured logging (JSON)
   - Log aggregation (Loki, Elasticsearch)
   - Real-time dashboards

### Long-Term (12+ Months)

**Datacenter-Scale Control Plane, Self-Hosted Models, Advanced Scheduling**:

1. **Datacenter-scale control plane**:
   - Multi-region deployment
   - High availability (HA control plane)
   - Horizontal scaling (sharded event store)
   - Global graph replication
   - Edge caching for artifacts

2. **Self-hosted models**:
   - Run LLMs on VaultScaler infrastructure
   - Reduce dependency on external APIs
   - Cost optimization
   - Data privacy and compliance
   - Fine-tuned models for specific tasks

3. **Advanced scheduling**:
   - Priority queues with preemption
   - Resource-aware scheduling (CPU, memory, GPU)
   - Deadline-based scheduling (SLO enforcement)
   - Dependency-aware scheduling (DAG execution)
   - Speculative execution (parallel attempts)

4. **VaultScaler integration**:
   - Leviathan as control plane for VaultScaler
   - Orchestrate datacenter operations
   - Manage GPU clusters
   - Automate infrastructure provisioning
   - Self-healing infrastructure

5. **Product evolution**:
   - Leviathan as SaaS offering
   - Multi-tenant control plane
   - Marketplace for task templates
   - Community-contributed policies
   - Enterprise features (SSO, audit logs, compliance)

---

## 11. Relationship to VaultScaler Vision

### How Leviathan Enables Product Creation

**VaultScaler** is a vision for datacenter-scale GPU orchestration and AI infrastructure. Building such a system requires:

- Reliable infrastructure automation
- Continuous evolution of complex codebases
- SRE-level operational discipline
- Institutional knowledge preservation

**Leviathan provides**:
- Platform for operating infrastructure codebases
- Deterministic knowledge graph of systems
- Automated task execution with human oversight
- Anti-forgetting mechanisms to prevent drift

**Leviathan enables VaultScaler by**:
- Operating VaultScaler infrastructure repos
- Automating routine maintenance tasks
- Tracking infrastructure changes in graph
- Providing audit trail for compliance
- Scaling operational capacity without scaling headcount

### How Radix Fits In

**Radix** is a research platform for evidence-based decision making. It is:
- A product in its own right
- A testbed for Leviathan capabilities
- A source of requirements for platform features

**Radix benefits from Leviathan**:
- Automated maintenance (dependency updates, refactoring)
- Consistent code quality (linting, testing)
- Documentation generation
- API evolution
- Schema management

**Leviathan benefits from Radix**:
- Real-world complexity (1481 files, 29 API routes)
- Feedback on task quality
- Use cases for backlog synthesis
- Requirements for GPU orchestration (future)

### How GPU Orchestration May Integrate

**Future integration**:

1. **Task-level GPU requests**:
   ```yaml
   - task_id: train-model-v1
     resources:
       gpu: 1
       gpu_type: A100
       memory: 32Gi
   ```

2. **Leviathan schedules on GPU nodes**:
   - Detects GPU requirement
   - Schedules on VaultScaler GPU cluster
   - Monitors resource usage
   - Tracks costs

3. **VaultScaler provides GPU capacity**:
   - Datacenter-scale GPU pools
   - Dynamic allocation
   - Cost optimization
   - Multi-tenancy

4. **Leviathan operates VaultScaler**:
   - Automates infrastructure tasks
   - Monitors cluster health
   - Applies configuration changes
   - Tracks operational history

### Why Leviathan Is a Foundational Platform, Not a Feature

**Leviathan is not**:
- A feature of Radix
- A feature of VaultScaler
- A one-off automation script

**Leviathan is**:
- A general-purpose platform for repository operation
- A foundation for building and maintaining complex systems
- A long-term investment in operational scalability
- A prerequisite for datacenter-scale ambitions

**Separation of concerns**:
- **Radix**: Product for research workflows
- **VaultScaler**: Infrastructure for GPU orchestration
- **Leviathan**: Platform for operating both

This separation allows:
- Radix to focus on domain problems
- VaultScaler to focus on infrastructure
- Leviathan to focus on operational automation
- Each to evolve independently
- Clear boundaries and interfaces

---

## 12. Conclusion

### Why This Architecture Matters

Leviathan represents a **conservative, deliberate approach** to AI-assisted engineering:

1. **Determinism over magic**: Bootstrap is LLM-free, ensuring reproducibility
2. **Auditability over autonomy**: Append-only events provide full history
3. **Human authority over automation**: All changes require PR approval
4. **Explicit over implicit**: Contracts, backlogs, and policies are declared
5. **Safety by construction**: Multiple layers of validation and enforcement

This architecture matters because:

- **It scales intellectually**: New engineers can understand the system by reading contracts and events
- **It scales operationally**: Control plane and workers are independently scalable
- **It prevents drift**: Invariants and policies are enforced automatically
- **It enables trust**: Humans retain final authority over all changes
- **It provides foundation**: Graph and events enable future capabilities

### Why It Is Intentionally Conservative

Leviathan could be more autonomous. It could:
- Generate tasks automatically
- Merge PRs without human review
- Make architectural decisions
- Plan roadmaps

**We deliberately choose not to**:

1. **Autonomy is dangerous**: Without human oversight, AI can cause harm
2. **Explainability is critical**: Humans must understand what happened and why
3. **Trust is earned**: Conservative design builds confidence over time
4. **Complexity is managed**: Simple, explicit systems are easier to debug
5. **Longevity matters**: Systems that last are boring, not clever

### Why It Scales Intellectually and Operationally

**Intellectual scalability**:
- New engineers read contracts to understand targets
- Events provide history of what happened
- Invariants document canonical configuration
- Policies explain boundaries
- Graph shows relationships

**Operational scalability**:
- Control plane is stateless (can scale horizontally)
- Workers are ephemeral (can run thousands concurrently)
- Event store is append-only (no write conflicts)
- Artifacts are immutable (can cache aggressively)
- Graph is event-sourced (can rebuild from events)

**Future scalability**:
- Multi-region deployment (replicate events)
- Multi-tenant control plane (namespace isolation)
- Self-hosted models (reduce API costs)
- Advanced scheduling (resource-aware, deadline-based)
- Datacenter-scale operations (VaultScaler integration)

---

## Appendix: Key Files and Directories

```
/home/ian/leviathan/
├── leviathan/
│   ├── control_plane/
│   │   ├── api.py              # FastAPI control plane
│   │   └── config.py           # Configuration management
│   ├── executor/
│   │   └── worker.py           # Worker execution loop
│   ├── bootstrap/
│   │   └── indexer.py          # Deterministic repo indexing
│   ├── synthesis/
│   │   └── backlog_synth.py    # Task proposal generation
│   ├── graph/
│   │   ├── events.py           # Event store
│   │   └── store.py            # Graph store
│   ├── artifacts/
│   │   └── store.py            # Artifact storage
│   ├── cli/
│   │   └── leviathanctl.py     # Operator CLI
│   ├── model_client.py         # Claude API client
│   ├── github.py               # GitHub API client
│   └── git_client.py           # Git operations
├── ops/
│   ├── invariants.yaml         # Canonical configuration truths
│   ├── k8s/
│   │   ├── control-plane.yaml  # K8s deployment
│   │   └── job-template.yaml   # Worker job template
│   └── docker/
│       ├── control-plane.Dockerfile
│       └── worker.Dockerfile
├── tools/
│   └── invariants_check.py     # Invariants validation
├── docs/
│   ├── ARCHITECTURE.md
│   ├── HOW_LEVIATHAN_OPERATES.md
│   ├── INVARIANTS.md
│   ├── LEVIATHANCTL.md
│   └── LEVIATHAN_CANONICAL.md  # This document
└── tests/
    └── unit/                   # 277 unit tests
```

---

**Document Maintenance**:
- This document should be updated as the system evolves
- Major architectural changes require document updates
- New features should be reflected in roadmap
- Known gaps should be tracked and addressed

**Version History**:
- v1.0 (2026-01-25): Initial canonical document

**Authors**:
- Principal Systems Architect: Claude (Windsurf)
- Technical Owner: Ian Green

**Review Cycle**: Quarterly or after major milestones
