# Leviathan k3s EC2 Infrastructure

Terraform module for provisioning AWS EC2 infrastructure for Leviathan k3s deployment.

## Overview

This module creates:
- EC2 instance (Ubuntu 22.04) with t3.medium default
- Security group with restricted ingress (SSH, k8s API, console)
- IAM role with Secrets Manager read access
- Optional Elastic IP
- 30GB gp3 root volume (encrypted)

## Prerequisites

1. AWS account with appropriate permissions
2. VPC and subnet already created
3. SSH key pair created in AWS
4. Terraform backend bootstrapped (see `backend/README.md`)

## Usage

### 1. Configure Variables

Copy the example tfvars file:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your values:

```hcl
aws_region     = "us-west-2"
environment    = "dev"
vpc_id         = "vpc-xxxxxxxxxxxxxxxxx"
subnet_id      = "subnet-xxxxxxxxxxxxxxxxx"
operator_cidrs = ["YOUR.IP.ADDRESS/32"]
ssh_key_name   = "your-ssh-key-name"
```

### 2. Plan via GitHub Actions

Push changes to a PR. The `infra-leviathan-k3s-plan` workflow will automatically run:
- `terraform fmt`
- `terraform validate`
- `terraform plan`
- Upload plan artifact and evidence

### 3. Apply via GitHub Actions

After PR is merged to main:
1. Go to Actions tab
2. Select `infra-leviathan-k3s-apply` workflow
3. Click "Run workflow"
4. Approve in GitHub Environment (if configured)

### 4. Access Instance

After apply completes, get instance IP from outputs:

```bash
ssh ubuntu@<instance-ip>
```

## Security

### Ingress Rules

All ingress is restricted to `operator_cidrs`:
- Port 22 (SSH)
- Port 6443 (Kubernetes API)
- Port 8080 (Leviathan Console)

### IAM Permissions

Instance has read-only access to specific Secrets Manager secrets:
- `leviathan/github-token`
- `leviathan/control-plane-token`

### Encryption

- Root volume: Encrypted with AWS-managed keys
- Terraform state: Encrypted in S3

## Cost Estimate

Monthly cost for default configuration (us-west-2):
- EC2 t3.medium (on-demand): ~$30.40
- EBS 30GB gp3: ~$2.40
- Data transfer: ~$1-5
- **Total: ~$35/month**

## Sentinel Policies

This module is subject to Sentinel policy checks:
- Provider versions must be pinned
- No 0.0.0.0/0 ingress on restricted ports
- Instance type must be in allowed list
- Root volume must be gp3 >= 20GB
- No public S3 buckets
- No wildcard IAM policies

See `ops/sentinel/policies.yaml` for full policy definitions.

## Outputs

- `instance_id` - EC2 instance ID
- `instance_private_ip` - Private IP address
- `instance_public_ip` - Public IP address
- `elastic_ip` - Elastic IP (if enabled)
- `security_group_id` - Security group ID
- `iam_role_arn` - IAM role ARN
- `ssh_command` - SSH command to connect

## Next Steps

After infrastructure is provisioned:
1. SSH into instance
2. Install k3s (see Phase 2 documentation)
3. Deploy Leviathan components

## Rollback

To destroy infrastructure:

```bash
# Manual rollback (not automated in workflows)
cd infra/leviathan_k3s_ec2
terraform destroy
```

**WARNING:** This will delete the EC2 instance and all associated resources. Ensure you have backups of any data.

## Troubleshooting

### Plan fails with "backend not configured"

Run backend bootstrap workflow first (see `backend/README.md`).

### Apply fails with "UnauthorizedOperation"

Ensure AWS credentials have necessary permissions. See IAM policy in documentation.

### Instance not accessible

Check:
1. Security group allows your IP (`operator_cidrs`)
2. Instance is in public subnet (or use bastion)
3. SSH key is correct
