# Leviathan Deployment Strategy

**Last Updated:** 2026-01-31  
**Status:** Canonical (Operational)

---

## Overview

This document defines Leviathan's deployment strategy across environments, from local development to production AWS infrastructure.

**Key Principle:** Start simple, scale incrementally. EC2 + k3s is the preferred first AWS deployment for cost efficiency and operational simplicity.

---

## Deployment Environments

### 1. Local Development (kind)

**Purpose:** Development, testing, and validation before production deployment.

**Infrastructure:**
- kind (Kubernetes in Docker)
- Single-node cluster
- Local Docker images (`:local` tag)
- No external dependencies

**Deployment:**
```bash
# Bootstrap kind cluster
./ops/k8s/kind-bootstrap.sh

# Build and load images
docker build -t leviathan-worker:local -f ops/docker/worker.Dockerfile .
kind load docker-image leviathan-worker:local --name leviathan

# Deploy via Kustomize
kubectl apply -k ops/k8s/overlays/kind

# Verify
kubectl -n leviathan get pods
```

**Characteristics:**
- ✅ Fast iteration cycle
- ✅ No cloud costs
- ✅ Full feature parity with production
- ⚠️ Not suitable for multi-user or high-volume testing
- ⚠️ No persistent storage across cluster restarts

**Use Cases:**
- Feature development
- Integration testing
- Documentation validation
- Pre-production smoke tests

---

### 2. AWS EC2 + k3s (Recommended First Production)

**Purpose:** Cost-effective production deployment with operational simplicity.

**Why EC2 + k3s?**
- **Cost:** 10-20x cheaper than EKS for small deployments
- **Simplicity:** Single EC2 instance, no managed service overhead
- **Control:** Full control over Kubernetes configuration
- **Sufficient:** Handles 10+ targets, 100+ PRs/day easily

**Infrastructure:**

```
┌─────────────────────────────────────────────────────┐
│                    AWS Account                       │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  VPC (10.0.0.0/16)                         │    │
│  │                                             │    │
│  │  ┌──────────────────────────────────────┐  │    │
│  │  │  Public Subnet (10.0.1.0/24)         │  │    │
│  │  │                                       │  │    │
│  │  │  ┌─────────────────────────────────┐ │  │    │
│  │  │  │  EC2 Instance (t3.medium)       │ │  │    │
│  │  │  │  - k3s (single-node)            │ │  │    │
│  │  │  │  - Control Plane                │ │  │    │
│  │  │  │  - Scheduler (CronJob)          │ │  │    │
│  │  │  │  - Workers (Jobs)               │ │  │    │
│  │  │  │  - Spider Node                  │ │  │    │
│  │  │  │  - Console                      │ │  │    │
│  │  │  └─────────────────────────────────┘ │  │    │
│  │  │                                       │  │    │
│  │  └──────────────────────────────────────┘  │    │
│  │                                             │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  AWS Secrets Manager                       │    │
│  │  - GITHUB_TOKEN                            │    │
│  │  - LEVIATHAN_CONTROL_PLANE_TOKEN           │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Elastic IP (optional)                     │    │
│  │  - Stable public IP for console access     │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Recommended Instance:**
- **Type:** `t3.medium` (2 vCPU, 4 GB RAM)
- **Storage:** 30 GB gp3 EBS volume
- **OS:** Ubuntu 22.04 LTS
- **Cost:** ~$30/month (on-demand) or ~$10/month (spot)

**Deployment Steps:**

#### Step 1: Provision EC2 Instance

```bash
# Using AWS CLI (or Terraform)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxxx \
  --subnet-id subnet-xxxxxxxxx \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=leviathan-k3s}]'
```

#### Step 2: Install k3s

```bash
# SSH into EC2 instance
ssh -i your-key.pem ubuntu@<instance-public-ip>

# Install k3s (single-node, no Traefik)
curl -sfL https://get.k3s.io | sh -s - --disable traefik

# Verify installation
sudo k3s kubectl get nodes

