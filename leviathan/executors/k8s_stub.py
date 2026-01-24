"""
Kubernetes executor stub - generates Job specs and emits events.

Does NOT actually submit to K8s cluster (that's PR #4).
"""
from datetime import datetime
from typing import Dict, Any

from leviathan.executors.base import Executor, AttemptResult, ArtifactRef


class K8sExecutorStub(Executor):
    """
    Stub executor that generates K8s Job specs but doesn't submit them.
    
    This allows testing the scheduler without requiring a K8s cluster.
    In PR #4, this will be replaced with a real K8sExecutor that submits jobs.
    """
    
    def __init__(self):
        """Initialize K8s executor stub."""
        pass
    
    def run_attempt(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """
        Generate K8s Job spec and return simulated result.
        
        Args:
            target_id: Target identifier
            task_id: Task identifier
            attempt_id: Attempt identifier
            task_spec: Task specification
            target_config: Target configuration
            
        Returns:
            AttemptResult (simulated success)
        """
        started_at = datetime.utcnow()
        
        # Generate K8s Job spec (not submitted)
        job_spec = self._generate_job_spec(
            target_id=target_id,
            task_id=task_id,
            attempt_id=attempt_id,
            task_spec=task_spec,
            target_config=target_config
        )
        
        # In PR #4, this would submit the job and wait for completion
        # For now, just return a simulated success
        
        completed_at = datetime.utcnow()
        
        return AttemptResult(
            success=True,
            branch_name=f"leviathan/{task_id}",
            artifacts=[],
            started_at=started_at,
            completed_at=completed_at
        )
    
    def _generate_job_spec(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate Kubernetes Job specification.
        
        Returns:
            K8s Job spec dict
        """
        return {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': f'leviathan-{attempt_id}',
                'labels': {
                    'app': 'leviathan',
                    'target': target_id,
                    'task': task_id,
                    'attempt': attempt_id
                }
            },
            'spec': {
                'template': {
                    'metadata': {
                        'labels': {
                            'app': 'leviathan',
                            'attempt': attempt_id
                        }
                    },
                    'spec': {
                        'restartPolicy': 'Never',
                        'containers': [
                            {
                                'name': 'executor',
                                'image': 'leviathan-executor:latest',
                                'env': [
                                    {'name': 'TARGET_ID', 'value': target_id},
                                    {'name': 'TASK_ID', 'value': task_id},
                                    {'name': 'ATTEMPT_ID', 'value': attempt_id},
                                    {'name': 'TASK_TITLE', 'value': task_spec.get('title', '')},
                                    {'name': 'TASK_SCOPE', 'value': task_spec.get('scope', '')},
                                ],
                                'volumeMounts': [
                                    {
                                        'name': 'workspace',
                                        'mountPath': '/workspace'
                                    }
                                ]
                            }
                        ],
                        'volumes': [
                            {
                                'name': 'workspace',
                                'emptyDir': {}
                            }
                        ]
                    }
                },
                'backoffLimit': 0  # No K8s-level retries, we handle retries in scheduler
            }
        }
    
    def cleanup(self, attempt_id: str):
        """
        Clean up K8s Job (no-op for stub).
        
        Args:
            attempt_id: Attempt identifier
        """
        # In PR #4, this would delete the K8s Job
        pass
