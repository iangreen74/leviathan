"""
Deterministic repository indexer for bootstrap.

This module walks a target repository and produces factual events about:
- Files (path, sha256, size, type, language)
- Documentation (markdown files with extracted titles)
- Workflows (GitHub Actions with parsed triggers)
- API routes (FastAPI routes via AST parsing)

All operations are deterministic and read-only. No LLM interpretation.
"""
import ast
import hashlib
import json
import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timezone


# File type classification by extension
FILE_TYPE_MAP = {
    '.py': 'python',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.jsx': 'javascript',
    '.tsx': 'typescript',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.c': 'c',
    '.cpp': 'cpp',
    '.h': 'c_header',
    '.hpp': 'cpp_header',
    '.sh': 'shell',
    '.bash': 'shell',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.json': 'json',
    '.toml': 'toml',
    '.md': 'markdown',
    '.txt': 'text',
    '.sql': 'sql',
    '.html': 'html',
    '.css': 'css',
    '.scss': 'scss',
    '.Dockerfile': 'dockerfile',
}

# Default exclusions (can be overridden by bootstrap.yaml)
DEFAULT_EXCLUDES = {
    '.git',
    'node_modules',
    '.venv',
    'venv',
    '__pycache__',
    'dist',
    'build',
    '.pytest_cache',
    '.mypy_cache',
    '.tox',
    'htmlcov',
    '.coverage',
    '*.pyc',
    '*.pyo',
    '*.egg-info',
}


class BootstrapConfig:
    """Configuration for bootstrap indexing."""
    
    def __init__(self, config_dict: Optional[Dict[str, Any]] = None):
        """Initialize from bootstrap.yaml dict or use defaults."""
        config_dict = config_dict or {}
        bootstrap = config_dict.get('bootstrap', {})
        
        self.include = bootstrap.get('include', ['**/*'])
        self.exclude = bootstrap.get('exclude', list(DEFAULT_EXCLUDES))
        self.api_routes_enabled = bootstrap.get('api_routes', {}).get('enabled', True)


