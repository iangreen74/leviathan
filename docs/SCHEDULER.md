# Leviathan Graph-Driven Scheduler

Graph-driven scheduler for orchestrating task attempts with executor abstraction.

## Overview

The scheduler is responsible for:
1. Selecting ready tasks from the graph
2. Creating Attempt nodes with relationships
3. Orchestrating execution via pluggable executors
4. Emitting lifecycle events
5. Handling retries with backoff policy

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Scheduler                            │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ Task         │───▶│ Attempt      │───▶│ Executor     │  │
│  │ Selection    │    │ Creation     │    │ Abstraction  │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                    │          │
│         ▼                    ▼                    ▼          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Event Store (Hash Chain)                │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Graph Store (Deterministic Projection)       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Attempt Lifecycle

### States

1. **created** - Attempt node created, not yet started
2. **running** - Executor is running the attempt
3. **succeeded** - Attempt completed successfully
4. **failed** - Attempt failed (may retry)

### Events

```
attempt.created
  ↓
attempt.started
  ↓
attempt.succeeded OR attempt.failed
  ↓ (if failed and retries remaining)
retry.scheduled
  ↓
attempt.created (new attempt)
```

### Event Payloads

**attempt.created:**
```json
{
  "attempt_id": "attempt-abc123",
  "node_id": "attempt-abc123",
  "node_type": "Attempt",
  "task_id": "task-001",
  "target_id": "radix",
  "attempt_number": 1,
  "status": "created",
  "created_at": "2026-01-24T10:00:00Z"
}
```

**attempt.started:**
```json
{
  "attempt_id": "attempt-abc123",
  "status": "running",
  "started_at": "2026-01-24T10:00:05Z"
}
```

**attempt.succeeded:**
```json
{
  "attempt_id": "attempt-abc123",
  "status": "succeeded",
  "completed_at": "2026-01-24T10:05:00Z",
  "branch_name": "leviathan/task-001",
  "pr_url": "https://github.com/org/repo/pull/123",
  "commit_sha": "abc123..."
}
```

**attempt.failed:**
```json
{
  "attempt_id": "attempt-abc123",
  "status": "failed",
  "completed_at": "2026-01-24T10:05:00Z",
  "failure_type": "tests_failed",
  "error_summary": "3 tests failed in services/api/test_auth.py"
}
```

**retry.scheduled:**
```json
{
  "task_id": "task-001",
  "retry_number": 2,
  "backoff_seconds": 60,
  "scheduled_at": "2026-01-24T10:06:00Z"
}
```

## Executor Abstraction

### Interface

```python
class Executor(ABC):
    @abstractmethod
    def run_attempt(
        self,
        target_id: str,
        task_id: str,
        attempt_id: str,
        task_spec: Dict[str, Any],
        target_config: Dict[str, Any]
    ) -> AttemptResult:
        """Execute task attempt."""
        pass
    
    @abstractmethod
    def cleanup(self, attempt_id: str):
        """Clean up resources."""
        pass
```

### Implementations

#### LocalWorktreeExecutor

Runs attempts in local git worktrees.

- **Use case:** Local development, testing
- **Environment:** Local filesystem
- **Artifacts:** Stored locally in `~/.leviathan/artifacts`

```python
from leviathan.executors.local_worktree import LocalWorktreeExecutor

executor = LocalWorktreeExecutor()
result = executor.run_attempt(
    target_id="radix",
    task_id="task-001",
    attempt_id="attempt-abc123",
    task_spec={"title": "Add feature X", "scope": "services"},
    target_config={"repo_url": "git@github.com:org/repo.git"}
)
```

#### K8sExecutorStub

Generates Kubernetes Job specs without submitting them.

- **Use case:** Testing scheduler without K8s cluster
- **Environment:** No cluster required
- **Artifacts:** Simulated

```python
from leviathan.executors.k8s_stub import K8sExecutorStub

executor = K8sExecutorStub()
result = executor.run_attempt(...)  # Returns simulated success
```

#### K8sExecutor (PR #4)

Submits Kubernetes Jobs and waits for completion.

- **Use case:** Production execution
- **Environment:** Kubernetes cluster
- **Artifacts:** Uploaded to S3/artifact store by Job

## Retry Policy

### Configuration

```python
from leviathan.control_plane.scheduler import RetryPolicy

policy = RetryPolicy(
    max_attempts_per_task=3,      # Max attempts before giving up
    backoff_seconds=60,            # Seconds between retries
    escalation_after=3             # Failures before escalation
)
```

### Behavior

