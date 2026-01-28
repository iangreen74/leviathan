> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# K8s PR Proof v1: End-to-End Guide

## Overview

This guide demonstrates running PR Proof v1 on Kubernetes (kind) using the packaged module entrypoint.

**Key Features:**
- Uses `python3 -m leviathan.executor.pr_proof_v1` (no scripts/ dependency)
- HTTPS authentication (works in pods without SSH keys)
- Creates real GitHub PR modifying only `.leviathan/backlog.yaml`
- Posts complete event lifecycle to control plane

## Prerequisites

- kind cluster running
- Docker installed
- GitHub token with `repo` scope
- Access to iangreen74/radix repository

## Quick Start

```bash
# 1. Create kind cluster
kind create cluster --name leviathan

# 2. Build and load images
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:latest .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:latest .

kind load docker-image leviathan-control-plane:latest --name leviathan
kind load docker-image leviathan-worker:latest --name leviathan

# 3. Create secrets
kubectl create secret generic leviathan-control-plane-secret \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token

kubectl create secret generic leviathan-secrets \
  --from-literal=github-token=<your-github-token>

# 4. Deploy control plane
kubectl apply -f ops/k8s/control-plane.yaml

# Wait for control plane to be ready
kubectl wait --for=condition=ready pod -l app=leviathan-control-plane --timeout=60s

# 5. Run PR proof job
kubectl apply -f ops/k8s/jobs/pr-proof-v1.yaml

# 6. Watch job progress
kubectl logs -f job/leviathan-pr-proof-v1

# 7. Verify PR created
# Check job output for PR URL
kubectl logs job/leviathan-pr-proof-v1 | grep "PR URL"
```

## Detailed Steps

### 1. Build Images

```bash
# Control plane
docker build -f ops/docker/control-plane.Dockerfile \
  -t leviathan-control-plane:latest .

# Worker (includes PR proof module)
docker build -f ops/docker/worker.Dockerfile \
  -t leviathan-worker:latest .
```

### 2. Load Images to kind

```bash
kind load docker-image leviathan-control-plane:latest --name leviathan
kind load docker-image leviathan-worker:latest --name leviathan
```

### 3. Create Secrets

**Control Plane Token:**
```bash
kubectl create secret generic leviathan-control-plane-secret \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
```

**GitHub Token:**
```bash
kubectl create secret generic leviathan-secrets \
  --from-literal=github-token=ghp_your_token_here
```

### 4. Deploy Control Plane

```bash
kubectl apply -f ops/k8s/control-plane.yaml

# Verify deployment
kubectl get pods -l app=leviathan-control-plane
kubectl logs -l app=leviathan-control-plane
```

### 5. Run PR Proof Job

```bash
kubectl apply -f ops/k8s/jobs/pr-proof-v1.yaml
```

**Job Manifest:** `ops/k8s/jobs/pr-proof-v1.yaml`
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: leviathan-pr-proof-v1
spec:
  template:
    spec:
      containers:
      - name: pr-proof-worker
        image: leviathan-worker:latest
        imagePullPolicy: IfNotPresent
        command: ["python3", "-m", "leviathan.executor.pr_proof_v1"]
        env:
        - name: GITHUB_TOKEN
          valueFrom:
            secretKeyRef:
              name: leviathan-secrets
              key: github-token
        - name: CONTROL_PLANE_TOKEN
          valueFrom:
            secretKeyRef:
              name: leviathan-control-plane-secret
              key: LEVIATHAN_CONTROL_PLANE_TOKEN
        - name: CONTROL_PLANE_URL
          value: "http://leviathan-control-plane:8000"
        - name: TARGET_NAME
          value: "radix"
        - name: TARGET_REPO_URL
          value: "https://github.com/iangreen74/radix.git"
        - name: TARGET_BRANCH
          value: "main"
        - name: ATTEMPT_ID
          value: "attempt-pr-proof-k8s"
        - name: LEVIATHAN_WORKSPACE_DIR
          value: "/workspace"
        volumeMounts:
        - name: workspace
          mountPath: /workspace
      volumes:
      - name: workspace
        emptyDir: {}
```

### 6. Monitor Job

```bash
# Watch job status
kubectl get jobs -w

# View logs
kubectl logs -f job/leviathan-pr-proof-v1

# Get job details
kubectl describe job leviathan-pr-proof-v1
```

### 7. Verify Results

**Check PR Created:**
```bash
# Extract PR URL from logs
kubectl logs job/leviathan-pr-proof-v1 | grep "PR URL"

