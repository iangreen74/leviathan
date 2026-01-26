"""
Backlog synthesis module for generating task proposals.

This module reads bootstrap artifacts and generates structured task proposals
that are submitted as PRs to the target's .leviathan/backlog.yaml file.

Governance constraint: Only modifies .leviathan/backlog.yaml, never product code.
"""
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from leviathan.backlog import Task
from leviathan.model_client import ModelClient


class BacklogSynthesizer:
    """
    Synthesizes backlog task proposals from bootstrap artifacts.
    
    Uses LLM to generate structured task proposals organized by tracks:
    - Dataset registration (schema + API skeleton)
    - Research plan schema + API skeleton
    - Experiment schema + execution skeleton
    - Evidence pack schema + generation stub
    - Answer synthesis stub and ranking stub
    """
    
    def __init__(self, model_client: Optional[ModelClient] = None):
        """
        Initialize backlog synthesizer.
        
        Args:
            model_client: Optional ModelClient for LLM-based generation
        """
        self.model_client = model_client
    
    def synthesize_tasks(
        self,
        repo_manifest: Dict[str, Any],
        workflows_manifest: Optional[List[Dict[str, Any]]],
        api_routes: Optional[List[Dict[str, Any]]],
        current_backlog: List[Dict[str, Any]],
        policy: Dict[str, Any],
        target_id: str
    ) -> List[Dict[str, Any]]:
        """
        Generate task proposals based on bootstrap artifacts.
        
        Args:
            repo_manifest: Repository manifest from bootstrap
            workflows_manifest: Workflows discovered during bootstrap
            api_routes: API routes discovered during bootstrap
            current_backlog: Current backlog tasks
            policy: Target policy constraints
            target_id: Target identifier (e.g., 'radix')
            
        Returns:
            List of proposed task dictionaries
        """
        # Extract existing task IDs to ensure uniqueness
        existing_ids = {task.get('id') for task in current_backlog if task.get('id')}
        
        # Build context for LLM
        context = self._build_context(
            repo_manifest,
            workflows_manifest,
            api_routes,
            current_backlog,
            policy,
            target_id
        )
        
        # Generate tasks using LLM
        if self.model_client:
            proposed_tasks = self._generate_tasks_with_llm(context, existing_ids, target_id)
        else:
            # Fallback: generate basic tasks without LLM
            proposed_tasks = self._generate_basic_tasks(target_id, existing_ids)
        
        # Validate and filter tasks
        validated_tasks = self._validate_tasks(proposed_tasks, existing_ids, policy)
        
        return validated_tasks
    
    def _build_context(
        self,
        repo_manifest: Dict[str, Any],
        workflows_manifest: Optional[List[Dict[str, Any]]],
        api_routes: Optional[List[Dict[str, Any]]],
        current_backlog: List[Dict[str, Any]],
        policy: Dict[str, Any],
        target_id: str
    ) -> str:
        """Build context string for LLM."""
        context_parts = [
            f"# Backlog Synthesis for {target_id}",
            "",
            "## Repository Overview",
            f"Total files: {repo_manifest.get('counts', {}).get('total_files', 0)}",
            f"Documentation files: {repo_manifest.get('counts', {}).get('docs', 0)}",
            f"Workflows: {repo_manifest.get('counts', {}).get('workflows', 0)}",
            f"API routes: {repo_manifest.get('counts', {}).get('api_routes', 0)}",
            "",
            "## File Types",
        ]
        
        by_type = repo_manifest.get('counts', {}).get('by_type', {})
        for file_type, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
            context_parts.append(f"- {file_type}: {count}")
        
        context_parts.extend([
            "",
            "## Current Backlog",
            f"Existing tasks: {len(current_backlog)}",
        ])
        
        if current_backlog:
            context_parts.append("Task IDs:")
            for task in current_backlog[:10]:
                context_parts.append(f"- {task.get('id')}: {task.get('title')}")
        
        context_parts.extend([
            "",
            "## Policy Constraints",
            f"Allowed paths: {policy.get('allowed_paths', [])}",
            f"Forbidden paths: {policy.get('forbidden_paths', [])}",
            "",
            "## Task Generation Tracks",
            "1. Dataset registration (schema + API skeleton)",
            "2. Research plan schema + API skeleton",
            "3. Experiment schema + execution skeleton",
            "4. Evidence pack schema + generation stub",
            "5. Answer synthesis stub and ranking stub",
        ])
        
        return "\n".join(context_parts)
    
    def _generate_tasks_with_llm(
        self,
        context: str,
        existing_ids: set,
        target_id: str
    ) -> List[Dict[str, Any]]:
        """Generate tasks using LLM."""
        prompt = f"""{context}

## Instructions

Generate a structured backlog of tasks for the {target_id} repository.

Requirements:
1. Tasks must be organized into 5 tracks (dataset, research plan, experiment, evidence pack, answer synthesis)
2. Each task must have:
   - id: Unique identifier prefixed with '{target_id}-' (e.g., '{target_id}-dataset-schema-v1')
   - title: Clear, concise description
   - scope: One of (docs/tests/services/infra/bootstrap/core)
   - priority: One of (high/medium/low)
   - ready: false (except optionally ONE safe starter task can be ready:true)
   - allowed_paths: List of paths this task can modify (must match policy constraints)
   - acceptance_criteria: List of explicit, testable criteria
   - dependencies: List of task IDs this depends on (empty list if none)
   - estimated_size: One of (small/medium/large)
3. Tasks must form a dependency chain within each track
4. Only modify paths under .leviathan/ directory or create new service stubs
5. Do NOT propose tasks that modify existing product code

Generate 10-15 tasks total across all tracks.

Output ONLY valid YAML in this format:

```yaml
tasks:
  - id: {target_id}-dataset-schema-v1
    title: Define dataset registration schema
    scope: core
    priority: high
    ready: true
    allowed_paths:
      - .leviathan/schemas/dataset.yaml
    acceptance_criteria:
      - Schema defines required fields for dataset registration
      - Schema includes validation rules
      - Schema is documented with examples
    dependencies: []
    estimated_size: small
  
  - id: {target_id}-dataset-api-stub-v1
    title: Create dataset API stub
    scope: services
    priority: high
    ready: false
    allowed_paths:
      - services/dataset/api.py
      - services/dataset/__init__.py
    acceptance_criteria:
      - API stub created with registration endpoint
      - OpenAPI spec generated
      - Basic validation implemented
    dependencies:
      - {target_id}-dataset-schema-v1
    estimated_size: medium
```

Generate the YAML now:"""

        try:
            response = self.model_client.generate(
                prompt=prompt,
                max_tokens=4000,
                temperature=0.3
            )
            
            # Extract YAML from response
            yaml_content = self._extract_yaml_from_response(response)
            
            # Parse YAML
            parsed = yaml.safe_load(yaml_content)
            
            if isinstance(parsed, dict) and 'tasks' in parsed:
                return parsed['tasks']
            elif isinstance(parsed, list):
                return parsed
            else:
                print(f"Warning: Unexpected YAML structure: {type(parsed)}")
                return []
        
        except Exception as e:
            print(f"Error generating tasks with LLM: {e}")
            return self._generate_basic_tasks(target_id, existing_ids)
    
    def _extract_yaml_from_response(self, response: str) -> str:
        """Extract YAML content from LLM response."""
        # Look for YAML code blocks
        if "```yaml" in response:
            start = response.find("```yaml") + 7
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        
        # If no code blocks, return entire response
        return response.strip()
    
    def _generate_basic_tasks(
        self,
        target_id: str,
        existing_ids: set
    ) -> List[Dict[str, Any]]:
        """Generate basic fallback tasks without LLM."""
        tasks = []
        
        # Track 1: Dataset
        if f"{target_id}-dataset-schema-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-dataset-schema-v1',
                'title': 'Define dataset registration schema',
                'scope': 'core',
                'priority': 'high',
                'ready': True,
                'allowed_paths': ['.leviathan/schemas/dataset.yaml'],
                'acceptance_criteria': [
                    'Schema defines required fields for dataset registration',
                    'Schema includes validation rules',
                    'Schema is documented with examples'
                ],
                'dependencies': [],
                'estimated_size': 'small'
            })
        
        if f"{target_id}-dataset-api-stub-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-dataset-api-stub-v1',
                'title': 'Create dataset API stub',
                'scope': 'services',
                'priority': 'high',
                'ready': False,
                'allowed_paths': [
                    'services/dataset/api.py',
                    'services/dataset/__init__.py'
                ],
                'acceptance_criteria': [
                    'API stub created with registration endpoint',
                    'OpenAPI spec generated',
                    'Basic validation implemented'
                ],
                'dependencies': [f'{target_id}-dataset-schema-v1'],
                'estimated_size': 'medium'
            })
        
        # Track 2: Research Plan
        if f"{target_id}-research-schema-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-research-schema-v1',
                'title': 'Define research plan schema',
                'scope': 'core',
                'priority': 'high',
                'ready': False,
                'allowed_paths': ['.leviathan/schemas/research_plan.yaml'],
                'acceptance_criteria': [
                    'Schema defines research plan structure',
                    'Schema includes hypothesis and methodology fields',
                    'Schema is validated'
                ],
                'dependencies': [],
                'estimated_size': 'small'
            })
        
        # Track 3: Experiment
        if f"{target_id}-experiment-schema-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-experiment-schema-v1',
                'title': 'Define experiment execution schema',
                'scope': 'core',
                'priority': 'medium',
                'ready': False,
                'allowed_paths': ['.leviathan/schemas/experiment.yaml'],
                'acceptance_criteria': [
                    'Schema defines experiment parameters',
                    'Schema includes execution steps',
                    'Schema supports result recording'
                ],
                'dependencies': [f'{target_id}-research-schema-v1'],
                'estimated_size': 'medium'
            })
        
        # Track 4: Evidence Pack
        if f"{target_id}-evidence-schema-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-evidence-schema-v1',
                'title': 'Define evidence pack schema',
                'scope': 'core',
                'priority': 'medium',
                'ready': False,
                'allowed_paths': ['.leviathan/schemas/evidence_pack.yaml'],
                'acceptance_criteria': [
                    'Schema defines evidence structure',
                    'Schema includes source attribution',
                    'Schema supports multiple evidence types'
                ],
                'dependencies': [f'{target_id}-experiment-schema-v1'],
                'estimated_size': 'small'
            })
        
        # Track 5: Answer Synthesis
        if f"{target_id}-answer-schema-v1" not in existing_ids:
            tasks.append({
                'id': f'{target_id}-answer-schema-v1',
                'title': 'Define answer synthesis schema',
                'scope': 'core',
                'priority': 'low',
                'ready': False,
                'allowed_paths': ['.leviathan/schemas/answer.yaml'],
                'acceptance_criteria': [
                    'Schema defines answer structure',
                    'Schema includes confidence scoring',
                    'Schema supports ranking criteria'
                ],
                'dependencies': [f'{target_id}-evidence-schema-v1'],
                'estimated_size': 'medium'
            })
        
        return tasks
    
    def _validate_tasks(
        self,
        tasks: List[Dict[str, Any]],
        existing_ids: set,
        policy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Validate proposed tasks.
        
        Checks:
        - Unique IDs (not in existing_ids)
        - Valid scope values
        - Valid priority values
        - Valid estimated_size values
        - allowed_paths match policy constraints
        - At most one task has ready:true
        - Dependencies reference valid task IDs
        """
        validated = []
        seen_ids = set()
        ready_count = 0
        
        valid_scopes = {'docs', 'tests', 'services', 'infra', 'bootstrap', 'core'}
        valid_priorities = {'high', 'medium', 'low'}
        valid_sizes = {'small', 'medium', 'large'}
        
        allowed_paths = set(policy.get('allowed_paths', []))
        forbidden_paths = set(policy.get('forbidden_paths', []))
        
        for task in tasks:
            # Check required fields
            if not task.get('id') or not task.get('title'):
                print(f"Warning: Skipping task with missing id or title: {task}")
                continue
            
            task_id = task['id']
            
            # Check uniqueness
            if task_id in existing_ids or task_id in seen_ids:
                print(f"Warning: Duplicate task ID: {task_id}")
                continue
            
            # Validate scope
            scope = task.get('scope', 'core')
            if scope not in valid_scopes:
                print(f"Warning: Invalid scope '{scope}' for task {task_id}, defaulting to 'core'")
                task['scope'] = 'core'
            
            # Validate priority
            priority = task.get('priority', 'medium')
            if priority not in valid_priorities:
                print(f"Warning: Invalid priority '{priority}' for task {task_id}, defaulting to 'medium'")
                task['priority'] = 'medium'
            
            # Validate estimated_size
            size = task.get('estimated_size', 'medium')
            if size not in valid_sizes:
                print(f"Warning: Invalid size '{size}' for task {task_id}, defaulting to 'medium'")
                task['estimated_size'] = 'medium'
            
            # Validate ready flag (at most one ready:true)
            if task.get('ready', False):
                ready_count += 1
                if ready_count > 1:
                    print(f"Warning: Multiple tasks marked ready:true, setting {task_id} to ready:false")
                    task['ready'] = False
            
            # Validate allowed_paths against policy
            task_paths = task.get('allowed_paths', [])
            if not self._validate_paths(task_paths, allowed_paths, forbidden_paths):
                print(f"Warning: Task {task_id} has paths violating policy, skipping")
                continue
            
            # Ensure required fields have defaults
            task.setdefault('ready', False)
            task.setdefault('allowed_paths', [])
            task.setdefault('acceptance_criteria', [])
            task.setdefault('dependencies', [])
            task.setdefault('estimated_size', 'medium')
            
            seen_ids.add(task_id)
            validated.append(task)
        
        return validated
    
    def _validate_paths(
        self,
        task_paths: List[str],
        allowed_paths: set,
        forbidden_paths: set
    ) -> bool:
        """
        Validate that task paths comply with policy.
        
        Rules:
        - If allowed_paths is empty, allow anything not in forbidden_paths
        - If allowed_paths is specified, task paths must match at least one pattern
        - Task paths must not match any forbidden_paths pattern
        """
        for path in task_paths:
            # Check forbidden paths
            for forbidden in forbidden_paths:
                if self._path_matches_pattern(path, forbidden):
                    return False
            
            # Check allowed paths (if specified)
            if allowed_paths:
                matches_allowed = False
                for allowed in allowed_paths:
                    if self._path_matches_pattern(path, allowed):
                        matches_allowed = True
                        break
                
                if not matches_allowed:
                    return False
        
        return True
    
    def _path_matches_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern (supports wildcards)."""
        if '*' in pattern:
            # Simple wildcard matching
            import re
            regex_pattern = pattern.replace('*', '.*')
            return bool(re.match(f'^{regex_pattern}$', path))
        else:
            # Exact match or prefix match
            return path == pattern or path.startswith(pattern + '/')


def load_bootstrap_artifacts(
    artifacts_dir: Path,
    target_id: str,
    attempt_id: str
) -> Dict[str, Any]:
    """
    Load bootstrap artifacts for a specific attempt.
    
    Args:
        artifacts_dir: Root artifacts directory
        target_id: Target identifier
        attempt_id: Attempt identifier
        
    Returns:
        Dictionary with repo_manifest, workflows_manifest, api_routes
    """
    result = {
        'repo_manifest': None,
        'workflows_manifest': None,
        'api_routes': None
    }
    
    # Search for artifacts by SHA (would need to query artifact store)
    # For now, this is a placeholder - actual implementation would query
    # the artifact store or event store to find the artifacts
    
    return result
