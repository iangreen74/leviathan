# Multi-Target Architecture

**Last Updated:** 2026-01-31  
**Status:** Canonical (Strategic)

---

## Overview

Multi-target architecture is Leviathan's key product unlock. It transforms Leviathan from a single-repository tool into a platform that manages multiple target repositories simultaneously, each with its own policy, backlog, and execution context.

**Current State:** Architecture exists but not fully operational. Scheduler is hardcoded to single target (`iangreen74/radix`).

**Target State:** Scheduler discovers and manages N targets dynamically, selecting tasks across targets based on priority, readiness, and fairness.

---

## Core Concepts

### Target

A **target** is a GitHub repository managed by Leviathan.

**Target Properties:**
- **Repository URL:** `https://github.com/owner/repo`
- **Backlog:** `.leviathan/backlog.yaml` in target repo
- **Policy:** `.leviathan/policy.yaml` in target repo (or inherited from platform defaults)
- **Contract:** `.leviathan/contract.yaml` defining target metadata

**Target Lifecycle:**
1. **Registration:** Target added to control plane graph
2. **Discovery:** Scheduler discovers target from graph
3. **Execution:** Scheduler selects tasks from target backlog
4. **Monitoring:** Spider Node tracks target health and metrics

### Policy

A **policy** defines guardrails and execution parameters for a target.

**Policy Fields:**
```yaml
# .leviathan/policy.yaml

target:
  name: "my-app"
  owner: "myorg"
  repo: "my-app"

autonomy:
  enabled: true  # Master switch for this target
  
guardrails:
  allowed_path_prefixes:
    - ".leviathan/"
    - "docs/"
    - "tests/"
  
  max_open_prs: 2
  max_running_attempts: 1
  max_attempts_per_task: 3
  
  circuit_breaker:
    enabled: true
    consecutive_failures_threshold: 3
    cooldown_minutes: 60
  
  timeout:
    attempt_timeout_minutes: 15
    
scheduling:
  priority: "normal"  # low, normal, high
  fairness_weight: 1.0  # Higher = more scheduler attention
  
auto_merge:
  enabled: false
  require_ci_pass: true
  require_approvals: 1
  allowed_scopes:
    - "docs"
    - "tests"
```

**Policy Inheritance:**
- Targets can inherit from platform defaults
- Target-specific policy overrides defaults
- Missing fields use safe defaults

### Backlog

A **backlog** is a YAML file defining tasks for a target.

**Backlog Location:** `.leviathan/backlog.yaml` in target repo

**Task Structure:**
```yaml
tasks:
  - id: "task-1"
    title: "Add API documentation"
    scope: "docs"
    priority: "high"
    ready: true
    status: "pending"
    allowed_paths:
      - "docs/api/"
    acceptance_criteria:
      - "Document all API endpoints"
      - "Include request/response examples"
    dependencies: []
    estimated_size: "small"
```

**Backlog Writeback:**
- Worker updates backlog in same PR
- Marks task as `status: completed`, `ready: false`
- Records attempt metadata
- Prevents re-execution

---

## Architecture

### Component Interactions

```
┌─────────────────────────────────────────────────────────────┐
│                    Control Plane                             │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Graph Store                                       │    │
│  │  - Targets (nodes)                                 │    │
│  │  - Tasks (nodes)                                   │    │
│  │  - Attempts (nodes)                                │    │
│  │  - PRs (nodes)                                     │    │
│  │  - Events (edges)                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       │ Query targets
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Scheduler (CronJob)                       │
│                                                              │
│  1. Query control plane for active targets                  │
│  2. For each target:                                        │
│     a. Check open PR count                                  │
│     b. Fetch backlog from target repo                       │
│     c. Select next ready task                               │
│     d. Validate against policy                              │
│  3. Select highest-priority task across all targets         │
│  4. Submit worker job                                        │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       │ Create job
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Worker (Job)                              │
│                                                              │
│  1. Receive task spec + target context                      │
│  2. Clone target repo                                        │
│  3. Execute task (docs, tests, etc.)                         │
│  4. Update backlog (writeback)                               │
│  5. Create PR to target repo                                 │
│  6. Post events to control plane                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Target Discovery

**Current (v1 - Hardcoded):**
```python
# Hardcoded in scheduler
TARGET_REPO_URL = "https://github.com/iangreen74/radix.git"
```

**Future (v2 - Dynamic Discovery):**
```python
# Query control plane for active targets
targets = control_plane.query_targets(status="active")

for target in targets:
    if target.autonomy_enabled:
        process_target(target)
```

**Target Registration:**
```bash
# Via control plane API
curl -X POST http://control-plane:8000/v1/targets \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "my-app",
    "repo_url": "https://github.com/myorg/my-app",
    "policy": {...}
  }'
