"""
Event store with hash chain for append-only event journal.

Events are the source of truth. The graph is a projection.
"""
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class Event(BaseModel):
    """Event in the append-only journal."""
    event_id: str
    event_type: str
    timestamp: datetime
    actor_id: Optional[str] = None
    payload: Dict[str, Any]
    prev_hash: Optional[str] = Field(None, description="Hash of previous event (hash chain)")
    hash: Optional[str] = Field(None, description="Hash of this event")
    
    def compute_hash(self) -> str:
        """Compute deterministic hash of this event."""
        # Create canonical representation
        canonical = {
            'event_id': self.event_id,
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'actor_id': self.actor_id,
            'payload': self.payload,
            'prev_hash': self.prev_hash
        }
        
        # Deterministic JSON serialization
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
        
        # SHA256 hash
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


class EventStore:
    """
    Append-only event store with hash chain.
    
    Supports two backends:
    - Postgres (production)
    - NDJSON file (local dev)
    """
    
    def __init__(self, backend: str = "ndjson", postgres_url: Optional[str] = None, ndjson_dir: Optional[str] = None):
        """
        Initialize event store.
        
        Args:
            backend: "postgres" or "ndjson"
            postgres_url: PostgreSQL connection URL (if backend is postgres)
            ndjson_dir: Optional directory for NDJSON file (for tests, defaults to ~/.leviathan/graph)
        """
        self.backend = backend
        self.postgres_url = postgres_url
        
        if backend == "ndjson":
            if ndjson_dir:
                # Use provided directory (for tests)
                self.ndjson_path = Path(ndjson_dir) / "events.ndjson"
            else:
                # Use default home directory
                self.ndjson_path = Path.home() / ".leviathan" / "graph" / "events.ndjson"
            
            self.ndjson_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.ndjson_path.exists():
                self.ndjson_path.touch()
        elif backend == "postgres":
            if not postgres_url:
                raise ValueError("postgres_url required for postgres backend")
            # Import here to avoid dependency if not using postgres
            import psycopg2
            self.conn = psycopg2.connect(postgres_url)
        else:
            raise ValueError(f"Unknown backend: {backend}")
    
    def get_last_hash(self) -> Optional[str]:
        """Get hash of the last event in the chain."""
        if self.backend == "ndjson":
            return self._get_last_hash_ndjson()
        elif self.backend == "postgres":
            return self._get_last_hash_postgres()
    
    def _get_last_hash_ndjson(self) -> Optional[str]:
        """Get last hash from NDJSON file."""
        last_line = None
        with open(self.ndjson_path, 'r') as f:
            for line in f:
                if line.strip():
                    last_line = line
        
        if last_line:
            event_data = json.loads(last_line)
            return event_data.get('hash')
        
        return None
    
    def _get_last_hash_postgres(self) -> Optional[str]:
        """Get last hash from Postgres."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT hash FROM events ORDER BY timestamp DESC LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None
    
    def append_event(self, event: Event) -> Event:
        """
        Append event to the journal with hash chain.
        
        Args:
            event: Event to append (hash will be computed)
            
        Returns:
            Event with hash computed
        """
        # Get previous hash
        event.prev_hash = self.get_last_hash()
        
        # Compute this event's hash
        event.hash = event.compute_hash()
        
        # Write to backend
        if self.backend == "ndjson":
            self._append_ndjson(event)
        elif self.backend == "postgres":
            self._append_postgres(event)
        
        return event
    
    def _append_ndjson(self, event: Event):
        """Append event to NDJSON file."""
        with open(self.ndjson_path, 'a') as f:
            f.write(event.json() + '\n')
    
    def _append_postgres(self, event: Event):
        """Append event to Postgres."""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO events (event_id, event_type, timestamp, actor_id, payload, prev_hash, hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                event.event_id,
                event.event_type,
                event.timestamp,
                event.actor_id,
                json.dumps(event.payload),
                event.prev_hash,
                event.hash
            ))
        self.conn.commit()
    
    def get_events(self, since: Optional[datetime] = None, limit: Optional[int] = None) -> List[Event]:
        """
        Get events from the journal.
        
        Args:
            since: Only return events after this timestamp
            limit: Maximum number of events to return
            
        Returns:
            List of events in chronological order
        """
        if self.backend == "ndjson":
            return self._get_events_ndjson(since, limit)
        elif self.backend == "postgres":
            return self._get_events_postgres(since, limit)
    
    def _get_events_ndjson(self, since: Optional[datetime], limit: Optional[int]) -> List[Event]:
        """Get events from NDJSON file."""
        events = []
        with open(self.ndjson_path, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                
                event = Event(**json.loads(line))
                
                if since and event.timestamp <= since:
                    continue
                
                events.append(event)
                
                if limit and len(events) >= limit:
                    break
        
        return events
    
    def _get_events_postgres(self, since: Optional[datetime], limit: Optional[int]) -> List[Event]:
        """Get events from Postgres."""
        query = "SELECT event_id, event_type, timestamp, actor_id, payload, prev_hash, hash FROM events"
        params = []
        
        if since:
            query += " WHERE timestamp > %s"
            params.append(since)
        
        query += " ORDER BY timestamp ASC"
        
        if limit:
            query += " LIMIT %s"
            params.append(limit)
        
        events = []
        with self.conn.cursor() as cur:
            cur.execute(query, params)
            for row in cur.fetchall():
                events.append(Event(
                    event_id=row[0],
                    event_type=row[1],
                    timestamp=row[2],
                    actor_id=row[3],
                    payload=json.loads(row[4]) if isinstance(row[4], str) else row[4],
                    prev_hash=row[5],
                    hash=row[6]
                ))
        
        return events
    
    def verify_chain(self) -> tuple[bool, Optional[str]]:
        """
        Verify hash chain integrity.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        events = self.get_events()
        
        if not events:
            return True, None
        
        # First event should have no prev_hash
        if events[0].prev_hash is not None:
            return False, f"First event {events[0].event_id} has prev_hash (should be None)"
        
        # Verify each event's hash
        for event in events:
            expected_hash = event.compute_hash()
            if event.hash != expected_hash:
                return False, f"Event {event.event_id} hash mismatch: expected {expected_hash}, got {event.hash}"
        
        # Verify chain links
        for i in range(1, len(events)):
            if events[i].prev_hash != events[i-1].hash:
                return False, f"Chain broken at event {events[i].event_id}: prev_hash {events[i].prev_hash} != {events[i-1].hash}"
        
        return True, None
    
    def close(self):
        """Close backend connections."""
        if self.backend == "postgres" and hasattr(self, 'conn'):
            self.conn.close()


