"""
Minimal CLI demo for Leviathan Graph Control Plane.

Demonstrates:
- Appending events with hash chain
- Rebuilding graph projection
- Querying nodes and edges

Usage:
    python -m leviathan.graph.demo [--backend ndjson|postgres] [--postgres-url URL]
"""
import argparse
import uuid
from datetime import datetime

from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.graph.schema import NodeType, EdgeType
from leviathan.artifacts.store import ArtifactStore


def demo_ndjson():
    """Demo with NDJSON backend (local dev)."""
    print("Leviathan Graph Control Plane - NDJSON Demo")
    print("=" * 60)
    
    # Initialize stores
    event_store = EventStore(backend="ndjson")
    graph_store = GraphStore(backend="memory")
    artifact_store = ArtifactStore()
    
    print("\n1. Appending events with hash chain...")
    
    # Event 1: Register target
    event1 = Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TARGET_REGISTERED,
        timestamp=datetime.utcnow(),
        actor_id="system",
        payload={
            'target_id': 'radix',
            'node_id': 'radix',
            'node_type': 'Target',
            'name': 'radix',
            'repo_url': 'git@github.com:iangreen74/radix.git',
            'default_branch': 'main',
            'created_at': datetime.utcnow().isoformat()
        }
    )
    event1 = event_store.append_event(event1)
    print(f"   ✅ Event 1: {event1.event_type} (hash: {event1.hash[:8]}...)")
    
    # Event 2: Create task
    event2 = Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TASK_CREATED,
        timestamp=datetime.utcnow(),
        actor_id="system",
        payload={
            'task_id': 'task-001',
            'node_id': 'task-001',
            'node_type': 'Task',
            'target_id': 'radix',
            'title': 'Implement feature X',
            'scope': 'services',
            'priority': 'high',
            'estimated_size': 'medium',
            'allowed_paths': ['services/api/'],
            'acceptance_criteria': ['Tests pass', 'Code reviewed'],
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
    )
    event2 = event_store.append_event(event2)
    print(f"   ✅ Event 2: {event2.event_type} (hash: {event2.hash[:8]}..., prev: {event2.prev_hash[:8]}...)")
    
    # Event 3: Create attempt
    event3 = Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.ATTEMPT_CREATED,
        timestamp=datetime.utcnow(),
        actor_id="scheduler",
        payload={
            'attempt_id': 'attempt-001',
            'node_id': 'attempt-001',
            'node_type': 'Attempt',
            'task_id': 'task-001',
            'attempt_number': 1,
            'status': 'created',
            'created_at': datetime.utcnow().isoformat()
        }
    )
    event3 = event_store.append_event(event3)
    print(f"   ✅ Event 3: {event3.event_type} (hash: {event3.hash[:8]}..., prev: {event3.prev_hash[:8]}...)")
    
    print("\n2. Verifying hash chain integrity...")
    is_valid, error = event_store.verify_chain()
    if is_valid:
        print("   ✅ Hash chain is valid")
    else:
        print(f"   ❌ Hash chain invalid: {error}")
    
    print("\n3. Rebuilding graph projection from events...")
    events = event_store.get_events()
    graph_store.rebuild_projection(events)
    print(f"   ✅ Applied {len(events)} events to graph")
    
    print("\n4. Querying graph...")
    
    # Count nodes by type
    targets = graph_store.query_nodes(node_type=NodeType.TARGET)
    tasks = graph_store.query_nodes(node_type=NodeType.TASK)
    attempts = graph_store.query_nodes(node_type=NodeType.ATTEMPT)
    
    print(f"   Nodes:")
    print(f"     - Targets: {len(targets)}")
    print(f"     - Tasks: {len(tasks)}")
    print(f"     - Attempts: {len(attempts)}")
    
    # Count edges
    all_edges = graph_store.query_edges()
    print(f"   Edges: {len(all_edges)}")
    
    # Show edge details
    for edge in all_edges:
        print(f"     - {edge['from_node']} --[{edge['edge_type']}]--> {edge['to_node']}")
    
    print("\n5. Testing artifact store...")
    test_content = b"Test log output\nLine 2\nLine 3"
    artifact_meta = artifact_store.store(test_content, "log", {"source": "demo"})
    print(f"   ✅ Stored artifact: {artifact_meta['sha256'][:16]}... ({artifact_meta['size_bytes']} bytes)")
    
    # Retrieve and verify
    retrieved = artifact_store.retrieve(artifact_meta['sha256'])
    if retrieved == test_content:
        print(f"   ✅ Retrieved artifact matches original")
    else:
        print(f"   ❌ Retrieved artifact does not match")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print(f"\nEvent journal: {event_store.ndjson_path}")
    print(f"Artifacts: {artifact_store.storage_root}")


