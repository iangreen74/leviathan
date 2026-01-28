"""
Unit tests for K8s Job runtime invariants.

Tests namespace and imagePullPolicy enforcement.
"""
import pytest
import tempfile
import yaml
from pathlib import Path

from tools.invariants_check import InvariantsChecker


class TestK8sJobInvariants:
    """Test K8s Job runtime invariants."""
    
    def test_job_with_leviathan_namespace_passes(self):
        """Job with namespace: leviathan should pass."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            jobs_dir = ops_dir / "k8s" / "jobs"
            jobs_dir.mkdir(parents=True)
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create valid job
            job_yaml = {
                'apiVersion': 'batch/v1',
                'kind': 'Job',
                'metadata': {
                    'name': 'test-job',
                    'namespace': 'leviathan'
                },
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [{
                                'name': 'worker',
                                'image': 'leviathan-worker:local',
                                'imagePullPolicy': 'IfNotPresent'
                            }]
                        }
                    }
                }
            }
            
            job_file = jobs_dir / "test-job.yaml"
            with open(job_file, 'w') as f:
                yaml.dump(job_yaml, f)
            
            # Check should pass
            checker = InvariantsChecker(repo_root)
            checker.check_k8s_packaging()
            
            assert len(checker.failures) == 0
    
    def test_job_with_default_namespace_fails(self):
        """Job with namespace: default should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            jobs_dir = ops_dir / "k8s" / "jobs"
            jobs_dir.mkdir(parents=True)
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create invalid job with default namespace
            job_yaml = {
                'apiVersion': 'batch/v1',
                'kind': 'Job',
                'metadata': {
                    'name': 'test-job',
                    'namespace': 'default'
                },
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [{
                                'name': 'worker',
                                'image': 'leviathan-worker:local',
                                'imagePullPolicy': 'IfNotPresent'
                            }]
                        }
                    }
                }
            }
            
            job_file = jobs_dir / "test-job.yaml"
            with open(job_file, 'w') as f:
                yaml.dump(job_yaml, f)
            
            # Check should fail
            checker = InvariantsChecker(repo_root)
            checker.check_k8s_packaging()
            
            assert len(checker.failures) > 0
            assert any('default' in failure for failure in checker.failures)
    
    def test_job_missing_namespace_fails(self):
        """Job without namespace should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            jobs_dir = ops_dir / "k8s" / "jobs"
            jobs_dir.mkdir(parents=True)
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create job without namespace
            job_yaml = {
                'apiVersion': 'batch/v1',
                'kind': 'Job',
                'metadata': {
                    'name': 'test-job'
                },
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [{
                                'name': 'worker',
                                'image': 'leviathan-worker:local',
                                'imagePullPolicy': 'IfNotPresent'
                            }]
                        }
                    }
                }
            }
            
            job_file = jobs_dir / "test-job.yaml"
            with open(job_file, 'w') as f:
                yaml.dump(job_yaml, f)
            
            # Check should fail
            checker = InvariantsChecker(repo_root)
            checker.check_k8s_packaging()
            
            assert len(checker.failures) > 0
            assert any('missing namespace' in failure for failure in checker.failures)
    
    def test_local_image_without_ifnotpresent_fails(self):
        """Local image without IfNotPresent should fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            
            # Create minimal structure
            ops_dir = repo_root / "ops"
            ops_dir.mkdir()
            jobs_dir = ops_dir / "k8s" / "jobs"
            jobs_dir.mkdir(parents=True)
            
            # Create invariants.yaml (minimal)
            (ops_dir / "invariants.yaml").write_text("kubernetes: {}\n")
            
            # Create job with local image but wrong pull policy
            job_yaml = {
                'apiVersion': 'batch/v1',
                'kind': 'Job',
                'metadata': {
                    'name': 'test-job',
                    'namespace': 'leviathan'
                },
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [{
                                'name': 'worker',
                                'image': 'leviathan-worker:local',
                                'imagePullPolicy': 'Always'
                            }]
                        }
                    }
                }
            }
            
            job_file = jobs_dir / "test-job.yaml"
            with open(job_file, 'w') as f:
                yaml.dump(job_yaml, f)
            
            # Check should fail
            checker = InvariantsChecker(repo_root)
            checker.check_k8s_packaging()
            
            assert len(checker.failures) > 0
            assert any('IfNotPresent' in failure for failure in checker.failures)
    
    def test_pr_proof_v1_yaml_passes(self):
        """Actual pr-proof-v1.yaml should pass all checks."""
        # This test uses the real repo structure
        repo_root = Path(__file__).parent.parent.parent
        
        checker = InvariantsChecker(repo_root)
        checker.check_k8s_packaging()
        
        # Should have no failures
        assert len(checker.failures) == 0
