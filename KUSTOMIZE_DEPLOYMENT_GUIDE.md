# Leviathan Kustomize Deployment Guide

**Version:** 1.0  
**Last Updated:** 2026-01-30

---

## Overview

Leviathan uses **Kustomize** for environment-specific deployments. This guide covers building images and deploying to kind (local) or EKS (production).

---

## Architecture

```
ops/k8s/
├── base/                          # Common manifests for all environments
│   ├── kustomization.yaml         # Base bundle definition
│   ├── control-plane.yaml         # Control plane deployment + service
│   ├── spider-deployment.yaml     # Spider deployment
│   ├── spider-service.yaml        # Spider service
│   ├── console-deployment.yaml    # Console deployment
│   ├── console-service.yaml       # Console service
│   ├── scheduler.yaml             # Scheduler CronJob
│   └── job-template.yaml          # Worker job template
│
├── overlays/
│   ├── kind/                      # Local development
│   │   └── kustomization.yaml     # Local image tags
│   │
│   └── eks/                       # AWS EKS production
│       └── kustomization.yaml     # ECR registry tags
│
├── control-plane.yaml             # Original manifest (kept for reference)
├── spider/                        # Original manifests (kept for reference)
├── console/                       # Original manifests (kept for reference)
└── scheduler/                     # Original manifests (kept for reference)
```

---

## Images

Leviathan consists of 3 Docker images:

1. **leviathan-control-plane** - Event ingestion, graph queries, autonomy API
2. **leviathan-worker** - Task execution, PR creation (includes git, kubectl)
3. **leviathan-console** - Observability dashboard (minimal, no git/kubectl)

---

## Quick Start: kind Deployment

### 1. Prerequisites

```bash
# Verify tools
kind version          # v0.20.0+
kubectl version       # v1.27.0+
docker --version      # 20.10.0+

# Create kind cluster
kind create cluster --name leviathan

# Create namespace
kubectl create namespace leviathan

# Create secrets
export CONTROL_PLANE_TOKEN=$(openssl rand -hex 32)
export GITHUB_TOKEN="ghp_your_token_here"

kubectl create secret generic leviathan-secrets \
  --namespace=leviathan \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN="$CONTROL_PLANE_TOKEN" \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN"
```

### 2. Build Images

```bash
cd /path/to/leviathan

# Build all images
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
docker build -f ops/docker/console.Dockerfile -t leviathan-console:local .
```

### 3. Load Images into kind

```bash
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
kind load docker-image leviathan-console:local --name leviathan
```

### 4. Deploy Stack

```bash
# Deploy entire stack with one command
kubectl apply -k ops/k8s/overlays/kind

# Wait for pods to be ready
kubectl wait --for=condition=ready pod --all -n leviathan --timeout=120s

# Verify deployment
kubectl get pods -n leviathan
```

**Expected output:**
```
NAME                                      READY   STATUS    RESTARTS   AGE
leviathan-control-plane-<id>              1/1     Running   0          <time>
leviathan-spider-<id>                     1/1     Running   0          <time>
leviathan-console-<id>                    1/1     Running   0          <time>
```

### 5. Access Console

```bash
# Port-forward console
kubectl -n leviathan port-forward svc/leviathan-console 8080:8080

# Open browser to http://localhost:8080
```

---

## EKS Deployment

### 1. Prerequisites

```bash
# AWS CLI configured
aws configure

# EKS cluster created and kubectl context set
kubectl config current-context  # Should show EKS cluster

# Create namespace
kubectl create namespace leviathan

# Create secrets (same as kind)
kubectl create secret generic leviathan-secrets \
  --namespace=leviathan \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN="$CONTROL_PLANE_TOKEN" \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN"
```

### 2. Create ECR Repositories

```bash
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-west-2  # or your region

# Create repositories
aws ecr create-repository --repository-name leviathan-control-plane --region $AWS_REGION
aws ecr create-repository --repository-name leviathan-worker --region $AWS_REGION
aws ecr create-repository --repository-name leviathan-console --region $AWS_REGION
```

### 3. Build and Push Images

```bash
export IMAGE_TAG=v1.0.0  # or use git commit SHA

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build images (if not already built)
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
docker build -f ops/docker/console.Dockerfile -t leviathan-console:local .

# Tag and push control plane
docker tag leviathan-control-plane:local \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-control-plane:$IMAGE_TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-control-plane:$IMAGE_TAG

# Tag and push worker
docker tag leviathan-worker:local \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-worker:$IMAGE_TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-worker:$IMAGE_TAG

# Tag and push console
docker tag leviathan-console:local \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-console:$IMAGE_TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-console:$IMAGE_TAG
```

### 4. Update EKS Overlay

Edit `ops/k8s/overlays/eks/kustomization.yaml` and replace placeholders:

