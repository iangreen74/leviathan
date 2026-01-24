# Leviathan Graph Control Plane API

FastAPI-based control plane for event ingestion and graph queries.

## Overview

The Control Plane API provides HTTP endpoints for:
- Event bundle ingestion from executors
- Graph state queries
- Attempt tracking and artifact retrieval

## Architecture

- **Event Store**: Append-only event journal with hash chain
- **Graph Store**: Deterministic projection from events
- **Artifact Store**: Content-addressed storage (SHA256)
- **Auth**: Bearer token authentication

## Running the API

### Prerequisites

```bash
# Install dependencies
pip3 install -r requirements.txt

# Start Postgres (optional - can use NDJSON backend)
docker-compose up -d
```

### Configuration

Set required environment variables:

```bash
# Required
export LEVIATHAN_CONTROL_PLANE_TOKEN=your-secret-token-here

# Optional (defaults shown)
export LEVIATHAN_BACKEND=ndjson  # or postgres
export LEVIATHAN_POSTGRES_URL=postgresql://leviathan:leviathan_dev_password@localhost:5432/leviathan
export LEVIATHAN_API_HOST=0.0.0.0
export LEVIATHAN_API_PORT=8000
export LEVIATHAN_ARTIFACTS_DIR=~/.leviathan/artifacts
export LEVIATHAN_EVENTS_PATH=~/.leviathan/graph/events.ndjson
```

### Start the API

```bash
python3 -m leviathan.control_plane.api
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Health Check

```bash
GET /healthz
```

No authentication required.

**Response:**
```json
{
  "status": "ok"
}
```

### Ingest Event Bundle

```bash
POST /v1/events/ingest
Authorization: Bearer <token>
Content-Type: application/json
```

**Request:**
```json
{
  "target": "radix",
  "bundle_id": "bundle-uuid",
  "events": [
    {
      "event_id": "event-uuid",
      "event_type": "attempt.created",
      "timestamp": "2026-01-24T10:00:00Z",
      "actor_id": "executor-001",
      "payload": {
        "attempt_id": "attempt-001",
        "node_id": "attempt-001",
        "node_type": "Attempt",
        "task_id": "task-001",
        "attempt_number": 1,
        "status": "created",
        "created_at": "2026-01-24T10:00:00Z"
      }
    }
  ],
  "artifacts": [
    {
      "sha256": "abc123...",
      "kind": "log",
      "uri": "file:///path/to/artifact",
      "size": 1024
    }
  ]
}
```

**Response:**
```json
{
  "ingested": 1,
  "bundle_id": "bundle-uuid",
  "status": "ok"
}
```

### Get Graph Summary

```bash
GET /v1/graph/summary
Authorization: Bearer <token>
```

**Response:**
```json
{
  "nodes_by_type": {
    "Target": 1,
    "Task": 5,
    "Attempt": 3
  },
  "edges_by_type": {
    "DEPENDS_ON": 8,
    "PRODUCED": 3
  },
  "recent_events": [
    {
      "event_id": "event-uuid",
      "timestamp": "2026-01-24T10:00:00Z",
      "event_type": "attempt.created",
      "actor_id": "executor-001",
      "target": "radix",
      "attempt_id": "attempt-001"
    }
  ]
}
```

### Get Attempt Details

```bash
GET /v1/attempts/{attempt_id}
Authorization: Bearer <token>
```

**Response:**
```json
{
  "attempt_node": {
    "node_id": "attempt-001",
    "node_type": "Attempt",
    "properties": {
      "attempt_id": "attempt-001",
      "task_id": "task-001",
      "attempt_number": 1,
      "status": "succeeded"
    }
  },
  "events": [
    {
      "event_id": "event-uuid",
      "event_type": "attempt.created",
      "timestamp": "2026-01-24T10:00:00Z",
      "actor_id": "scheduler",
      "payload": {...}
    }
  ],
  "artifacts": [
    {
      "node_id": "artifact-001",
      "node_type": "Artifact",
      "properties": {
        "sha256": "abc123...",
        "artifact_type": "log",
        "size_bytes": 1024
      }
    }
  ]
}
```

## Example Usage

### Ingest Events

```bash
export TOKEN=your-secret-token

curl -X POST http://localhost:8000/v1/events/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target": "radix",
    "bundle_id": "test-bundle-001",
    "events": [
      {
        "event_id": "evt-001",
        "event_type": "target.registered",
        "timestamp": "2026-01-24T10:00:00Z",
        "actor_id": "system",
        "payload": {
          "target_id": "radix",
          "node_id": "radix",
          "node_type": "Target",
          "name": "radix",
          "repo_url": "git@github.com:iangreen74/radix.git",
          "default_branch": "main",
          "created_at": "2026-01-24T10:00:00Z"
        }
      }
    ]
  }'
```

### Query Graph Summary

```bash
curl http://localhost:8000/v1/graph/summary \
  -H "Authorization: Bearer $TOKEN"
```

### Get Attempt Details

```bash
curl http://localhost:8000/v1/attempts/attempt-001 \
  -H "Authorization: Bearer $TOKEN"
```

## Testing

Run unit tests:

```bash
export LEVIATHAN_CONTROL_PLANE_TOKEN=test-token
python3 -m pytest tests/unit/test_control_plane_api.py -v
```

## Security

- **Token Authentication**: All endpoints (except `/healthz`) require `Authorization: Bearer <token>` header
- **Token Storage**: Store token in environment variable, never commit to git
- **Future**: Structure supports migration to Cognito/OIDC

## Backend Modes

### NDJSON (Development)

- Events stored in `~/.leviathan/graph/events.ndjson`
- Graph projection in memory
- No database required
- Good for local development and testing

### Postgres (Production)

- Events stored in `events` table with hash chain
- Graph projection in `nodes` and `edges` tables
- Persistent storage
- Supports concurrent access

## Event Types

See `leviathan/graph/events.py` for full list:

- `target.registered`, `target.updated`
- `task.created`, `task.updated`, `task.completed`
- `attempt.created`, `attempt.started`, `attempt.succeeded`, `attempt.failed`
- `job.submitted`, `job.completed`
- `artifact.created`
- `tests.passed`, `tests.failed`
- `pr.created`, `pr.merged`
- `model.call_started`, `model.call_completed`

## Next Steps

- PR #3: Scheduler with K8s job creation
- PR #4: K8s executor worker with event bundle submission
