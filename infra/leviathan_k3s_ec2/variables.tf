variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-west-2"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_id" {
  description = "VPC ID where resources will be created"
  type        = string
}

variable "subnet_id" {
  description = "Subnet ID for EC2 instance"
  type        = string
}

variable "operator_cidrs" {
  description = "CIDR blocks allowed to access SSH, k8s API, and console"
  type        = list(string)
  validation {
    condition     = length(var.operator_cidrs) > 0 && alltrue([for cidr in var.operator_cidrs : can(cidrhost(cidr, 0))])
    error_message = "operator_cidrs must be a non-empty list of valid CIDR blocks"
  }
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.medium"
  validation {
    condition     = contains(["t3.small", "t3.medium", "t3.large"], var.instance_type)
    error_message = "instance_type must be one of: t3.small, t3.medium, t3.large"
  }
}

variable "root_volume_size_gb" {
  description = "Root volume size in GB"
  type        = number
  default     = 30
  validation {
    condition     = var.root_volume_size_gb >= 20
    error_message = "root_volume_size_gb must be at least 20 GB"
  }
}

variable "ssh_key_name" {
  description = "SSH key pair name for EC2 instance access"
  type        = string
}

variable "enable_elastic_ip" {
  description = "Whether to allocate and associate an Elastic IP"
  type        = bool
  default     = false
}