# Copy kubeconfig for local access
sudo cat /etc/rancher/k3s/k3s.yaml
# Replace 127.0.0.1 with instance public IP, save to ~/.kube/config
```

#### Step 3: Configure Secrets

```bash
# Create secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name leviathan/github-token \
  --secret-string "ghp_your_github_token"

aws secretsmanager create-secret \
  --name leviathan/control-plane-token \
  --secret-string "$(openssl rand -hex 32)"

# Install AWS Secrets CSI Driver in k3s
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/secrets-store-csi-driver/main/deploy/rbac-secretproviderclass.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/secrets-store-csi-driver/main/deploy/csidriver.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/secrets-store-csi-driver/main/deploy/secrets-store.csi.x-k8s.io_secretproviderclasses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/secrets-store-csi-driver/main/deploy/secrets-store.csi.x-k8s.io_secretproviderclasspodstatuses.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/secrets-store-csi-driver/main/deploy/secrets-store-csi-driver.yaml

# Install AWS Secrets Provider
kubectl apply -f https://raw.githubusercontent.com/aws/secrets-store-csi-driver-provider-aws/main/deployment/aws-provider-installer.yaml
```

#### Step 4: Build and Push Images

```bash
# Build worker image
docker build -t leviathan-worker:v1.0.0 -f ops/docker/worker.Dockerfile .

# Tag for ECR (or Docker Hub)
docker tag leviathan-worker:v1.0.0 <your-registry>/leviathan-worker:v1.0.0

# Push to registry
docker push <your-registry>/leviathan-worker:v1.0.0
```

#### Step 5: Deploy Leviathan

```bash
# Update image references in ops/k8s/overlays/aws-k3s/kustomization.yaml
# (Create this overlay if it doesn't exist)

# Deploy
kubectl apply -k ops/k8s/overlays/aws-k3s

# Verify deployment
kubectl -n leviathan get pods
kubectl -n leviathan get cronjobs
kubectl -n leviathan get services
```

#### Step 6: Access Console

```bash
# Port-forward (temporary)
kubectl -n leviathan port-forward svc/leviathan-console 3000:3000

# Or configure LoadBalancer (requires MetalLB or cloud provider)
# Or use Elastic IP + nginx ingress
```

**Cost Breakdown (Monthly):**
- EC2 t3.medium (on-demand): $30.40
- EBS 30 GB gp3: $2.40
- Data transfer (minimal): $1-5
- **Total: ~$35/month**

**Spot Instance Option:**
- EC2 t3.medium (spot): ~$10/month
- Risk: Instance may be terminated with 2-minute notice
- Mitigation: Use persistent EBS volume, redeploy on new instance

---

### 3. AWS EKS (Managed Kubernetes)

**Purpose:** Production deployment with managed control plane, suitable for scale.

**When to Use EKS:**
- Managing 50+ targets
- High-volume PR creation (1000+/day)
- Multi-team usage requiring isolation
- Compliance requirements for managed services
- Need for auto-scaling and high availability

**Infrastructure:**

```
┌─────────────────────────────────────────────────────┐
│                    AWS Account                       │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  EKS Cluster                               │    │
│  │  - Managed control plane                   │    │
│  │  - Multi-AZ deployment                     │    │
│  │                                             │    │
│  │  ┌──────────────────────────────────────┐  │    │
│  │  │  Node Group (t3.medium x 2)          │  │    │
│  │  │  - Leviathan workloads               │  │    │
│  │  └──────────────────────────────────────┘  │    │
│  │                                             │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Application Load Balancer                 │    │
│  │  - Console ingress                         │    │
│  │  - Control Plane API                       │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  RDS PostgreSQL (future)                   │    │
│  │  - Event store                             │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Cost Breakdown (Monthly):**
- EKS control plane: $73
- EC2 t3.medium x 2 (nodes): $60
- ALB: $16
- EBS volumes: $10
- Data transfer: $10-20
- **Total: ~$170/month**

**Deployment:**
```bash
# Deploy via Kustomize
kubectl apply -k ops/k8s/overlays/eks

# Verify
kubectl -n leviathan get pods
```

