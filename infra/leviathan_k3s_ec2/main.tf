terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Backend configuration provided via backend config file or CLI
    # See backend/README.md for setup instructions
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "leviathan"
      ManagedBy = "terraform"
    }
  }
}

# Data source for latest Ubuntu 22.04 AMI
data "aws_ami" "ubuntu_22_04" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security group for k3s instance
resource "aws_security_group" "leviathan_k3s" {
  name_prefix = "leviathan-k3s-${var.environment}-"
  description = "Security group for Leviathan k3s instance"
  vpc_id      = var.vpc_id

  # SSH access from operator CIDR
  ingress {
    description = "SSH from operator"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.operator_cidrs
  }

  # Kubernetes API access from operator CIDR
  ingress {
    description = "Kubernetes API from operator"
    from_port   = 6443
    to_port     = 6443
    protocol    = "tcp"
    cidr_blocks = var.operator_cidrs
  }

  # Console access from operator CIDR
  ingress {
    description = "Leviathan Console from operator"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = var.operator_cidrs
  }

  # Allow all outbound traffic
  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "leviathan-k3s-${var.environment}"
    Environment = var.environment
  }

  lifecycle {
    create_before_destroy = true
  }
}

# IAM role for EC2 instance
resource "aws_iam_role" "leviathan_k3s" {
  name_prefix = "leviathan-k3s-${var.environment}-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "leviathan-k3s-${var.environment}"
    Environment = var.environment
  }
}

# IAM policy for Secrets Manager access
resource "aws_iam_role_policy" "secrets_manager_read" {
  name_prefix = "secrets-manager-read-"
  role        = aws_iam_role.leviathan_k3s.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:leviathan/github-token-*",
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:leviathan/control-plane-token-*"
        ]
      }
    ]
  })
}

# IAM instance profile
resource "aws_iam_instance_profile" "leviathan_k3s" {
  name_prefix = "leviathan-k3s-${var.environment}-"
  role        = aws_iam_role.leviathan_k3s.name

  tags = {
    Name        = "leviathan-k3s-${var.environment}"
    Environment = var.environment
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# EC2 instance
resource "aws_instance" "leviathan_k3s" {
  ami                    = data.aws_ami.ubuntu_22_04.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [aws_security_group.leviathan_k3s.id]
  iam_instance_profile   = aws_iam_instance_profile.leviathan_k3s.name
  key_name               = var.ssh_key_name

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_size_gb
    delete_on_termination = true
    encrypted             = true

    tags = {
      Name        = "leviathan-k3s-${var.environment}-root"
      Environment = var.environment
    }
  }

  user_data = templatefile("${path.module}/user_data.sh", {
    hostname = "leviathan-k3s-${var.environment}"
  })

  tags = {
    Name        = "leviathan-k3s-${var.environment}"
    Environment = var.environment
  }

  lifecycle {
    ignore_changes = [
      ami, # Prevent replacement on AMI updates
    ]
  }
}

# Optional Elastic IP
resource "aws_eip" "leviathan_k3s" {
  count    = var.enable_elastic_ip ? 1 : 0
  instance = aws_instance.leviathan_k3s.id
  domain   = "vpc"

  tags = {
    Name        = "leviathan-k3s-${var.environment}"
    Environment = var.environment
  }
}
