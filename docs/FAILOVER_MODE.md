# Failover Mode v1: Cold Standby for Leviathan

## Overview

Failover Mode enables **cold standby** disaster recovery: if the local Leviathan node crashes, deploy a new instance on AWS (or any cloud) and it will reconstruct state from durable storage and continue operations.

## Architecture

**Event Sourcing = Disaster Recovery**

Leviathan's event-sourced architecture makes failover straightforward:
- **Event journal** (Postgres) is the source of truth
- **Artifacts** (S3) are content-addressed and immutable
- **Graph** is a projection that can be rebuilt deterministically from events

```
┌─────────────────┐
│  Local Primary  │
│   Leviathan     │
│                 │
│  writes to:     │
│  - RDS Postgres │──┐
│  - S3 Artifacts │  │
└─────────────────┘  │
                     │
     (crash)         │ Durable state
                     │ persists
                     │
┌─────────────────┐  │
│  AWS Standby    │  │
│   Leviathan     │  │
│                 │  │
│  reads from:    │  │
│  - RDS Postgres │◄─┘
│  - S3 Artifacts │◄─┘
│                 │
│  rebuilds graph │
│  from events    │
└─────────────────┘
```

## Durable State Components

### 1. Event Journal (Postgres RDS)

**Purpose**: Append-only event log (source of truth)

**Schema**: Auto-initialized on first connection
- Table: `events`
- Append-only enforced by triggers
- Hash chain for integrity verification

**Configuration**:
```bash
LEVIATHAN_CONTROL_PLANE_BACKEND=postgres
LEVIATHAN_POSTGRES_URL=postgresql://user:pass@rds-endpoint:5432/leviathan
```

### 2. Artifact Store (S3)

**Purpose**: Content-addressed artifact storage

**Structure**: 
```
s3://bucket/artifacts/
  ab/abc123...  (sharded by first 2 chars of SHA256)
  cd/cdef45...
```

**Configuration**:
```bash
LEVIATHAN_ARTIFACT_BACKEND=s3
LEVIATHAN_ARTIFACT_S3_BUCKET=leviathan-artifacts
LEVIATHAN_ARTIFACT_S3_PREFIX=artifacts  # optional
```

### 3. Graph Projection (Ephemeral)

**Purpose**: Query-optimized view of event journal

**Rebuild**: Deterministic replay of events
- Cleared on startup if `LEVIATHAN_REBUILD_ON_START=1`
- Replays all events in chronological order
- Projects events into graph nodes/edges
- Verifies hash chain integrity

## Failover Scenarios

### Scenario 1: Local Node Crash

**Before crash** (local primary):
```bash
# Local Leviathan writing to AWS services
LEVIATHAN_CONTROL_PLANE_BACKEND=postgres
LEVIATHAN_POSTGRES_URL=postgresql://user:pass@rds.us-east-1.amazonaws.com:5432/leviathan
LEVIATHAN_ARTIFACT_BACKEND=s3
LEVIATHAN_ARTIFACT_S3_BUCKET=leviathan-prod-artifacts
```

**After crash** (AWS standby):
```bash
# Launch EC2 instance with same config + rebuild flag
LEVIATHAN_CONTROL_PLANE_BACKEND=postgres
LEVIATHAN_POSTGRES_URL=postgresql://user:pass@rds.us-east-1.amazonaws.com:5432/leviathan
LEVIATHAN_ARTIFACT_BACKEND=s3
LEVIATHAN_ARTIFACT_S3_BUCKET=leviathan-prod-artifacts
LEVIATHAN_REBUILD_ON_START=1  # Rebuild graph from events

# Start control plane
python3 -m leviathan.control_plane.api
```

**Result**: 
- Graph rebuilt from event journal
- All historical state recovered
- Operations resume from last event

### Scenario 2: Planned Migration

**Step 1**: Local writes to AWS services (already configured)

**Step 2**: Launch AWS standby (read-only verification)
```bash
LEVIATHAN_REBUILD_ON_START=1
python3 -m leviathan.control_plane.api
# Verify graph summary matches local
```

**Step 3**: Shutdown local, promote AWS standby
```bash
# Remove read-only restrictions
# Start accepting writes
```

## Configuration Reference

### Environment Variables

#### Control Plane Backend
```bash
# Event journal backend
LEVIATHAN_CONTROL_PLANE_BACKEND=postgres  # or ndjson (local only)
LEVIATHAN_POSTGRES_URL=postgresql://user:pass@host:5432/dbname

# Rebuild graph on startup (failover mode)
LEVIATHAN_REBUILD_ON_START=1  # 0=disabled (default), 1=enabled
```

#### Artifact Storage
```bash
# Artifact backend
LEVIATHAN_ARTIFACT_BACKEND=s3  # or file (local only)

# S3 configuration (required for s3 backend)
LEVIATHAN_ARTIFACT_S3_BUCKET=my-bucket
LEVIATHAN_ARTIFACT_S3_PREFIX=artifacts  # optional, default: artifacts

# AWS credentials (use IAM role or env vars)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
```

