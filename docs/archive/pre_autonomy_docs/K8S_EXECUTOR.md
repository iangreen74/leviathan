> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# Kubernetes Executor Setup Guide

Complete guide for running Leviathan with Kubernetes Job execution.

## Overview

The K8s executor submits ephemeral Jobs to a Kubernetes cluster. Each Job:
1. Runs the worker container
2. Clones target repo
3. Loads task from `.leviathan/backlog.yaml`
4. Executes task using rewrite mode (real code generation)
5. Commits changes to branch `agent/<task_id>-<attempt_id>`
6. Pushes branch to GitHub using token authentication
7. Creates pull request via GitHub API
8. Posts event bundle to control plane API (includes PR number, URL, commit SHA)
9. Exits

**Success requires a real PR**: The worker must successfully create a GitHub PR with a valid PR number and URL. Placeholder PRs are not accepted.

## Container Images

Pre-built images are available on GitHub Container Registry:

```bash
# Worker image (executes tasks in Kubernetes Jobs)
ghcr.io/iangreen74/leviathan-worker:latest
ghcr.io/iangreen74/leviathan-worker:<sha>
ghcr.io/iangreen74/leviathan-worker:v1.0.0

# Control plane image (API server)
ghcr.io/iangreen74/leviathan-control-plane:latest
ghcr.io/iangreen74/leviathan-control-plane:<sha>
ghcr.io/iangreen74/leviathan-control-plane:v1.0.0
```

**Image tags:**
- `:latest` - Latest release from main branch
- `:v*` - Specific version tag (e.g., v1.0.0)
- `:<sha>` - Specific commit SHA (7 chars)

Images are automatically built and published via GitHub Actions on every push to main and on version tags.

## Prerequisites

- Kubernetes cluster (kind, minikube, or production cluster)
- kubectl configured
- Control plane API running
- (Optional) Docker for building images locally

## Kind Quickstart

The fastest way to get Leviathan running on Kubernetes is using our automated bootstrap script.

### Prerequisites

Install required tools:

```bash
# macOS
brew install kind kubectl docker

# Linux
# Install Docker: https://docs.docker.com/engine/install/
# Install kubectl: https://kubernetes.io/docs/tasks/tools/
# Install kind:
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```

### One-Command Setup

1. **Create environment file** with your credentials:

```bash
mkdir -p ~/.leviathan
cat > ~/.leviathan/env << 'EOF'
export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export LEVIATHAN_CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export LEVIATHAN_CLAUDE_MODEL=claude-3-5-sonnet-20241022
EOF

# Edit with your actual tokens
vim ~/.leviathan/env
```

Get your tokens:
- **GITHUB_TOKEN**: Create at https://github.com/settings/tokens (needs `repo` scope)
- **LEVIATHAN_CLAUDE_API_KEY**: Get from https://console.anthropic.com/

**Note**: The control plane token is auto-generated and persisted to `~/.leviathan/control-plane-token` on first run.

2. **Run bootstrap script**:

```bash
./ops/k8s/kind-bootstrap.sh
```

This script is **idempotent** and will:
- ✓ Load environment from `~/.leviathan/env`
- ✓ Generate and persist control plane token (once)
- ✓ Validate all required environment variables
- ✓ Create Kind cluster `leviathan` (if missing)
- ✓ Build worker image `leviathan-worker:local`
- ✓ Load image into Kind cluster
- ✓ Create namespace `leviathan`
- ✓ Create/update secrets (without printing values)
- ✓ Deploy control plane API
- ✓ Run smoke tests:
  - Health check endpoint
  - Event ingestion with authentication

3. **Run scheduler**:

```bash
# Load environment and token
source ~/.leviathan/env
export LEVIATHAN_CONTROL_PLANE_TOKEN=$(cat ~/.leviathan/control-plane-token)

# Run scheduler with K8s executor
python3 -m leviathan.control_plane \
  --target <target-name> \
  --once \
  --executor k8s
```

### Branch Naming Convention

