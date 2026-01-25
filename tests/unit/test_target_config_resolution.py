"""
Unit tests for target config resolution.
"""
import pytest
import yaml
from pathlib import Path
from leviathan.control_plane.__main__ import resolve_target_config


class TestTargetConfigResolution:
    """Test target configuration resolution."""
    
    def test_resolve_relative_paths_under_cache_dir(self, tmp_path):
        """Should resolve relative paths under local_cache_dir."""
        # Create target config with relative paths
        target_file = tmp_path / "test-target.yaml"
        cache_dir = tmp_path / "cache"
        
        config_data = {
            'name': 'test-target',
            'repo_url': 'git@github.com:test/repo.git',
            'default_branch': 'main',
            'local_cache_dir': str(cache_dir),
            'backlog_path': '.leviathan/backlog.yaml',
            'contract_path': '.leviathan/contract.yaml',
            'policy_path': '.leviathan/policy.yaml'
        }
        
        with open(target_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Resolve config
        config = resolve_target_config(str(target_file))
        
        # Check that paths are absolute and under cache_dir
        assert Path(config['backlog_path']).is_absolute()
        assert Path(config['contract_path']).is_absolute()
        assert Path(config['policy_path']).is_absolute()
        
        assert config['backlog_path'] == str(cache_dir / '.leviathan' / 'backlog.yaml')
        assert config['contract_path'] == str(cache_dir / '.leviathan' / 'contract.yaml')
        assert config['policy_path'] == str(cache_dir / '.leviathan' / 'policy.yaml')
    
    def test_preserve_absolute_paths(self, tmp_path):
        """Should preserve absolute paths (backward compatibility)."""
        # Create target config with absolute paths
        target_file = tmp_path / "test-target.yaml"
        cache_dir = tmp_path / "cache"
        absolute_backlog = tmp_path / "custom" / "backlog.yaml"
        
        config_data = {
            'name': 'test-target',
            'repo_url': 'git@github.com:test/repo.git',
            'default_branch': 'main',
            'local_cache_dir': str(cache_dir),
            'backlog_path': str(absolute_backlog),
            'contract_path': '.leviathan/contract.yaml',
            'policy_path': '.leviathan/policy.yaml'
        }
        
        with open(target_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Resolve config
        config = resolve_target_config(str(target_file))
        
        # Check that absolute path is preserved
        assert config['backlog_path'] == str(absolute_backlog)
        
        # Check that relative paths are still resolved
        assert config['contract_path'] == str(cache_dir / '.leviathan' / 'contract.yaml')
        assert config['policy_path'] == str(cache_dir / '.leviathan' / 'policy.yaml')
    
    def test_default_paths_when_missing(self, tmp_path):
        """Should set default paths when not specified."""
        # Create target config without path fields
        target_file = tmp_path / "test-target.yaml"
        cache_dir = tmp_path / "cache"
        
        config_data = {
            'name': 'test-target',
            'repo_url': 'git@github.com:test/repo.git',
            'default_branch': 'main',
            'local_cache_dir': str(cache_dir)
        }
        
        with open(target_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Resolve config
        config = resolve_target_config(str(target_file))
        
        # Check that default paths are set
        assert config['backlog_path'] == str(cache_dir / '.leviathan' / 'backlog.yaml')
        assert config['contract_path'] == str(cache_dir / '.leviathan' / 'contract.yaml')
        assert config['policy_path'] == str(cache_dir / '.leviathan' / 'policy.yaml')
    
    def test_expand_tilde_in_cache_dir(self, tmp_path):
        """Should expand ~ in local_cache_dir."""
        # Create target config with ~ in cache_dir
        target_file = tmp_path / "test-target.yaml"
        
        config_data = {
            'name': 'test-target',
            'repo_url': 'git@github.com:test/repo.git',
            'default_branch': 'main',
            'local_cache_dir': '~/.leviathan/targets/test-target',
            'backlog_path': '.leviathan/backlog.yaml'
        }
        
        with open(target_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Resolve config
        config = resolve_target_config(str(target_file))
        
        # Check that ~ is expanded
        assert '~' not in config['local_cache_dir']
        assert Path(config['local_cache_dir']).is_absolute()
        
        # Check that backlog_path is resolved under expanded cache_dir
        assert '~' not in config['backlog_path']
        assert Path(config['backlog_path']).is_absolute()
        assert config['backlog_path'].startswith(config['local_cache_dir'])
    
    def test_resolve_by_name(self, tmp_path, monkeypatch):
        """Should resolve target by name from ~/.leviathan/targets/."""
        # Create ~/.leviathan/targets directory structure
        leviathan_dir = tmp_path / ".leviathan" / "targets"
        leviathan_dir.mkdir(parents=True)
        
        target_file = leviathan_dir / "myapp.yaml"
        cache_dir = tmp_path / "cache" / "myapp"
        
        config_data = {
            'name': 'myapp',
            'repo_url': 'git@github.com:test/myapp.git',
            'default_branch': 'main',
            'local_cache_dir': str(cache_dir),
            'backlog_path': '.leviathan/backlog.yaml'
        }
        
        with open(target_file, 'w') as f:
            yaml.dump(config_data, f)
        
        # Mock Path.home() to return tmp_path
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        
        # Resolve by name
        config = resolve_target_config('myapp')
        
        # Check that config is loaded correctly
        assert config['name'] == 'myapp'
        assert config['backlog_path'] == str(cache_dir / '.leviathan' / 'backlog.yaml')
    
    def test_error_when_target_not_found(self, tmp_path, monkeypatch):
        """Should raise FileNotFoundError when target doesn't exist."""
        # Mock Path.home() to return tmp_path
        monkeypatch.setattr(Path, 'home', lambda: tmp_path)
        
        # Try to resolve non-existent target
        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_target_config('nonexistent')
        
        assert 'Target config not found' in str(exc_info.value)
