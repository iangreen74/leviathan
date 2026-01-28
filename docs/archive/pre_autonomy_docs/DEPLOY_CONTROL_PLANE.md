> ⚠️ ARCHIVED DOCUMENT
> This file is preserved for historical context only.
> It does NOT describe the current Leviathan system.
>
> Canonical documentation begins at:
> `docs/00_CANONICAL_OVERVIEW.md`

# Control Plane Deployment Guide

This guide covers deploying the Leviathan control plane API to Kubernetes clusters.

## Overview

The control plane is a FastAPI service that:
- Receives event bundles from workers via `/v1/events/ingest`
- Stores events and maintains task/attempt graph state
- Provides health check endpoint at `/healthz`
- Supports two backends: NDJSON (dev) and PostgreSQL (production)

## Quick Start (kind)

For local development with kind:

```bash
# 1. Create namespace
kubectl apply -f ops/k8s/control-plane/namespace.yaml

# 2. Create secret from template
cp ops/k8s/control-plane/secret.template.yaml ops/k8s/control-plane/secret.yaml

# Generate token and update secret.yaml
TOKEN=$(openssl rand -hex 32)
sed -i "s/REPLACE_WITH_ACTUAL_TOKEN/$TOKEN/" ops/k8s/control-plane/secret.yaml

# Apply secret
kubectl apply -f ops/k8s/control-plane/secret.yaml

# Save token for scheduler
echo $TOKEN > ~/.leviathan/control-plane-token

# 3. Apply configmap, deployment, and service
kubectl apply -f ops/k8s/control-plane/configmap.yaml
kubectl apply -f ops/k8s/control-plane/deployment.yaml
kubectl apply -f ops/k8s/control-plane/service.yaml

# 4. Wait for deployment
kubectl wait --for=condition=available --timeout=60s \
  deployment/leviathan-control-plane -n leviathan

# 5. Verify health
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &
curl http://localhost:8000/healthz
```

## Production Deployment (EKS, GKE, AKS)

### Prerequisites

- Kubernetes cluster with kubectl access
- Container registry access (GHCR images are public)
- Secrets management solution (AWS Secrets Manager, HashiCorp Vault, etc.)

### Step 1: Create Namespace

```bash
kubectl apply -f ops/k8s/control-plane/namespace.yaml
```

### Step 2: Configure Backend

**Option A: NDJSON Backend (Simple, Dev/Testing)**

Use default configmap (already set to ndjson):

```bash
kubectl apply -f ops/k8s/control-plane/configmap.yaml
```

**Option B: PostgreSQL Backend (Production)**

1. Deploy PostgreSQL (or use managed service like RDS, Cloud SQL)

2. Update configmap:

```yaml
# ops/k8s/control-plane/configmap.yaml
data:
  LEVIATHAN_CONTROL_PLANE_BACKEND: "postgres"
  POSTGRES_HOST: "your-postgres-host"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "leviathan"
  POSTGRES_USER: "leviathan"
```

3. Apply configmap:

```bash
kubectl apply -f ops/k8s/control-plane/configmap.yaml
```

### Step 3: Create Secrets

**Generate Control Plane Token:**

```bash
openssl rand -hex 32
```

**Create Secret:**

```bash
# Copy template
cp ops/k8s/control-plane/secret.template.yaml ops/k8s/control-plane/secret.yaml

# Edit secret.yaml and replace placeholders:
# - LEVIATHAN_CONTROL_PLANE_TOKEN: <generated-token>
# - POSTGRES_PASSWORD: <postgres-password> (if using postgres)

# Apply secret
kubectl apply -f ops/k8s/control-plane/secret.yaml

# IMPORTANT: Do not commit secret.yaml to git!
# Add to .gitignore if not already present
```

**Alternative: Use External Secrets Operator**

For production, consider using External Secrets Operator to sync from AWS Secrets Manager, Vault, etc.

### Step 4: Deploy Control Plane

```bash
kubectl apply -f ops/k8s/control-plane/deployment.yaml
kubectl apply -f ops/k8s/control-plane/service.yaml
```

### Step 5: Verify Deployment

```bash
# Check deployment status
kubectl get deployment -n leviathan leviathan-control-plane

# Check pod logs
kubectl logs -f -n leviathan deployment/leviathan-control-plane

# Check health endpoint
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000
curl http://localhost:8000/healthz
```

Expected response:
```json
{"status": "healthy"}
```

## Accessing the Control Plane

### From Within Cluster (Workers)

Workers use the service DNS name:

```
http://leviathan-control-plane.leviathan.svc.cluster.local:8000
```

Or short form (within same namespace):

```
http://leviathan-control-plane:8000
```

This is already configured in `ops/k8s/job-template.yaml`.

### From Outside Cluster (Scheduler)

**Option 1: Port Forward (Development)**

```bash
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000
```

Then use `http://localhost:8000` in scheduler.

**Option 2: Ingress (Production)**

Create an Ingress resource:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: leviathan-control-plane
  namespace: leviathan
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - leviathan.example.com
    secretName: leviathan-tls
  rules:
  - host: leviathan.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: leviathan-control-plane
            port:
              number: 8000
