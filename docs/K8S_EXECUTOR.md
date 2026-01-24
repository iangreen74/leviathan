# Kubernetes Executor Setup Guide

Complete guide for running Leviathan with Kubernetes Job execution.

## Overview

The K8s executor submits ephemeral Jobs to a Kubernetes cluster. Each Job:
1. Runs the worker container
2. Clones target repo
3. Executes one task attempt
4. Posts event bundle to control plane API
5. Exits

## Prerequisites

- Kubernetes cluster (kind, minikube, or production cluster)
- Docker for building worker image
- kubectl configured
- Control plane API running

## Quick Start with kind

### 1. Install kind

```bash
# macOS
brew install kind

# Linux
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind
```

### 2. Create kind cluster

```bash
kind create cluster --name leviathan
```

### 3. Build worker image

```bash
# Build image
docker build -t leviathan-worker:local -f ops/executor/Dockerfile .

# Load into kind
kind load docker-image leviathan-worker:local --name leviathan
```

### 4. Create namespace

```bash
kubectl apply -f ops/k8s/namespace.yaml
```

### 5. Create secrets

```bash
# Copy template
cp ops/k8s/secret.template.yaml ops/k8s/secret.yaml

# Edit with your tokens
# - LEVIATHAN_CONTROL_PLANE_TOKEN: openssl rand -hex 32
# - GITHUB_TOKEN: https://github.com/settings/tokens
# - CLAUDE_API_KEY: https://console.anthropic.com/

vim ops/k8s/secret.yaml

# Apply (DO NOT commit secret.yaml)
kubectl apply -f ops/k8s/secret.yaml
```

### 6. Start control plane API

```bash
# In separate terminal
export LEVIATHAN_CONTROL_PLANE_TOKEN=<your-token>
python3 -m leviathan.control_plane.api
```

### 7. Run scheduler with K8s executor

```bash
export LEVIATHAN_CONTROL_PLANE_TOKEN=<your-token>
export LEVIATHAN_EXECUTOR_IMAGE=leviathan-worker:local

python3 -m leviathan.control_plane.scheduler \
  --target radix \
  --once \
  --executor k8s
```

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
    control_plane_url="http://leviathan-api:8000",
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
  curl http://leviathan-api:8000/healthz
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
  name: leviathan-api
  namespace: leviathan
spec:
  replicas: 2
  selector:
    matchLabels:
      app: leviathan-api
  template:
    metadata:
      labels:
        app: leviathan-api
    spec:
      containers:
      - name: api
        image: leviathan-api:v1.0.0
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
  name: leviathan-api
  namespace: leviathan
spec:
  selector:
    app: leviathan-api
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