Worker creates branches with collision-safe naming:
```
agent/<task_id>-<attempt_id>
```

Examples:
- `agent/task-001-attempt-abc123`
- `agent/fix-login-attempt-def456`

This ensures:
- Each attempt gets a unique branch
- Retries don't collide with previous attempts
- Branch names are traceable to specific attempts

### What Gets Deployed

The bootstrap script creates:

```
kind cluster: leviathan
└── namespace: leviathan
    ├── Secret: leviathan-secrets
    │   ├── control-plane-token
    │   ├── github-token
    │   ├── claude-api-key
    │   └── claude-model
    ├── Deployment: leviathan-control-plane
    │   └── Pod: control plane API (port 8000)
    └── Service: leviathan-control-plane
        └── http://leviathan-control-plane:8000
```

### Monitoring

```bash
# Watch jobs
kubectl get jobs -n leviathan -w

# View pod logs
kubectl logs -f <pod-name> -n leviathan

# Check control plane logs
kubectl logs -f deployment/leviathan-control-plane -n leviathan

# List all resources
kubectl get all -n leviathan
```

### Cleanup

```bash
# Delete cluster
kind delete cluster --name leviathan

# Or just delete namespace
kubectl delete namespace leviathan
```

### Manual Setup (Alternative)

If you prefer manual setup instead of the bootstrap script:

<details>
<summary>Click to expand manual steps</summary>

### 1. Create kind cluster

```bash
kind create cluster --name leviathan
```

### 2. Build or pull worker image

**Option A: Use pre-built GHCR images (recommended)**

```bash
# Pull from GitHub Container Registry
docker pull ghcr.io/iangreen74/leviathan-worker:latest
docker pull ghcr.io/iangreen74/leviathan-control-plane:latest

# Tag for kind
docker tag ghcr.io/iangreen74/leviathan-worker:latest leviathan-worker:local
docker tag ghcr.io/iangreen74/leviathan-control-plane:latest leviathan-control-plane:local

# Load into kind cluster
kind load docker-image leviathan-worker:local --name leviathan
kind load docker-image leviathan-control-plane:local --name leviathan
```

**Option B: Build locally**

```bash
docker build -t leviathan-worker:local -f ops/docker/worker.Dockerfile .
docker build -t leviathan-control-plane:local -f ops/docker/control-plane.Dockerfile .
kind load docker-image leviathan-worker:local --name leviathan
kind load docker-image leviathan-control-plane:local --name leviathan
```

### 3. Create namespace

```bash
kubectl apply -f ops/k8s/namespace.yaml
```

### 4. Create secrets

```bash
kubectl create secret generic leviathan-secrets \
  -n leviathan \
  --from-literal=control-plane-token="$(openssl rand -hex 32)" \
  --from-literal=github-token="$GITHUB_TOKEN" \
  --from-literal=claude-api-key="$LEVIATHAN_CLAUDE_API_KEY" \
  --from-literal=claude-model="$LEVIATHAN_CLAUDE_MODEL"
```

### 5. Deploy control plane

```bash
kubectl apply -f ops/k8s/control-plane.yaml
kubectl wait --for=condition=available --timeout=120s \
  deployment/leviathan-control-plane -n leviathan
```

### 6. Test control plane

```bash
kubectl run test --image=curlimages/curl --restart=Never --rm -i -n leviathan -- \
  curl -f http://leviathan-control-plane:8000/healthz
```

