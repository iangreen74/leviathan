# Terraform Backend Configuration

This directory contains backend configuration for Terraform state management using S3 + DynamoDB locking.

## Bootstrap Backend (One-Time Setup)

The backend infrastructure (S3 bucket + DynamoDB table) is created via GitHub Actions workflow.

### Required GitHub Secrets

Set these in your repository settings under `Settings > Secrets and variables > Actions`:

1. **AWS_ACCOUNT_ID** - Your AWS account ID (12 digits)
2. **AWS_REGION** - AWS region (default: us-west-2)
3. **AWS_ACCESS_KEY_ID** - AWS access key for Terraform (or use OIDC)
4. **AWS_SECRET_ACCESS_KEY** - AWS secret key for Terraform (or use OIDC)

### Bootstrap via GitHub Actions

1. Trigger the `infra-bootstrap-backend` workflow manually from Actions tab
2. Workflow creates:
   - S3 bucket: `leviathan-terraform-state-<account-id>-<region>`
   - DynamoDB table: `leviathan-terraform-locks`
3. Backend config is automatically generated

### Backend Configuration

After bootstrap, Terraform uses this backend config:

```hcl
terraform {
  backend "s3" {
    bucket         = "leviathan-terraform-state-<account-id>-<region>"
    key            = "leviathan-k3s-ec2/terraform.tfstate"
    region         = "<region>"
    dynamodb_table = "leviathan-terraform-locks"
    encrypt        = true
  }
}
```

## Manual Bootstrap (Alternative)

If you prefer to bootstrap manually:

```bash
cd infra/leviathan_k3s_ec2/backend
terraform init
terraform apply -var="aws_account_id=123456789012" -var="aws_region=us-west-2"
```

Then configure backend in main module:

```bash
cd ../
terraform init \
  -backend-config="bucket=leviathan-terraform-state-123456789012-us-west-2" \
  -backend-config="key=leviathan-k3s-ec2/terraform.tfstate" \
  -backend-config="region=us-west-2" \
  -backend-config="dynamodb_table=leviathan-terraform-locks" \
  -backend-config="encrypt=true"
```

## State Locking

DynamoDB table provides state locking to prevent concurrent modifications.

## Encryption

- S3 bucket uses AES256 encryption
- Terraform state is encrypted at rest
- DynamoDB table uses AWS-managed encryption
