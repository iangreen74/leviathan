#!/usr/bin/env python3
"""
Leviathan Invariants Gate - Prevents Configuration Drift

Validates that repository configuration files match canonical invariants
defined in ops/invariants.yaml. This prevents drift and repeated failures.

Usage:
    python3 tools/invariants_check.py

Exit codes:
    0 - All invariants validated successfully
    1 - One or more invariants failed validation
"""
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Tuple


class InvariantsChecker:
    """Validates repository files against canonical invariants."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.invariants = self._load_invariants()
        self.failures: List[str] = []
    
    def _load_invariants(self) -> Dict[str, Any]:
        """Load invariants from ops/invariants.yaml."""
        invariants_path = self.repo_root / "ops" / "invariants.yaml"
        
        if not invariants_path.exists():
            print(f"ERROR: Invariants file not found: {invariants_path}")
            sys.exit(1)
        
        with open(invariants_path, 'r') as f:
            return yaml.safe_load(f)
    
    def fail(self, message: str):
        """Record a validation failure."""
        self.failures.append(message)
        print(f"FAIL: {message}")
    
    def check_k8s_control_plane(self):
        """Validate control plane Kubernetes manifests."""
        print("\n=== Checking Control Plane K8s Manifests ===")
        
        k8s_dir = self.repo_root / "ops" / "k8s"
        control_plane_yaml = k8s_dir / "control-plane.yaml"
        
        if not control_plane_yaml.exists():
            self.fail(f"Control plane manifest not found: {control_plane_yaml}")
            return
        
        with open(control_plane_yaml, 'r') as f:
            docs = list(yaml.safe_load_all(f))
        
        cp_inv = self.invariants['kubernetes']['control_plane']
        
        # Check Deployment
        deployment = next((d for d in docs if d.get('kind') == 'Deployment'), None)
        if deployment:
            # Check container name and image
            containers = deployment.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
            if containers:
                container = containers[0]
                
                if container.get('name') != cp_inv['container_name']:
                    self.fail(f"Control plane container name must be '{cp_inv['container_name']}', got '{container.get('name')}'")
                
                image = container.get('image', '')
                if not image.startswith(cp_inv['image_name']):
                    self.fail(f"Control plane image must start with '{cp_inv['image_name']}', got '{image}'")
                
                # Check for forbidden :latest tag
                if ':latest' in image:
                    self.fail(f"Control plane image uses forbidden ':latest' tag: {image}")
            
            # Check labels
            labels = deployment.get('metadata', {}).get('labels', {})
            if labels.get('app') != cp_inv['labels']['app']:
                self.fail(f"Control plane deployment label 'app' must be '{cp_inv['labels']['app']}', got '{labels.get('app')}'")
            
            # Check selector
            selector = deployment.get('spec', {}).get('selector', {}).get('matchLabels', {})
            if selector.get('app') != cp_inv['selectors']['app']:
                self.fail(f"Control plane selector 'app' must be '{cp_inv['selectors']['app']}', got '{selector.get('app')}'")
        else:
            self.fail("Control plane Deployment not found in manifest")
        
        # Check Service
        service = next((d for d in docs if d.get('kind') == 'Service'), None)
        if service:
            if service.get('metadata', {}).get('name') != cp_inv['service_name']:
                self.fail(f"Control plane service name must be '{cp_inv['service_name']}', got '{service.get('metadata', {}).get('name')}'")
            
            ports = service.get('spec', {}).get('ports', [])
            if ports and ports[0].get('port') != cp_inv['port']:
                self.fail(f"Control plane service port must be {cp_inv['port']}, got {ports[0].get('port')}")
            
            selector = service.get('spec', {}).get('selector', {})
            if selector.get('app') != cp_inv['selectors']['app']:
                self.fail(f"Control plane service selector 'app' must be '{cp_inv['selectors']['app']}', got '{selector.get('app')}'")
        else:
            self.fail("Control plane Service not found in manifest")
        
        if not self.failures:
            print("✓ Control plane manifests valid")
    
    def check_k8s_worker_job(self):
        """Validate worker job template."""
        print("\n=== Checking Worker Job Template ===")
        
        job_template = self.repo_root / "ops" / "k8s" / "job-template.yaml"
        
        if not job_template.exists():
            self.fail(f"Worker job template not found: {job_template}")
            return
        
        with open(job_template, 'r') as f:
            job = yaml.safe_load(f)
        
        worker_inv = self.invariants['kubernetes']['worker']
        secrets_inv = self.invariants['secrets']['worker']
        
        # Check container name and image
        containers = job.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
        if containers:
            container = containers[0]
            
            if container.get('name') != worker_inv['container_name']:
                self.fail(f"Worker container name must be '{worker_inv['container_name']}', got '{container.get('name')}'")
            
            image = container.get('image', '')
            if not image.startswith(worker_inv['image_name']):
                self.fail(f"Worker image must start with '{worker_inv['image_name']}', got '{image}'")
            
            # Check for forbidden :latest tag
            if ':latest' in image:
                self.fail(f"Worker image uses forbidden ':latest' tag: {image}")
            
            # Check required environment variables
            env_vars = {e.get('name'): e for e in container.get('env', [])}
            for required_var in secrets_inv['required_env_vars']:
                if required_var not in env_vars:
                    self.fail(f"Worker job template missing required env var: {required_var}")
        else:
            self.fail("Worker container not found in job template")
        
        # Check job labels
        labels = job.get('metadata', {}).get('labels', {})
        if labels.get('app') != worker_inv['job_labels']['app']:
            self.fail(f"Worker job label 'app' must be '{worker_inv['job_labels']['app']}', got '{labels.get('app')}'")
        
        if not self.failures:
            print("✓ Worker job template valid")
    
    def check_ci_workflows(self):
        """Validate GitHub Actions workflows."""
        print("\n=== Checking CI Workflows ===")
        
        workflows_dir = self.repo_root / ".github" / "workflows"
        
        if not workflows_dir.exists():
            self.fail(f"Workflows directory not found: {workflows_dir}")
            return
        
        ci_inv = self.invariants['ci']
        
        # Check main CI workflow
        ci_yaml = workflows_dir / "ci.yml"
        if ci_yaml.exists():
            with open(ci_yaml, 'r') as f:
                ci_workflow = yaml.safe_load(f)
            
            # Check for invariants_check step
            jobs = ci_workflow.get('jobs', {})
            has_invariants_check = False
            has_pytest = False
            
            for job_name, job_config in jobs.items():
                steps = job_config.get('steps', [])
                for step in steps:
                    run_cmd = step.get('run', '')
                    
                    if 'invariants_check' in run_cmd or 'tools/invariants_check.py' in run_cmd:
                        has_invariants_check = True
                    
                    if 'pytest' in run_cmd:
                        has_pytest = True
            
            if not has_invariants_check:
                self.fail("CI workflow must run invariants_check.py")
            
            if not has_pytest:
                self.fail("CI workflow must run pytest")
        else:
            self.fail(f"CI workflow not found: {ci_yaml}")
        
        # Check all workflows for :latest tag usage
        for workflow_file in workflows_dir.glob("*.yml"):
            with open(workflow_file, 'r') as f:
                content = f.read()
                if ':latest' in content and 'image:' in content:
                    # Check if it's actually an image reference
                    for line in content.split('\n'):
                        if 'image:' in line and ':latest' in line:
                            self.fail(f"Workflow {workflow_file.name} contains forbidden ':latest' image tag: {line.strip()}")
        
        if not self.failures:
            print("✓ CI workflows valid")
    
    def check_requirements(self):
        """Validate requirements files contain necessary dependencies."""
        print("\n=== Checking Requirements ===")
        
        req_dev = self.repo_root / "requirements-dev.txt"
        
        if not req_dev.exists():
            self.fail(f"requirements-dev.txt not found: {req_dev}")
            return
        
        with open(req_dev, 'r') as f:
            requirements = f.read().lower()
        
        ci_inv = self.invariants['ci']
        for dep in ci_inv['required_dependencies']:
            if dep.lower() not in requirements:
                self.fail(f"requirements-dev.txt missing required dependency: {dep}")
        
        if not self.failures:
            print("✓ Requirements valid")
    
    def check_namespace_consistency(self):
        """Validate namespace is consistent across all K8s manifests."""
        print("\n=== Checking Namespace Consistency ===")
        
        k8s_dir = self.repo_root / "ops" / "k8s"
        expected_namespace = self.invariants['kubernetes']['namespace']
        
        for yaml_file in k8s_dir.glob("*.yaml"):
            with open(yaml_file, 'r') as f:
                try:
                    docs = list(yaml.safe_load_all(f))
                    for doc in docs:
                        if doc and isinstance(doc, dict):
                            namespace = doc.get('metadata', {}).get('namespace')
                            if namespace and namespace != expected_namespace:
                                self.fail(f"{yaml_file.name}: namespace must be '{expected_namespace}', got '{namespace}'")
                except yaml.YAMLError as e:
                    self.fail(f"Failed to parse {yaml_file.name}: {e}")
        
        if not self.failures:
            print("✓ Namespace consistency valid")
    
    def check_topology_artifacts(self):
        """Validate topology artifact names are defined."""
        print("\n=== Checking Topology Artifacts ===")
        
        topo_inv = self.invariants.get('topology', {})
        artifact_names = topo_inv.get('artifact_names', [])
        
        # Check that artifact names are referenced in topology indexer
        indexer_file = self.repo_root / "leviathan" / "topology" / "indexer.py"
        
        if not indexer_file.exists():
            self.fail("Topology indexer not found: leviathan/topology/indexer.py")
            return
        
        with open(indexer_file, 'r') as f:
            content = f.read()
        
        for artifact_name in artifact_names:
            if artifact_name not in content:
                self.fail(f"Topology artifact '{artifact_name}' not found in indexer code")
        
        if not self.failures:
            print("✓ Topology artifacts valid")
    
    def check_topology_api_endpoints(self):
        """Validate topology API endpoints exist."""
        print("\n=== Checking Topology API Endpoints ===")
        
        topo_inv = self.invariants.get('topology', {})
        endpoints = topo_inv.get('api_endpoints', [])
        
        # Check that endpoints are defined in control plane API
        api_file = self.repo_root / "leviathan" / "control_plane" / "api.py"
        
        if not api_file.exists():
            self.fail("Control plane API not found: leviathan/control_plane/api.py")
            return
        
        with open(api_file, 'r') as f:
            content = f.read()
        
        for endpoint in endpoints:
            # Check for @app.get decorator with endpoint path
            if f'@app.get("{endpoint}"' not in content:
                self.fail(f"Topology API endpoint '{endpoint}' not found in control plane")
        
        if not self.failures:
            print("✓ Topology API endpoints valid")
    
    def check_failover_documentation(self):
        """Validate failover documentation exists."""
        print("\n=== Checking Failover Documentation ===")
        
        failover_inv = self.invariants.get('failover', {})
        docs = failover_inv.get('documentation', [])
        
        for doc_path in docs:
            doc_file = self.repo_root / doc_path
            if not doc_file.exists():
                self.fail(f"Failover documentation not found: {doc_path}")
        
        if not self.failures:
            print("✓ Failover documentation valid")
    
    def check_failover_backends(self):
        """Validate failover backend implementations exist."""
        print("\n=== Checking Failover Backends ===")
        
        failover_inv = self.invariants.get('failover', {})
        backends = failover_inv.get('backends', {})
        
        # Check artifact store backends
        artifact_backends = backends.get('artifact_store', [])
        artifact_store_file = self.repo_root / "leviathan" / "artifacts" / "store.py"
        
        if artifact_store_file.exists():
            with open(artifact_store_file, 'r') as f:
                content = f.read()
            
            for backend in artifact_backends:
                if backend == 'file':
                    if 'class FileBackend' not in content:
                        self.fail(f"FileBackend not found in artifact store")
                elif backend == 's3':
                    if 'class S3Backend' not in content:
                        self.fail(f"S3Backend not found in artifact store")
        else:
            self.fail("Artifact store file not found")
        
        # Check event store backends
        event_backends = backends.get('event_store', [])
        events_file = self.repo_root / "leviathan" / "graph" / "events.py"
        
        if events_file.exists():
            with open(events_file, 'r') as f:
                content = f.read()
            
            for backend in event_backends:
                if backend == 'ndjson':
                    if '_append_ndjson' not in content:
                        self.fail(f"NDJSON backend not found in event store")
                elif backend == 'postgres':
                    if '_append_postgres' not in content:
                        self.fail(f"Postgres backend not found in event store")
        else:
            self.fail("Event store file not found")
        
        if not self.failures:
            print("✓ Failover backends valid")
    
    def check_k8s_packaging(self):
        """Validate K8s manifests don't reference non-packaged scripts."""
        print("\n=== Checking K8s Packaging Invariants ===")
        
        k8s_dir = self.repo_root / "ops" / "k8s"
        
        # Find all YAML files in k8s directory
        yaml_files = list(k8s_dir.glob("**/*.yaml"))
        
        for yaml_file in yaml_files:
            with open(yaml_file, 'r') as f:
                try:
                    docs = list(yaml.safe_load_all(f))
                except yaml.YAMLError:
                    continue
            
            for doc in docs:
                if not doc:
                    continue
                
                # Check Job and Pod specs for command/args referencing scripts/
                self._check_container_commands(doc, yaml_file)
                
                # Check namespace and image pull policy for Jobs
                self._check_job_runtime_invariants(doc, yaml_file)
        
        print("✓ K8s packaging invariants valid")
    
    def _check_container_commands(self, doc: Dict, yaml_file: Path):
        """Check container commands/args for forbidden script references."""
        if doc.get('kind') not in ['Job', 'Pod', 'Deployment', 'StatefulSet', 'DaemonSet']:
            return
        
        # Get containers from spec
        spec = doc.get('spec', {})
        
        # Handle Job template
        if doc.get('kind') == 'Job':
            spec = spec.get('template', {}).get('spec', {})
        # Handle Deployment/StatefulSet/DaemonSet template
        elif doc.get('kind') in ['Deployment', 'StatefulSet', 'DaemonSet']:
            spec = spec.get('template', {}).get('spec', {})
        
        containers = spec.get('containers', [])
        
        for container in containers:
            # Check command
            command = container.get('command', [])
            for cmd_part in command:
                if isinstance(cmd_part, str) and 'scripts/' in cmd_part:
                    self.fail(f"K8s manifest {yaml_file.name} references scripts/ in command: {cmd_part}. "
                             f"Use 'python3 -m leviathan.module' instead.")
            
            # Check args
            args = container.get('args', [])
            for arg in args:
                if isinstance(arg, str) and 'scripts/' in arg:
                    self.fail(f"K8s manifest {yaml_file.name} references scripts/ in args: {arg}. "
                             f"Use 'python3 -m leviathan.module' instead.")
    
    def _check_job_runtime_invariants(self, doc: Dict, yaml_file: Path):
        """Check Job namespace and image pull policy invariants."""
        if doc.get('kind') != 'Job':
            return
        
        # Check if this is a Job in ops/k8s/jobs/
        if 'jobs' not in str(yaml_file):
            return
        
        # Check namespace
        namespace = doc.get('metadata', {}).get('namespace')
        if namespace == 'default':
            self.fail(f"K8s Job {yaml_file.name} uses namespace 'default'. "
                     f"Jobs must specify namespace: leviathan")
        elif not namespace:
            self.fail(f"K8s Job {yaml_file.name} missing namespace. "
                     f"Jobs must specify namespace: leviathan")
        
        # Check image pull policy for local images
        spec = doc.get('spec', {}).get('template', {}).get('spec', {})
        containers = spec.get('containers', [])
        
        for container in containers:
            image = container.get('image', '')
            pull_policy = container.get('imagePullPolicy')
            
            # If using local leviathan image, must have IfNotPresent
            if image.startswith('leviathan-') and ':local' in image:
                if pull_policy != 'IfNotPresent':
                    self.fail(f"K8s Job {yaml_file.name} container '{container.get('name')}' "
                             f"uses local image '{image}' but imagePullPolicy is '{pull_policy}'. "
                             f"Must be 'IfNotPresent' for local images.")
    
    def check_autonomy_config(self):
        """Validate DEV autonomy configuration."""
        print("\n=== Checking Autonomy Configuration ===")
        
        autonomy_config = self.repo_root / "ops" / "autonomy" / "dev.yaml"
        
        if not autonomy_config.exists():
            self.fail("DEV autonomy config not found: ops/autonomy/dev.yaml")
            return
        
        with open(autonomy_config, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check required fields
        required_fields = [
            'target_id',
            'allowed_path_prefixes',
            'max_open_prs',
            'max_attempts_per_task',
            'circuit_breaker_failures'
        ]
        
        for field in required_fields:
            if field not in config:
                self.fail(f"Autonomy config missing required field: {field}")
        
        # Check allowed_path_prefixes is a list
        if 'allowed_path_prefixes' in config:
            if not isinstance(config['allowed_path_prefixes'], list):
                self.fail("Autonomy config allowed_path_prefixes must be a list")
        
        # Check max_open_prs is set
        if 'max_open_prs' in config:
            if config['max_open_prs'] < 1:
                self.fail("Autonomy config max_open_prs must be >= 1")
        
        print("✓ Autonomy configuration valid")
    
    def check_scheduler_manifest(self):
        """Validate scheduler K8s manifest exists."""
        print("\n=== Checking Scheduler Manifest ===")
        
        scheduler_dir = self.repo_root / "ops" / "k8s" / "scheduler"
        
        if not scheduler_dir.exists():
            self.fail("Scheduler manifest directory not found: ops/k8s/scheduler/")
            return
        
        yaml_files = list(scheduler_dir.glob("*.yaml"))
        
        if not yaml_files:
            self.fail("No scheduler manifests found in ops/k8s/scheduler/")
            return
        
        # Check at least one manifest has CronJob or Deployment
        found_scheduler = False
        for yaml_file in yaml_files:
            with open(yaml_file, 'r') as f:
                try:
                    docs = list(yaml.safe_load_all(f))
                except yaml.YAMLError:
                    continue
            
            for doc in docs:
                if not doc:
                    continue
                
                if doc.get('kind') in ['CronJob', 'Deployment']:
                    found_scheduler = True
                    
                    # Check namespace
                    namespace = doc.get('metadata', {}).get('namespace')
                    if namespace != 'leviathan':
                        self.fail(f"Scheduler manifest {yaml_file.name} must use namespace: leviathan")
        
        if not found_scheduler:
            self.fail("No CronJob or Deployment found in scheduler manifests")
        
        print("✓ Scheduler manifest valid")
    
    def run_all_checks(self) -> bool:
        """Run all invariant checks."""
        print("Leviathan Invariants Gate")
        print("=" * 60)
        
        self.check_k8s_control_plane()
        self.check_k8s_worker_job()
        self.check_ci_workflows()
        self.check_requirements()
        self.check_namespace_consistency()
        self.check_topology_artifacts()
        self.check_topology_api_endpoints()
        self.check_failover_documentation()
        self.check_failover_backends()
        self.check_k8s_packaging()
        self.check_autonomy_config()
        self.check_scheduler_manifest()
        
        print("\n" + "=" * 60)
        
        if self.failures:
            print(f"\n❌ FAILED: {len(self.failures)} invariant(s) violated")
            print("\nFailures:")
            for i, failure in enumerate(self.failures, 1):
                print(f"  {i}. {failure}")
            return False
        else:
            print("\n✅ SUCCESS: All invariants validated")
            return True


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    
    checker = InvariantsChecker(repo_root)
    success = checker.run_all_checks()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
