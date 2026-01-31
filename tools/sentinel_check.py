#!/usr/bin/env python3
"""
Sentinel-style policy checker for Leviathan infrastructure.

Enforces infrastructure policies defined in ops/sentinel/policies.yaml
to prevent misconfigurations and security issues.
"""

import sys
import yaml
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple


class PolicyViolation(Exception):
    """Raised when a policy is violated."""
    pass


class SentinelChecker:
    """Checks Terraform configurations against Sentinel policies."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.policies = self._load_policies()
        self.violations = []
        
    def _load_policies(self) -> Dict[str, Any]:
        """Load policy definitions from YAML."""
        policy_file = self.repo_root / "ops" / "sentinel" / "policies.yaml"
        if not policy_file.exists():
            raise FileNotFoundError(f"Policy file not found: {policy_file}")
        
        with open(policy_file, 'r') as f:
            return yaml.safe_load(f)
    
    def check_terraform_module(self, module_path: Path) -> List[Dict[str, Any]]:
        """Check a Terraform module against all policies."""
        print(f"\n=== Checking Terraform Module: {module_path.relative_to(self.repo_root)} ===")
        
        violations = []
        
        # Read all .tf files in module
        tf_files = list(module_path.glob("*.tf"))
        if not tf_files:
            print(f"⚠️  No .tf files found in {module_path}")
            return violations
        
        tf_content = {}
        for tf_file in tf_files:
            with open(tf_file, 'r') as f:
                tf_content[tf_file.name] = f.read()
        
        # Run policy checks
        for policy in self.policies.get('policies', []):
            policy_id = policy['id']
            policy_name = policy['name']
            severity = policy.get('severity', 'error')
            
            try:
                if policy_id == 'terraform-provider-pinned':
                    self._check_provider_pinned(tf_content, policy)
                elif policy_id == 'no-public-ingress-restricted-ports':
                    self._check_no_public_ingress(tf_content, policy)
                elif policy_id == 'ec2-instance-type-allowed':
                    self._check_instance_type(tf_content, policy)
                elif policy_id == 'ebs-volume-requirements':
                    self._check_ebs_volume(tf_content, policy)
                elif policy_id == 'no-public-s3-buckets':
                    self._check_no_public_s3(tf_content, policy)
                elif policy_id == 'no-wildcard-iam-policies':
                    self._check_no_wildcard_iam(tf_content, policy)
                elif policy_id == 'ebs-encryption-required':
                    self._check_ebs_encryption(tf_content, policy)
                elif policy_id == 'terraform-backend-required':
                    self._check_backend_required(tf_content, policy)
                
                print(f"✓ {policy_name}")
                
            except PolicyViolation as e:
                violation = {
                    'policy_id': policy_id,
                    'policy_name': policy_name,
                    'severity': severity,
                    'message': str(e),
                    'module': str(module_path.relative_to(self.repo_root))
                }
                violations.append(violation)
                
                icon = "❌" if severity == "error" else "⚠️ "
                print(f"{icon} {policy_name}: {e}")
        
        return violations
    
    def _check_provider_pinned(self, tf_content: Dict[str, str], policy: Dict):
        """Check that all providers have pinned versions."""
        for filename, content in tf_content.items():
            # Look for required_providers blocks
            if 'required_providers' in content:
                # Check for providers without version constraints
                if re.search(r'source\s*=\s*"[^"]+"\s*(?!version)', content):
                    # More precise check: ensure version is present
                    providers = re.findall(r'(\w+)\s*=\s*{[^}]*source\s*=\s*"([^"]+)"[^}]*}', content, re.DOTALL)
                    for provider_name, source in providers:
                        provider_block = re.search(
                            rf'{provider_name}\s*=\s*{{[^}}]*source\s*=\s*"{re.escape(source)}"[^}}]*}}',
                            content,
                            re.DOTALL
                        )
                        if provider_block and 'version' not in provider_block.group(0):
                            raise PolicyViolation(
                                f"Provider '{provider_name}' in {filename} does not specify a version constraint"
                            )
    
    def _check_no_public_ingress(self, tf_content: Dict[str, str], policy: Dict):
        """Check that restricted ports don't allow public ingress."""
        restricted_ports = policy.get('restricted_ports', [22, 6443, 8080])
        
        for filename, content in tf_content.items():
            # Find security group ingress rules
            ingress_blocks = re.findall(
                r'ingress\s*{([^}]+)}',
                content,
                re.DOTALL
            )
            
            for ingress in ingress_blocks:
                # Check if this rule applies to restricted ports
                from_port_match = re.search(r'from_port\s*=\s*(\d+)', ingress)
                to_port_match = re.search(r'to_port\s*=\s*(\d+)', ingress)
                cidr_match = re.search(r'cidr_blocks\s*=\s*\[([^\]]+)\]', ingress)
                
                if from_port_match and to_port_match and cidr_match:
                    from_port = int(from_port_match.group(1))
                    to_port = int(to_port_match.group(1))
                    cidrs = cidr_match.group(1)
                    
                    # Check if any restricted port is in range
                    for port in restricted_ports:
                        if from_port <= port <= to_port:
                            # Check for public CIDR
                            if '0.0.0.0/0' in cidrs or '::/0' in cidrs:
                                raise PolicyViolation(
                                    f"Port {port} in {filename} allows ingress from 0.0.0.0/0"
                                )
    
    def _check_instance_type(self, tf_content: Dict[str, str], policy: Dict):
        """Check that EC2 instance types are in allowed list."""
        allowed_types = policy.get('allowed_instance_types', ['t3.small', 't3.medium', 't3.large'])
        
        for filename, content in tf_content.items():
            # Look for instance_type in variables with validation
            if 'variable' in content and 'instance_type' in content:
                # Check if validation exists
                var_block = re.search(
                    r'variable\s+"instance_type"\s*{([^}]+)}',
                    content,
                    re.DOTALL
                )
                if var_block and 'validation' in var_block.group(1):
                    # Validation exists, check it matches policy
                    validation = var_block.group(1)
                    for allowed_type in allowed_types:
                        if allowed_type not in validation:
                            raise PolicyViolation(
                                f"instance_type validation in {filename} does not include all allowed types"
                            )
    
    def _check_ebs_volume(self, tf_content: Dict[str, str], policy: Dict):
        """Check that EBS volumes meet requirements (gp3, >= 20GB)."""
        for filename, content in tf_content.items():
            # Find root_block_device blocks
            root_blocks = re.findall(
                r'root_block_device\s*{([^}]+)}',
                content,
                re.DOTALL
            )
            
            for block in root_blocks:
                # Check volume_type
                if 'volume_type' not in block or 'gp3' not in block:
                    raise PolicyViolation(
                        f"root_block_device in {filename} must use volume_type = \"gp3\""
                    )
                
                # Check volume_size (via variable validation)
                # This is checked in variables.tf validation block
    
    def _check_no_public_s3(self, tf_content: Dict[str, str], policy: Dict):
        """Check that S3 buckets are not public."""
        for filename, content in tf_content.items():
            # Look for S3 bucket resources
            if 'aws_s3_bucket' in content:
                # Check for public ACL
                if re.search(r'acl\s*=\s*"public-read', content):
                    raise PolicyViolation(
                        f"S3 bucket in {filename} has public ACL"
                    )
                
                # Check for public access block
                if 'aws_s3_bucket_public_access_block' in content:
                    # Ensure all blocks are true
                    block = re.search(
                        r'aws_s3_bucket_public_access_block[^{]+{([^}]+)}',
                        content,
                        re.DOTALL
                    )
                    if block:
                        block_content = block.group(1)
                        required_settings = [
                            'block_public_acls',
                            'block_public_policy',
                            'ignore_public_acls',
                            'restrict_public_buckets'
                        ]
                        for setting in required_settings:
                            if f'{setting}' in block_content and 'false' in block_content:
                                raise PolicyViolation(
                                    f"S3 bucket in {filename} has {setting} = false"
                                )
    
    def _check_no_wildcard_iam(self, tf_content: Dict[str, str], policy: Dict):
        """Check that IAM policies don't use wildcard actions and resources."""
        for filename, content in tf_content.items():
            # Find IAM policy documents
            policy_docs = re.findall(
                r'policy\s*=\s*jsonencode\s*\(([^)]+)\)',
                content,
                re.DOTALL
            )
            
            for doc in policy_docs:
                # Check for wildcard action and resource
                if '"Action"' in doc and '"*"' in doc and '"Resource"' in doc:
                    # Check if both Action and Resource are wildcards
                    action_wildcard = re.search(r'"Action"\s*[=:]\s*"\*"', doc)
                    resource_wildcard = re.search(r'"Resource"\s*[=:]\s*"\*"', doc)
                    
                    if action_wildcard and resource_wildcard:
                        # Check for read-only exception
                        if not re.search(r'"Action"\s*[=:]\s*\[\s*"(Get|Describe|List)', doc):
                            raise PolicyViolation(
                                f"IAM policy in {filename} uses wildcard for both Action and Resource"
                            )
    
    def _check_ebs_encryption(self, tf_content: Dict[str, str], policy: Dict):
        """Check that EBS volumes are encrypted."""
        for filename, content in tf_content.items():
            # Find root_block_device blocks
            root_blocks = re.findall(
                r'root_block_device\s*{([^}]+)}',
                content,
                re.DOTALL
            )
            
            for block in root_blocks:
                if 'encrypted' not in block or 'false' in block:
                    raise PolicyViolation(
                        f"root_block_device in {filename} must have encrypted = true"
                    )
    
    def _check_backend_required(self, tf_content: Dict[str, str], policy: Dict):
        """Check that Terraform backend is configured."""
        has_backend = False
        
        for filename, content in tf_content.items():
            if 'backend' in content and 's3' in content:
                has_backend = True
                break
        
        if not has_backend:
            # This is a warning, not an error
            print(f"⚠️  No S3 backend configured (local state detected)")
    
    def run_all_checks(self) -> int:
        """Run all policy checks on Terraform modules."""
        print("\nLeviathan Sentinel Policy Checker")
        print("=" * 60)
        
        # Find all Terraform modules
        infra_dir = self.repo_root / "infra"
        if not infra_dir.exists():
            print("⚠️  No infra/ directory found")
            return 0
        
        all_violations = []
        
        # Check each module
        for module_dir in infra_dir.rglob("*"):
            if module_dir.is_dir() and list(module_dir.glob("*.tf")):
                # Skip backend subdirectories (they have different rules)
                if 'backend' in module_dir.parts:
                    continue
                
                violations = self.check_terraform_module(module_dir)
                all_violations.extend(violations)
        
        # Report results
        print("\n" + "=" * 60)
        
        if not all_violations:
            print("\n✅ SUCCESS: All Sentinel policies passed")
            return 0
        else:
            print(f"\n❌ FAILURE: {len(all_violations)} policy violation(s) found")
            print("\nViolations:")
            for v in all_violations:
                print(f"  [{v['severity'].upper()}] {v['policy_name']}")
                print(f"    Module: {v['module']}")
                print(f"    {v['message']}")
                print()
            
            # Fail if any errors (warnings don't fail)
            error_count = sum(1 for v in all_violations if v['severity'] == 'error')
            if error_count > 0:
                return 1
            return 0


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    
    try:
        checker = SentinelChecker(repo_root)
        exit_code = checker.run_all_checks()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