def demo_postgres(postgres_url: str):
    """Demo with Postgres backend."""
    print("Leviathan Graph Control Plane - Postgres Demo")
    print("=" * 60)
    
    # Initialize stores
    event_store = EventStore(backend="postgres", postgres_url=postgres_url)
    graph_store = GraphStore(backend="postgres", postgres_url=postgres_url)
    artifact_store = ArtifactStore()
    
    print("\n1. Appending events with hash chain...")
    
    # Event 1: Register target
    event1 = Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TARGET_REGISTERED,
        timestamp=datetime.utcnow(),
        actor_id="system",
        payload={
            'target_id': 'radix',
            'node_id': 'radix',
            'node_type': 'Target',
            'name': 'radix',
            'repo_url': 'git@github.com:iangreen74/radix.git',
            'default_branch': 'main',
            'created_at': datetime.utcnow().isoformat()
        }
    )
    event1 = event_store.append_event(event1)
    print(f"   ✅ Event 1: {event1.event_type} (hash: {event1.hash[:8]}...)")
    
    # Event 2: Create task
    event2 = Event(
        event_id=str(uuid.uuid4()),
        event_type=EventType.TASK_CREATED,
        timestamp=datetime.utcnow(),
        actor_id="system",
        payload={
            'task_id': 'task-001',
            'node_id': 'task-001',
            'node_type': 'Task',
            'target_id': 'radix',
            'title': 'Implement feature X',
            'scope': 'services',
            'priority': 'high',
            'estimated_size': 'medium',
            'allowed_paths': ['services/api/'],
            'acceptance_criteria': ['Tests pass', 'Code reviewed'],
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
    )
    event2 = event_store.append_event(event2)
    print(f"   ✅ Event 2: {event2.event_type} (hash: {event2.hash[:8]}..., prev: {event2.prev_hash[:8]}...)")
    
    print("\n2. Verifying hash chain integrity...")
    is_valid, error = event_store.verify_chain()
    if is_valid:
        print("   ✅ Hash chain is valid")
    else:
        print(f"   ❌ Hash chain invalid: {error}")
    
    print("\n3. Rebuilding graph projection from events...")
    events = event_store.get_events()
    graph_store.rebuild_projection(events)
    print(f"   ✅ Applied {len(events)} events to graph")
    
    print("\n4. Querying graph...")
    targets = graph_store.query_nodes(node_type=NodeType.TARGET)
    tasks = graph_store.query_nodes(node_type=NodeType.TASK)
    
    print(f"   Nodes:")
    print(f"     - Targets: {len(targets)}")
    print(f"     - Tasks: {len(tasks)}")
    
    all_edges = graph_store.query_edges()
    print(f"   Edges: {len(all_edges)}")
    
    for edge in all_edges:
        print(f"     - {edge['from_node']} --[{edge['edge_type']}]--> {edge['to_node']}")
    
    print("\n5. Testing artifact store...")
    test_content = b"Test log output from Postgres demo"
    artifact_meta = artifact_store.store(test_content, "log")
    print(f"   ✅ Stored artifact: {artifact_meta['sha256'][:16]}...")
    
    event_store.close()
    graph_store.close()
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")


def main():
    parser = argparse.ArgumentParser(description="Leviathan Graph Control Plane Demo")
    parser.add_argument(
        "--backend",
        choices=["ndjson", "postgres"],
        default="ndjson",
        help="Storage backend (default: ndjson)"
    )
    parser.add_argument(
        "--postgres-url",
        default="postgresql://leviathan:leviathan_dev_password@localhost:5432/leviathan",
        help="PostgreSQL connection URL"
    )
    
    args = parser.parse_args()
    
    if args.backend == "ndjson":
        demo_ndjson()
    else:
        demo_postgres(args.postgres_url)


if __name__ == "__main__":
    main()
