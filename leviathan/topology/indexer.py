"""
Deterministic topology indexer for Leviathan.

Analyzes repository structure to derive:
- Repository areas (docs, ci, services, infra, tools, tests)
- Subsystems (directory-based boundaries)
- Dependencies (static analysis of imports and references)
- Data flows (optional, based on deterministic signals)

All operations are deterministic and read-only. No LLM calls.
"""
import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timezone


# Topology rules version
TOPO_RULES_VERSION = "topo_rules_v1"

# Area classification rules (deterministic path mapping)
AREA_RULES = [
    ('area/docs', ['docs/**', '**/*.md']),
    ('area/ci', ['.github/workflows/**']),
    ('area/infra', ['infra/**', 'ops/**', 'cloudformation/**', 'terraform/**']),
    ('area/services', ['services/**']),
    ('area/tools', ['tools/**', 'scripts/**']),
    ('area/tests', ['tests/**', 'test/**', '**/*_test.py', '**/test_*.py']),
]

# Subsystem derivation rules (directory boundaries)
SUBSYSTEM_ROOTS = [
    'services',
    'ops/k8s',
    'charts',
    'tools',
    'infra',
]


class TopologyIndexer:
    """Deterministic topology analyzer."""
    
    def __init__(self, repo_path: Path, target_id: str, commit_sha: str):
        """
        Initialize topology indexer.
        
        Args:
            repo_path: Path to repository root
            target_id: Target identifier
            commit_sha: Git commit SHA being analyzed
        """
        self.repo_path = Path(repo_path)
        self.target_id = target_id
        self.commit_sha = commit_sha
        self.rules_version = TOPO_RULES_VERSION
        
        # Collected data
        self.areas: Dict[str, Dict[str, Any]] = {}
        self.subsystems: Dict[str, Dict[str, Any]] = {}
        self.dependencies: List[Dict[str, Any]] = []
        self.flows: List[Dict[str, Any]] = []
        
        # File inventory for analysis
        self.files_by_area: Dict[str, List[str]] = {}
        self.files_by_subsystem: Dict[str, List[str]] = {}
    
    def index(self) -> Dict[str, Any]:
        """
        Run full topology indexing.
        
        Returns:
            Dict with events, artifacts, and summary
        """
        # Step 1: Walk repository and classify files
        self._walk_repository()
        
        # Step 2: Derive areas
        self._derive_areas()
        
        # Step 3: Derive subsystems
        self._derive_subsystems()
        
        # Step 4: Analyze dependencies
        self._analyze_dependencies()
        
        # Step 5: Generate events and artifacts
        events = self._generate_events()
        artifacts = self._generate_artifacts()
        
        return {
            'events': events,
            'artifacts': artifacts,
            'summary': {
                'areas_count': len(self.areas),
                'subsystems_count': len(self.subsystems),
                'dependencies_count': len(self.dependencies),
                'flows_count': len(self.flows),
            }
        }
    
    def _walk_repository(self):
        """Walk repository and collect file paths."""
        import os
        
        exclude_dirs = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 
                       'dist', 'build', '.pytest_cache', '.mypy_cache'}
        
        for root, dirs, files in os.walk(self.repo_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            root_path = Path(root)
            for file in files:
                file_path = (root_path / file).relative_to(self.repo_path)
                
                # Classify by area
                area_id = self._classify_area(file_path)
                if area_id:
                    self.files_by_area.setdefault(area_id, []).append(str(file_path))
                
                # Classify by subsystem
                subsystem_id = self._classify_subsystem(file_path)
                if subsystem_id:
                    self.files_by_subsystem.setdefault(subsystem_id, []).append(str(file_path))
    
    def _classify_area(self, file_path: Path) -> Optional[str]:
        """Classify file into an area based on path rules."""
        file_str = str(file_path)
        
        # Check each area rule
        for area_id, patterns in AREA_RULES:
            for pattern in patterns:
                if self._match_pattern(file_str, pattern):
                    return area_id
        
        # Default: no specific area
        return None
    
    def _classify_subsystem(self, file_path: Path) -> Optional[str]:
        """Classify file into a subsystem based on directory boundaries."""
        file_str = str(file_path)
        parts = Path(file_str).parts
        
        if len(parts) == 0:
            return None
        
        # Check subsystem roots
        for root in SUBSYSTEM_ROOTS:
            root_parts = root.split('/')
            if len(parts) > len(root_parts):
                # Check if file is under this root
                if parts[:len(root_parts)] == tuple(root_parts):
                    # Subsystem is root + next directory
                    if len(parts) > len(root_parts):
                        subsystem_path = '/'.join(parts[:len(root_parts) + 1])
                        return f"subsystem/{subsystem_path}"
        
        # Fallback: top-level directory as subsystem
        if len(parts) > 1:
            return f"subsystem/{parts[0]}"
        
        return None
    
    def _match_pattern(self, path: str, pattern: str) -> bool:
        """Match path against glob-like pattern."""
        # Simple pattern matching
        if pattern.endswith('/**'):
            prefix = pattern[:-3]
            return path.startswith(prefix + '/')
        elif pattern.startswith('**/'):
            suffix = pattern[3:]
            return path.endswith(suffix)
        elif '**' in pattern:
            parts = pattern.split('**')
            return path.startswith(parts[0]) and path.endswith(parts[1])
        else:
            return path == pattern
    
    def _derive_areas(self):
        """Derive repository areas from classified files."""
        for area_id, file_paths in sorted(self.files_by_area.items()):
            # Determine path prefixes for this area
            path_prefixes = self._extract_path_prefixes(file_paths)
            
            self.areas[area_id] = {
                'area_id': area_id,
                'path_prefixes': path_prefixes,
                'file_count': len(file_paths),
                'rules_version': self.rules_version,
                'target_id': self.target_id,
                'commit_sha': self.commit_sha,
            }
    
    def _derive_subsystems(self):
        """Derive subsystems from classified files."""
        for subsystem_id, file_paths in sorted(self.files_by_subsystem.items()):
            # Determine root path
            root_path = subsystem_id.replace('subsystem/', '')
            
            # Compute language distribution
            languages = self._compute_languages(file_paths)
            
            # Determine area
            area_id = self._subsystem_area(root_path)
            
            self.subsystems[subsystem_id] = {
                'subsystem_id': subsystem_id,
                'area_id': area_id,
                'root_path': root_path,
                'languages': languages,
                'file_count': len(file_paths),
                'rules_version': self.rules_version,
                'target_id': self.target_id,
                'commit_sha': self.commit_sha,
            }
    
    def _extract_path_prefixes(self, file_paths: List[str]) -> List[str]:
        """Extract common path prefixes from file list."""
        if not file_paths:
            return []
        
        # Get unique top-level directories
        prefixes = set()
        for path in file_paths:
            parts = Path(path).parts
            if len(parts) > 0:
                prefixes.add(parts[0])
        
        return sorted(prefixes)
    
    def _compute_languages(self, file_paths: List[str]) -> Dict[str, float]:
        """Compute language distribution for files."""
        ext_counts: Dict[str, int] = {}
        total = 0
        
        for path in file_paths:
            ext = Path(path).suffix
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                total += 1
        
        if total == 0:
            return {}
        
        # Convert to fractions
        return {ext: count / total for ext, count in sorted(ext_counts.items())}
    
    def _subsystem_area(self, root_path: str) -> Optional[str]:
        """Determine which area a subsystem belongs to."""
        # Simple heuristic based on root path
        if root_path.startswith('services'):
            return 'area/services'
        elif root_path.startswith('ops') or root_path.startswith('infra'):
            return 'area/infra'
        elif root_path.startswith('tools'):
            return 'area/tools'
        elif root_path.startswith('tests'):
            return 'area/tests'
        elif root_path.startswith('docs'):
            return 'area/docs'
        elif root_path.startswith('.github'):
            return 'area/ci'
        return None
    
    def _analyze_dependencies(self):
        """Analyze dependencies between subsystems using static analysis."""
        # Analyze Python imports
        for subsystem_id, file_paths in self.files_by_subsystem.items():
            for file_path in file_paths:
                if file_path.endswith('.py'):
                    self._analyze_python_imports(subsystem_id, file_path)
                elif file_path.endswith(('.js', '.ts', '.jsx', '.tsx')):
                    self._analyze_js_imports(subsystem_id, file_path)
                elif file_path.endswith(('.yaml', '.yml', '.json')):
                    self._analyze_config_refs(subsystem_id, file_path)
    
    def _analyze_python_imports(self, from_subsystem: str, file_path: str):
        """Analyze Python imports via AST parsing."""
        full_path = self.repo_path / file_path
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._record_import_dependency(
                            from_subsystem, file_path, alias.name, 'py_import'
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        self._record_import_dependency(
                            from_subsystem, file_path, node.module, 'py_from_import'
                        )
        except (SyntaxError, UnicodeDecodeError):
            # Skip files that can't be parsed
            pass
    
    def _analyze_js_imports(self, from_subsystem: str, file_path: str):
        """Analyze JS/TS imports via regex."""
        full_path = self.repo_path / file_path
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Match import statements
            import_pattern = r'import\s+.*?\s+from\s+["\']([^"\']+)["\']'
            for match in re.finditer(import_pattern, content):
                module = match.group(1)
                self._record_import_dependency(
                    from_subsystem, file_path, module, 'js_import'
                )
        except UnicodeDecodeError:
            pass
    
    def _analyze_config_refs(self, from_subsystem: str, file_path: str):
        """Analyze config files for service references."""
        full_path = self.repo_path / file_path
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for service references (http://<service>, <service>.svc, etc.)
            patterns = [
                r'https?://([a-z0-9-]+)',
                r'([a-z0-9-]+)\.([a-z0-9-]+)\.svc',
            ]
            
            for pattern in patterns:
                for match in re.finditer(pattern, content):
                    ref = match.group(1)
                    self._record_url_dependency(
                        from_subsystem, file_path, ref, 'url_ref'
                    )
        except UnicodeDecodeError:
            pass
    
    def _record_import_dependency(self, from_subsystem: str, from_file: str, 
                                   to_module: str, kind: str):
        """Record an import-based dependency."""
        # Try to map module to subsystem
        to_subsystem = self._module_to_subsystem(to_module)
        
        if to_subsystem and to_subsystem != from_subsystem:
            evidence = {
                'kind': kind,
                'from_file': from_file,
                'to_module': to_module,
                'mapped_subsystem': to_subsystem,
            }
            
            # Check if dependency already exists
            dep_key = (from_subsystem, to_subsystem)
            existing = next((d for d in self.dependencies 
                           if d['from_subsystem_id'] == from_subsystem 
                           and d['to_subsystem_id'] == to_subsystem), None)
            
            if existing:
                existing['evidence'].append(evidence)
            else:
                self.dependencies.append({
                    'from_subsystem_id': from_subsystem,
                    'to_subsystem_id': to_subsystem,
                    'evidence': [evidence],
                })
    
    def _record_url_dependency(self, from_subsystem: str, from_file: str,
                               ref: str, kind: str):
        """Record a URL-based dependency."""
        # Try to map URL reference to subsystem
        to_subsystem = self._url_to_subsystem(ref)
        
        if to_subsystem and to_subsystem != from_subsystem:
            evidence = {
                'kind': kind,
                'from_file': from_file,
                'ref': ref,
                'mapped_subsystem': to_subsystem,
            }
            
            existing = next((d for d in self.dependencies 
                           if d['from_subsystem_id'] == from_subsystem 
                           and d['to_subsystem_id'] == to_subsystem), None)
            
            if existing:
                existing['evidence'].append(evidence)
            else:
                self.dependencies.append({
                    'from_subsystem_id': from_subsystem,
                    'to_subsystem_id': to_subsystem,
                    'evidence': [evidence],
                })
    
    def _module_to_subsystem(self, module: str) -> Optional[str]:
        """Map Python module name to subsystem."""
        # Simple heuristic: check if module matches a subsystem root
        for subsystem_id in self.subsystems.keys():
            root_path = subsystem_id.replace('subsystem/', '').replace('/', '.')
            if module.startswith(root_path):
                return subsystem_id
        return None
    
    def _url_to_subsystem(self, url_ref: str) -> Optional[str]:
        """Map URL reference to subsystem."""
        # Look for known service names in subsystems
        for subsystem_id in self.subsystems.keys():
            root_path = subsystem_id.replace('subsystem/', '')
            service_name = root_path.split('/')[-1]
            if service_name in url_ref:
                return subsystem_id
        return None
    
    def _generate_events(self) -> List[Dict[str, Any]]:
        """Generate topology events."""
        events = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # topo.started
        events.append({
            'event_id': f'topo-started-{self.target_id}-{self.commit_sha[:8]}',
            'event_type': 'topo.started',
            'timestamp': timestamp,
            'actor_id': 'topology-indexer',
            'payload': {
                'target_id': self.target_id,
                'commit_sha': self.commit_sha,
                'rules_version': self.rules_version,
            }
        })
        
        # topo.area.discovered (one per area)
        for area_id, area_data in sorted(self.areas.items()):
            events.append({
                'event_id': f'topo-area-{area_id.replace("/", "-")}-{self.commit_sha[:8]}',
                'event_type': 'topo.area.discovered',
                'timestamp': timestamp,
                'actor_id': 'topology-indexer',
                'payload': area_data,
            })
        
        # topo.subsystem.discovered (one per subsystem)
        for subsystem_id, subsystem_data in sorted(self.subsystems.items()):
            events.append({
                'event_id': f'topo-subsystem-{subsystem_id.replace("/", "-")}-{self.commit_sha[:8]}',
                'event_type': 'topo.subsystem.discovered',
                'timestamp': timestamp,
                'actor_id': 'topology-indexer',
                'payload': subsystem_data,
            })
        
        # topo.dependency.discovered (one per dependency)
        for i, dep in enumerate(self.dependencies):
            events.append({
                'event_id': f'topo-dep-{i}-{self.commit_sha[:8]}',
                'event_type': 'topo.dependency.discovered',
                'timestamp': timestamp,
                'actor_id': 'topology-indexer',
                'payload': {
                    'target_id': self.target_id,
                    'commit_sha': self.commit_sha,
                    'rules_version': self.rules_version,
                    **dep,
                }
            })
        
        # topo.indexed (summary)
        events.append({
            'event_id': f'topo-indexed-{self.target_id}-{self.commit_sha[:8]}',
            'event_type': 'topo.indexed',
            'timestamp': timestamp,
            'actor_id': 'topology-indexer',
            'payload': {
                'target_id': self.target_id,
                'commit_sha': self.commit_sha,
                'rules_version': self.rules_version,
                'areas_count': len(self.areas),
                'subsystems_count': len(self.subsystems),
                'dependencies_count': len(self.dependencies),
            }
        })
        
        # topo.completed
        events.append({
            'event_id': f'topo-completed-{self.target_id}-{self.commit_sha[:8]}',
            'event_type': 'topo.completed',
            'timestamp': timestamp,
            'actor_id': 'topology-indexer',
            'payload': {
                'target_id': self.target_id,
                'commit_sha': self.commit_sha,
                'rules_version': self.rules_version,
                'status': 'completed',
            }
        })
        
        return events
    
    def _generate_artifacts(self) -> Dict[str, str]:
        """Generate topology artifacts as JSON strings."""
        artifacts = {}
        
        # topo_areas.json
        artifacts['topo_areas.json'] = json.dumps({
            'target_id': self.target_id,
            'commit_sha': self.commit_sha,
            'rules_version': self.rules_version,
            'areas': list(self.areas.values()),
        }, indent=2, sort_keys=True)
        
        # topo_subsystems.json
        artifacts['topo_subsystems.json'] = json.dumps({
            'target_id': self.target_id,
            'commit_sha': self.commit_sha,
            'rules_version': self.rules_version,
            'subsystems': list(self.subsystems.values()),
        }, indent=2, sort_keys=True)
        
        # topo_deps.json
        artifacts['topo_deps.json'] = json.dumps({
            'target_id': self.target_id,
            'commit_sha': self.commit_sha,
            'rules_version': self.rules_version,
            'dependencies': self.dependencies,
        }, indent=2, sort_keys=True)
        
        # topo_summary.json
        artifacts['topo_summary.json'] = json.dumps({
            'target_id': self.target_id,
            'commit_sha': self.commit_sha,
            'rules_version': self.rules_version,
            'areas_count': len(self.areas),
            'subsystems_count': len(self.subsystems),
            'dependencies_count': len(self.dependencies),
            'flows_count': len(self.flows),
        }, indent=2, sort_keys=True)
        
        return artifacts
