"""
Target configuration loader for Leviathan.

Handles loading and parsing target YAML configs that specify external repos to work on.
"""
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class TargetConfig:
    """Represents a target repository configuration."""
    name: str
    repo_url: str
    default_branch: str
    local_cache_dir: Path
    contract_path: str
    backlog_path: str
    policy_path: str
    
    @classmethod
    def from_yaml(cls, yaml_path: Path) -> 'TargetConfig':
        """
        Load target configuration from YAML file.
        
        Args:
            yaml_path: Path to target YAML config file
            
        Returns:
            TargetConfig instance
            
        Raises:
            FileNotFoundError: If YAML file doesn't exist
            ValueError: If required fields are missing
        """
        if not yaml_path.exists():
            raise FileNotFoundError(f"Target config not found: {yaml_path}")
        
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Validate required fields
        required_fields = [
            'name', 'repo_url', 'default_branch', 'local_cache_dir',
            'contract_path', 'backlog_path', 'policy_path'
        ]
        
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields in {yaml_path}: {', '.join(missing_fields)}")
        
        # Expand ~ in local_cache_dir
        cache_dir = Path(data['local_cache_dir']).expanduser()
        
        return cls(
            name=data['name'],
            repo_url=data['repo_url'],
            default_branch=data['default_branch'],
            local_cache_dir=cache_dir,
            contract_path=data['contract_path'],
            backlog_path=data['backlog_path'],
            policy_path=data['policy_path']
        )
    
    def get_backlog_full_path(self) -> Path:
        """Get full path to backlog file within target repo."""
        return self.local_cache_dir / self.backlog_path
    
    def get_contract_full_path(self) -> Path:
        """Get full path to contract file within target repo."""
        return self.local_cache_dir / self.contract_path
    
    def get_policy_full_path(self) -> Path:
        """Get full path to policy file within target repo."""
        return self.local_cache_dir / self.policy_path