```

---

## Scheduling Strategies

### 1. Round-Robin (Simple)

**Algorithm:**
- Maintain list of active targets
- Rotate through targets in order
- Select next ready task from current target
- Move to next target on next cycle

**Pros:**
- Simple to implement
- Fair across targets
- Predictable behavior

**Cons:**
- Ignores priority
- May select low-priority tasks over high-priority tasks from other targets

**Implementation:**
```python
def select_next_task_round_robin(targets):
    current_index = get_last_target_index()
    next_index = (current_index + 1) % len(targets)
    
    target = targets[next_index]
    task = select_ready_task(target)
    
    save_last_target_index(next_index)
    return task, target
```

### 2. Priority-Based (Recommended)

**Algorithm:**
- Query all targets for ready tasks
- Score each task: `score = task.priority * target.fairness_weight`
- Select highest-scoring task
- Track target execution counts for fairness

**Pros:**
- Respects task priority
- Configurable fairness
- Flexible for different use cases

**Cons:**
- More complex
- Requires fairness tracking

**Implementation:**
```python
def select_next_task_priority(targets):
    candidates = []
    
    for target in targets:
        tasks = get_ready_tasks(target)
        for task in tasks:
            score = calculate_score(task, target)
            candidates.append((score, task, target))
    
    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)
    
    if candidates:
        score, task, target = candidates[0]
        return task, target
    
    return None, None

def calculate_score(task, target):
    priority_weight = {
        "high": 3.0,
        "medium": 2.0,
        "low": 1.0
    }
    
    base_score = priority_weight.get(task.priority, 1.0)
    fairness_weight = target.policy.scheduling.fairness_weight
    
    # Penalize targets with many recent executions
    recent_executions = count_recent_executions(target, hours=24)
    fairness_penalty = 1.0 / (1.0 + recent_executions * 0.1)
    
    return base_score * fairness_weight * fairness_penalty
```

### 3. Deadline-Based (Future)

**Algorithm:**
- Each task has optional deadline
- Select task closest to deadline
- Fall back to priority if no deadlines

**Use Case:** Time-sensitive tasks (security patches, compliance updates)

---

## Per-Target State Management

### Target State

**States:**
- **Active:** Target is being monitored and scheduled
- **Idle:** No ready tasks in backlog
- **Blocked:** Circuit breaker tripped or max PRs reached
- **Paused:** Autonomy disabled for this target
- **Error:** Target inaccessible or policy invalid

**State Transitions:**
```
Active ──┬──> Idle (no ready tasks)
         ├──> Blocked (circuit breaker or max PRs)
         ├──> Paused (autonomy disabled)
         └──> Error (repo inaccessible)

Idle ────┬──> Active (new ready task)
         └──> Paused (autonomy disabled)

Blocked ─┬──> Active (cooldown expired, PRs merged)
         └──> Paused (autonomy disabled)

Paused ──┬──> Active (autonomy re-enabled)
         └──> Error (repo deleted)

Error ───┬──> Active (issue resolved)
         └──> Paused (manual intervention)
```

### Concurrency Control

**Per-Target Limits:**
- `max_open_prs`: Max open PRs for this target
- `max_running_attempts`: Max concurrent worker jobs for this target

**Global Limits:**
- `max_total_workers`: Max concurrent workers across all targets
- `max_scheduler_cycles`: Max scheduler executions per hour

**Implementation:**
```python
def can_schedule_task(target, task):
    # Check per-target limits
    open_prs = count_open_prs(target)
    if open_prs >= target.policy.max_open_prs:
        return False, "Max open PRs reached"
    
    running_attempts = count_running_attempts(target)
    if running_attempts >= target.policy.max_running_attempts:
        return False, "Max running attempts reached"
    
    # Check global limits
    total_workers = count_total_workers()
    if total_workers >= GLOBAL_MAX_WORKERS:
        return False, "Global worker limit reached"
    
    return True, None
