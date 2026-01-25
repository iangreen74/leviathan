# leviathanctl - Operator CLI

Command-line tool for querying and operating the Leviathan control plane.

## Installation

The CLI is included with Leviathan. No additional installation required.

## Configuration

Set environment variables:

```bash
# Control plane API URL (default: http://localhost:8000)
export LEVIATHAN_API_URL=http://localhost:8000

# Authentication token (required)
export LEVIATHAN_CONTROL_PLANE_TOKEN=$(cat ~/.leviathan/control-plane-token)
```

Or use command-line flags:

```bash
python3 -m leviathan.cli.leviathanctl \
  --api-url http://localhost:8000 \
  --token your-token-here \
  graph-summary
```

## Commands

### graph-summary

Display graph summary statistics.

```bash
python3 -m leviathan.cli.leviathanctl graph-summary
```

Output:
```
Graph Summary
==================================================
Total Nodes: 150
Total Edges: 200

Node Types:
  task: 10
  attempt: 50
  artifact: 90

Edge Types:
  EXECUTES: 50
  PRODUCED: 90
  DEPENDS_ON: 60
```

### attempts-list

List recent attempts, optionally filtered by target.

```bash
# List last 10 attempts
python3 -m leviathan.cli.leviathanctl attempts-list

# List last 20 attempts
python3 -m leviathan.cli.leviathanctl attempts-list --limit 20

# Filter by target
python3 -m leviathan.cli.leviathanctl attempts-list --target my-repo
```

Output:
```
Recent Attempts (limit: 10)
================================================================================
Attempt: attempt-abc123
  Task: task-001
  Target: my-repo
  Status: succeeded
  Timestamp: 2024-01-15T10:30:00
  PR: https://github.com/owner/repo/pull/123

Attempt: attempt-def456
  Task: task-002
  Target: my-repo
  Status: failed
  Timestamp: 2024-01-15T09:15:00
```

### attempts-show

Show detailed information about a specific attempt.

```bash
python3 -m leviathan.cli.leviathanctl attempts-show attempt-abc123
```

Output:
```json
{
  "attempt_node": {
    "node_id": "attempt-abc123",
    "node_type": "attempt",
    "properties": {
      "task_id": "task-001",
      "target": "my-repo",
      "status": "succeeded",
      "pr_url": "https://github.com/owner/repo/pull/123",
      "pr_number": 123
    }
  },
  "events": [...],
  "artifacts": [...]
}
```

### failures-recent

List recent failures, optionally filtered by target.

```bash
# List last 10 failures
python3 -m leviathan.cli.leviathanctl failures-recent

# List last 20 failures
python3 -m leviathan.cli.leviathanctl failures-recent --limit 20

# Filter by target
python3 -m leviathan.cli.leviathanctl failures-recent --target my-repo
```

Output:
```
Recent Failures (limit: 10)
================================================================================
Attempt: attempt-xyz789
  Task: task-003
  Target: my-repo
  Error: Rewrite mode validation failed
  Timestamp: 2024-01-15T08:00:00

Attempt: attempt-uvw456
  Task: task-004
  Target: my-repo
  Error: Tests failed
  Timestamp: 2024-01-14T16:30:00
```

### invalidate

Invalidate an attempt (mark as invalid for retry).

```bash
python3 -m leviathan.cli.leviathanctl invalidate attempt-abc123 \
  --reason "Flaky test failure, retry needed"
```

Output:
```
Invalidated attempt: attempt-abc123
Reason: Flaky test failure, retry needed
Response: {
  "attempt_id": "attempt-abc123",
  "invalidated": true,
  "reason": "Flaky test failure, retry needed"
}
```

## Usage Patterns

### Quick Health Check

```bash
# Check if control plane is accessible
python3 -m leviathan.cli.leviathanctl graph-summary
```

### Monitor Recent Activity

```bash
# See what's happening
python3 -m leviathan.cli.leviathanctl attempts-list --limit 5
```

### Investigate Failures

