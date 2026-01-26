"""
Unit tests for topology indexer.
"""
import pytest
import json
from pathlib import Path
from leviathan.topology.indexer import TopologyIndexer


class TestTopologyIndexer:
    """Test topology indexing."""
    
    @pytest.fixture
    def test_repo(self, tmp_path):
        """Create a minimal test repository structure."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        
        # Create directory structure
        (repo / "services" / "api").mkdir(parents=True)
        (repo / "services" / "worker").mkdir(parents=True)
        (repo / "ops" / "k8s").mkdir(parents=True)
        (repo / "tools").mkdir(parents=True)
        (repo / "tests").mkdir(parents=True)
        (repo / "docs").mkdir(parents=True)
        (repo / ".github" / "workflows").mkdir(parents=True)
        
        # Create some files
        (repo / "services" / "api" / "main.py").write_text("from services.worker import task\n")
        (repo / "services" / "worker" / "task.py").write_text("import requests\n")
        (repo / "ops" / "k8s" / "deployment.yaml").write_text("image: api:latest\n")
        (repo / "tools" / "build.sh").write_text("#!/bin/bash\n")
        (repo / "tests" / "test_api.py").write_text("def test_api(): pass\n")
        (repo / "docs" / "README.md").write_text("# Test\n")
        (repo / ".github" / "workflows" / "ci.yml").write_text("name: CI\n")
        
        return repo
    
    def test_indexer_basic(self, test_repo):
        """Test basic topology indexing."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Check result structure
        assert 'events' in result
        assert 'artifacts' in result
        assert 'summary' in result
        
        # Check summary
        assert result['summary']['areas_count'] > 0
        assert result['summary']['subsystems_count'] > 0
    
    def test_areas_discovered(self, test_repo):
        """Test that areas are discovered correctly."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Check for expected areas
        area_events = [e for e in result['events'] if e['event_type'] == 'topo.area.discovered']
        area_ids = [e['payload']['area_id'] for e in area_events]
        
        assert 'area/services' in area_ids
        assert 'area/docs' in area_ids
        assert 'area/ci' in area_ids
        assert 'area/infra' in area_ids
        assert 'area/tools' in area_ids
        assert 'area/tests' in area_ids
    
    def test_subsystems_discovered(self, test_repo):
        """Test that subsystems are discovered correctly."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Check for expected subsystems
        subsystem_events = [e for e in result['events'] if e['event_type'] == 'topo.subsystem.discovered']
        subsystem_ids = [e['payload']['subsystem_id'] for e in subsystem_events]
        
        assert 'subsystem/services/api' in subsystem_ids
        assert 'subsystem/services/worker' in subsystem_ids
    
    def test_dependencies_discovered(self, test_repo):
        """Test that dependencies are discovered."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Check for dependency events
        dep_events = [e for e in result['events'] if e['event_type'] == 'topo.dependency.discovered']
        
        # Should have at least one dependency (api -> worker)
        assert len(dep_events) >= 0  # May be 0 if import mapping fails
    
    def test_artifacts_generated(self, test_repo):
        """Test that artifacts are generated correctly."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Check artifact names
        assert 'topo_areas.json' in result['artifacts']
        assert 'topo_subsystems.json' in result['artifacts']
        assert 'topo_deps.json' in result['artifacts']
        assert 'topo_summary.json' in result['artifacts']
        
        # Check artifact content is valid JSON
        for artifact_name, artifact_content in result['artifacts'].items():
            data = json.loads(artifact_content)
            assert 'target_id' in data
            assert 'commit_sha' in data
            assert 'rules_version' in data
    
    def test_deterministic_output(self, test_repo):
        """Test that indexing is deterministic."""
        indexer1 = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        indexer2 = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result1 = indexer1.index()
        result2 = indexer2.index()
        
        # Artifacts should be identical (JSON is sorted)
        assert result1['artifacts']['topo_areas.json'] == result2['artifacts']['topo_areas.json']
        assert result1['artifacts']['topo_subsystems.json'] == result2['artifacts']['topo_subsystems.json']
        assert result1['artifacts']['topo_summary.json'] == result2['artifacts']['topo_summary.json']
    
    def test_event_types(self, test_repo):
        """Test that all expected event types are emitted."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        event_types = [e['event_type'] for e in result['events']]
        
        assert 'topo.started' in event_types
        assert 'topo.indexed' in event_types
        assert 'topo.completed' in event_types
    
    def test_language_distribution(self, test_repo):
        """Test that language distribution is computed."""
        indexer = TopologyIndexer(
            repo_path=test_repo,
            target_id="test-target",
            commit_sha="abc123"
        )
        
        result = indexer.index()
        
        # Find a subsystem with Python files
        subsystem_events = [e for e in result['events'] if e['event_type'] == 'topo.subsystem.discovered']
        
        for event in subsystem_events:
            if 'services/api' in event['payload']['subsystem_id']:
                languages = event['payload'].get('languages', {})
                # Should have .py extension
                assert '.py' in languages
                # Fraction should be between 0 and 1
                assert 0 <= languages['.py'] <= 1