```

---

## Console UX Implications

### Multi-Target Dashboard

**View: Target List**
```
┌─────────────────────────────────────────────────────────┐
│  Targets                                                 │
├─────────────────────────────────────────────────────────┤
│  Name         Status    Open PRs  Ready Tasks  Last Run │
│  ─────────────────────────────────────────────────────  │
│  radix        Active    1/2       3            2m ago   │
│  leviathan    Idle      0/1       0            15m ago  │
│  my-app       Blocked   2/2       5            1h ago   │
│  other-app    Paused    0/2       2            -        │
└─────────────────────────────────────────────────────────┘
```

**View: Target Detail**
```
┌─────────────────────────────────────────────────────────┐
│  Target: radix                                           │
├─────────────────────────────────────────────────────────┤
│  Status: Active                                          │
│  Repository: github.com/iangreen74/radix                 │
│  Open PRs: 1/2                                           │
│  Ready Tasks: 3                                          │
│  Last Execution: 2 minutes ago                           │
│                                                          │
│  Policy:                                                 │
│    Allowed Paths: .leviathan/, docs/, tests/             │
│    Max Open PRs: 2                                       │
│    Circuit Breaker: Enabled (3 failures)                 │
│                                                          │
│  Recent Activity:                                        │
│    ✓ PR #722 merged (api-base-normalization-test)       │
│    ⏳ PR #721 open (docs-update)                         │
│    ✗ Attempt failed (ci-workflow-update)                 │
└─────────────────────────────────────────────────────────┘
```

**View: Task Queue (Across All Targets)**
```
┌─────────────────────────────────────────────────────────┐
│  Task Queue                                              │
├─────────────────────────────────────────────────────────┤
│  Priority  Target      Task                    Score    │
│  ────────────────────────────────────────────────────   │
│  High      radix       Add API docs            3.0      │
│  High      my-app      Update README           2.7      │
│  Medium    leviathan   Archive old docs        2.0      │
│  Medium    radix       Add unit tests          1.8      │
│  Low       other-app   Update deps             1.0      │
└─────────────────────────────────────────────────────────┘
```

### Per-Target Controls

**Actions:**
- **Pause/Resume Autonomy:** Toggle `autonomy_enabled` for target
- **Trigger Task Manually:** Force execution of specific task (admin only)
- **View Policy:** Display current policy configuration
- **Edit Policy:** Update policy (requires approval)
- **View Backlog:** Display all tasks in target backlog
- **View PRs:** List open PRs for target

---

## Migration Path

### Phase 1: Single Target (Current)

**Implementation:**
- Hardcoded target in scheduler
- No target discovery
- No multi-target scheduling

**Status:** ✅ Operational

### Phase 2: Multi-Target Discovery

**Implementation:**
- Control plane stores target metadata
- Scheduler queries control plane for targets
- Still processes one target at a time (round-robin)

**Changes Required:**
1. Add target registration API to control plane
2. Update scheduler to query targets from control plane
3. Remove hardcoded target reference
4. Add target state tracking

**Estimated Effort:** 2-3 days

### Phase 3: Multi-Target Scheduling

**Implementation:**
- Scheduler evaluates tasks across all targets
- Priority-based task selection
- Per-target concurrency limits
- Fairness tracking

**Changes Required:**
1. Implement priority-based scheduling algorithm
2. Add fairness weight to target policy
3. Track per-target execution counts
4. Update console to show multi-target view

**Estimated Effort:** 3-5 days

### Phase 4: Advanced Features

**Implementation:**
- Deadline-based scheduling
- Auto-merge per target
- Target-specific executors
- Resource quotas

**Estimated Effort:** 1-2 weeks

---

## Testing Strategy

### Unit Tests

**Test Cases:**
- Target discovery from control plane
- Priority-based task selection
- Fairness calculation
- Concurrency limit enforcement
- State transition logic

### Integration Tests

**Test Cases:**
- Scheduler processes multiple targets
- Worker executes tasks from different targets
- Control plane tracks per-target metrics
- Console displays multi-target view

### Load Tests

**Scenarios:**
- 10 targets, 100 tasks total
- 50 targets, 500 tasks total
- 100 targets, 1000 tasks total

**Metrics:**
- Scheduler cycle time
- Task selection latency
- Worker job creation rate
- Control plane event ingestion rate

---

## Security Considerations

### Per-Target Secrets

**Challenge:** Each target may require different GitHub tokens or credentials.

**Solution:**
- Store per-target secrets in AWS Secrets Manager
- Secret naming convention: `leviathan/targets/{owner}/{repo}/github-token`
- Worker fetches target-specific secret at runtime

**Implementation:**
```python
def get_target_secret(target):
    secret_name = f"leviathan/targets/{target.owner}/{target.repo}/github-token"
    return secrets_manager.get_secret(secret_name)
```

### Policy Validation

**Challenge:** Malicious or misconfigured policies could bypass guardrails.

**Solution:**
- Validate policy schema on registration
- Enforce minimum guardrails (max_open_prs >= 1, timeout >= 5 minutes)
- Require admin approval for policy changes
- Audit log all policy modifications

---

## Monitoring and Alerting

### Per-Target Metrics

**Metrics:**
- `leviathan_target_status{target="name"}` - Target state (active, idle, blocked, paused, error)
- `leviathan_target_open_prs{target="name"}` - Open PR count
- `leviathan_target_ready_tasks{target="name"}` - Ready task count
- `leviathan_target_attempts_total{target="name", status="success|failure"}` - Attempt count
- `leviathan_target_last_execution_timestamp{target="name"}` - Last execution time

**Alerts:**
- Target blocked for >1 hour
- Target in error state
- Target has ready tasks but not scheduled for >1 hour
- Target open PR count at max for >6 hours

---

## Next Steps

1. **Implement Target Registration API** (control plane)
2. **Update Scheduler for Target Discovery** (remove hardcoded target)
3. **Add Per-Target State Tracking** (control plane)
4. **Implement Priority-Based Scheduling** (scheduler)
5. **Update Console for Multi-Target View** (console)
6. **Add Integration Tests** (multi-target scenarios)

---

## References

- [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Strategic roadmap
- [00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md) - System overview
- [10_ARCHITECTURE.md](10_ARCHITECTURE.md) - System architecture
- [12_BACKLOG_FORMAT.md](12_BACKLOG_FORMAT.md) - Backlog specification

---

**Document Status:** Living document, updated as multi-target architecture evolves.
