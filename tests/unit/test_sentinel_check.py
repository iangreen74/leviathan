"""
Unit tests for Sentinel policy checker.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from tools.sentinel_check import SentinelChecker, PolicyViolation


@pytest.fixture
def temp_repo():
    """Create a temporary repository structure for testing."""
    temp_dir = tempfile.mkdtemp()
    repo_path = Path(temp_dir)
    
    # Create ops/sentinel directory
    sentinel_dir = repo_path / "ops" / "sentinel"
    sentinel_dir.mkdir(parents=True)
    
    # Create minimal policies.yaml
    policies_content = """
policies:
  - id: terraform-provider-pinned
    name: Terraform providers must be pinned
    severity: error
    scope: terraform
  
  - id: no-public-ingress-restricted-ports
    name: No 0.0.0.0/0 ingress on restricted ports
    severity: error
    scope: terraform
    restricted_ports: [22, 6443, 8080]
  
  - id: ebs-encryption-required
    name: EBS volumes must be encrypted
    severity: error
    scope: terraform
"""
    
    with open(sentinel_dir / "policies.yaml", 'w') as f:
        f.write(policies_content)
    
    # Create infra directory
    infra_dir = repo_path / "infra" / "test_module"
    infra_dir.mkdir(parents=True)
    
    yield repo_path
    
    # Cleanup
    shutil.rmtree(temp_dir)


def test_sentinel_checker_initialization(temp_repo):
    """Test that SentinelChecker initializes correctly."""
    checker = SentinelChecker(temp_repo)
    assert checker.repo_root == temp_repo
    assert 'policies' in checker.policies
    assert len(checker.policies['policies']) == 3


def test_provider_pinned_valid(temp_repo):
    """Test that valid provider pinning passes."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    # Create valid Terraform file with pinned provider
    tf_content = """
terraform {
  required_version = ">= 1.5.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have no violations
    assert len(violations) == 0


def test_no_public_ingress_valid(temp_repo):
    """Test that restricted ingress rules pass when using specific CIDRs."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    tf_content = """
resource "aws_security_group" "test" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have no violations
    assert len(violations) == 0


def test_no_public_ingress_violation(temp_repo):
    """Test that public ingress on restricted ports is caught."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    tf_content = """
resource "aws_security_group" "test" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have violation
    assert len(violations) == 1
    assert violations[0]['policy_id'] == 'no-public-ingress-restricted-ports'
    assert violations[0]['severity'] == 'error'


def test_ebs_encryption_valid(temp_repo):
    """Test that encrypted EBS volumes pass."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    tf_content = """
resource "aws_instance" "test" {
  root_block_device {
    volume_type = "gp3"
    volume_size = 30
    encrypted   = true
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have no violations
    assert len(violations) == 0


def test_ebs_encryption_violation(temp_repo):
    """Test that unencrypted EBS volumes are caught."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    tf_content = """
resource "aws_instance" "test" {
  root_block_device {
    volume_type = "gp3"
    volume_size = 30
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have violation
    assert len(violations) == 1
    assert violations[0]['policy_id'] == 'ebs-encryption-required'


def test_multiple_violations(temp_repo):
    """Test that multiple violations are all caught."""
    infra_dir = temp_repo / "infra" / "test_module"
    
    tf_content = """
resource "aws_security_group" "test" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "test" {
  root_block_device {
    volume_type = "gp3"
    volume_size = 30
  }
}
"""
    
    with open(infra_dir / "main.tf", 'w') as f:
        f.write(tf_content)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have 2 violations
    assert len(violations) == 2
    policy_ids = [v['policy_id'] for v in violations]
    assert 'no-public-ingress-restricted-ports' in policy_ids
    assert 'ebs-encryption-required' in policy_ids


def test_empty_module(temp_repo):
    """Test that empty modules don't cause errors."""
    infra_dir = temp_repo / "infra" / "empty_module"
    infra_dir.mkdir(parents=True)
    
    checker = SentinelChecker(temp_repo)
    violations = checker.check_terraform_module(infra_dir)
    
    # Should have no violations (and no errors)
    assert len(violations) == 0


def test_run_all_checks(temp_repo):
    """Test that run_all_checks processes all modules."""
    # Create two modules
    module1 = temp_repo / "infra" / "module1"
    module2 = temp_repo / "infra" / "module2"
    module1.mkdir(parents=True)
    module2.mkdir(parents=True)
    
    # Module1: valid
    with open(module1 / "main.tf", 'w') as f:
        f.write("""
resource "aws_instance" "test" {
  root_block_device {
    encrypted = true
  }
}
""")
    
    # Module2: violation
    with open(module2 / "main.tf", 'w') as f:
        f.write("""
resource "aws_security_group" "test" {
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
""")
    
    checker = SentinelChecker(temp_repo)
    exit_code = checker.run_all_checks()
    
    # Should fail due to violation in module2
    assert exit_code == 1