#### Authentication
```bash
LEVIATHAN_CONTROL_PLANE_TOKEN=your-secure-token
```

## AWS Deployment Guide

### Prerequisites

1. **RDS Postgres** instance
   - Engine: PostgreSQL 14+
   - Instance: db.t3.micro (dev) or db.t3.medium (prod)
   - Storage: 20GB+ (events grow ~1KB per event)
   - Backup: Automated daily snapshots
   - Multi-AZ: Recommended for production

2. **S3 Bucket** for artifacts
   - Versioning: Enabled (recommended)
   - Lifecycle: Transition to Glacier after 90 days (optional)
   - Encryption: AES-256 or KMS

3. **EC2 Instance** for control plane
   - Instance: t3.medium (2 vCPU, 4GB RAM)
   - OS: Ubuntu 22.04 LTS
   - IAM Role: S3 read/write, RDS connect
   - Security Group: Port 8000 (API), 22 (SSH)

### Step-by-Step Deployment

#### 1. Create RDS Instance

```bash
# Via AWS CLI
aws rds create-db-instance \
  --db-instance-identifier leviathan-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --master-username leviathan \
  --master-user-password <secure-password> \
  --allocated-storage 20 \
  --backup-retention-period 7 \
  --publicly-accessible false \
  --vpc-security-group-ids sg-xxxxx

# Get endpoint
aws rds describe-db-instances \
  --db-instance-identifier leviathan-db \
  --query 'DBInstances[0].Endpoint.Address'
```

#### 2. Create S3 Bucket

```bash
aws s3 mb s3://leviathan-prod-artifacts --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket leviathan-prod-artifacts \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket leviathan-prod-artifacts \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

#### 3. Launch EC2 Instance

```bash
# Create IAM role with S3 and RDS permissions
aws iam create-role \
  --role-name leviathan-control-plane \
  --assume-role-policy-document file://trust-policy.json

# Attach policies
aws iam attach-role-policy \
  --role-name leviathan-control-plane \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess

aws iam attach-role-policy \
  --role-name leviathan-control-plane \
  --policy-arn arn:aws:iam::aws:policy/AmazonRDSFullAccess

# Launch instance
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --iam-instance-profile Name=leviathan-control-plane \
  --key-name my-key \
  --security-group-ids sg-xxxxx \
  --user-data file://install-leviathan.sh
```

#### 4. Install Leviathan on EC2

SSH into instance:
```bash
ssh -i my-key.pem ubuntu@<ec2-public-ip>
```

Install dependencies:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install -y python3.10 python3-pip git

# Clone Leviathan
git clone https://github.com/iangreen74/leviathan.git
cd leviathan

# Install dependencies
pip3 install -r requirements.txt
pip3 install boto3 psycopg2-binary  # For S3 and Postgres
```

#### 5. Configure Environment

Create `/etc/leviathan/env`:
```bash
# Control plane
LEVIATHAN_CONTROL_PLANE_TOKEN=<secure-token>
LEVIATHAN_CONTROL_PLANE_BACKEND=postgres
LEVIATHAN_POSTGRES_URL=postgresql://leviathan:<password>@<rds-endpoint>:5432/leviathan

# Artifacts
LEVIATHAN_ARTIFACT_BACKEND=s3
LEVIATHAN_ARTIFACT_S3_BUCKET=leviathan-prod-artifacts
LEVIATHAN_ARTIFACT_S3_PREFIX=artifacts

# Failover mode (rebuild on start)
LEVIATHAN_REBUILD_ON_START=1

# AWS region
AWS_REGION=us-east-1
```

#### 6. Start Control Plane

```bash
# Load environment
source /etc/leviathan/env

# Start control plane
python3 -m leviathan.control_plane.api

# Or use systemd (see ops/systemd/leviathan.service)
sudo systemctl start leviathan-control-plane
```

#### 7. Verify Failover

```bash
# Check logs for rebuild
# Should see:
# === REBUILD ON START ENABLED ===
# Rebuilding graph from event journal...
# Replaying N events...
# ✓ Graph rebuilt: N events projected
# ✓ Event chain integrity verified

# Query API
curl -H "Authorization: Bearer $LEVIATHAN_CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/graph/summary

# Compare with local instance (should match)
```

## Local Development with Failover

Test failover locally using Docker Compose:

