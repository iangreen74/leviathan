"""
Real Kubernetes Job executor - submits Jobs to K8s cluster.

Replaces k8s_stub for production use.
"""
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from leviathan.executors.base import Executor, AttemptResult, ArtifactRef
from leviathan.artifacts.store import ArtifactStore


class K8sExecutor(Executor):
    """
    Executor that submits Kubernetes Jobs for task attempts.
    
    Submits ephemeral Jobs that run the worker container, which:
    1. Clones target repo
    2. Executes task
    3. Posts event bundle to control plane API
    4. Exits
    """
    
    def __init__(
        self,
        namespace: str = "leviathan",
        image: str = None,
        control_plane_url: str = None,
        control_plane_token: str = None,
        artifact_store: ArtifactStore = None,
        in_cluster: bool = False
    ):
        """
        Initialize K8s executor.
        
        Args:
            namespace: K8s namespace for Jobs (default: leviathan)
            image: Worker container image (default: from env LEVIATHAN_EXECUTOR_IMAGE)
            control_plane_url: Control plane API URL
            control_plane_token: Control plane auth token
            artifact_store: Artifact store for logs
            in_cluster: Whether running inside K8s cluster
        """
        self.namespace = namespace
        self.image = image or os.getenv("LEVIATHAN_EXECUTOR_IMAGE", "leviathan-worker:local")
        self.control_plane_url = control_plane_url or os.getenv("LEVIATHAN_CONTROL_PLANE_URL", "http://leviathan-control-plane:8000")
        self.control_plane_token = control_plane_token or os.getenv("LEVIATHAN_CONTROL_PLANE_TOKEN")
        
        if artifact_store is None:
            artifact_store = ArtifactStore()
        self.artifact_store = artifact_store
        
        # Initialize K8s client
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()
        
        self.batch_api = client.BatchV1Api()
        self.core_api = client.CoreV1Api()
    
    def generate_job_spec(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate Kubernetes Job specification.
        
        Args:
            target_id: Target identifier
            task_id: Task identifier
            attempt_id: Attempt identifier
            task_spec: Task specification
            target_config: Target configuration
            
        Returns:
            K8s Job spec dict
        """
        job_name = f"leviathan-{attempt_id}"
        
        # Environment variables for worker
        env_vars = [
            {"name": "TARGET_NAME", "value": target_id},
            {"name": "TARGET_REPO_URL", "value": target_config.get("repo_url", "")},
            {"name": "TARGET_BRANCH", "value": target_config.get("default_branch", "main")},
            {"name": "TASK_ID", "value": task_id},
            {"name": "ATTEMPT_ID", "value": attempt_id},
            {"name": "CONTROL_PLANE_URL", "value": self.control_plane_url},
            {
                "name": "CONTROL_PLANE_TOKEN",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "leviathan-secrets",
                        "key": "control-plane-token"
                    }
                }
            },
            {
                "name": "GITHUB_TOKEN",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "leviathan-secrets",
                        "key": "github-token"
                    }
                }
            },
            {
                "name": "LEVIATHAN_CLAUDE_API_KEY",
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "leviathan-secrets",
                        "key": "claude-api-key"
                    }
                }
            },
            {
                "name": "LEVIATHAN_CLAUDE_MODEL",
                "value": os.getenv("LEVIATHAN_CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
            }
        ]
        
        return {
            "apiVersion": "batch/v1",
            "kind": "Job",
            "metadata": {
                "name": job_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "leviathan",
                    "target": target_id,
                    "task": task_id,
                    "attempt": attempt_id
                }
            },
            "spec": {
                "template": {
                    "metadata": {
                        "labels": {
                            "app": "leviathan",
                            "attempt": attempt_id
                        }
                    },
                    "spec": {
                        "restartPolicy": "Never",
                        "containers": [
                            {
                                "name": "worker",
                                "image": self.image,
                                "command": ["python", "-m", "leviathan.executor.worker"],
                                "env": env_vars,
                                "volumeMounts": [
                                    {
                                        "name": "workspace",
                                        "mountPath": "/workspace"
                                    }
                                ]
                            }
                        ],
                        "volumes": [
                            {
                                "name": "workspace",
                                "emptyDir": {}
                            }
                        ]
                    }
                },
                "backoffLimit": 0,
                "ttlSecondsAfterFinished": 3600
            }
        }
    
    def run_attempt(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """
        Submit K8s Job and wait for completion.
        
        Args:
            target_id: Target identifier
            task_id: Task identifier
            attempt_id: Attempt identifier
            task_spec: Task specification
            target_config: Target configuration
            
        Returns:
            AttemptResult
        """
        started_at = datetime.utcnow()
        
        # Generate job spec
        job_spec = self.generate_job_spec(
            target_id=target_id,
            task_id=task_id,
            attempt_id=attempt_id,
            task_spec=task_spec,
            target_config=target_config
        )
        
        job_name = job_spec["metadata"]["name"]
        
        try:
            # Submit job
            self.batch_api.create_namespaced_job(
                namespace=self.namespace,
                body=job_spec
            )
            
            print(f"Submitted K8s Job: {job_name}")
            
            # Wait for completion
            success, pod_name, exit_code = self._wait_for_job_completion(job_name)
            
            completed_at = datetime.utcnow()
            
            # Collect pod logs as artifact
            artifacts = []
            if pod_name:
                log_artifact = self._collect_pod_logs(pod_name, attempt_id)
                if log_artifact:
                    artifacts.append(log_artifact)
            
            if success:
                return AttemptResult(
                    success=True,
                    branch_name=f"agent/{task_id}",
                    artifacts=artifacts,
                    started_at=started_at,
                    completed_at=completed_at
                )
            else:
                return AttemptResult(
                    success=False,
                    failure_type="job_failed",
                    error_summary=f"K8s Job failed with exit code {exit_code}",
                    artifacts=artifacts,
                    started_at=started_at,
                    completed_at=completed_at
                )
        
        except ApiException as e:
            completed_at = datetime.utcnow()
            
            error_log = f"K8s API error: {e.status} {e.reason}"
            error_artifact_meta = self.artifact_store.store(
                error_log.encode('utf-8'),
                "log",
                metadata={'attempt_id': attempt_id, 'error': True}
            )
            
            return AttemptResult(
                success=False,
                failure_type="k8s_api_error",
                error_summary=error_log,
                artifacts=[
                    ArtifactRef(
                        path=error_artifact_meta['storage_path'],
                        sha256=error_artifact_meta['sha256'],
                        artifact_type='log',
                        size_bytes=error_artifact_meta['size_bytes']
                    )
                ],
                started_at=started_at,
                completed_at=completed_at
            )
    
    def _wait_for_job_completion(
        self,
        job_name: str,
        timeout: int = 3600,
        poll_interval: int = 5
    ) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Wait for Job to complete.
        
        Args:
            job_name: Job name
            timeout: Max seconds to wait
            poll_interval: Seconds between polls
            
        Returns:
            (success, pod_name, exit_code)
        """
        elapsed = 0
        pod_name = None
        
        while elapsed < timeout:
            try:
                job = self.batch_api.read_namespaced_job(
                    name=job_name,
                    namespace=self.namespace
                )
                
                # Check if job completed
                if job.status.succeeded:
                    pod_name = self._get_job_pod_name(job_name)
                    return (True, pod_name, 0)
                
                if job.status.failed:
                    pod_name = self._get_job_pod_name(job_name)
                    return (False, pod_name, 1)
                
                # Still running
                time.sleep(poll_interval)
                elapsed += poll_interval
            
            except ApiException as e:
                print(f"Error checking job status: {e}")
                return (False, None, None)
        
        # Timeout
        print(f"Job {job_name} timed out after {timeout}s")
        return (False, None, None)
    
    def _get_job_pod_name(self, job_name: str) -> Optional[str]:
        """Get pod name for job."""
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"job-name={job_name}"
            )
            
            if pods.items:
                return pods.items[0].metadata.name
        
        except ApiException as e:
            print(f"Error getting pod name: {e}")
        
        return None
    
    def _collect_pod_logs(self, pod_name: str, attempt_id: str) -> Optional[ArtifactRef]:
        """Collect pod logs as artifact."""
        try:
            logs = self.core_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace
            )
            
            # Store logs as artifact
            log_artifact_meta = self.artifact_store.store(
                logs.encode('utf-8'),
                "log",
                metadata={
                    'attempt_id': attempt_id,
                    'pod_name': pod_name
                }
            )
            
            return ArtifactRef(
                path=log_artifact_meta['storage_path'],
                sha256=log_artifact_meta['sha256'],
                artifact_type='log',
                size_bytes=log_artifact_meta['size_bytes']
            )
        
        except ApiException as e:
            print(f"Error collecting pod logs: {e}")
            return None
    
    def cleanup(self, attempt_id: str):
        """
        Clean up K8s Job.
        
        Args:
            attempt_id: Attempt identifier
        """
        job_name = f"leviathan-{attempt_id}"
        
        try:
            self.batch_api.delete_namespaced_job(
                name=job_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(propagation_policy="Foreground")
            )
            print(f"Deleted K8s Job: {job_name}")
        
        except ApiException as e:
            if e.status != 404:
                print(f"Error deleting job: {e}")