```yaml
images:
  - name: leviathan-control-plane
    newName: 123456789012.dkr.ecr.us-west-2.amazonaws.com/leviathan-control-plane
    newTag: v1.0.0
  - name: leviathan-worker
    newName: 123456789012.dkr.ecr.us-west-2.amazonaws.com/leviathan-worker
    newTag: v1.0.0
  - name: leviathan-console
    newName: 123456789012.dkr.ecr.us-west-2.amazonaws.com/leviathan-console
    newTag: v1.0.0
```

Or use `kustomize edit set image`:

```bash
cd ops/k8s/overlays/eks

kustomize edit set image \
  leviathan-control-plane=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-control-plane:$IMAGE_TAG \
  leviathan-worker=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-worker:$IMAGE_TAG \
  leviathan-console=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-console:$IMAGE_TAG
```

### 5. Deploy to EKS

```bash
# Deploy entire stack
kubectl apply -k ops/k8s/overlays/eks

# Verify deployment
kubectl get pods -n leviathan
kubectl get svc -n leviathan
```

---

## Updating Deployments

### Update Single Component

```bash
# Rebuild image
docker build -f ops/docker/console.Dockerfile -t leviathan-console:local .

# For kind: reload image
kind load docker-image leviathan-console:local --name leviathan

# For EKS: tag and push
docker tag leviathan-console:local \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-console:$IMAGE_TAG
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/leviathan-console:$IMAGE_TAG

# Restart deployment
kubectl rollout restart deployment/leviathan-console -n leviathan
```

### Update All Components

```bash
# Rebuild all images
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
docker build -f ops/docker/console.Dockerfile -t leviathan-console:local .

# For kind: reload all
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
kind load docker-image leviathan-console:local --name leviathan

# Reapply manifests
kubectl apply -k ops/k8s/overlays/kind

# Restart all deployments
kubectl rollout restart deployment -n leviathan
```

---

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl get pods -n leviathan

# Check pod logs
kubectl logs -n leviathan <pod-name>

# Describe pod for events
kubectl describe pod -n leviathan <pod-name>
```

### Image Pull Errors

```bash
# Verify images are loaded (kind)
docker exec -it leviathan-control-plane crictl images | grep leviathan

# Verify ECR authentication (EKS)
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

### Secret Issues

```bash
# Verify secret exists
kubectl get secret leviathan-secrets -n leviathan

# Check secret keys
kubectl get secret leviathan-secrets -n leviathan -o jsonpath='{.data}' | jq
```

### Kustomize Rendering Issues

```bash
# Preview rendered manifests without applying
kubectl kustomize ops/k8s/overlays/kind

# Check for YAML syntax errors
kubectl kustomize ops/k8s/overlays/kind | kubectl apply --dry-run=client -f -
```

---

## Cleanup

### kind Cluster

```bash
# Delete entire cluster
kind delete cluster --name leviathan
```

### EKS Deployment

```bash
# Delete Leviathan resources
kubectl delete -k ops/k8s/overlays/eks

# Delete namespace
kubectl delete namespace leviathan

# Delete ECR images (optional)
aws ecr batch-delete-image \
  --repository-name leviathan-control-plane \
  --image-ids imageTag=$IMAGE_TAG \
  --region $AWS_REGION
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy to EKS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v2
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-west-2
      
      - name: Login to ECR
        run: |
          aws ecr get-login-password --region us-west-2 | \
            docker login --username AWS --password-stdin \
            ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-west-2.amazonaws.com
      
      - name: Build and push images
        run: |
          IMAGE_TAG=${{ github.sha }}
          
          docker build -f ops/docker/control-plane.Dockerfile \
            -t ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-west-2.amazonaws.com/leviathan-control-plane:$IMAGE_TAG .
          docker push ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-west-2.amazonaws.com/leviathan-control-plane:$IMAGE_TAG
          
          # Repeat for worker and console...
      
      - name: Update kustomization
        run: |
          cd ops/k8s/overlays/eks
          kustomize edit set image \
            leviathan-control-plane=${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-west-2.amazonaws.com/leviathan-control-plane:${{ github.sha }}
      
      - name: Deploy to EKS
        run: |
          kubectl apply -k ops/k8s/overlays/eks
```

---

## Best Practices

1. **Use Specific Image Tags** - Never use `:latest` in production
2. **Version Control Overlays** - Commit overlay changes with image updates
3. **Test in kind First** - Validate changes locally before EKS deployment
4. **Monitor Deployments** - Use `kubectl rollout status` to verify updates
5. **Backup Secrets** - Store secrets securely (AWS Secrets Manager, etc.)
6. **Resource Limits** - Set appropriate CPU/memory limits for production
7. **Health Checks** - Ensure liveness/readiness probes are configured
8. **Logging** - Aggregate logs to CloudWatch or similar service

---

## Reference

- **Kustomize Documentation:** https://kustomize.io/
- **kubectl Reference:** https://kubernetes.io/docs/reference/kubectl/
- **kind Documentation:** https://kind.sigs.k8s.io/
- **EKS Documentation:** https://docs.aws.amazon.com/eks/

---

**Questions or Issues?** See `docs/23_INTEGRATION_EVIDENCE_KIND.md` for detailed integration testing steps.
