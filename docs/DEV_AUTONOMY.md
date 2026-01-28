# Leviathan Autonomy v1 - DEV Environment

## Overview

Autonomy v1 enables Leviathan to run as a closed-loop operator in DEV environments. The scheduler continuously selects and executes ready tasks from target backlogs with strict guardrails.

**Key Features:**
- Continuous operation via Kubernetes CronJob (every 5 minutes)
- Only executes tasks with `ready: true` (no autonomous planning)
- Strict scope restrictions: `.leviathan/**` and `docs/**` only
- Concurrency limits: max 1 open PR at a time
- Circuit breaker: stops after consecutive failures
- PR-based delivery (no auto-merge)

## Guardrails

### 1. No Autonomous Planning
Leviathan does NOT invent tasks. It only executes tasks already present in target backlog with `ready: true`.

### 2. Scope Restrictions
Tasks must have `allowed_paths` within:
- `.leviathan/**`
- `docs/**`

Tasks outside this scope are skipped.

### 3. Concurrency Limits
- `max_open_prs: 1` - Only 1 open PR at a time
- `max_running_attempts: 1` - Only 1 worker job running
- `max_attempts_per_task: 2` - Retry limit per task

### 4. Circuit Breaker
After 2 consecutive failures on the same task, scheduler stops scheduling further tasks for that target.

### 5. PR-Based Delivery
All changes delivered via GitHub PR. No direct commits to main. No auto-merge.

## Prerequisites

- kind cluster
- Docker
- kubectl
- GitHub token with `repo` scope

## Bootstrap Commands

### 1. Create kind Cluster

```bash
kind create cluster --name leviathan
```

### 2. Build and Load Images

```bash
# Build images
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .

# Load into kind
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
```

### 3. Create Namespace

```bash
kubectl create namespace leviathan
```

### 4. Create Secrets

```bash
# Control plane token
kubectl -n leviathan create secret generic leviathan-control-plane-secret \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token

# GitHub token
kubectl -n leviathan create secret generic leviathan-secrets \
  --from-literal=github-token=<your-github-token>
```

### 5. Create Autonomy ConfigMap

```bash
kubectl -n leviathan create configmap leviathan-autonomy-config \
  --from-file=dev.yaml=ops/autonomy/dev.yaml
```

### 6. Deploy Control Plane

```bash
kubectl apply -f ops/k8s/control-plane.yaml

# Wait for ready
kubectl -n leviathan wait --for=condition=ready pod -l app=leviathan-control-plane --timeout=60s
```

### 7. Deploy Scheduler

```bash
kubectl apply -f ops/k8s/scheduler/dev-autonomy.yaml
```

## Observing Autonomy

### Check Scheduler Status

```bash
# View CronJob
kubectl -n leviathan get cronjobs

# View recent scheduler jobs
kubectl -n leviathan get jobs -l app=leviathan-scheduler

# View scheduler logs
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=100
```

### Check Worker Jobs

```bash
# View worker jobs
kubectl -n leviathan get jobs -l app=leviathan-worker

# View worker pods
kubectl -n leviathan get pods -l app=leviathan-worker

# View worker logs
kubectl -n leviathan logs -l app=leviathan-worker --tail=100
```

### Check for PR Creation

```bash
# Grep for PR creation in worker logs
kubectl -n leviathan logs -l app=leviathan-worker | grep "PR created:"

# List PRs on Radix repo
gh pr list --repo iangreen74/radix --state open
```

### Query Control Plane

```bash
# Port-forward to control plane
kubectl -n leviathan port-forward svc/leviathan-control-plane 8000:8000

# Query events (in another terminal)
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/graph/summary | jq
```

## Expected Behavior

### Scheduler Cycle (Every 5 Minutes)

1. **Check Open PRs**: Count open PRs with branch prefix `agent/`
2. **Skip if Max Reached**: If >= 1 open PR, skip this cycle
3. **Fetch Backlog**: Clone Radix repo and read `.leviathan/backlog.yaml`
4. **Select Task**: Find first task with:
   - `ready: true`
   - `status: pending` (or missing)
   - No dependencies (conservative for v1)
   - `allowed_paths` within `.leviathan/**` or `docs/**`
5. **Check Retry Limit**: Skip if task has >= 2 attempts
6. **Submit Worker Job**: Create K8s Job to execute task
7. **Worker Creates PR**: Worker clones repo, modifies backlog, creates PR

### Worker Execution

1. **Post Events**: `attempt.created`, `attempt.started`
2. **Clone Repo**: Fetch target repo and task spec
3. **Create PR**: Use BacklogProposer to modify backlog and create PR
4. **Post Events**: `pr.created`, `attempt.succeeded`

### Example Scheduler Output

```
============================================================
DEV Autonomy Scheduler - 2026-01-28T12:00:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

Open PRs: 0/1
Backlog tasks: 5

→ Selected task: update-readme-links
  Title: Fix broken links in README
  Scope: docs
  Attempt ID: attempt-update-readme-links-abc123
  Attempt number: 1/2

✓ Worker job submitted: attempt-update-readme-links-abc123
```

### Example Worker Output

