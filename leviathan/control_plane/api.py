"""
Leviathan Graph Control Plane API.

FastAPI application for event ingestion and graph queries.

Usage:
    export LEVIATHAN_CONTROL_PLANE_TOKEN=your-secret-token
    python3 -m leviathan.control_plane.api
"""
import sys
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import uvicorn

from leviathan.control_plane.config import get_config, ControlPlaneConfig
from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.graph.schema import NodeType, EdgeType
from leviathan.artifacts.store import ArtifactStore


# Pydantic models for API requests/responses

class ArtifactRef(BaseModel):
    """Reference to an artifact in an event bundle."""
    sha256: str
    kind: str
    uri: str
    size: int


class EventIngestRequest(BaseModel):
    """Request model for event ingestion."""
    target: str
    bundle_id: str
    events: List[Dict[str, Any]]
    artifacts: Optional[List[ArtifactRef]] = None


class EventIngestResponse(BaseModel):
    """Response model for event ingestion."""
    ingested: int
    bundle_id: str
    status: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str


class EventSummary(BaseModel):
    """Summary of an event."""
    event_id: str
    timestamp: str
    event_type: str
    actor_id: Optional[str]
    target: Optional[str]
    attempt_id: Optional[str]


class GraphSummaryResponse(BaseModel):
    """Graph summary response."""
    nodes_by_type: Dict[str, int]
    edges_by_type: Dict[str, int]
    recent_events: List[EventSummary]


class AttemptResponse(BaseModel):
    """Attempt details response."""
    attempt_node: Optional[Dict[str, Any]]
    events: List[Dict[str, Any]]
    artifacts: List[Dict[str, Any]]


class AttemptsListResponse(BaseModel):
    """List of attempts response."""
    attempts: List[Dict[str, Any]]
    count: int


class FailuresListResponse(BaseModel):
    """List of failures response."""
    failures: List[Dict[str, Any]]
    count: int


class InvalidateRequest(BaseModel):
    """Request to invalidate an attempt."""
    reason: str


class InvalidateResponse(BaseModel):
    """Response for invalidation."""
    status: str
    attempt_id: str


class BacklogSuggestRequest(BaseModel):
    """Request to generate backlog suggestions."""
    target: str


class BacklogSuggestResponse(BaseModel):
    """Response for backlog suggestion."""
    status: str
    attempt_id: Optional[str] = None
    pr_url: Optional[str] = None
    tasks_proposed: Optional[int] = None
    message: Optional[str] = None


# Global state (initialized on startup)
config: Optional[ControlPlaneConfig] = None
event_store: Optional[EventStore] = None
graph_store: Optional[GraphStore] = None
artifact_store: Optional[ArtifactStore] = None


def reset_stores():
    """Reset global store state (for tests)."""
    global config, event_store, graph_store, artifact_store
    
    if event_store:
        try:
            event_store.close()
        except:
            pass
    if graph_store:
        try:
            graph_store.close()
        except:
            pass
    
    config = None
    event_store = None
    graph_store = None
    artifact_store = None