</details>

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Scheduler                               │
│  ┌────────────────────────────────────────────────────┐     │
│  │  K8sExecutor                                       │     │
│  │  - generate_job_spec()                             │     │
│  │  - submit Job to K8s                               │     │
│  │  - wait for completion                             │     │
│  │  - collect pod logs                                │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Kubernetes Cluster                          │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Job: leviathan-attempt-abc123                     │     │
│  │  ┌──────────────────────────────────────────────┐ │     │
│  │  │  Pod: worker container                       │ │     │
│  │  │  - Clone repo                                │ │     │
│  │  │  - Execute task                              │ │     │
│  │  │  - POST event bundle to API                  │ │     │
│  │  │  - Exit                                      │ │     │
│  │  └──────────────────────────────────────────────┘ │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Control Plane API                               │
│  POST /v1/events/ingest                                      │
│  - Receives event bundle from worker                         │
│  - Appends events to event store                             │
│  - Updates graph projection                                  │
└─────────────────────────────────────────────────────────────┘
```

## Worker Environment Variables

The worker container receives these environment variables:

| Variable | Description | Source |
|----------|-------------|--------|
| `TARGET_NAME` | Target identifier | Job spec |
| `TARGET_REPO_URL` | Git repository URL | Job spec |
| `TARGET_BRANCH` | Branch to checkout | Job spec |
| `TASK_ID` | Task identifier | Job spec |
| `ATTEMPT_ID` | Attempt identifier | Job spec |
| `CONTROL_PLANE_URL` | API URL | Job spec |
| `CONTROL_PLANE_TOKEN` | API auth token | Secret |
| `GITHUB_TOKEN` | GitHub PAT | Secret |
| `LEVIATHAN_CLAUDE_API_KEY` | Claude API key | Secret |
| `LEVIATHAN_CLAUDE_MODEL` | Claude model name | Job spec |

## Job Lifecycle

1. **Scheduler creates attempt** → `attempt.created` event
2. **K8sExecutor generates Job spec** → deterministic from attempt metadata
3. **K8sExecutor submits Job** → `job.submitted` event
4. **K8s schedules pod** → pulls worker image
5. **Worker starts** → `attempt.started` event (from worker)
6. **Worker clones repo** → uses GITHUB_TOKEN
7. **Worker executes task** → generates code, runs tests, repair loop
8. **Worker commits & pushes** → creates branch `agent/<task_id>`
9. **Worker creates PR** → GitHub API
10. **Worker posts event bundle** → `POST /v1/events/ingest`
11. **Worker exits** → Job completes
12. **K8sExecutor collects logs** → stores as artifact
13. **K8sExecutor returns result** → `attempt.succeeded` or `attempt.failed`

## Monitoring

### Watch Jobs

```bash
# List jobs
kubectl get jobs -n leviathan

# Watch job status
kubectl get jobs -n leviathan -w

# Describe job
kubectl describe job leviathan-attempt-abc123 -n leviathan
```

### View Pod Logs

```bash
# List pods
kubectl get pods -n leviathan

# Tail logs
kubectl logs -f <pod-name> -n leviathan

# Get logs for completed pod
kubectl logs leviathan-attempt-abc123-<hash> -n leviathan
```

### Query Control Plane

```bash
# Get graph summary
curl http://localhost:8000/v1/graph/summary \
  -H "Authorization: Bearer $LEVIATHAN_CONTROL_PLANE_TOKEN"

# Get attempt details
curl http://localhost:8000/v1/attempts/attempt-abc123 \
  -H "Authorization: Bearer $LEVIATHAN_CONTROL_PLANE_TOKEN"
```

## Configuration

### Executor Configuration

```python
from leviathan.executors.k8s_executor import K8sExecutor

executor = K8sExecutor(
    namespace="leviathan",
    image="leviathan-worker:v1.0.0",
    control_plane_url="http://leviathan-control-plane:8000",
    control_plane_token="<token>",
    in_cluster=True  # Set True when running inside K8s
)
```

### Scheduler with K8s Executor

```python
from leviathan.control_plane.scheduler import Scheduler
from leviathan.executors.k8s_executor import K8sExecutor

executor = K8sExecutor(namespace="leviathan")

scheduler = Scheduler(
    event_store=event_store,
    graph_store=graph_store,
    artifact_store=artifact_store,
    executor=executor,
    retry_policy=retry_policy
)

scheduler.run_once("radix", target_config)
```

## Troubleshooting

### Job fails immediately

```bash
# Check pod events
kubectl describe pod <pod-name> -n leviathan