```

**Option 3: LoadBalancer Service**

Change service type to LoadBalancer:

```yaml
# ops/k8s/control-plane/service.yaml
spec:
  type: LoadBalancer
  # ... rest of spec
```

## Token Management

### Creating Tokens

```bash
# Generate secure token
openssl rand -hex 32

# Or use Python
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### Storing Tokens

**For Scheduler (Local):**

```bash
# Save to file
echo "your-token-here" > ~/.leviathan/control-plane-token

# Use in scheduler
export LEVIATHAN_CONTROL_PLANE_TOKEN=$(cat ~/.leviathan/control-plane-token)
```

**For Workers (Kubernetes):**

Tokens are automatically injected from secrets via `job-template.yaml`.

### Rotating Tokens

```bash
# 1. Generate new token
NEW_TOKEN=$(openssl rand -hex 32)

# 2. Update secret
kubectl create secret generic leviathan-control-plane-secret \
  -n leviathan \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN="$NEW_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

# 3. Restart control plane to pick up new token
kubectl rollout restart deployment/leviathan-control-plane -n leviathan

# 4. Update scheduler token
echo "$NEW_TOKEN" > ~/.leviathan/control-plane-token
```

## Monitoring

### Health Checks

```bash
# Via port-forward
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000
curl http://localhost:8000/healthz

# Via pod exec
kubectl exec -n leviathan deployment/leviathan-control-plane -- \
  curl -s http://localhost:8000/healthz
```

### Logs

```bash
# Follow logs
kubectl logs -f -n leviathan deployment/leviathan-control-plane

# Last 100 lines
kubectl logs -n leviathan deployment/leviathan-control-plane --tail=100

# Logs from specific pod
kubectl logs -n leviathan <pod-name>
```

### Metrics

The control plane exposes metrics at `/metrics` (if configured).

## Scaling

### Horizontal Scaling

For high availability, increase replicas:

```bash
kubectl scale deployment/leviathan-control-plane -n leviathan --replicas=3
```

**Note:** When using NDJSON backend with multiple replicas, ensure shared storage (PVC) or use PostgreSQL backend instead.

### Resource Tuning

Adjust resource requests/limits in `deployment.yaml`:

```yaml
resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl get pods -n leviathan -l component=control-plane

# Describe pod for events
kubectl describe pod -n leviathan <pod-name>

# Check logs
kubectl logs -n leviathan <pod-name>
```

Common issues:
- Missing secret: Ensure `leviathan-control-plane-secret` exists
- Image pull errors: Check GHCR access (images are public)
- Port conflicts: Ensure port 8000 is not in use

### Health Check Failing

```bash
# Check if pod is running
kubectl get pods -n leviathan

# Test health endpoint directly
kubectl exec -n leviathan <pod-name> -- curl -v http://localhost:8000/healthz

# Check logs for errors
kubectl logs -n leviathan <pod-name>
```

### Workers Can't Connect

```bash
# Verify service exists
kubectl get svc -n leviathan leviathan-control-plane

# Test DNS resolution from worker pod
kubectl run -n leviathan test-dns --rm -it --image=busybox -- \
  nslookup leviathan-control-plane

# Test connectivity
kubectl run -n leviathan test-curl --rm -it --image=curlimages/curl -- \
  curl -v http://leviathan-control-plane:8000/healthz
```

### Database Connection Issues (PostgreSQL)

```bash
# Check postgres connectivity from control plane pod
kubectl exec -n leviathan <pod-name> -- \
  psql "$POSTGRES_DSN" -c "SELECT 1"

# Check configmap
kubectl get configmap -n leviathan leviathan-control-plane-config -o yaml

# Check secret (without revealing values)
kubectl get secret -n leviathan leviathan-control-plane-secret
```

## Cleanup

```bash
# Delete all control plane resources
kubectl delete -f ops/k8s/control-plane/

# Or delete namespace (removes everything)
kubectl delete namespace leviathan
```

## Architecture Notes

### NDJSON Backend

- **Pros:** Simple, no external dependencies, good for dev/testing
- **Cons:** Not suitable for multiple replicas, limited query capabilities
- **Storage:** Uses emptyDir volume (ephemeral) or PVC for persistence

### PostgreSQL Backend

- **Pros:** Production-ready, supports multiple replicas, rich queries
- **Cons:** Requires PostgreSQL setup and maintenance
- **Recommended for:** Production deployments, high availability

### Service Discovery

Workers discover control plane via Kubernetes DNS:
- Full DNS: `leviathan-control-plane.leviathan.svc.cluster.local`
- Short form: `leviathan-control-plane` (within same namespace)

### Security

- Control plane requires authentication token for `/v1/events/ingest`
- Tokens should be rotated regularly
- Use network policies to restrict access if needed
- Consider using service mesh (Istio, Linkerd) for mTLS

## Next Steps

After deploying control plane:

1. Deploy worker jobs using K8s executor (see `docs/K8S_EXECUTOR.md`)
2. Run scheduler with `--executor k8s`
3. Monitor events and task progress via control plane API
4. Set up ingress for external access (optional)
5. Configure PostgreSQL backend for production (recommended)