# Event type constants
class EventType:
    """Standard event types."""
    # Target events
    TARGET_REGISTERED = "target.registered"
    TARGET_UPDATED = "target.updated"
    
    # Task events
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    TASK_BLOCKED = "task.blocked"
    
    # Attempt events
    ATTEMPT_CREATED = "attempt.created"
    ATTEMPT_STARTED = "attempt.started"
    ATTEMPT_SUCCEEDED = "attempt.succeeded"
    ATTEMPT_FAILED = "attempt.failed"
    ATTEMPT_INVALIDATED = "attempt.invalidated"
    
    # Job events
    JOB_SUBMITTED = "job.submitted"
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    
    # Artifact events
    ARTIFACT_CREATED = "artifact.created"
    
    # Test events
    TESTS_STARTED = "tests.started"
    TESTS_PASSED = "tests.passed"
    TESTS_FAILED = "tests.failed"
    
    # PR events
    PR_CREATED = "pr.created"
    PR_MERGED = "pr.merged"
    PR_CLOSED = "pr.closed"
    
    # Model events
    MODEL_CALL_STARTED = "model.call_started"
    MODEL_CALL_COMPLETED = "model.call_completed"
    
    # Bootstrap events
    BOOTSTRAP_STARTED = "bootstrap.started"
    BOOTSTRAP_COMPLETED = "bootstrap.completed"
    REPO_INDEXED = "repo.indexed"
    FILE_DISCOVERED = "file.discovered"
    DOC_DISCOVERED = "doc.discovered"
    WORKFLOW_DISCOVERED = "workflow.discovered"
    API_ROUTE_DISCOVERED = "api.route.discovered"
