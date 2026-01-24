"""
Unit tests for K8s executor with mocked Kubernetes client.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from leviathan.executors.k8s_executor import K8sExecutor
from leviathan.executors.base import AttemptResult
from leviathan.artifacts.store import ArtifactStore


class TestK8sExecutorMock:
    """Test K8s executor with mocked Kubernetes client."""
    
    @patch('leviathan.executors.k8s_executor.config')
    @patch('leviathan.executors.k8s_executor.client')
    def test_run_attempt_success(self, mock_client, mock_config):
        """Should submit job and return success result."""
        # Mock K8s client
        mock_batch_api = Mock()
        mock_core_api = Mock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        mock_client.CoreV1Api.return_value = mock_core_api
        
        # Mock job status (succeeded)
        mock_job = Mock()
        mock_job.status.succeeded = 1
        mock_job.status.failed = None
        mock_batch_api.read_namespaced_job.return_value = mock_job
        
        # Mock pod listing
        mock_pod = Mock()
        mock_pod.metadata.name = "test-pod"
        mock_pods = Mock()
        mock_pods.items = [mock_pod]
        mock_core_api.list_namespaced_pod.return_value = mock_pods
        
        # Mock pod logs
        mock_core_api.read_namespaced_pod_log.return_value = "Test logs"
        
        # Create executor
        executor = K8sExecutor(namespace="test-ns", image="test-image:latest")
        
        # Run attempt
        result = executor.run_attempt(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        # Verify job was created
        assert mock_batch_api.create_namespaced_job.called
        call_args = mock_batch_api.create_namespaced_job.call_args
        assert call_args[1]['namespace'] == 'test-ns'
        
        # Verify result
        assert result.success is True
        assert result.branch_name == 'agent/task-001'
        assert len(result.artifacts) > 0
    
    @patch('leviathan.executors.k8s_executor.config')
    @patch('leviathan.executors.k8s_executor.client')
    def test_run_attempt_failure(self, mock_client, mock_config):
        """Should handle job failure."""
        # Mock K8s client
        mock_batch_api = Mock()
        mock_core_api = Mock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        mock_client.CoreV1Api.return_value = mock_core_api
        
        # Mock job status (failed)
        mock_job = Mock()
        mock_job.status.succeeded = None
        mock_job.status.failed = 1
        mock_batch_api.read_namespaced_job.return_value = mock_job
        
        # Mock pod listing
        mock_pod = Mock()
        mock_pod.metadata.name = "test-pod"
        mock_pods = Mock()
        mock_pods.items = [mock_pod]
        mock_core_api.list_namespaced_pod.return_value = mock_pods
        
        # Mock pod logs
        mock_core_api.read_namespaced_pod_log.return_value = "Error logs"
        
        # Create executor
        executor = K8sExecutor(namespace="test-ns")
        
        # Run attempt
        result = executor.run_attempt(
            target_id="test-target",
            task_id="task-001",
            attempt_id="attempt-abc123",
            task_spec={'title': 'Test task'},
            target_config={'repo_url': 'test'}
        )
        
        # Verify result
        assert result.success is False
        assert result.failure_type == 'job_failed'
    
    @patch('leviathan.executors.k8s_executor.config')
    @patch('leviathan.executors.k8s_executor.client')
    def test_cleanup_deletes_job(self, mock_client, mock_config):
        """Cleanup should delete K8s job."""
        # Mock K8s client
        mock_batch_api = Mock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        mock_client.CoreV1Api.return_value = Mock()
        
        # Create executor
        executor = K8sExecutor(namespace="test-ns")
        
        # Cleanup
        executor.cleanup("attempt-abc123")
        
        # Verify delete was called
        assert mock_batch_api.delete_namespaced_job.called
        call_args = mock_batch_api.delete_namespaced_job.call_args
        assert call_args[1]['name'] == 'leviathan-attempt-abc123'
        assert call_args[1]['namespace'] == 'test-ns'
    
    @patch('leviathan.executors.k8s_executor.config')
    @patch('leviathan.executors.k8s_executor.client')
    @patch('leviathan.executors.k8s_executor.time.sleep')
    def test_wait_for_job_polls_status(self, mock_sleep, mock_client, mock_config):
        """Should poll job status until completion."""
        # Mock K8s client
        mock_batch_api = Mock()
        mock_core_api = Mock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        mock_client.CoreV1Api.return_value = mock_core_api
        
        # Mock job status progression (running -> succeeded)
        mock_job_running = Mock()
        mock_job_running.status.succeeded = None
        mock_job_running.status.failed = None
        
        mock_job_succeeded = Mock()
        mock_job_succeeded.status.succeeded = 1
        mock_job_succeeded.status.failed = None
        
        mock_batch_api.read_namespaced_job.side_effect = [
            mock_job_running,
            mock_job_succeeded
        ]
        
        # Mock pod listing
        mock_pod = Mock()
        mock_pod.metadata.name = "test-pod"
        mock_pods = Mock()
        mock_pods.items = [mock_pod]
        mock_core_api.list_namespaced_pod.return_value = mock_pods
        
        # Create executor
        executor = K8sExecutor(namespace="test-ns")
        
        # Wait for completion
        success, pod_name, exit_code = executor._wait_for_job_completion(
            "test-job",
            timeout=30,
            poll_interval=1
        )
        
        # Verify polling occurred
        assert mock_batch_api.read_namespaced_job.call_count == 2
        assert success is True
        assert exit_code == 0
    
    @patch('leviathan.executors.k8s_executor.config')
    @patch('leviathan.executors.k8s_executor.client')
    def test_collect_pod_logs(self, mock_client, mock_config):
        """Should collect pod logs as artifact."""
        # Mock K8s client
        mock_batch_api = Mock()
        mock_core_api = Mock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        mock_client.CoreV1Api.return_value = mock_core_api
        
        # Mock pod logs
        test_logs = "Test log output\nLine 2\nLine 3"
        mock_core_api.read_namespaced_pod_log.return_value = test_logs
        
        # Create executor
        executor = K8sExecutor(namespace="test-ns")
        
        # Collect logs
        artifact = executor._collect_pod_logs("test-pod", "attempt-abc123")
        
        # Verify artifact
        assert artifact is not None
        assert artifact.artifact_type == 'log'
        assert artifact.size_bytes > 0
        
        # Verify API was called
        assert mock_core_api.read_namespaced_pod_log.called
        call_args = mock_core_api.read_namespaced_pod_log.call_args
        assert call_args[1]['name'] == 'test-pod'
        assert call_args[1]['namespace'] == 'test-ns'
