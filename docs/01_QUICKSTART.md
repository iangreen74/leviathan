# Quickstart: Run Autonomy v1 on kind

**Estimated Time:** 5 minutes  
**Prerequisites:** Docker, kubectl, kind, gh CLI

---

## What You'll Build

A fully autonomous Leviathan system running on a local Kubernetes cluster (kind) that:
- Continuously monitors the Radix repository backlog
- Selects ready tasks every 5 minutes
- Creates pull requests automatically
- Enforces strict safety guardrails

---

## Step 1: Create kind Cluster

```bash
kind create cluster --name leviathan
```

**Expected output:**
```
Creating cluster "leviathan" ...
✓ Ensuring node image (kindest/node:v1.27.3)
✓ Preparing nodes
✓ Writing configuration
✓ Starting control-plane
✓ Installing CNI
✓ Installing StorageClass
Set kubectl context to "kind-leviathan"
```

---

## Step 2: Build and Load Images

```bash
# Build control plane image
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .

# Build worker image (includes scheduler)
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .

# Load into kind
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
```

**Time:** ~2-3 minutes

---

## Step 3: Create Namespace and Secrets

```bash
# Create namespace
kubectl create namespace leviathan

# Create control plane secret
kubectl -n leviathan create secret generic leviathan-control-plane-secret \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token

# Create GitHub token secret (replace with your token)
kubectl -n leviathan create secret generic leviathan-secrets \
  --from-literal=github-token=ghp_your_token_here
```

**Note:** Get a GitHub token at https://github.com/settings/tokens with `repo` scope.

---

## Step 4: Create Autonomy ConfigMap

```bash
kubectl -n leviathan create configmap leviathan-autonomy-config \
  --from-file=dev.yaml=ops/autonomy/dev.yaml
```

---

## Step 5: Deploy Control Plane

```bash
kubectl apply -f ops/k8s/control-plane.yaml

# Wait for ready
kubectl -n leviathan wait --for=condition=ready pod -l app=leviathan-control-plane --timeout=60s
```

**Expected output:**
```
deployment.apps/leviathan-control-plane created
service/leviathan-control-plane created
pod/leviathan-control-plane-xxx condition met
```

---

## Step 6: Deploy Scheduler

```bash
kubectl apply -f ops/k8s/scheduler/dev-autonomy.yaml
```

**Expected output:**
```
cronjob.batch/leviathan-dev-scheduler created
serviceaccount/leviathan-scheduler created
role.rbac.authorization.k8s.io/leviathan-scheduler created
rolebinding.rbac.authorization.k8s.io/leviathan-scheduler created
```

---

## Step 7: Verify Deployment

```bash
# Check all resources
kubectl -n leviathan get all

# Expected output:
# NAME                                          READY   STATUS    RESTARTS   AGE
# pod/leviathan-control-plane-xxx               1/1     Running   0          1m
#
# NAME                              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
# service/leviathan-control-plane   ClusterIP   10.96.xxx.xxx   <none>        8000/TCP   1m
#
# NAME                                      READY   UP-TO-DATE   AVAILABLE   AGE
# deployment.apps/leviathan-control-plane   1/1     1            1           1m
#
# NAME                                      SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
# cronjob.batch/leviathan-dev-scheduler     */5 * * * *   False     0        <none>          30s
```

---

## Step 8: Observe Autonomy in Action

### Watch Scheduler Logs

```bash
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=100 -f
```

**Expected output (every 5 minutes):**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T13:00:00.000000
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

### Watch Worker Logs

```bash
kubectl -n leviathan logs -l app=leviathan-worker --tail=100 -f
```

**Expected output:**
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

### Check Created PRs

```bash
gh pr list --repo iangreen74/radix --state open
```

**Expected output:**
```
#42  Fix broken links in README  agent/backlog-propose-attempt-update-readme-links-abc123
```

---

## Step 9: Query Control Plane

```bash
# Port-forward to control plane
kubectl -n leviathan port-forward svc/leviathan-control-plane 8000:8000 &

# Query graph summary
curl -H "Authorization: Bearer dev-token" http://localhost:8000/v1/graph/summary | jq

# Expected output:
# {
#   "targets": ["radix"],
#   "total_events": 4,
#   "recent_events": [
#     {"event_type": "attempt.created", "timestamp": "..."},
#     {"event_type": "attempt.started", "timestamp": "..."},
#     {"event_type": "pr.created", "timestamp": "..."},
#     {"event_type": "attempt.succeeded", "timestamp": "..."}
#   ]
# }
```

---

## Pause/Resume Autonomy

### Pause (Stop Scheduling)

```bash
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":true}}'
```

### Resume

```bash
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":false}}'
```

---

## Cleanup

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

---

## Troubleshooting

### Scheduler Not Running

```bash
# Check CronJob status
kubectl -n leviathan describe cronjob leviathan-dev-scheduler

# Check if suspended
kubectl -n leviathan get cronjob leviathan-dev-scheduler -o yaml | grep suspend
```

### Worker Job Fails

```bash
# View failed jobs
kubectl -n leviathan get jobs -l app=leviathan-worker

# View pod logs
kubectl -n leviathan logs -l app=leviathan-worker --tail=100

# Describe pod for events
kubectl -n leviathan describe pod -l app=leviathan-worker
```

### No Tasks Selected

Check scheduler logs for reasons:
- No tasks with `ready: true`
- Max open PRs reached (1)
- Task scope outside allowed prefixes (`.leviathan/**`, `docs/**`)
- Task has dependencies (skipped in v1)

---

## Next Steps

- **Understand the system:** [10_ARCHITECTURE.md](10_ARCHITECTURE.md)
- **Deploy to production:** [20_KUBERNETES_DEPLOYMENT.md](20_KUBERNETES_DEPLOYMENT.md)
- **Configure autonomy:** [41_CONFIGURATION.md](41_CONFIGURATION.md)
- **Monitor operations:** [22_MONITORING.md](22_MONITORING.md)

---

## What Just Happened?

1. **Scheduler runs every 5 minutes** (CronJob)
2. **Checks open PRs** on Radix repo (max 1 allowed)
3. **Fetches backlog** from `.leviathan/backlog.yaml`
4. **Selects first ready task** with allowed scope
5. **Submits worker job** to Kubernetes
6. **Worker creates PR** and posts events
7. **Cycle repeats** until max PRs reached or no tasks

**Guardrails enforced:**
- ✅ Only tasks with `ready: true`
- ✅ Scope restricted to `.leviathan/**` and `docs/**`
- ✅ Max 1 open PR at a time
- ✅ Max 2 attempts per task
- ✅ Circuit breaker after consecutive failures
- ✅ PR-based delivery (no auto-merge)

**You now have a fully autonomous software engineering system running locally!**
