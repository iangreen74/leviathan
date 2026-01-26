"""
Unit tests for backlog synthesis module.
"""
import pytest
import yaml
from pathlib import Path

from leviathan.synthesis.backlog_synth import BacklogSynthesizer


class TestBacklogSynthesizer:
    """Test backlog task synthesis."""
    
    @pytest.fixture
    def synthesizer(self):
        """Create synthesizer without model client."""
        return BacklogSynthesizer(model_client=None)
    
    @pytest.fixture
    def sample_repo_manifest(self):
        """Sample repository manifest."""
        return {
            'target_id': 'radix',
            'repo_url': 'git@github.com:test/radix.git',
            'commit_sha': 'abc123',
            'default_branch': 'main',
            'indexed_at': '2026-01-25T23:00:00Z',
            'counts': {
                'total_files': 1481,
                'by_type': {
                    'python': 450,
                    'markdown': 367,
                    'yaml': 89,
                    'json': 45
                },
                'docs': 367,
                'workflows': 21,
                'api_routes': 29
            }
        }
    
    @pytest.fixture
    def sample_policy(self):
        """Sample policy constraints."""
        return {
            'allowed_paths': [
                '.leviathan/*',
                'services/*',
                'tests/*',
                'docs/*'
            ],
            'forbidden_paths': [
                'secrets/*',
                '.env',
                'credentials/*'
            ]
        }
    
    def test_generate_basic_tasks(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test basic task generation without LLM."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        # Should generate at least 5 tasks (one per track)
        assert len(tasks) >= 5
        
        # Check task structure
        for task in tasks:
            assert 'id' in task
            assert 'title' in task
            assert 'scope' in task
            assert 'priority' in task
            assert 'ready' in task
            assert 'allowed_paths' in task
            assert 'acceptance_criteria' in task
            assert 'dependencies' in task
            assert 'estimated_size' in task
            
            # Check ID prefix
            assert task['id'].startswith('radix-')
            
            # Check valid values
            assert task['scope'] in {'docs', 'tests', 'services', 'infra', 'bootstrap', 'core'}
            assert task['priority'] in {'high', 'medium', 'low'}
            assert task['estimated_size'] in {'small', 'medium', 'large'}
    
    def test_unique_task_ids(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that generated task IDs are unique."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        task_ids = [task['id'] for task in tasks]
        assert len(task_ids) == len(set(task_ids)), "Task IDs must be unique"
    
    def test_at_most_one_ready_task(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that at most one task is marked ready:true."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        ready_tasks = [task for task in tasks if task.get('ready', False)]
        assert len(ready_tasks) <= 1, "At most one task should be ready:true"
    
    def test_no_duplicate_ids_with_existing_backlog(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that new tasks don't duplicate existing task IDs."""
        current_backlog = [
            {
                'id': 'radix-dataset-schema-v1',
                'title': 'Existing task',
                'scope': 'core',
                'priority': 'high',
                'ready': False,
                'allowed_paths': [],
                'acceptance_criteria': [],
                'dependencies': [],
                'estimated_size': 'small'
            }
        ]
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        # Should not include the existing task ID
        task_ids = [task['id'] for task in tasks]
        assert 'radix-dataset-schema-v1' not in task_ids
    
    def test_validate_paths_against_policy(self, synthesizer):
        """Test path validation against policy constraints."""
        allowed_paths = {'.leviathan/*', 'services/*', 'tests/*'}
        forbidden_paths = {'secrets/*', '.env'}
        
        # Valid paths
        assert synthesizer._validate_paths(
            ['.leviathan/schemas/dataset.yaml'],
            allowed_paths,
            forbidden_paths
        )
        
        assert synthesizer._validate_paths(
            ['services/dataset/api.py'],
            allowed_paths,
            forbidden_paths
        )
        
        # Invalid: forbidden path
        assert not synthesizer._validate_paths(
            ['secrets/api_key.txt'],
            allowed_paths,
            forbidden_paths
        )
        
        # Invalid: not in allowed paths
        assert not synthesizer._validate_paths(
            ['src/main.py'],
            allowed_paths,
            forbidden_paths
        )
    
    def test_path_pattern_matching(self, synthesizer):
        """Test wildcard path pattern matching."""
        # Exact match
        assert synthesizer._path_matches_pattern('test.py', 'test.py')
        
        # Prefix match
        assert synthesizer._path_matches_pattern('services/api.py', 'services')
        
        # Wildcard match
        assert synthesizer._path_matches_pattern('services/dataset/api.py', 'services/*')
        assert synthesizer._path_matches_pattern('.leviathan/schemas/test.yaml', '.leviathan/*')
        
        # No match
        assert not synthesizer._path_matches_pattern('src/main.py', 'services/*')
    
    def test_task_tracks_coverage(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that tasks cover all required tracks."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        task_ids = [task['id'] for task in tasks]
        
        # Check for tasks from each track
        tracks = {
            'dataset': any('dataset' in tid for tid in task_ids),
            'research': any('research' in tid for tid in task_ids),
            'experiment': any('experiment' in tid for tid in task_ids),
            'evidence': any('evidence' in tid for tid in task_ids),
            'answer': any('answer' in tid for tid in task_ids)
        }
        
        # Should have tasks from multiple tracks
        assert sum(tracks.values()) >= 3, "Should have tasks from at least 3 tracks"
    
    def test_dependency_chain(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that dependencies form valid chains."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        task_ids = {task['id'] for task in tasks}
        
        # Check that all dependencies reference valid task IDs
        for task in tasks:
            for dep_id in task.get('dependencies', []):
                # Dependency should either be in the new tasks or existing backlog
                assert dep_id in task_ids or dep_id.startswith('radix-'), \
                    f"Invalid dependency: {dep_id} for task {task['id']}"
    
    def test_yaml_serialization(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that generated tasks can be serialized to valid YAML."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        # Should be able to serialize to YAML
        yaml_str = yaml.dump({'tasks': tasks}, default_flow_style=False)
        
        # Should be able to parse back
        parsed = yaml.safe_load(yaml_str)
        assert 'tasks' in parsed
        assert len(parsed['tasks']) == len(tasks)
    
    def test_only_leviathan_paths_modified(self, synthesizer, sample_repo_manifest, sample_policy):
        """Test that proposed tasks only modify .leviathan/ or new service stubs."""
        current_backlog = []
        
        tasks = synthesizer.synthesize_tasks(
            repo_manifest=sample_repo_manifest,
            workflows_manifest=None,
            api_routes=None,
            current_backlog=current_backlog,
            policy=sample_policy,
            target_id='radix'
        )
        
        # Check that all allowed_paths are either:
        # 1. Under .leviathan/
        # 2. Under services/ (new stubs)
        # 3. Under tests/
        # 4. Under docs/
        for task in tasks:
            for path in task.get('allowed_paths', []):
                assert (
                    path.startswith('.leviathan/') or
                    path.startswith('services/') or
                    path.startswith('tests/') or
                    path.startswith('docs/')
                ), f"Task {task['id']} has invalid path: {path}"