```bash
# Find recent failures
python3 -m leviathan.cli.leviathanctl failures-recent --limit 10

# Get details on specific failure
python3 -m leviathan.cli.leviathanctl attempts-show attempt-xyz789
```

### Retry Failed Attempts

```bash
# Invalidate a failed attempt to trigger retry
python3 -m leviathan.cli.leviathanctl invalidate attempt-xyz789 \
  --reason "Infrastructure issue resolved, retry"
```

### Target-Specific Queries

```bash
# Check status of specific target
python3 -m leviathan.cli.leviathanctl attempts-list --target my-repo --limit 20
python3 -m leviathan.cli.leviathanctl failures-recent --target my-repo --limit 10
```

## Port Forwarding (Kubernetes)

When control plane is running in Kubernetes:

```bash
# Forward control plane port
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &

# Use CLI with local port
export LEVIATHAN_API_URL=http://localhost:8000
python3 -m leviathan.cli.leviathanctl graph-summary
```

## Authentication

The CLI uses bearer token authentication. Token must match the control plane's `LEVIATHAN_CONTROL_PLANE_TOKEN`.

**Security best practices:**
- Store token in `~/.leviathan/control-plane-token`
- Set restrictive permissions: `chmod 600 ~/.leviathan/control-plane-token`
- Rotate tokens regularly
- Never commit tokens to git

## Troubleshooting

### Connection Refused

```
Error: API Error: HTTPConnectionPool(host='localhost', port=8000): Max retries exceeded
```

**Solution:** Ensure control plane is running and accessible:
```bash
# Check if control plane is running
kubectl get pods -n leviathan

# Port forward if needed
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000
```

### Unauthorized (401)

```
Error: API Error: 401 Client Error: Unauthorized
```

**Solution:** Check token:
```bash
# Verify token is set
echo $LEVIATHAN_CONTROL_PLANE_TOKEN

# Or use --token flag
python3 -m leviathan.cli.leviathanctl --token your-token graph-summary
```

### Not Found (404)

```
Error: API Error: 404 Client Error: Not Found
Response: {"detail":"Attempt attempt-xyz not found"}
```

**Solution:** Verify the resource exists:
```bash
# List all attempts to find correct ID
python3 -m leviathan.cli.leviathanctl attempts-list --limit 50
```

## API Endpoints

The CLI uses these control plane API endpoints:

- `GET /v1/graph/summary` - Graph statistics
- `GET /v1/attempts?target=&limit=` - List attempts
- `GET /v1/attempts/{attempt_id}` - Get attempt details
- `GET /v1/failures?target=&limit=` - List failures
- `POST /v1/attempts/{attempt_id}/invalidate` - Invalidate attempt

All endpoints require bearer token authentication.

## Examples

### Daily Operations Workflow

```bash
# Morning check: What happened overnight?
python3 -m leviathan.cli.leviathanctl attempts-list --limit 20

# Any failures?
python3 -m leviathan.cli.leviathanctl failures-recent --limit 10

# Investigate specific failure
python3 -m leviathan.cli.leviathanctl attempts-show attempt-abc123

# Retry if needed
python3 -m leviathan.cli.leviathanctl invalidate attempt-abc123 \
  --reason "Transient failure, retry"
```

### Target Health Check

```bash
# Check specific target
TARGET=my-critical-repo

python3 -m leviathan.cli.leviathanctl attempts-list --target $TARGET --limit 10
python3 -m leviathan.cli.leviathanctl failures-recent --target $TARGET --limit 5
```

### Bulk Invalidation Script

```bash
#!/bin/bash
# Invalidate all attempts from a specific time period

for attempt_id in $(get_failed_attempts_from_period); do
  python3 -m leviathan.cli.leviathanctl invalidate $attempt_id \
    --reason "Bulk retry after infrastructure issue"
done
```

## See Also

- [Control Plane Deployment Guide](DEPLOY_CONTROL_PLANE.md)
- [K8s Executor Setup](K8S_EXECUTOR.md)
- [Graph Control Plane API](GRAPH_CONTROL_PLANE_API.md)
