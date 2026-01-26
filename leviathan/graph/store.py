"""
Graph store with projection builder.

The graph is a projection from the event journal.
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from leviathan.graph.schema import NodeType, EdgeType, NodeProperties, EdgeProperties, validate_node, validate_edge
from leviathan.graph.events import Event, EventType


class GraphStore:
    """
    Graph database that projects events into nodes and edges.
    
    Supports Postgres and in-memory backends.
    """
    
    def __init__(self, backend: str = "memory", postgres_url: Optional[str] = None):
        """
        Initialize graph store.
        
        Args:
            backend: "postgres" or "memory"
            postgres_url: PostgreSQL connection URL (if backend is postgres)
        """
        self.backend = backend
        self.postgres_url = postgres_url
        
        if backend == "memory":
            self.nodes: Dict[str, Dict[str, Any]] = {}
            self.edges: Dict[str, Dict[str, Any]] = {}
        elif backend == "postgres":
            if not postgres_url:
                raise ValueError("postgres_url required for postgres backend")
            import psycopg2
            self.conn = psycopg2.connect(postgres_url)
        else:
            raise ValueError(f"Unknown backend: {backend}")
    
    def upsert_node(self, node_id: str, node_type: NodeType, properties: Dict[str, Any]) -> NodeProperties:
        """
        Insert or update a node.
        
        Args:
            node_id: Unique node identifier
            node_type: Type of node
            properties: Node properties
            
        Returns:
            Validated node properties
        """
        # Enrich properties with node_id and created_at for validation
        enriched_properties = {
            'node_id': node_id,
            'created_at': properties.get('created_at', datetime.utcnow()),
            **properties
        }
        
        # Validate properties
        validated = validate_node(node_type, enriched_properties)
        
        if self.backend == "memory":
            self.nodes[node_id] = {
                'node_id': node_id,
                'node_type': node_type.value,
                'properties': validated.dict(),
                'created_at': properties.get('created_at', datetime.utcnow()),
                'updated_at': datetime.utcnow()
            }
        elif self.backend == "postgres":
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO nodes (node_id, node_type, properties, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (node_id) DO UPDATE
                    SET properties = EXCLUDED.properties, updated_at = EXCLUDED.updated_at
                """, (
                    node_id,
                    node_type.value,
                    json.dumps(validated.dict()),
                    properties.get('created_at', datetime.utcnow()),
                    datetime.utcnow()
                ))
            self.conn.commit()
        
        return validated
    
    def add_edge(self, edge_type: EdgeType, from_node: str, to_node: str, properties: Dict[str, Any] = None) -> EdgeProperties:
        """
        Add an edge between nodes.
        
        Args:
            edge_type: Type of edge
            from_node: Source node ID
            to_node: Target node ID
            properties: Additional edge properties
            
        Returns:
            Validated edge properties
        """
        if properties is None:
            properties = {}
        
        # Validate edge
        validated = validate_edge(edge_type, from_node, to_node, properties)
        
        if self.backend == "memory":
            self.edges[validated.edge_id] = {
                'edge_id': validated.edge_id,
                'edge_type': edge_type.value,
                'from_node': from_node,
                'to_node': to_node,
                'properties': properties,
                'created_at': validated.created_at
            }
        elif self.backend == "postgres":
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO edges (edge_id, edge_type, from_node, to_node, properties, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (edge_id) DO NOTHING
                """, (
                    validated.edge_id,
                    edge_type.value,
                    from_node,
                    to_node,
                    json.dumps(properties),
                    validated.created_at
                ))
            self.conn.commit()
        
        return validated
    
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node by ID."""
        if self.backend == "memory":
            return self.nodes.get(node_id)
        elif self.backend == "postgres":
            with self.conn.cursor() as cur:
                cur.execute("SELECT node_id, node_type, properties, created_at, updated_at FROM nodes WHERE node_id = %s", (node_id,))
                row = cur.fetchone()
                if row:
                    return {
                        'node_id': row[0],
                        'node_type': row[1],
                        'properties': json.loads(row[2]) if isinstance(row[2], str) else row[2],
                        'created_at': row[3],
                        'updated_at': row[4]
                    }
        return None
    
    def query_nodes(self, node_type: Optional[NodeType] = None, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Query nodes by type and filters.
        
        Args:
            node_type: Filter by node type
            filters: Additional filters on properties
            
        Returns:
            List of matching nodes
        """
        if self.backend == "memory":
            results = []
            for node in self.nodes.values():
                if node_type and node['node_type'] != node_type.value:
                    continue
                
                if filters:
                    props = node['properties']
                    match = all(props.get(k) == v for k, v in filters.items())
                    if not match:
                        continue
                
                results.append(node)
            return results
        
        elif self.backend == "postgres":
            query = "SELECT node_id, node_type, properties, created_at, updated_at FROM nodes WHERE 1=1"
            params = []
            
            if node_type:
                query += " AND node_type = %s"
                params.append(node_type.value)
            
            if filters:
                for key, value in filters.items():
                    query += " AND properties->>%s = %s"
                    params.extend([key, str(value)])
            
            results = []
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                for row in cur.fetchall():
                    results.append({
                        'node_id': row[0],
                        'node_type': row[1],
                        'properties': json.loads(row[2]) if isinstance(row[2], str) else row[2],
                        'created_at': row[3],
                        'updated_at': row[4]
                    })
            return results
    
    def clear(self):
        """
        Clear all nodes and edges from the graph.
        
        Used for idempotent rebuild from event journal.
        """
        if self.backend == "memory":
            self.nodes.clear()
            self.edges.clear()
        elif self.backend == "postgres":
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM edges")
                cur.execute("DELETE FROM nodes")
            self.conn.commit()
    
    def query_edges(self, from_node: Optional[str] = None, to_node: Optional[str] = None, edge_type: Optional[EdgeType] = None) -> List[Dict[str, Any]]:
        """Query edges."""
        if self.backend == "memory":
            results = []
            for edge in self.edges.values():
                if from_node and edge['from_node'] != from_node:
                    continue
                if to_node and edge['to_node'] != to_node:
                    continue
                if edge_type and edge['edge_type'] != edge_type.value:
                    continue
                results.append(edge)
            return results
        
        elif self.backend == "postgres":
            query = "SELECT edge_id, edge_type, from_node, to_node, properties, created_at FROM edges WHERE 1=1"
            params = []
            
            if from_node:
                query += " AND from_node = %s"
                params.append(from_node)
            if to_node:
                query += " AND to_node = %s"
                params.append(to_node)
            if edge_type:
                query += " AND edge_type = %s"
                params.append(edge_type.value)
            
            results = []
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                for row in cur.fetchall():
                    results.append({
                        'edge_id': row[0],
                        'edge_type': row[1],
                        'from_node': row[2],
                        'to_node': row[3],
                        'properties': json.loads(row[4]) if isinstance(row[4], str) else row[4],
                        'created_at': row[5]
                    })
            return results
    
    def apply_event(self, event: Event):
        """
        Apply an event to the graph projection.
        
        This is deterministic: same events always produce same graph state.
        """
        event_type = event.event_type
        payload = event.payload
        
        # Target events
        if event_type == EventType.TARGET_REGISTERED:
            self.upsert_node(
                node_id=payload['target_id'],
                node_type=NodeType.TARGET,
                properties=payload
            )
        
        # Task events
        elif event_type == EventType.TASK_CREATED:
            self.upsert_node(
                node_id=payload['task_id'],
                node_type=NodeType.TASK,
                properties=payload
            )
            # Add edge from task to target
            if 'target_id' in payload:
                self.add_edge(
                    edge_type=EdgeType.DEPENDS_ON,
                    from_node=payload['task_id'],
                    to_node=payload['target_id'],
                    properties={'created_at': event.timestamp}
                )
        
        # Attempt events
        elif event_type == EventType.ATTEMPT_CREATED:
            self.upsert_node(
                node_id=payload['attempt_id'],
                node_type=NodeType.ATTEMPT,
                properties=payload
            )
            # Link attempt to task
            if 'task_id' in payload:
                self.add_edge(
                    edge_type=EdgeType.DEPENDS_ON,
                    from_node=payload['attempt_id'],
                    to_node=payload['task_id'],
                    properties={'created_at': event.timestamp}
                )
        
        elif event_type in [EventType.ATTEMPT_STARTED, EventType.ATTEMPT_SUCCEEDED, EventType.ATTEMPT_FAILED]:
            # Update attempt node
            node = self.get_node(payload['attempt_id'])
            if node:
                props = node['properties']
                props.update(payload)
                self.upsert_node(
                    node_id=payload['attempt_id'],
                    node_type=NodeType.ATTEMPT,
                    properties=props
                )
        
        # Artifact events
        elif event_type == EventType.ARTIFACT_CREATED:
            self.upsert_node(
                node_id=payload['artifact_id'],
                node_type=NodeType.ARTIFACT,
                properties=payload
            )
            # Link artifact to attempt if specified
            if 'attempt_id' in payload:
                self.add_edge(
                    edge_type=EdgeType.PRODUCED,
                    from_node=payload['attempt_id'],
                    to_node=payload['artifact_id'],
                    properties={'created_at': event.timestamp}
                )
        
        # PR events
        elif event_type == EventType.PR_CREATED:
            # Generate node_id based on available fields
            if 'pr_number' in payload:
                node_id = f"pr-{payload['pr_number']}"
            elif 'pr_url' in payload and payload['pr_url']:
                # Hash pr_url for deterministic node_id
                import hashlib
                url_hash = hashlib.sha256(payload['pr_url'].encode()).hexdigest()[:12]
                node_id = f"pr-{url_hash}"
            else:
                # Fallback to event_id
                node_id = f"pr-{event.event_id[:12]}"
            
            self.upsert_node(
                node_id=node_id,
                node_type=NodeType.PULL_REQUEST,
                properties=payload
            )
            # Link PR to attempt
            if 'attempt_id' in payload:
                self.add_edge(
                    edge_type=EdgeType.PRODUCED,
                    from_node=payload['attempt_id'],
                    to_node=node_id,
                    properties={'created_at': event.timestamp}
                )
    
    def rebuild_projection(self, events: List[Event]):
        """
        Rebuild graph projection from events.
        
        This is deterministic and idempotent.
        """
        for event in events:
            self.apply_event(event)
    
    def close(self):
        """Close backend connections."""
        if self.backend == "postgres" and hasattr(self, 'conn'):
            self.conn.close()
