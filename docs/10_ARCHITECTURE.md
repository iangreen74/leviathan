# Architecture

**Last Updated:** 2026-01-28  
**Status:** Canonical

---

## System Overview

Leviathan is a closed-loop autonomous software engineering system that executes tasks from target repository backlogs and creates pull requests automatically.

**Design Philosophy:**
- **No autonomous planning:** Only executes pre-defined tasks
- **PR-based delivery:** All changes via pull requests
- **Deterministic operation:** Full event audit trail
- **Invariant enforcement:** Runtime checks at commit time
- **Strict guardrails:** Scope, concurrency, and retry limits

---

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                          │
│                                                                  │
│  ┌──────────────────┐                                           │
│  │   CronJob        │  Runs every 5 minutes                     │
│  │   (Scheduler)    │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           │ 1. Check open PRs                                   │
│           │ 2. Fetch target backlog                             │
│           │ 3. Select next ready task                           │
│           │ 4. Submit worker job                                │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐         ┌────────────────────┐           │
│  │   Worker Job     │ events  │  Control Plane     │           │
│  │   (Pod)          │────────▶│  (Deployment)      │           │
│  │                  │         │  - Event ingestion │           │
│  │  1. Clone repo   │         │  - Event store     │           │
│  │  2. Modify files │         │  - Query API       │           │
│  │  3. Create PR    │         └────────────────────┘           │
│  │  4. Post events  │                                           │
│  └────────┬─────────┘                                           │
│           │                                                      │
└───────────┼──────────────────────────────────────────────────────┘
            │
            │ HTTPS + token auth
            ▼
 ┌──────────────────────┐
 │   GitHub API         │
 │   - Clone repo       │
 │   - Push branch      │
 │   - Create PR        │
 │   - Check open PRs   │
 └──────────────────────┘