**When to Migrate from k3s to EKS:**
- EC2 instance CPU/memory consistently >80%
- Need for multi-node cluster (high availability)
- Compliance requirements
- Team size >10 engineers

---

## Deployment Comparison

| Feature | kind (Local) | EC2 + k3s | AWS EKS |
|---------|-------------|-----------|---------|
| **Cost** | $0 | ~$35/month | ~$170/month |
| **Setup Time** | 5 minutes | 30 minutes | 1 hour |
| **Scalability** | Single node | Single node | Multi-node |
| **High Availability** | No | No | Yes (multi-AZ) |
| **Managed Control Plane** | No | No | Yes |
| **Suitable For** | Development | 1-50 targets | 50+ targets |
| **Operational Complexity** | Low | Medium | Medium-High |
| **Upgrade Path** | N/A | Manual | Managed |

---

## Upgrade Strategy

### From kind to EC2 + k3s

1. **Export Event Store**
   ```bash
   kubectl -n leviathan exec -it <control-plane-pod> -- tar czf /tmp/events.tar.gz /data/events
   kubectl cp leviathan/<control-plane-pod>:/tmp/events.tar.gz ./events.tar.gz
   ```

2. **Deploy to EC2 + k3s** (follow steps above)

3. **Import Event Store**
   ```bash
   kubectl cp ./events.tar.gz leviathan/<control-plane-pod>:/tmp/events.tar.gz
   kubectl -n leviathan exec -it <control-plane-pod> -- tar xzf /tmp/events.tar.gz -C /data
   ```

4. **Verify**
   ```bash
   curl http://<ec2-public-ip>:8000/v1/health
   ```

### From EC2 + k3s to EKS

1. **Provision EKS Cluster** (Terraform recommended)

2. **Migrate Event Store** (same as above, or use PostgreSQL)

3. **Update Image Registry** (ECR for EKS)

4. **Deploy to EKS**
   ```bash
   kubectl apply -k ops/k8s/overlays/eks
   ```

5. **Cutover DNS** (if using custom domain)

6. **Decommission EC2 Instance** (after validation)

---

## Recovery Strategy

### Backup

**What to Back Up:**
1. **Event Store** (`/data/events` in control plane pod)
2. **Kubernetes Manifests** (version-controlled in repo)
3. **Secrets** (AWS Secrets Manager)

**Backup Frequency:**
- Event store: Daily (automated via cron)
- Manifests: On every commit (Git)
- Secrets: On creation/rotation

**Backup Script:**
```bash
#!/bin/bash
# backup-leviathan.sh

BACKUP_DIR="/backups/leviathan/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Backup event store
kubectl -n leviathan exec -it <control-plane-pod> -- \
  tar czf /tmp/events-$(date +%Y%m%d).tar.gz /data/events

kubectl cp leviathan/<control-plane-pod>:/tmp/events-$(date +%Y%m%d).tar.gz \
  $BACKUP_DIR/events.tar.gz

# Upload to S3
aws s3 cp $BACKUP_DIR/events.tar.gz \
  s3://leviathan-backups/events-$(date +%Y%m%d).tar.gz
```

### Restore

**Scenario: Complete Cluster Failure**

1. **Provision New Cluster** (kind, k3s, or EKS)

2. **Restore Secrets**
   ```bash
   # Secrets are in AWS Secrets Manager (no restore needed)
   ```

3. **Deploy Leviathan**
   ```bash
   kubectl apply -k ops/k8s/overlays/<environment>
   ```

4. **Restore Event Store**
   ```bash
   # Download from S3
   aws s3 cp s3://leviathan-backups/events-latest.tar.gz ./events.tar.gz
   
   # Upload to control plane pod
   kubectl cp ./events.tar.gz leviathan/<control-plane-pod>:/tmp/events.tar.gz
   
   # Extract
   kubectl -n leviathan exec -it <control-plane-pod> -- \
     tar xzf /tmp/events.tar.gz -C /data
   ```

5. **Verify**
   ```bash
   kubectl -n leviathan get pods
   curl http://<control-plane-url>/v1/health
   ```