# Example output:
# PR URL: https://github.com/iangreen74/radix/pull/1
```

**Verify PR Diff:**
```bash
gh pr view <PR_NUMBER> --repo iangreen74/radix
gh pr diff <PR_NUMBER> --repo iangreen74/radix --name-only
```

**Expected:** Only `.leviathan/backlog.yaml` modified

**Check Control Plane Events:**
```bash
# Port-forward to control plane
kubectl port-forward svc/leviathan-control-plane 8000:8000

# Query events (in another terminal)
curl -H "Authorization: Bearer dev-token" \
  http://localhost:8000/v1/graph/summary | jq
```

## Expected Output

```
============================================================
PR Proof v1: Backlog-Only PR Creation
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git
Task: pr-proof-v1-backlog-only
Attempt: attempt-pr-proof-k8s

✓ Posted attempt.created event to control plane
✓ Posted attempt.started event to control plane

Cloning https://github.com/iangreen74/radix.git...
✓ Cloned to /workspace/attempt-pr-proof-k8s/target
✓ Added task pr-proof-v1-backlog-only to backlog
Pushing branch agent/backlog-propose-attempt-pr-proof-k8s...
✓ Branch pushed: agent/backlog-propose-attempt-pr-proof-k8s
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
Branch: agent/backlog-propose-attempt-pr-proof-k8s
Commit SHA: abc123def456...
```

## Troubleshooting

### Job Fails with "Missing required env vars"

**Cause:** Secrets not created or incorrect secret keys

**Fix:**
```bash
# Verify secrets exist
kubectl get secrets

# Check secret contents
kubectl describe secret leviathan-secrets
kubectl describe secret leviathan-control-plane-secret
```

### Job Fails with "Authentication failed"

**Cause:** Invalid GitHub token

**Fix:**
```bash
# Verify token has repo scope
gh auth status

# Recreate secret with valid token
kubectl delete secret leviathan-secrets
kubectl create secret generic leviathan-secrets \
  --from-literal=github-token=<new-token>
```

### Job Fails with "Connection refused" to control plane

**Cause:** Control plane not running or wrong URL

**Fix:**
```bash
# Check control plane status
kubectl get pods -l app=leviathan-control-plane
kubectl logs -l app=leviathan-control-plane

# Verify service exists
kubectl get svc leviathan-control-plane
```

### Image Pull Errors

**Cause:** Images not loaded to kind

**Fix:**
```bash
# List images in kind
docker exec -it leviathan-control-plane crictl images

# Reload images
kind load docker-image leviathan-worker:latest --name leviathan
```

## Cleanup

```bash
# Delete job
kubectl delete job leviathan-pr-proof-v1

# Delete control plane
kubectl delete -f ops/k8s/control-plane.yaml

# Delete secrets
kubectl delete secret leviathan-secrets
kubectl delete secret leviathan-control-plane-secret

# Delete kind cluster
kind delete cluster --name leviathan
```

## Architecture Notes

### Module Entrypoint

The PR proof logic is packaged as a first-class module:
```
leviathan/executor/pr_proof_v1/
  __init__.py
  __main__.py  # Entry point
```

**Invocation:**
```bash
python3 -m leviathan.executor.pr_proof_v1
```

**Benefits:**
- No dependency on scripts/ directory
- Packaged in worker image
- Consistent with other Leviathan modules
- CI-validated via packaging invariants

### HTTPS Authentication

K8s pods don't have SSH keys, so we use HTTPS with token:
```
TARGET_REPO_URL=https://github.com/iangreen74/radix.git
GITHUB_TOKEN=<from-secret>
```

Token is injected into git URLs: `https://<token>@github.com/...`

### Event Lifecycle

```
attempt.created (attempt_number=1)
  ↓
attempt.started
  ↓
[Clone, modify backlog, commit, push]
  ↓
pr.created (pr_number, pr_url, commit_sha)
  ↓
attempt.succeeded
```

All events include:
- `event_id` (UUID)
- `event_type`
- `timestamp` (ISO8601)
- `actor_id` (pr-proof-worker-<attempt_id>)
- `payload`

### Backlog-Only Enforcement

- Only `.leviathan/backlog.yaml` is modified
- Uses `git add -f` to force-add even if directory is ignored
- Task spec: `allowed_paths: [".leviathan/backlog.yaml"]`

## Related Documentation

- [PR Proof v1 Fixed](../PR_PROOF_V1_FIXED.md) - Local execution guide
- [Control Plane Deployment](DEPLOY_CONTROL_PLANE.md) - Control plane setup
- [Worker Architecture](../leviathan/executor/README.md) - Worker design