# Common issues:
# - Image pull error: verify image exists in cluster
# - Secret not found: verify secret created
# - Permission denied: check RBAC
```

### Worker can't clone repo

```bash
# Check GITHUB_TOKEN in secret
kubectl get secret leviathan-secrets -n leviathan -o yaml

# Verify token has repo scope
# Verify repo URL is correct
```

### Worker can't post to API

```bash
# Check CONTROL_PLANE_URL
# Verify API is accessible from cluster
# Check token matches

# Test from pod
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n leviathan -- \
  curl http://leviathan-control-plane:8000/healthz
```

### Job stuck in pending

```bash
# Check node resources
kubectl top nodes

# Check pod events
kubectl describe pod <pod-name> -n leviathan

# Common issues:
# - Insufficient resources
# - Image pull backoff
# - Volume mount issues
```

## Production Deployment

### 1. Deploy Control Plane API

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: leviathan-control-plane
  namespace: leviathan
spec:
  replicas: 2
  selector:
    matchLabels:
      app: leviathan-control-plane
  template:
    metadata:
      labels:
        app: leviathan-control-plane
    spec:
      containers:
      - name: api
        image: leviathan-worker:v1.0.0
        command: ["python", "-m", "leviathan.control_plane.api"]
        env:
        - name: LEVIATHAN_CONTROL_PLANE_TOKEN
          valueFrom:
            secretKeyRef:
              name: leviathan-secrets
              key: control-plane-token
        - name: LEVIATHAN_BACKEND
          value: postgres
        - name: LEVIATHAN_POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: leviathan-secrets
              key: postgres-url
        ports:
        - containerPort: 8000
---
apiVersion: v1
kind: Service
metadata:
  name: leviathan-control-plane
  namespace: leviathan
spec:
  selector:
    app: leviathan-control-plane
  ports:
  - port: 8000
    targetPort: 8000
```

### 2. Deploy Scheduler

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: leviathan-scheduler
  namespace: leviathan
spec:
  replicas: 1
  selector:
    matchLabels:
      app: leviathan-scheduler
  template:
    metadata:
      labels:
        app: leviathan-scheduler
    spec:
      serviceAccountName: leviathan-scheduler
      containers:
      - name: scheduler
        image: leviathan-scheduler:v1.0.0
        env:
        - name: LEVIATHAN_CONTROL_PLANE_TOKEN
          valueFrom:
            secretKeyRef:
              name: leviathan-secrets
              key: control-plane-token
        - name: LEVIATHAN_EXECUTOR_IMAGE
          value: leviathan-worker:v1.0.0
```

### 3. RBAC for Scheduler

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: leviathan-scheduler
  namespace: leviathan
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: leviathan-scheduler
  namespace: leviathan
rules:
- apiGroups: ["batch"]
  resources: ["jobs"]
  verbs: ["create", "get", "list", "watch", "delete"]
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: leviathan-scheduler
  namespace: leviathan
subjects:
- kind: ServiceAccount
  name: leviathan-scheduler
roleRef:
  kind: Role
  name: leviathan-scheduler
  apiGroup: rbac.authorization.k8s.io
```

## Security Best Practices

1. **Secrets Management**
   - Never commit secrets to git
   - Use external secret managers (Vault, AWS Secrets Manager)
   - Rotate tokens regularly

2. **RBAC**
   - Minimal permissions for scheduler ServiceAccount
   - Namespace isolation
   - Network policies

3. **Image Security**
   - Scan images for vulnerabilities
   - Use minimal base images
   - Pin image versions

4. **Network Policies**
   - Restrict worker pod egress
   - Allow only necessary API access

## Testing

Run unit tests (no cluster required):

```bash
python3 -m pytest tests/unit/test_k8s_job_spec.py -v
python3 -m pytest tests/unit/test_k8s_executor_mock.py -v
python3 -m pytest tests/unit/test_worker_event_bundle.py -v
```

All tests use mocked Kubernetes client and don't require a live cluster.
