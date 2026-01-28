"""
Unit tests for control plane autonomy mount invariants.

Tests that the invariants checker correctly validates autonomy ConfigMap mounting.
"""
import pytest
import yaml
from pathlib import Path

from tools.invariants_check import InvariantsChecker


class TestControlPlaneAutonomyInvariants:
    """Test control plane autonomy mount invariants."""
    
    def test_control_plane_has_autonomy_configmap(self):
        """Should validate that control-plane.yaml has autonomy ConfigMap."""
        repo_root = Path(__file__).parent.parent.parent
        checker = InvariantsChecker(repo_root)
        
        # Load control plane manifest
        control_plane_yaml = repo_root / "ops" / "k8s" / "control-plane.yaml"
        assert control_plane_yaml.exists(), "control-plane.yaml should exist"
        
        with open(control_plane_yaml, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        # Check ConfigMap exists
        configmap = next((d for d in docs if d.get('kind') == 'ConfigMap' and 
                         d.get('metadata', {}).get('name') == 'leviathan-autonomy-config'), None)
        
        assert configmap is not None, "ConfigMap 'leviathan-autonomy-config' should exist"
        
        # Check ConfigMap has dev.yaml
        data = configmap.get('data', {})
        assert 'dev.yaml' in data, "ConfigMap should have 'dev.yaml' key"
        
        # Check dev.yaml has autonomy_enabled
        dev_yaml_content = data['dev.yaml']
        assert 'autonomy_enabled' in dev_yaml_content, "dev.yaml should contain 'autonomy_enabled'"
    
    def test_control_plane_has_autonomy_env_var(self):
        """Should validate that control plane has LEVIATHAN_AUTONOMY_CONFIG_PATH env var."""
        repo_root = Path(__file__).parent.parent.parent
        
        control_plane_yaml = repo_root / "ops" / "k8s" / "control-plane.yaml"
        with open(control_plane_yaml, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        deployment = next((d for d in docs if d.get('kind') == 'Deployment' and
                          d.get('metadata', {}).get('name') == 'leviathan-control-plane'), None)
        
        assert deployment is not None, "Control plane Deployment should exist"
        
        containers = deployment.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
        assert len(containers) > 0, "Deployment should have containers"
        
        container = containers[0]
        env_vars = container.get('env', [])
        
        autonomy_config_path_env = next((e for e in env_vars if e.get('name') == 'LEVIATHAN_AUTONOMY_CONFIG_PATH'), None)
        
        assert autonomy_config_path_env is not None, "Should have LEVIATHAN_AUTONOMY_CONFIG_PATH env var"
        assert autonomy_config_path_env.get('value') == '/etc/leviathan/autonomy/dev.yaml', \
            "LEVIATHAN_AUTONOMY_CONFIG_PATH should point to /etc/leviathan/autonomy/dev.yaml"
    
    def test_control_plane_has_autonomy_volume_mount(self):
        """Should validate that control plane has autonomy-config volumeMount."""
        repo_root = Path(__file__).parent.parent.parent
        
        control_plane_yaml = repo_root / "ops" / "k8s" / "control-plane.yaml"
        with open(control_plane_yaml, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        deployment = next((d for d in docs if d.get('kind') == 'Deployment' and
                          d.get('metadata', {}).get('name') == 'leviathan-control-plane'), None)
        
        containers = deployment.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
        container = containers[0]
        
        volume_mounts = container.get('volumeMounts', [])
        autonomy_mount = next((vm for vm in volume_mounts if vm.get('name') == 'autonomy-config'), None)
        
        assert autonomy_mount is not None, "Should have autonomy-config volumeMount"
        assert autonomy_mount.get('mountPath') == '/etc/leviathan/autonomy', \
            "autonomy-config should mount to /etc/leviathan/autonomy"
        assert autonomy_mount.get('readOnly') is True, \
            "autonomy-config volumeMount should be readOnly"
    
    def test_control_plane_has_autonomy_volume(self):
        """Should validate that control plane has autonomy-config volume."""
        repo_root = Path(__file__).parent.parent.parent
        
        control_plane_yaml = repo_root / "ops" / "k8s" / "control-plane.yaml"
        with open(control_plane_yaml, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        deployment = next((d for d in docs if d.get('kind') == 'Deployment' and
                          d.get('metadata', {}).get('name') == 'leviathan-control-plane'), None)
        
        volumes = deployment.get('spec', {}).get('template', {}).get('spec', {}).get('volumes', [])
        autonomy_volume = next((v for v in volumes if v.get('name') == 'autonomy-config'), None)
        
        assert autonomy_volume is not None, "Should have autonomy-config volume"
        
        configmap_ref = autonomy_volume.get('configMap', {})
        assert configmap_ref.get('name') == 'leviathan-autonomy-config', \
            "autonomy-config volume should reference ConfigMap 'leviathan-autonomy-config'"
    
    def test_invariants_checker_passes(self):
        """Should pass invariants check for control plane autonomy mount."""
        repo_root = Path(__file__).parent.parent.parent
        checker = InvariantsChecker(repo_root)
        
        # Run the autonomy mount check
        checker.check_control_plane_autonomy_mount()
        
        # Should have no failures related to autonomy
        autonomy_failures = [f for f in checker.failures if 'autonomy' in f.lower()]
        assert len(autonomy_failures) == 0, f"Should have no autonomy-related failures, got: {autonomy_failures}"