```

---

## Components

### 1. Scheduler

**Module:** `leviathan.scheduler.dev_autonomy`  
**Deployment:** Kubernetes CronJob  
**Schedule:** Every 5 minutes  
**Namespace:** `leviathan`

**Responsibilities:**
1. Check open PR count via GitHub API
2. Skip if max open PRs reached (configurable, default 1)
3. Clone target repo and read `.leviathan/backlog.yaml`
4. Select next executable task:
   - `ready: true`
   - `status: pending` or missing
   - No dependencies (conservative for v1)
   - `allowed_paths` within allowed scope
5. Check retry limit (max attempts per task)
6. Submit Kubernetes Job for worker execution

**Guardrails Enforced:**
- Scope restrictions (`.leviathan/**`, `docs/**` in DEV)
- Max open PRs (prevents overwhelming reviewers)
- Retry limits (prevents infinite loops)
- Circuit breaker (stops after consecutive failures)

**Configuration:** `ops/autonomy/dev.yaml`

**RBAC:** ServiceAccount with permissions to create Jobs

---

### 2. Worker

**Module:** `leviathan.executor.backlog_propose_worker`  
**Deployment:** Kubernetes Job (one per task attempt)  
**Namespace:** `leviathan`

**Responsibilities:**
1. Post `attempt.created` event to control plane
2. Post `attempt.started` event
3. Clone target repository (HTTPS with token)
4. Fetch task spec from backlog
5. Execute task (currently: add task to backlog)
6. Commit changes with `git add -f` (handles ignored directories)
7. Push branch to GitHub
8. Create pull request via GitHub API
9. Post `pr.created` event
10. Post `attempt.succeeded` or `attempt.failed` event

**Environment Variables:**
- `GITHUB_TOKEN`: GitHub personal access token
- `TARGET_NAME`: Target identifier
- `TARGET_REPO_URL`: Repository URL (HTTPS)
- `TARGET_BRANCH`: Base branch
- `TASK_ID`: Task to execute
- `ATTEMPT_ID`: Unique attempt identifier
- `CONTROL_PLANE_URL`: Control plane endpoint
- `CONTROL_PLANE_TOKEN`: Control plane auth token
- `LEVIATHAN_WORKSPACE_DIR`: Workspace directory

**Image:** `leviathan-worker:local` (includes scheduler and worker)

**Lifecycle:**
```
Created → Started → [Execute Task] → PR Created → Succeeded
                                   ↓
                                 Failed
```

---

### 3. Control Plane

**Module:** `leviathan.control_plane`  
**Deployment:** Kubernetes Deployment  
**Port:** 8000  
**Namespace:** `leviathan`

**Responsibilities:**
1. Ingest event bundles from workers
2. Persist events to NDJSON backend
3. Provide query API for graph state
4. Validate event schema

**API Endpoints:**
- `POST /v1/events/ingest` - Ingest event bundle
- `GET /v1/graph/summary` - Query graph summary
- `GET /health` - Health check

**Event Store:**
- Backend: NDJSON files
- Location: `/data/events/` (persistent volume in production)
- Format: One JSON object per line

**Authentication:** Bearer token (from secret)

---

## Data Flow

### Scheduler Cycle (Every 5 Minutes)

```
1. Scheduler Pod starts
   ↓
2. Check open PRs via GitHub API
   ↓
3. If >= max_open_prs → Skip cycle
   ↓
4. Clone target repo (temp directory)
   ↓
5. Read .leviathan/backlog.yaml
   ↓
6. Select first task matching:
   - ready: true
   - status: pending
   - no dependencies
   - allowed_paths in scope
   ↓
7. Check attempt count < max_attempts
   ↓
8. Generate attempt_id (UUID)
   ↓
9. Create Kubernetes Job manifest
   ↓
10. Submit Job via kubectl apply
    ↓
11. Scheduler Pod exits
```

### Worker Execution

```
1. Worker Pod starts
   ↓
2. Load environment variables
   ↓
3. POST attempt.created event
   ↓
4. POST attempt.started event
   ↓
5. Clone target repo to workspace
   ↓
6. Read task spec from backlog
   ↓
7. Execute task (modify files)
   ↓
8. git add -f .leviathan/backlog.yaml
   ↓
9. git commit -m "..."
   ↓
10. git push origin agent/backlog-propose-{attempt_id}
    ↓
11. Create PR via GitHub API
    ↓
12. POST pr.created event
    ↓
13. POST attempt.succeeded event
    ↓
14. Worker Pod exits (success)

    [On error: POST attempt.failed event → exit 1]
```

---

## Event Model

### Event Schema

Every event includes:
- `event_id`: UUID (unique identifier)
- `event_type`: String (e.g., `attempt.created`)
- `timestamp`: ISO8601 UTC timestamp
- `actor_id`: String (e.g., `worker-{attempt_id}`)
- `payload`: Dict (event-specific data)

### Event Types

**Attempt Lifecycle:**
- `attempt.created` - Attempt initialized
- `attempt.started` - Attempt execution began
- `attempt.succeeded` - Attempt completed successfully
- `attempt.failed` - Attempt failed with error

**PR Lifecycle:**
- `pr.created` - Pull request created
- `pr.merged` - Pull request merged (future)
- `pr.closed` - Pull request closed (future)

### Event Bundle

Events are sent in bundles:
```json
{
  "target": "radix",
  "bundle_id": "bundle-attempt-123",
  "events": [
    {
      "event_id": "uuid-1",
      "event_type": "attempt.created",
      "timestamp": "2026-01-28T12:00:00.000000",
      "actor_id": "worker-attempt-123",
      "payload": {
        "attempt_id": "attempt-123",
        "task_id": "task-456",
        "target_id": "radix",
        "attempt_number": 1
      }
    }
  ],
  "artifacts": []
}
```

---

## Backlog Format

Target repositories must have `.leviathan/backlog.yaml`:

```yaml
tasks:
  - id: task-1
    title: "Fix broken links in README"
    description: "Update all broken documentation links"
    scope: docs
    ready: true
    status: pending
    allowed_paths:
      - docs/README.md
      - docs/architecture/design.md
    acceptance_criteria:
      - All links return 200 status
      - No broken anchors
    dependencies: []
```

**Required Fields:**
- `id`: Unique task identifier
- `title`: Human-readable title
- `ready`: Boolean (must be `true` for execution)
- `allowed_paths`: List of files task may modify

**Optional Fields:**
- `status`: `pending`, `in_progress`, `completed`, `blocked`
- `description`: Detailed description
- `scope`: Scope label
- `acceptance_criteria`: List of criteria
- `dependencies`: List of task IDs

---

## Autonomy Configuration

**File:** `ops/autonomy/dev.yaml`

```yaml
target_id: radix
target_repo_url: https://github.com/iangreen74/radix.git
target_branch: main

# Scope restrictions
allowed_path_prefixes:
  - .leviathan/
  - docs/

# Concurrency limits
max_open_prs: 1
max_running_attempts: 1

# Retry policy
max_attempts_per_task: 2

# Circuit breaker
circuit_breaker_failures: 2

# Scheduler
schedule_cron: "*/5 * * * *"
attempt_timeout_seconds: 900