```
============================================================
Backlog Propose Worker
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git
Task: update-readme-links
Attempt: attempt-update-readme-links-abc123

✓ Posted attempt.created event to control plane
✓ Posted attempt.started event to control plane
Cloning https://github.com/iangreen74/radix.git...
✓ Cloned to /workspace/attempt-update-readme-links-abc123/target
✓ Loaded task spec: Fix broken links in README
✓ Added task update-readme-links to backlog
Pushing branch agent/backlog-propose-attempt-update-readme-links-abc123...
✓ Branch pushed
✓ Commit SHA: def456...

Creating pull request...
✓ PR created: https://github.com/iangreen74/radix/pull/42
✓ PR number: 42
✓ Posted pr.created event to control plane
✓ Posted attempt.succeeded event to control plane

============================================================
✅ Worker Complete
============================================================
PR URL: https://github.com/iangreen74/radix/pull/42
PR Number: 42
Branch: agent/backlog-propose-attempt-update-readme-links-abc123
Commit SHA: def456...
```

## Stopping Autonomy

### Pause Scheduler

```bash
# Suspend CronJob (stops new runs)
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":true}}'
```

### Resume Scheduler

```bash
# Resume CronJob
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":false}}'
```

### Delete Scheduler

```bash
kubectl delete -f ops/k8s/scheduler/dev-autonomy.yaml
```

### Cleanup All

```bash
# Delete scheduler
kubectl delete -f ops/k8s/scheduler/dev-autonomy.yaml

# Delete control plane
kubectl delete -f ops/k8s/control-plane.yaml

# Delete namespace (removes all resources)
kubectl delete namespace leviathan

# Delete kind cluster
kind delete cluster --name leviathan
```

## Configuration

Configuration file: `ops/autonomy/dev.yaml`

```yaml
target_id: radix
target_repo_url: https://github.com/iangreen74/radix.git
target_branch: main

allowed_path_prefixes:
  - .leviathan/
  - docs/

max_open_prs: 1
max_running_attempts: 1
max_attempts_per_task: 2
circuit_breaker_failures: 2

schedule_cron: "*/5 * * * *"
attempt_timeout_seconds: 900

control_plane_url: http://leviathan-control-plane:8000
worker_image: leviathan-worker:local
worker_namespace: leviathan
workspace_dir: /workspace
```

## Troubleshooting

### Scheduler Not Running

```bash
# Check CronJob status
kubectl -n leviathan describe cronjob leviathan-dev-scheduler

# Check if suspended
kubectl -n leviathan get cronjob leviathan-dev-scheduler -o yaml | grep suspend
```

### No Tasks Selected

Check scheduler logs:
```bash
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=50
```

Common reasons:
- No tasks with `ready: true`
- Max open PRs reached (1)
- Task scope outside allowed prefixes
- Task has dependencies (skipped in v1)

### Worker Job Fails

```bash
# View failed jobs
kubectl -n leviathan get jobs -l app=leviathan-worker

# View pod logs
kubectl -n leviathan logs -l app=leviathan-worker --tail=100

# Describe pod for events
kubectl -n leviathan describe pod -l app=leviathan-worker
```

Common issues:
- Git clone authentication failure (check GITHUB_TOKEN secret)
- Control plane unreachable (check service and deployment)
- Task not found in backlog

### Control Plane Unreachable

```bash
# Check control plane status
kubectl -n leviathan get pods -l app=leviathan-control-plane

# View logs
kubectl -n leviathan logs -l app=leviathan-control-plane --tail=50

# Check service
kubectl -n leviathan get svc leviathan-control-plane
```

## Safety Guarantees

### Scope Isolation
Tasks modifying files outside `.leviathan/**` or `docs/**` are automatically skipped.

### Concurrency Control
Only 1 open PR at a time prevents overwhelming reviewers.

### Retry Limits
Max 2 attempts per task prevents infinite retry loops.

### Circuit Breaker
After 2 consecutive failures, scheduler stops to prevent cascading failures.

### No Auto-Merge
All changes delivered via PR. Human review required before merge.

### Deterministic Evidence
Full event history persisted in control plane:
- `attempt.created`
- `attempt.started`
- `pr.created`
- `attempt.succeeded` / `attempt.failed`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
│                                                          │
│  ┌────────────────┐         ┌──────────────────┐       │
│  │   CronJob      │         │  Control Plane   │       │
│  │   (Scheduler)  │────────▶│  (Deployment)    │       │
│  │   Every 5min   │  events │  Port 8000       │       │
│  └────────┬───────┘         └──────────────────┘       │
│           │                                              │
│           │ creates                                      │
│           ▼                                              │
│  ┌────────────────┐                                     │
│  │   Worker Job   │                                     │
│  │   (Pod)        │─────────────────────────┐          │
│  └────────────────┘                         │          │
│                                              │          │
└──────────────────────────────────────────────┼──────────┘
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │  GitHub API      │
                                    │  - Clone repo    │
                                    │  - Create PR     │
                                    └──────────────────┘
```

## Related Documentation

- [K8s PR Proof v1](K8S_PR_PROOF_V1.md) - Worker execution details
- [Control Plane Deployment](DEPLOY_CONTROL_PLANE.md) - Control plane setup
- [Backlog Format](../ops/autonomy/dev.yaml) - Autonomy configuration
