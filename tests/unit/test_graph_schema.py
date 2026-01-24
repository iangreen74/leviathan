"""
Unit tests for graph schema validation.
"""
import pytest
from datetime import datetime

from leviathan.graph.schema import (
    NodeType, EdgeType, 
    TargetNode, TaskNode, AttemptNode, ArtifactNode,
    validate_node, validate_edge,
    NODE_TYPE_REGISTRY
)


class TestSchemaValidation:
    """Test schema validation for nodes and edges."""
    
    def test_target_node_validation(self):
        """TargetNode should validate required fields."""
        node = TargetNode(
            node_id="radix",
            created_at=datetime.utcnow(),
            name="radix",
            repo_url="git@github.com:iangreen74/radix.git",
            default_branch="main"
        )
        
        assert node.node_type == NodeType.TARGET
        assert node.name == "radix"
        assert node.repo_url == "git@github.com:iangreen74/radix.git"
    
    def test_task_node_validation(self):
        """TaskNode should validate required fields."""
        node = TaskNode(
            node_id="task-001",
            created_at=datetime.utcnow(),
            target_id="radix",
            task_id="task-001",
            title="Test task",
            scope="services",
            priority="high",
            estimated_size="medium",
            allowed_paths=["services/api/"],
            acceptance_criteria=["Tests pass"]
        )
        
        assert node.node_type == NodeType.TASK
        assert node.task_id == "task-001"
        assert node.status == "pending"  # default
    
    def test_attempt_node_validation(self):
        """AttemptNode should validate required fields."""
        node = AttemptNode(
            node_id="attempt-001",
            created_at=datetime.utcnow(),
            attempt_id="attempt-001",
            task_id="task-001",
            attempt_number=1
        )
        
        assert node.node_type == NodeType.ATTEMPT
        assert node.status == "created"  # default
        assert node.attempt_number == 1
    
    def test_artifact_node_validation(self):
        """ArtifactNode should validate required fields."""
        node = ArtifactNode(
            node_id="artifact-001",
            created_at=datetime.utcnow(),
            artifact_id="artifact-001",
            sha256="a" * 64,
            artifact_type="log",
            size_bytes=1024,
            storage_path="/path/to/artifact"
        )
        
        assert node.node_type == NodeType.ARTIFACT
        assert node.sha256 == "a" * 64
        assert node.size_bytes == 1024
    
    def test_validate_node_function(self):
        """validate_node should return correct node class."""
        props = {
            'node_id': 'test',
            'created_at': datetime.utcnow(),
            'name': 'test',
            'repo_url': 'test',
            'default_branch': 'main'
        }
        
        node = validate_node(NodeType.TARGET, props)
        
        assert isinstance(node, TargetNode)
        assert node.name == 'test'
    
    def test_validate_node_missing_field(self):
        """validate_node should raise error for missing required field."""
        props = {
            'node_id': 'test',
            'created_at': datetime.utcnow(),
            'name': 'test'
            # Missing repo_url and default_branch
        }
        
        with pytest.raises(Exception):  # Pydantic ValidationError
            validate_node(NodeType.TARGET, props)
    
    def test_validate_node_unknown_type(self):
        """validate_node should raise error for unknown node type."""
        with pytest.raises(ValueError, match="Unknown node type"):
            validate_node("InvalidType", {})
    
    def test_edge_validation(self):
        """validate_edge should create valid edge."""
        edge = validate_edge(
            edge_type=EdgeType.DEPENDS_ON,
            from_node="task-001",
            to_node="target-001",
            properties={'created_at': datetime.utcnow()}
        )
        
        assert edge.edge_type == EdgeType.DEPENDS_ON
        assert edge.from_node == "task-001"
        assert edge.to_node == "target-001"
        assert edge.edge_id == "task-001:DEPENDS_ON:target-001"
    
    def test_node_type_enum_values(self):
        """NodeType enum should have all expected values."""
        expected_types = [
            "Target", "Task", "Attempt", "Workspace", "Artifact",
            "ModelCall", "TestRun", "Commit", "PullRequest",
            "PolicySnapshot", "Actor", "Delegation"
        ]
        
        for expected in expected_types:
            assert expected in [t.value for t in NodeType]
    
    def test_edge_type_enum_values(self):
        """EdgeType enum should have all expected values."""
        expected_types = [
            "DEPENDS_ON", "PRODUCED", "RUNS_IN", "AUTHORIZED_BY",
            "DELEGATES", "INVALIDATES", "SUPPORTS", "CONTESTS"
        ]
        
        for expected in expected_types:
            assert expected in [t.value for t in EdgeType]
    
    def test_node_registry_completeness(self):
        """NODE_TYPE_REGISTRY should have entry for each NodeType."""
        for node_type in NodeType:
            assert node_type in NODE_TYPE_REGISTRY
            assert NODE_TYPE_REGISTRY[node_type] is not None