# Control plane
control_plane_url: http://leviathan-control-plane:8000

# Worker
worker_image: leviathan-worker:local
worker_namespace: leviathan
workspace_dir: /workspace
```

---

## Security Model

### Authentication

**GitHub API:**
- Token-based authentication
- Token stored in Kubernetes Secret
- Injected as environment variable
- Scope: `repo` (read/write access)

**Control Plane:**
- Bearer token authentication
- Token stored in Kubernetes Secret
- Injected as environment variable
- Validated on every request

**Git Operations:**
- HTTPS with token: `https://x-access-token:{token}@github.com/...`
- No SSH keys required (suitable for pods)

### Authorization

**Kubernetes RBAC:**
- Scheduler ServiceAccount can create Jobs
- Worker pods run with default ServiceAccount
- Control plane runs with default ServiceAccount

**GitHub:**
- Token must have `repo` scope
- PRs created by token owner
- Branch prefix: `agent/` (identifies Leviathan PRs)

---

## Guardrails

### Scope Restrictions

Tasks must have `allowed_paths` within configured prefixes:
- DEV: `.leviathan/**`, `docs/**`
- Production: Configurable per target

Tasks outside scope are skipped with log message.

### Concurrency Limits

**Max Open PRs:**
- Scheduler counts open PRs with branch prefix `agent/`
- Skips cycle if limit reached
- Prevents overwhelming reviewers

**Max Running Attempts:**
- Only 1 worker job runs at a time (future enhancement)
- Prevents resource exhaustion

### Retry Policy

**Max Attempts Per Task:**
- Default: 2 attempts
- After max attempts, task marked blocked
- Prevents infinite retry loops

**Retry Logic:**
- Scheduler tracks attempt count (future: query control plane)
- Increments on each submission
- Stops at max_attempts_per_task

### Circuit Breaker

**Consecutive Failures:**
- Default: 2 failures
- After threshold, scheduler stops scheduling for target
- Prevents cascading failures
- Requires manual intervention to reset

---

## Failure Modes

### Scheduler Failures

**Symptom:** No jobs created  
**Causes:**
- CronJob suspended
- Max open PRs reached
- No ready tasks
- Circuit breaker tripped

**Recovery:**
- Check CronJob status
- Review scheduler logs
- Verify backlog has ready tasks
- Reset circuit breaker if needed

### Worker Failures

**Symptom:** Job fails, no PR created  
**Causes:**
- Git clone authentication failure
- Control plane unreachable
- GitHub API rate limit
- Task execution error

**Recovery:**
- Check worker logs
- Verify secrets are correct
- Check GitHub API rate limits
- Review task spec

### Control Plane Failures

**Symptom:** Events not persisted  
**Causes:**
- Pod not running
- Disk full (event store)
- Authentication failure

**Recovery:**
- Check pod status
- Check disk usage
- Verify secrets
- Review control plane logs

---

## Scaling Considerations

### Current Limits (DEV)

- 1 scheduler instance (CronJob)
- 1 worker job at a time (max_running_attempts)
- 1 control plane replica
- 1 target (Radix)

### Future Scaling

**Multiple Targets:**
- One scheduler per target
- Separate autonomy configs
- Shared control plane

**Parallel Workers:**
- Increase max_running_attempts
- Add resource limits
- Implement job queue

**Control Plane:**
- Horizontal scaling (multiple replicas)
- Shared event store (persistent volume)
- Database backend (PostgreSQL)

---

## Observability

### Logs

**Scheduler:**
```bash
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=100
```

**Worker:**
```bash
kubectl -n leviathan logs -l app=leviathan-worker --tail=100
```

**Control Plane:**
```bash
kubectl -n leviathan logs -l app=leviathan-control-plane --tail=100
```

### Metrics (Future)

- Tasks selected per cycle
- Worker success/failure rate
- PR creation rate
- Event ingestion rate
- API latency

### Tracing (Future)

- Distributed tracing with OpenTelemetry
- Trace ID propagation through events
- End-to-end attempt tracing

---

## Next Steps

- **Operations:** [21_AUTONOMY_OPERATIONS.md](21_AUTONOMY_OPERATIONS.md)
- **Monitoring:** [22_MONITORING.md](22_MONITORING.md)
- **Configuration:** [41_CONFIGURATION.md](41_CONFIGURATION.md)
- **API Reference:** [40_API_REFERENCE.md](40_API_REFERENCE.md)
