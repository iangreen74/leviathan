"""
Graph schema with strict typed primitives.

Defines node types, edge types, and validation schemas for the Leviathan control plane graph.
"""
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator


class NodeType(str, Enum):
    """Strict node types in the Leviathan graph."""
    TARGET = "Target"
    TASK = "Task"
    ATTEMPT = "Attempt"
    WORKSPACE = "Workspace"
    ARTIFACT = "Artifact"
    MODEL_CALL = "ModelCall"
    TEST_RUN = "TestRun"
    COMMIT = "Commit"
    PULL_REQUEST = "PullRequest"
    POLICY_SNAPSHOT = "PolicySnapshot"
    ACTOR = "Actor"
    DELEGATION = "Delegation"


class EdgeType(str, Enum):
    """Strict edge types representing relationships and authority."""
    DEPENDS_ON = "DEPENDS_ON"           # Task depends on another task
    PRODUCED = "PRODUCED"               # Attempt produced artifact/commit/PR
    RUNS_IN = "RUNS_IN"                 # Attempt runs in workspace
    AUTHORIZED_BY = "AUTHORIZED_BY"     # Action authorized by policy/delegation
    DELEGATES = "DELEGATES"             # Actor delegates authority to another
    INVALIDATES = "INVALIDATES"         # New attempt invalidates old one
    SUPPORTS = "SUPPORTS"               # Evidence supports a claim
    CONTESTS = "CONTESTS"               # Evidence contests a claim


class NodeProperties(BaseModel):
    """Base properties for all nodes."""
    node_id: str = Field(..., description="Unique node identifier")
    node_type: NodeType
    created_at: datetime
    created_by: Optional[str] = Field(None, description="Actor ID that created this node")
    
    class Config:
        use_enum_values = True


class TargetNode(NodeProperties):
    """Target repository node."""
    node_type: NodeType = NodeType.TARGET
    name: str
    repo_url: str
    default_branch: str
    contract_sha256: Optional[str] = None
    policy_sha256: Optional[str] = None


class TaskNode(NodeProperties):
    """Task node from backlog."""
    node_type: NodeType = NodeType.TASK
    target_id: str
    task_id: str
    title: str
    scope: str
    priority: str
    estimated_size: str
    allowed_paths: List[str]
    acceptance_criteria: List[str]
    status: str = Field("pending", description="pending, in_progress, completed, blocked, failed")


class AttemptNode(NodeProperties):
    """Attempt to execute a task."""
    node_type: NodeType = NodeType.ATTEMPT
    attempt_id: str
    task_id: str
    attempt_number: int
    status: str = Field("created", description="created, running, succeeded, failed, invalidated")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    failure_reason: Optional[str] = None


class WorkspaceNode(NodeProperties):
    """Ephemeral workspace for an attempt."""
    node_type: NodeType = NodeType.WORKSPACE
    workspace_id: str
    workspace_type: str = Field(..., description="worktree, clone, ephemeral")
    path: Optional[str] = None
    branch_name: Optional[str] = None
    destroyed_at: Optional[datetime] = None


class ArtifactNode(NodeProperties):
    """Content-addressed artifact."""
    node_type: NodeType = NodeType.ARTIFACT
    artifact_id: str
    sha256: str
    artifact_type: str = Field(..., description="log, test_output, diff, model_output, patch")
    size_bytes: int
    mime_type: Optional[str] = None
    storage_path: str


class ModelCallNode(NodeProperties):
    """LLM API call."""
    node_type: NodeType = NodeType.MODEL_CALL
    call_id: str
    model: str
    prompt_sha256: str
    response_sha256: str
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cost_usd: Optional[float] = None


class TestRunNode(NodeProperties):
    """Test execution."""
    node_type: NodeType = NodeType.TEST_RUN
    test_run_id: str
    scope: str
    passed: bool
    test_count: int
    failure_count: int
    output_sha256: str


class CommitNode(NodeProperties):
    """Git commit."""
    node_type: NodeType = NodeType.COMMIT
    commit_sha: str
    branch_name: str
    message: str
    author: str
    committed_at: datetime


class PullRequestNode(NodeProperties):
    """GitHub pull request."""
    node_type: NodeType = NodeType.PULL_REQUEST
    pr_number: int
    pr_url: str
    title: str
    state: str = Field(..., description="open, closed, merged")
    merged_at: Optional[datetime] = None


class PolicySnapshotNode(NodeProperties):
    """Immutable policy snapshot."""
    node_type: NodeType = NodeType.POLICY_SNAPSHOT
    policy_sha256: str
    version: str
    rules: Dict[str, Any]


class ActorNode(NodeProperties):
    """Actor (human, bot, service)."""
    node_type: NodeType = NodeType.ACTOR
    actor_id: str
    actor_type: str = Field(..., description="human, bot, service")
    name: str
    email: Optional[str] = None


class DelegationNode(NodeProperties):
    """Authority delegation."""
    node_type: NodeType = NodeType.DELEGATION
    delegation_id: str
    from_actor: str
    to_actor: str
    scope: str
    granted_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class EdgeProperties(BaseModel):
    """Base properties for all edges."""
    edge_id: str = Field(..., description="Unique edge identifier")
    edge_type: EdgeType
    from_node: str = Field(..., description="Source node ID")
    to_node: str = Field(..., description="Target node ID")
    created_at: datetime
    properties: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


# Node type registry for validation
NODE_TYPE_REGISTRY: Dict[NodeType, type[NodeProperties]] = {
    NodeType.TARGET: TargetNode,
    NodeType.TASK: TaskNode,
    NodeType.ATTEMPT: AttemptNode,
    NodeType.WORKSPACE: WorkspaceNode,
    NodeType.ARTIFACT: ArtifactNode,
    NodeType.MODEL_CALL: ModelCallNode,
    NodeType.TEST_RUN: TestRunNode,
    NodeType.COMMIT: CommitNode,
    NodeType.PULL_REQUEST: PullRequestNode,
    NodeType.POLICY_SNAPSHOT: PolicySnapshotNode,
    NodeType.ACTOR: ActorNode,
    NodeType.DELEGATION: DelegationNode,
}


def validate_node(node_type: NodeType, properties: Dict[str, Any]) -> NodeProperties:
    """
    Validate node properties against schema.
    
    Args:
        node_type: Type of node
        properties: Node properties dict
        
    Returns:
        Validated node properties
        
    Raises:
        ValueError: If validation fails
    """
    node_class = NODE_TYPE_REGISTRY.get(node_type)
    if not node_class:
        raise ValueError(f"Unknown node type: {node_type}")
    
    return node_class(**properties)


def validate_edge(edge_type: EdgeType, from_node: str, to_node: str, properties: Dict[str, Any]) -> EdgeProperties:
    """
    Validate edge properties.
    
    Args:
        edge_type: Type of edge
        from_node: Source node ID
        to_node: Target node ID
        properties: Additional edge properties
        
    Returns:
        Validated edge properties
    """
    edge_id = f"{from_node}:{edge_type.value}:{to_node}"
    
    return EdgeProperties(
        edge_id=edge_id,
        edge_type=edge_type,
        from_node=from_node,
        to_node=to_node,
        created_at=properties.get('created_at', datetime.utcnow()),
        properties=properties
    )