```yaml
# docker-compose-failover.yml
version: '3.8'
services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: leviathan
      POSTGRES_USER: leviathan
      POSTGRES_PASSWORD: dev-password
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
  
  localstack:
    image: localstack/localstack
    environment:
      SERVICES: s3
      DEFAULT_REGION: us-east-1
    ports:
      - "4566:4566"
  
  control-plane:
    build: .
    environment:
      LEVIATHAN_CONTROL_PLANE_TOKEN: test-token
      LEVIATHAN_CONTROL_PLANE_BACKEND: postgres
      LEVIATHAN_POSTGRES_URL: postgresql://leviathan:dev-password@postgres:5432/leviathan
      LEVIATHAN_ARTIFACT_BACKEND: s3
      LEVIATHAN_ARTIFACT_S3_BUCKET: leviathan-dev
      AWS_ENDPOINT_URL: http://localstack:4566
      LEVIATHAN_REBUILD_ON_START: 1
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - localstack

volumes:
  postgres-data:
```

Test failover:
```bash
# Start services
docker-compose -f docker-compose-failover.yml up -d

# Create S3 bucket
aws --endpoint-url=http://localhost:4566 s3 mb s3://leviathan-dev

# Generate events (run some tasks)
# ...

# Simulate crash: stop control plane
docker-compose -f docker-compose-failover.yml stop control-plane

# Restart with rebuild
docker-compose -f docker-compose-failover.yml up control-plane

# Verify graph rebuilt from events
```

## Operational Procedures

### Monitoring Failover Readiness

Check that durable state is being written:

```bash
# Verify Postgres events
psql $LEVIATHAN_POSTGRES_URL -c "SELECT COUNT(*) FROM events;"

# Verify S3 artifacts
aws s3 ls s3://leviathan-prod-artifacts/artifacts/ --recursive | wc -l

# Verify hash chain integrity
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/v1/graph/verify-chain
```

### Testing Failover

Periodically test failover to ensure it works:

```bash
# 1. Launch standby instance
# 2. Set LEVIATHAN_REBUILD_ON_START=1
# 3. Start control plane
# 4. Verify graph summary matches primary
# 5. Shutdown standby
```

### Recovery Time Objective (RTO)

Expected recovery times:
- **Event replay**: ~100 events/second = 10,000 events in ~100 seconds
- **EC2 launch**: 2-5 minutes
- **Total RTO**: 5-10 minutes for typical workloads

### Recovery Point Objective (RPO)

- **RPO**: Near-zero (events written synchronously to Postgres)
- **Data loss**: Only in-flight events not yet committed

## Limitations (v1)

**What Failover Mode v1 provides**:
✅ Durable event journal (Postgres)  
✅ Durable artifact storage (S3)  
✅ Deterministic graph rebuild  
✅ Cold standby failover  
✅ Manual failover process  

**What Failover Mode v1 does NOT provide**:
❌ Hot standby (active-active)  
❌ Automatic failover detection  
❌ Load balancing across instances  
❌ Real-time replication  
❌ Sub-second RTO  

## Future Enhancements (v2+)

Planned improvements:
- **Hot standby**: Active-active control plane with leader election
- **Automatic failover**: Health checks + DNS failover
- **Read replicas**: Scale read queries across multiple instances
- **Event streaming**: Kafka/Kinesis for real-time event distribution
- **Multi-region**: Cross-region replication for disaster recovery

## Security Considerations

1. **Postgres**: Use SSL/TLS connections, rotate passwords regularly
2. **S3**: Enable bucket encryption, use IAM roles (not access keys)
3. **Tokens**: Rotate `LEVIATHAN_CONTROL_PLANE_TOKEN` regularly
4. **Network**: Use VPC, private subnets, security groups
5. **Backups**: Enable RDS automated backups, S3 versioning

## Troubleshooting

### Graph rebuild fails

**Symptom**: Rebuild errors during startup

**Diagnosis**:
```bash
# Check event count
psql $LEVIATHAN_POSTGRES_URL -c "SELECT COUNT(*) FROM events;"

# Check for corrupted events
psql $LEVIATHAN_POSTGRES_URL -c "SELECT * FROM events WHERE payload IS NULL;"

# Verify hash chain
curl http://localhost:8000/v1/graph/verify-chain
```

**Solution**: Fix corrupted events or restore from backup

### S3 artifacts not accessible

**Symptom**: Worker fails to upload artifacts

**Diagnosis**:
```bash
# Test S3 access
aws s3 ls s3://leviathan-prod-artifacts/

# Check IAM permissions
aws sts get-caller-identity
```

**Solution**: Fix IAM role or credentials

### Postgres connection timeout

**Symptom**: Control plane fails to connect to RDS

**Diagnosis**:
```bash
# Test connection
psql $LEVIATHAN_POSTGRES_URL -c "SELECT 1;"

# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

**Solution**: Update security group to allow EC2 → RDS traffic

## Related Documentation

- [Leviathan Architecture](LEVIATHAN_CANONICAL.md)
- [Event Sourcing](HOW_LEVIATHAN_OPERATES.md)
- [Invariants Gate](INVARIANTS.md)
- [Deployment Guide](DEPLOY_CONTROL_PLANE.md)
