"""
Unit tests for K8s Job spec generation.
"""
import pytest
import os

from leviathan.executors.k8s_executor import K8sExecutor


class TestK8sJobSpec:
    """Test K8s Job specification generation."""
    
    def setup_method(self):
        """Create K8s executor (without connecting to cluster)."""
        # Token is set by conftest.py - don't override it
        
        # Create executor without initializing K8s client
        self.executor = K8sExecutor.__new__(K8sExecutor)
        self.executor.namespace = "leviathan"
        self.executor.image = "leviathan-worker:test"
        self.executor.control_plane_url = "http://test-api:8000"
        self.executor.control_plane_token = "test-token"
    
    def test_job_spec_structure(self):
        """Job spec should have correct structure."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'git@github.com:test/repo.git', 'default_branch': 'main'}
        )
        
        assert spec['apiVersion'] == 'batch/v1'
        assert spec['kind'] == 'Job'
        assert spec['metadata']['name'] == 'leviathan-attempt-abc123'
        assert spec['metadata']['namespace'] == 'leviathan'
    
    def test_job_spec_labels(self):
        """Job spec should include correct labels."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'git@github.com:test/repo.git'}
        )
        
        labels = spec['metadata']['labels']
        assert labels['app'] == 'leviathan'
        assert labels['target'] == 'test-target'
        assert labels['task'] == 'task-001'
        assert labels['attempt'] == 'attempt-abc123'
    
    def test_job_spec_env_vars(self):
        """Job spec should include required environment variables."""
        spec = self.executor.generate_job_spec(
            target_id="radix",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={
                'repo_url': 'git@github.com:test/radix.git',
                'default_branch': 'develop'
            }
        )
        
        container = spec['spec']['template']['spec']['containers'][0]
        env_vars = {env['name']: env for env in container['env']}
        
        # Check plain env vars
        assert env_vars['TARGET_NAME']['value'] == 'radix'
        assert env_vars['TARGET_REPO_URL']['value'] == 'git@github.com:test/radix.git'
        assert env_vars['TARGET_BRANCH']['value'] == 'develop'
        assert env_vars['TASK_ID']['value'] == 'task-001'
        assert env_vars['ATTEMPT_ID']['value'] == 'attempt-abc123'
        assert env_vars['CONTROL_PLANE_URL']['value'] == 'http://test-api:8000'
        
        # Check secret refs
        assert 'valueFrom' in env_vars['CONTROL_PLANE_TOKEN']
        assert env_vars['CONTROL_PLANE_TOKEN']['valueFrom']['secretKeyRef']['name'] == 'leviathan-secrets'
        assert env_vars['CONTROL_PLANE_TOKEN']['valueFrom']['secretKeyRef']['key'] == 'control-plane-token'
        
        assert 'valueFrom' in env_vars['GITHUB_TOKEN']
        assert env_vars['GITHUB_TOKEN']['valueFrom']['secretKeyRef']['key'] == 'github-token'
        
        assert 'valueFrom' in env_vars['LEVIATHAN_CLAUDE_API_KEY']
        assert env_vars['LEVIATHAN_CLAUDE_API_KEY']['valueFrom']['secretKeyRef']['key'] == 'claude-api-key'
    
    def test_job_spec_container_config(self):
        """Job spec should have correct container configuration."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        container = spec['spec']['template']['spec']['containers'][0]
        
        assert container['name'] == 'worker'
        assert container['image'] == 'leviathan-worker:test'
        assert container['command'] == ['python', '-m', 'leviathan.executor.worker']
        
        # Check volume mounts
        volume_mounts = container['volumeMounts']
        assert len(volume_mounts) == 1
        assert volume_mounts[0]['name'] == 'workspace'
        assert volume_mounts[0]['mountPath'] == '/workspace'
    
    def test_job_spec_restart_policy(self):
        """Job spec should have correct restart policy."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        assert spec['spec']['template']['spec']['restartPolicy'] == 'Never'
        assert spec['spec']['backoffLimit'] == 0
        assert spec['spec']['ttlSecondsAfterFinished'] == 3600
    
    def test_job_spec_volumes(self):
        """Job spec should define workspace volume."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        volumes = spec['spec']['template']['spec']['volumes']
        assert len(volumes) == 1
        assert volumes[0]['name'] == 'workspace'
        assert 'emptyDir' in volumes[0]
    
    def test_job_name_from_attempt_id(self):
        """Job name should be derived from attempt ID."""
        spec1 = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        spec2 = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-xyz789",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        assert spec1['metadata']['name'] == 'leviathan-attempt-abc123'
        assert spec2['metadata']['name'] == 'leviathan-attempt-xyz789'
    
    def test_job_spec_default_branch(self):
        """Job spec should use default branch if not specified."""
        spec = self.executor.generate_job_spec(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}  # No default_branch
        )
        
        container = spec['spec']['template']['spec']['containers'][0]
        env_vars = {env['name']: env for env in container['env']}
        
        assert env_vars['TARGET_BRANCH']['value'] == 'main'