def initialize_stores(ndjson_dir: Optional[str] = None, artifacts_dir: Optional[str] = None):
    """
    Initialize stores (called on startup or lazily).
    
    Args:
        ndjson_dir: Optional override for NDJSON storage directory (for tests)
        artifacts_dir: Optional override for artifacts directory (for tests)
    """
    global config, event_store, graph_store, artifact_store
    
    if event_store is not None:
        return  # Already initialized
    
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Set LEVIATHAN_CONTROL_PLANE_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)
    
    # Initialize stores based on backend
    if config.backend == "postgres":
        event_store = EventStore(backend="postgres", postgres_url=config.postgres_url)
        graph_store = GraphStore(backend="postgres", postgres_url=config.postgres_url)
    else:
        # Use override directory for tests, or default from config
        store_dir = ndjson_dir if ndjson_dir else config.ndjson_dir
        event_store = EventStore(backend="ndjson", ndjson_dir=store_dir)
        graph_store = GraphStore(backend="memory")
    
    # Use override directory for tests, or default from config
    artifact_root = artifacts_dir if artifacts_dir else config.artifacts_dir
    # Convert to Path if string
    if isinstance(artifact_root, str):
        from pathlib import Path
        artifact_root = Path(artifact_root)
    artifact_store = ArtifactStore(storage_root=artifact_root)
    
    print(f"Leviathan Control Plane API initialized")
    print(f"Backend: {config.backend}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    initialize_stores()
    
    yield
    
    # Shutdown
    if event_store:
        event_store.close()
    if graph_store:
        graph_store.close()


# FastAPI app
app = FastAPI(
    title="Leviathan Graph Control Plane API",
    description="Event ingestion and graph query API for Leviathan",
    version="1.0.0",
    lifespan=lifespan
)

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Verify bearer token.
    
    Raises:
        HTTPException: 401 if token is invalid
    """
    # Lazy initialization for tests
    if not config:
        initialize_stores()
    
    if credentials.credentials != config.token:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    return credentials.credentials


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    """Health check endpoint."""
    return HealthResponse(status="ok")


@app.post("/v1/events/ingest", response_model=EventIngestResponse)
async def ingest_events(
    request: EventIngestRequest,
    token: str = Depends(verify_token)
):
    """
    Ingest event bundle from executor.
    
    Args:
        request: Event bundle with events and optional artifact references
        token: Verified bearer token
        
    Returns:
        Ingestion confirmation
    """
    if not event_store or not graph_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    ingested_count = 0
    
    # Append events to event store
    for event_data in request.events:
        try:
            # Convert dict to Event object
            event = Event(**event_data)
            
            # Append to event store (hash chain computed automatically)
            event_store.append_event(event)
            
            # Apply to graph projection
            graph_store.apply_event(event)
            
            ingested_count += 1
        except Exception as e:
            print(f"Error ingesting event {event_data.get('event_id', 'unknown')}: {e}")
            print(f"Event data: {event_data}")
            # Continue processing other events instead of failing entire bundle
            continue
    
    # Record artifact references if present
    if request.artifacts and artifact_store:
        for artifact_ref in request.artifacts:
            # Artifact metadata already stored by executor
            # We just validate it exists
            if not artifact_store.exists(artifact_ref.sha256):
                print(f"Warning: artifact {artifact_ref.sha256} not found in store")
    
    return EventIngestResponse(
        ingested=ingested_count,
        bundle_id=request.bundle_id,
        status="ok"
    )


@app.get("/v1/graph/summary", response_model=GraphSummaryResponse)
async def graph_summary(token: str = Depends(verify_token)):
    """
    Get graph summary with node/edge counts and recent events.
    
    Args:
        token: Verified bearer token
        
    Returns:
        Graph summary
    """
    if not event_store or not graph_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # Count nodes by type
    nodes_by_type = {}
    for node_type in NodeType:
        count = len(graph_store.query_nodes(node_type=node_type))
        if count > 0:
            nodes_by_type[node_type.value] = count
    
    # Count edges by type
    edges_by_type = {}
    for edge_type in EdgeType:
        count = len(graph_store.query_edges(edge_type=edge_type))
        if count > 0:
            edges_by_type[edge_type.value] = count
    
    # Get last 20 events
    all_events = event_store.get_events()
    recent_events_data = all_events[-20:] if len(all_events) > 20 else all_events
    
    recent_events = []
    for event in reversed(recent_events_data):  # Most recent first
        recent_events.append(EventSummary(
            event_id=event.event_id,
            timestamp=event.timestamp.isoformat(),
            event_type=event.event_type,
            actor_id=event.actor_id,
            target=event.payload.get('target_id'),
            attempt_id=event.payload.get('attempt_id')
        ))
    
    return GraphSummaryResponse(
        nodes_by_type=nodes_by_type,
        edges_by_type=edges_by_type,
        recent_events=recent_events
    )


@app.get("/v1/attempts", response_model=AttemptsListResponse)
async def list_attempts(
    target: Optional[str] = None,
    limit: int = 10,
    token: str = Depends(verify_token)
):
    """
    List recent attempts, optionally filtered by target.
    
    Args:
        target: Optional target name filter
        limit: Maximum number of attempts to return
        token: Verified bearer token
        
    Returns:
        List of attempts
    """
    if not graph_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # Query attempt nodes
    attempt_nodes = graph_store.query_nodes(node_type=NodeType.ATTEMPT)
    
    # Filter by target if specified
    if target:
        attempt_nodes = [n for n in attempt_nodes if n.get('properties', {}).get('target') == target]
    
    # Sort by timestamp (most recent first)
    attempt_nodes.sort(
        key=lambda n: n.get('properties', {}).get('timestamp', ''),
        reverse=True
    )
    
    # Limit results
    attempt_nodes = attempt_nodes[:limit]
    
    # Format response
    attempts = []
    for node in attempt_nodes:
        props = node.get('properties', {})
        attempts.append({
            'attempt_id': node.get('node_id'),
            'task_id': props.get('task_id'),
            'target': props.get('target'),
            'status': props.get('status'),
            'timestamp': props.get('timestamp'),
            'pr_url': props.get('pr_url'),
            'pr_number': props.get('pr_number')
        })
    
    return AttemptsListResponse(attempts=attempts, count=len(attempts))


@app.get("/v1/attempts/{attempt_id}", response_model=AttemptResponse)
async def get_attempt(
    attempt_id: str,
    token: str = Depends(verify_token)
):
    """
    Get attempt details including node, events, and artifacts.
    
    Args:
        attempt_id: Attempt identifier
        token: Verified bearer token
        
    Returns:
        Attempt details
    """
    if not event_store or not graph_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # Get attempt node
    attempt_node = graph_store.get_node(attempt_id)
    
    # Get related events
    all_events = event_store.get_events()
    related_events = [
        {
            'event_id': e.event_id,
            'event_type': e.event_type,
            'timestamp': e.timestamp.isoformat(),
            'actor_id': e.actor_id,
            'payload': e.payload
        }
        for e in all_events
        if e.payload.get('attempt_id') == attempt_id
    ]
    
    # Get related artifacts (via PRODUCED edges)
    artifact_edges = graph_store.query_edges(from_node=attempt_id, edge_type=EdgeType.PRODUCED)
    artifacts = []
    for edge in artifact_edges:
        artifact_node = graph_store.get_node(edge['to_node'])
        if artifact_node:
            artifacts.append(artifact_node)
    
    return AttemptResponse(
        attempt_node=attempt_node,
        events=related_events,
        artifacts=artifacts
    )


@app.get("/v1/failures", response_model=FailuresListResponse)
async def list_failures(
    target: Optional[str] = None,
    limit: int = 10,
    token: str = Depends(verify_token)
):
    """
    List recent failures, optionally filtered by target.
    
    Args:
        target: Optional target name filter
        limit: Maximum number of failures to return
        token: Verified bearer token
        
    Returns:
        List of failures
    """
    if not event_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # Get all events and filter for failures
    all_events = event_store.get_events()
    failure_events = [
        e for e in all_events
        if e.event_type in ['attempt.failed', 'task.failed']
    ]
    
    # Filter by target if specified
    if target:
        failure_events = [
            e for e in failure_events
            if e.payload.get('target') == target or e.payload.get('target_id') == target
        ]
    
    # Sort by timestamp (most recent first)
    failure_events.sort(key=lambda e: e.timestamp, reverse=True)
    
    # Limit results
    failure_events = failure_events[:limit]
    
    # Format response
    failures = []
    for event in failure_events:
        failures.append({
            'attempt_id': event.payload.get('attempt_id'),
            'task_id': event.payload.get('task_id'),
            'target': event.payload.get('target') or event.payload.get('target_id'),
            'error': event.payload.get('error') or event.payload.get('reason'),
            'timestamp': event.timestamp.isoformat()
        })
    
    return FailuresListResponse(failures=failures, count=len(failures))


@app.post("/v1/attempts/{attempt_id}/invalidate", response_model=InvalidateResponse)
async def invalidate_attempt(
    attempt_id: str,
    request: InvalidateRequest,
    token: str = Depends(verify_token)
):
    """
    Invalidate an attempt (mark as invalid for retry).
    
    Args:
        attempt_id: Attempt identifier
        request: Invalidation request with reason
        token: Verified bearer token
        
    Returns:
        Invalidation confirmation
    """
    if not graph_store or not event_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # Check if attempt exists
    attempt_node = graph_store.get_node(attempt_id)
    if not attempt_node:
        raise HTTPException(status_code=404, detail=f"Attempt {attempt_id} not found")
    
    # Update attempt node status
    props = attempt_node.get('properties', {})
    props['status'] = 'invalidated'
    props['invalidation_reason'] = request.reason
    props['invalidated_at'] = datetime.utcnow().isoformat()
    
    graph_store.add_node(
        node_id=attempt_id,
        node_type=NodeType.ATTEMPT,
        properties=props
    )
    
    # Create invalidation event
    invalidation_event = Event(
        event_id=f"invalidation-{attempt_id}-{datetime.utcnow().timestamp()}",
        timestamp=datetime.utcnow(),
        event_type='attempt.invalidated',
        actor_id='operator',
        payload={
            'attempt_id': attempt_id,
            'reason': request.reason
        }
    )
    event_store.append(invalidation_event)
    
    return InvalidateResponse(
        status='invalidated',
        attempt_id=attempt_id
    )


@app.post("/v1/backlog/suggest", response_model=BacklogSuggestResponse)
async def backlog_suggest(
    request: BacklogSuggestRequest,
    token: str = Depends(verify_token)
):
    """
    Generate backlog task proposals for a target.
    
    This endpoint triggers a backlog synthesis process that:
    1. Finds the most recent successful bootstrap attempt for the target
    2. Loads bootstrap artifacts (repo_manifest, workflows, api_routes)
    3. Loads current backlog and policy from target repo
    4. Generates proposed tasks using LLM
    5. Creates a PR with the proposed tasks
    
    Args:
        request: Backlog suggestion request with target name
        token: Verified bearer token
        
    Returns:
        Backlog suggestion response with attempt ID and PR URL
    """
    if not event_store or not graph_store:
        raise HTTPException(status_code=500, detail="Stores not initialized")
    
    # This is a placeholder - full implementation would:
    # 1. Query graph for most recent successful bootstrap attempt
    # 2. Load artifacts from artifact store
    # 3. Clone target repo to get current backlog/policy
    # 4. Run BacklogSynthesizer
    # 5. Create PR with proposed tasks
    # 6. Return response with PR URL
    
    return BacklogSuggestResponse(
        status='not_implemented',
        message='Backlog synthesis endpoint is a placeholder. Full implementation requires scheduler integration.'
    )


def main():
    """Run the API server."""
    # Load config to get host/port
    try:
        cfg = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        print("Set LEVIATHAN_CONTROL_PLANE_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)
    
    uvicorn.run(
        "leviathan.control_plane.api:app",
        host=cfg.host,
        port=cfg.port,
        reload=False
    )


if __name__ == "__main__":
    main()