class RepositoryIndexer:
    """Deterministic repository indexer."""
    
    def __init__(self, repo_path: Path, config: Optional[BootstrapConfig] = None):
        """
        Initialize indexer.
        
        Args:
            repo_path: Path to repository root
            config: Bootstrap configuration (or None for defaults)
        """
        self.repo_path = Path(repo_path)
        self.config = config or BootstrapConfig()
        self.exclude_patterns = set(self.config.exclude)
        
    def should_exclude(self, path: Path) -> bool:
        """Check if path should be excluded."""
        # Check each part of the path
        for part in path.parts:
            if part in self.exclude_patterns:
                return True
            # Check wildcard patterns
            for pattern in self.exclude_patterns:
                if pattern.startswith('*') and part.endswith(pattern[1:]):
                    return True
        return False
    
    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def classify_file_type(self, file_path: Path) -> str:
        """Classify file type by extension."""
        suffix = file_path.suffix.lower()
        if suffix in FILE_TYPE_MAP:
            return FILE_TYPE_MAP[suffix]
        
        # Special cases
        if file_path.name == 'Dockerfile':
            return 'dockerfile'
        if file_path.name == 'Makefile':
            return 'makefile'
        
        return 'unknown'
    
    def extract_markdown_title(self, file_path: Path) -> Optional[str]:
        """Extract first markdown heading from file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        # Extract title after # symbols
                        title = line.lstrip('#').strip()
                        if title:
                            return title
        except Exception:
            pass
        return None
    
    def parse_workflow_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Parse GitHub Actions workflow file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                workflow = yaml.safe_load(f)
            
            if not isinstance(workflow, dict):
                return None
            
            # Extract workflow name and triggers
            name = workflow.get('name', file_path.stem)
            triggers = []
            
            if 'on' in workflow:
                on_config = workflow['on']
                if isinstance(on_config, str):
                    triggers = [on_config]
                elif isinstance(on_config, list):
                    triggers = on_config
                elif isinstance(on_config, dict):
                    triggers = list(on_config.keys())
            
            return {
                'name': name,
                'triggers': triggers,
                'path': str(file_path.relative_to(self.repo_path))
            }
        except Exception:
            return None
    
    def extract_fastapi_routes(self, file_path: Path) -> List[Dict[str, str]]:
        """Extract FastAPI routes via AST parsing (deterministic)."""
        if not self.config.api_routes_enabled:
            return []
        
        if file_path.suffix != '.py':
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            # Quick check if file might contain FastAPI routes
            if 'FastAPI' not in source and '@app.' not in source and '@router.' not in source:
                return []
            
            tree = ast.parse(source)
            routes = []
            
            # Walk AST looking for decorated functions
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for decorator in node.decorator_list:
                        route_info = self._parse_route_decorator(decorator, node.name)
                        if route_info:
                            route_info['source_file'] = str(file_path.relative_to(self.repo_path))
                            routes.append(route_info)
            
            return routes
        except Exception:
            return []
    
    def _parse_route_decorator(self, decorator: ast.expr, func_name: str) -> Optional[Dict[str, str]]:
        """Parse a route decorator to extract method and path."""
        # Handle @app.get("/path") or @router.post("/path")
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                # Check if it's app.get, app.post, router.get, etc.
                if isinstance(decorator.func.value, ast.Name):
                    obj_name = decorator.func.value.id
                    method_name = decorator.func.attr
                    
                    if obj_name in ('app', 'router') and method_name in ('get', 'post', 'put', 'delete', 'patch', 'options', 'head'):
                        # Extract path from first argument
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            path = decorator.args[0].value
                            if isinstance(path, str):
                                return {
                                    'method': method_name.upper(),
                                    'path': path,
                                    'function_name': func_name
                                }
        return None
    
    def index_repository(self, target_id: str, repo_url: str, commit_sha: str, default_branch: str) -> Dict[str, Any]:
        """
        Index repository and produce bootstrap events.
        
        Returns:
            Dict with:
                - events: List of event dicts
                - artifacts: Dict of artifact name -> content
                - manifest: Summary statistics
        """
        events = []
        files_discovered = []
        docs_discovered = []
        workflows_discovered = []
        api_routes_discovered = []
        
        # Emit bootstrap.started event
        events.append({
            'event_id': f'bootstrap-{target_id}-started',
            'event_type': 'bootstrap.started',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'actor_id': 'bootstrap-indexer',
            'payload': {
                'target_id': target_id,
                'repo_url': repo_url,
                'commit_sha': commit_sha,
                'default_branch': default_branch
            }
        })
        
        # Walk repository
        for root, dirs, files in os.walk(self.repo_path):
            root_path = Path(root)
            rel_root = root_path.relative_to(self.repo_path)
            
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if not self.should_exclude(rel_root / d)]
            
            for filename in files:
                file_path = root_path / filename
                rel_path = file_path.relative_to(self.repo_path)
                
                if self.should_exclude(rel_path):
                    continue
                
                try:
                    # Compute file metadata
                    file_hash = self.compute_file_hash(file_path)
                    file_size = file_path.stat().st_size
                    file_type = self.classify_file_type(file_path)
                    
                    # Emit file.discovered event
                    file_event = {
                        'event_id': f'file-{file_hash[:12]}',
                        'event_type': 'file.discovered',
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'actor_id': 'bootstrap-indexer',
                        'payload': {
                            'target_id': target_id,
                            'file_path': str(rel_path),
                            'sha256': file_hash,
                            'size_bytes': file_size,
                            'file_type': file_type,
                            'language': file_type if file_type in ('python', 'javascript', 'go', 'rust') else None
                        }
                    }
                    events.append(file_event)
                    files_discovered.append(file_event['payload'])
                    
                    # Check if it's a documentation file
                    if file_type == 'markdown':
                        title = self.extract_markdown_title(file_path)
                        doc_event = {
                            'event_id': f'doc-{file_hash[:12]}',
                            'event_type': 'doc.discovered',
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'actor_id': 'bootstrap-indexer',
                            'payload': {
                                'target_id': target_id,
                                'doc_path': str(rel_path),
                                'doc_title': title or file_path.name,
                                'sha256': file_hash
                            }
                        }
                        events.append(doc_event)
                        docs_discovered.append(doc_event['payload'])
                    
                    # Check if it's a GitHub Actions workflow
                    if str(rel_path).startswith('.github/workflows/') and file_path.suffix in ('.yml', '.yaml'):
                        workflow_info = self.parse_workflow_file(file_path)
                        if workflow_info:
                            workflow_event = {
                                'event_id': f'workflow-{file_hash[:12]}',
                                'event_type': 'workflow.discovered',
                                'timestamp': datetime.now(timezone.utc).isoformat(),
                                'actor_id': 'bootstrap-indexer',
                                'payload': {
                                    'target_id': target_id,
                                    'workflow_name': workflow_info['name'],
                                    'workflow_path': workflow_info['path'],
                                    'triggers': workflow_info['triggers'],
                                    'sha256': file_hash
                                }
                            }
                            events.append(workflow_event)
                            workflows_discovered.append(workflow_event['payload'])
                    
                    # Extract FastAPI routes if Python file
                    if file_type == 'python':
                        routes = self.extract_fastapi_routes(file_path)
                        for route in routes:
                            route_event = {
                                'event_id': f'route-{file_hash[:8]}-{route["method"]}-{hash(route["path"]) % 10000}',
                                'event_type': 'api.route.discovered',
                                'timestamp': datetime.now(timezone.utc).isoformat(),
                                'actor_id': 'bootstrap-indexer',
                                'payload': {
                                    'target_id': target_id,
                                    'method': route['method'],
                                    'path': route['path'],
                                    'source_file': route['source_file'],
                                    'function_name': route['function_name']
                                }
                            }
                            events.append(route_event)
                            api_routes_discovered.append(route_event['payload'])
                
                except Exception as e:
                    # Skip files that can't be processed
                    continue
        
        # Emit repo.indexed event
        events.append({
            'event_id': f'repo-indexed-{target_id}',
            'event_type': 'repo.indexed',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'actor_id': 'bootstrap-indexer',
            'payload': {
                'target_id': target_id,
                'repo_url': repo_url,
                'commit_sha': commit_sha,
                'default_branch': default_branch,
                'files_count': len(files_discovered),
                'docs_count': len(docs_discovered),
                'workflows_count': len(workflows_discovered),
                'api_routes_count': len(api_routes_discovered)
            }
        })
        
        # Emit bootstrap.completed event
        events.append({
            'event_id': f'bootstrap-{target_id}-completed',
            'event_type': 'bootstrap.completed',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'actor_id': 'bootstrap-indexer',
            'payload': {
                'target_id': target_id,
                'status': 'completed',
                'files_indexed': len(files_discovered),
                'docs_indexed': len(docs_discovered),
                'workflows_indexed': len(workflows_discovered),
                'api_routes_indexed': len(api_routes_discovered)
            }
        })
        
        # Generate artifacts
        artifacts = {}
        
        # repo_tree.txt
        tree_lines = []
        for event in events:
            if event['event_type'] == 'file.discovered':
                tree_lines.append(event['payload']['file_path'])
        tree_lines.sort()
        artifacts['repo_tree.txt'] = '\n'.join(tree_lines)
        
        # repo_manifest.json
        file_types = {}
        for file_info in files_discovered:
            ft = file_info['file_type']
            file_types[ft] = file_types.get(ft, 0) + 1
        
        manifest = {
            'target_id': target_id,
            'repo_url': repo_url,
            'commit_sha': commit_sha,
            'default_branch': default_branch,
            'indexed_at': datetime.now(timezone.utc).isoformat(),
            'counts': {
                'total_files': len(files_discovered),
                'by_type': file_types,
                'docs': len(docs_discovered),
                'workflows': len(workflows_discovered),
                'api_routes': len(api_routes_discovered)
            }
        }
        artifacts['repo_manifest.json'] = json.dumps(manifest, indent=2)
        
        # workflows_manifest.json
        if workflows_discovered:
            artifacts['workflows_manifest.json'] = json.dumps(workflows_discovered, indent=2)
        
        # api_routes.json
        if api_routes_discovered:
            artifacts['api_routes.json'] = json.dumps(api_routes_discovered, indent=2)
        
        return {
            'events': events,
            'artifacts': artifacts,
            'manifest': manifest
        }


def load_bootstrap_config(repo_path: Path) -> BootstrapConfig:
    """Load bootstrap.yaml from repository if present."""
    config_path = repo_path / '.leviathan' / 'bootstrap.yaml'
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config_dict = yaml.safe_load(f)
            return BootstrapConfig(config_dict)
        except Exception:
            pass
    return BootstrapConfig()