1. **First failure:** Schedule retry after `backoff_seconds`
2. **Subsequent failures:** Continue retrying up to `max_attempts_per_task`
3. **Max reached:** Mark task as failed, emit `task.completed` with status=failed
4. **Escalation:** After `escalation_after` failures, trigger escalation (future)

## Running the Scheduler

### CLI Usage

```bash
# Run once with local executor
python3 -m leviathan.control_plane.scheduler \
  --target radix \
  --once \
  --executor local

# Run once with K8s stub
python3 -m leviathan.control_plane.scheduler \
  --target radix \
  --once \
  --executor k8s-stub

# Custom retry policy
python3 -m leviathan.control_plane.scheduler \
  --target radix \
  --once \
  --max-attempts 5
```

### Programmatic Usage

```python
from leviathan.graph.events import EventStore
from leviathan.graph.store import GraphStore
from leviathan.artifacts.store import ArtifactStore
from leviathan.control_plane.scheduler import Scheduler, RetryPolicy
from leviathan.executors.local_worktree import LocalWorktreeExecutor

# Initialize stores
event_store = EventStore(backend="ndjson")
graph_store = GraphStore(backend="memory")
artifact_store = ArtifactStore()

# Initialize executor and policy
executor = LocalWorktreeExecutor(artifact_store=artifact_store)
retry_policy = RetryPolicy(max_attempts_per_task=3)

# Create scheduler
scheduler = Scheduler(
    event_store=event_store,
    graph_store=graph_store,
    artifact_store=artifact_store,
    executor=executor,
    retry_policy=retry_policy
)

# Run once
target_config = {
    'target_id': 'radix',
    'repo_url': 'git@github.com:org/radix.git'
}

executed = scheduler.run_once('radix', target_config)
```

## Graph Relationships

### Nodes Created

- **Attempt** - One per execution attempt
- **Artifact** - Logs, test outputs, diffs, etc.

### Edges Created

- `Task --[DEPENDS_ON]--> Target`
- `Attempt --[DEPENDS_ON]--> Task`
- `Attempt --[PRODUCED]--> Artifact`

## Kubernetes Job Mapping (PR #4)

In PR #4, the K8sExecutor will:

1. **Generate Job spec** from task and target config
2. **Submit Job** to Kubernetes cluster
3. **Watch Job** for completion
4. **Collect artifacts** from Job pod
5. **Upload artifacts** to artifact store
6. **Emit events** via control plane API

### Job Spec Template

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: leviathan-attempt-abc123
  labels:
    app: leviathan
    target: radix
    task: task-001
    attempt: attempt-abc123
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: executor
        image: leviathan-executor:latest
        env:
        - name: TARGET_ID
          value: radix
        - name: TASK_ID
          value: task-001
        - name: ATTEMPT_ID
          value: attempt-abc123
        - name: CONTROL_PLANE_URL
          value: http://leviathan-api:8000
        - name: CONTROL_PLANE_TOKEN
          valueFrom:
            secretKeyRef:
              name: leviathan-secrets
              key: token
        volumeMounts:
        - name: workspace
          mountPath: /workspace
      volumes:
      - name: workspace
        emptyDir: {}
  backoffLimit: 0  # No K8s retries, scheduler handles retries
```

### Job Lifecycle

1. Scheduler creates Attempt node
2. K8sExecutor submits Job
3. Job pod starts, runs task
4. Job pod emits events to control plane API
5. Job pod uploads artifacts
6. Job completes (success/failure)
7. K8sExecutor collects final status
8. Scheduler emits completion event

## Testing

### Unit Tests

```bash
python3 -m pytest tests/unit/test_scheduler.py -v
```

Tests cover:
- Task selection logic
- Attempt creation and lifecycle
- Event emission
- Retry policy enforcement
- Executor abstraction

### Integration Test (Manual)

```bash
# 1. Create target and task in graph
python3 -m leviathan.graph.demo --backend ndjson

# 2. Run scheduler
python3 -m leviathan.control_plane.scheduler --target radix --once

# 3. Verify events
python3 -c "
from leviathan.graph.events import EventStore
store = EventStore(backend='ndjson')
events = store.get_events()
for e in events[-10:]:
    print(f'{e.event_type}: {e.payload.get(\"attempt_id\", \"N/A\")}')
"
```

## Future Enhancements

- **Dependency resolution:** Respect task dependencies via DEPENDS_ON edges
- **Priority scheduling:** Select high-priority tasks first
- **Parallel execution:** Run multiple attempts concurrently
- **Escalation:** Notify humans after repeated failures
- **Metrics:** Emit metrics for attempt duration, success rate, etc.
- **Continuous mode:** Run scheduler as daemon, not just --once
