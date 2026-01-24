"""
Unit tests for target configuration resolution.
"""
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

from leviathan.control_plane.__main__ import resolve_target_config


class TestTargetResolution:
    """Test target configuration resolution from name or path."""
    
    def setup_method(self):
        """Create temporary directory for test configs."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.targets_dir = self.temp_dir / ".leviathan" / "targets"
        self.targets_dir.mkdir(parents=True)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_resolve_by_name(self):
        """Should resolve target name to ~/.leviathan/targets/<name>.yaml"""
        # Create target config
        config_file = self.targets_dir / "test-target.yaml"
        config_data = {
            'name': 'test-target',
            'repo_url': 'git@github.com:org/test-target.git',
            'default_branch': 'main',
            'local_cache_dir': '~/.leviathan/targets/test-target'
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Mock Path.home() to return temp_dir
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            config = resolve_target_config('test-target')
        
        assert config['name'] == 'test-target'
        assert config['repo_url'] == 'git@github.com:org/test-target.git'
        assert 'backlog_path' in config
        assert '.leviathan/backlog.yaml' in config['backlog_path']
    
    def test_resolve_by_explicit_path(self):
        """Should load config from explicit file path."""
        # Create target config at explicit path
        config_file = self.temp_dir / "my-target.yaml"
        config_data = {
            'name': 'my-target',
            'repo_url': 'git@github.com:org/my-target.git'
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = resolve_target_config(str(config_file))
        
        assert config['name'] == 'my-target'
        assert config['repo_url'] == 'git@github.com:org/my-target.git'
    
    def test_missing_target_raises_clear_error(self):
        """Should raise FileNotFoundError with helpful message for missing target."""
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            with pytest.raises(FileNotFoundError) as exc_info:
                resolve_target_config('nonexistent-target')
        
        error_msg = str(exc_info.value)
        assert 'Target config not found' in error_msg
        assert 'nonexistent-target.yaml' in error_msg
        assert 'To create a target config' in error_msg
    
    def test_sets_contract_backlog_policy_paths(self):
        """Should set contract/backlog/policy paths relative to cache dir."""
        config_file = self.targets_dir / "leviathan.yaml"
        cache_dir = self.temp_dir / "targets" / "leviathan"
        config_data = {
            'name': 'leviathan',
            'repo_url': 'git@github.com:iangreen74/leviathan.git',
            'local_cache_dir': str(cache_dir)
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            config = resolve_target_config('leviathan')
        
        assert 'contract_path' in config
        assert 'backlog_path' in config
        assert 'policy_path' in config
        assert config['contract_path'] == str(cache_dir / ".leviathan" / "contract.yaml")
        assert config['backlog_path'] == str(cache_dir / ".leviathan" / "backlog.yaml")
        assert config['policy_path'] == str(cache_dir / ".leviathan" / "policy.yaml")
    
    def test_expands_tilde_in_cache_dir(self):
        """Should expand ~ in local_cache_dir."""
        config_file = self.targets_dir / "test.yaml"
        config_data = {
            'name': 'test',
            'repo_url': 'git@github.com:org/test.git',
            'local_cache_dir': '~/.leviathan/targets/test'
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            config = resolve_target_config('test')
        
        # Should expand ~ (will use real home directory)
        assert '~' not in config['local_cache_dir']
        assert config['local_cache_dir'].endswith('.leviathan/targets/test')
    
    def test_invalid_yaml_raises_error(self):
        """Should raise ValueError for invalid YAML config."""
        config_file = self.targets_dir / "bad.yaml"
        # Write a YAML list instead of dict
        with open(config_file, 'w') as f:
            f.write("- item1\n- item2\n")
        
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            with pytest.raises(ValueError) as exc_info:
                resolve_target_config('bad')
        
        assert 'Invalid target config' in str(exc_info.value)
        assert 'must be a YAML dict' in str(exc_info.value)
    
    def test_adds_name_if_missing(self):
        """Should add name field if not present in config."""
        config_file = self.targets_dir / "unnamed.yaml"
        config_data = {
            'repo_url': 'git@github.com:org/unnamed.git'
        }
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        with patch('pathlib.Path.home', return_value=self.temp_dir):
            config = resolve_target_config('unnamed')
        
        assert config['name'] == 'unnamed'