**RTO (Recovery Time Objective):** 30 minutes  
**RPO (Recovery Point Objective):** 24 hours (daily backups)

---

## Security Considerations

### Secrets Management

**DO:**
- ✅ Use AWS Secrets Manager for all secrets
- ✅ Rotate secrets every 90 days
- ✅ Use IAM roles for EC2 instance (no hardcoded credentials)
- ✅ Encrypt secrets at rest

**DON'T:**
- ❌ Hardcode secrets in manifests or code
- ❌ Commit secrets to Git
- ❌ Share secrets via Slack or email
- ❌ Use long-lived tokens (prefer short-lived)

### Network Security

**EC2 + k3s:**
- Restrict security group to allow only:
  - SSH (port 22) from operator IPs
  - HTTPS (port 443) from anywhere (console)
  - Kubernetes API (port 6443) from operator IPs
- Use VPC with private subnets for production

**EKS:**
- Use private subnets for node groups
- Use ALB for ingress (TLS termination)
- Enable VPC Flow Logs
- Use Security Groups for pod-level isolation

### Access Control

**Current State (v1):**
- ⚠️ No authentication on control plane or console
- ⚠️ Suitable for internal networks only

**Future (Phase 2):**
- AWS Cognito OIDC for console
- API keys for control plane
- RBAC for per-target permissions

---

## Monitoring and Alerting

### Metrics to Monitor

1. **System Health**
   - Control plane uptime
   - Scheduler execution frequency
   - Worker job success rate

2. **Performance**
   - PR creation latency
   - Event ingestion rate
   - API response times

3. **Resource Usage**
   - CPU and memory utilization
   - Disk usage (event store)
   - Network bandwidth

### Alerting Rules

**Critical:**
- Control plane down for >5 minutes
- Scheduler not running for >15 minutes
- Circuit breaker tripped

**Warning:**
- Worker job failure rate >20%
- Event store disk usage >80%
- Open PR count at max limit

### Monitoring Stack

**Recommended:**
- Prometheus (metrics collection)
- Grafana (dashboards)
- AlertManager (alerting)

**Integration:**
```bash
# Deploy Prometheus + Grafana
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/main/manifests/setup/
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/main/manifests/

# Configure ServiceMonitor for Spider Node
kubectl apply -f ops/k8s/monitoring/spider-servicemonitor.yaml
```

---

## Cost Optimization

### EC2 + k3s

1. **Use Spot Instances**
   - 70% cost savings
   - Acceptable for non-critical workloads
   - Use persistent EBS volume

2. **Right-Size Instance**
   - Start with t3.small ($15/month)
   - Scale up if CPU/memory >80%

3. **Use gp3 EBS Volumes**
   - 20% cheaper than gp2
   - Better performance

### EKS

1. **Use Fargate for Workers**
   - Pay per job execution
   - No idle node costs
   - Higher per-job cost

2. **Use Spot Node Groups**
   - 70% cost savings
   - Suitable for worker jobs (stateless)

3. **Enable Cluster Autoscaler**
   - Scale nodes based on demand
   - Reduce idle capacity

---

## Next Steps

1. **Provision EC2 Instance** (t3.medium, Ubuntu 22.04)
2. **Install k3s** (single-node, no Traefik)
3. **Configure AWS Secrets Manager** (GITHUB_TOKEN, CONTROL_PLANE_TOKEN)
4. **Build and Push Images** (to ECR or Docker Hub)
5. **Deploy Leviathan** (via Kustomize)
6. **Validate Console** (port-forward or Elastic IP)
7. **Configure Backups** (daily event store backup to S3)
8. **Set Up Monitoring** (Prometheus + Grafana)

---

## References

- [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Strategic roadmap
- [00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md) - System overview
- [01_QUICKSTART.md](01_QUICKSTART.md) - Local development quickstart
- [24_EKS_DEPLOYMENT_EVIDENCE.md](24_EKS_DEPLOYMENT_EVIDENCE.md) - EKS deployment evidence

---

**Document Status:** Living document, updated as deployment strategy evolves.
