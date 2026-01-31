# Observability and Operator Experience

**Last Updated:** 2026-01-31  
**Status:** Canonical (Operational)

---

## Overview

Leviathan's observability stack enables operators to understand system state, diagnose issues, and control autonomous execution. This document defines the operator experience and observability architecture.

**Design Principle:** Operators should understand system state at a glance and have clear controls for intervention.

---

## Component Roles

### 1. Control Plane

**Purpose:** Event ingestion, storage, and query API.

**Endpoints:**
- `POST /v1/events` - Ingest events from workers
- `GET /v1/graph/nodes` - Query graph nodes
- `GET /v1/graph/events` - Query event history
- `GET /v1/autonomy/status` - Query autonomy state
- `GET /v1/health` - Health check

**Observability Features:**
- Full event history (NDJSON store)
- Graph state reconstruction
- Autonomy status reporting
- API request logging

**Deployment:**
- Kubernetes Deployment (1 replica)
- Port 8000
- Persistent volume for event store

**Logs:**
```bash
# View control plane logs
kubectl -n leviathan logs -l app=leviathan-control-plane --tail=100

# Follow logs
kubectl -n leviathan logs -l app=leviathan-control-plane -f
```

**Key Log Messages:**
- `Event received: attempt.created` - Worker started
- `Event received: pr.created` - PR created
- `Event received: attempt.succeeded` - Task completed
- `Event received: attempt.failed` - Task failed

---

### 2. Spider Node

**Purpose:** Metrics collection and health monitoring.

**Endpoints:**
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics

**Current Metrics (v1):**
- `leviathan_spider_up` (gauge) - Spider Node is running
- `leviathan_events_received_total` (counter) - Events received (static in v1)

**Future Metrics (v2):**
- `leviathan_attempts_total{target, status}` - Attempts by target and status
- `leviathan_prs_created_total{target}` - PRs created by target
- `leviathan_tasks_selected_total{target}` - Tasks selected by target
- `leviathan_scheduler_cycles_total` - Scheduler cycles
- `leviathan_circuit_breaker_trips_total{target}` - Circuit breaker trips
- `leviathan_target_status{target, status}` - Target state (active, idle, blocked)

**Deployment:**
- Kubernetes Deployment (1 replica)
- Port 8001
- No persistent storage

**Integration (v2):**
```
Control Plane ──(event stream)──> Spider Node
                                   │
                                   ├─> Update metrics
                                   ├─> Detect anomalies
                                   └─> Trigger alerts
```

---

### 3. Console

**Purpose:** Web UI for operators to view and control Leviathan.

**Features:**
- **Dashboard:** System overview (targets, tasks, PRs)
- **Event Stream:** Real-time event visualization
- **Target View:** Per-target status and controls
- **Task Queue:** Pending tasks across targets
- **Graph Explorer:** Navigate event graph

**Deployment:**
- Kubernetes Deployment (1 replica)
- Port 3000
- No persistent storage (queries control plane)

**Access:**
```bash
# Port-forward to access locally
kubectl -n leviathan port-forward svc/leviathan-console 3000:3000

# Open in browser
open http://localhost:3000
```

**Current State (v1):**
- ✅ Basic dashboard
- ✅ Event stream view
- ✅ Graph visualization
- ⚠️ No authentication
- ⚠️ Single-target view only

**Future State (v2):**
- Multi-target dashboard
- Per-target controls (pause/resume)
- Manual task triggering
- Policy editor
- Authentication (AWS Cognito)

---

## Understanding System State

### Healthy System

**Indicators:**
- ✅ Control plane responding to health checks
- ✅ Scheduler running on schedule (every 5 minutes)
- ✅ Workers completing successfully
- ✅ PRs being created
- ✅ No circuit breaker trips

**Console View:**
```
┌─────────────────────────────────────────────────────────┐
│  Leviathan Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│  Status: Healthy ✓                                       │
│  Targets: 1 active, 0 blocked                            │
│  Open PRs: 1/2                                           │
│  Ready Tasks: 3                                          │
│  Last Execution: 2 minutes ago                           │
│                                                          │
│  Recent Activity:                                        │
│    ✓ 2m ago: PR #722 created (api-base-normalization)   │
│    ✓ 15m ago: PR #721 merged (docs-update)              │
│    ✓ 30m ago: Task selected (add-unit-tests)            │
└─────────────────────────────────────────────────────────┘
```

**Logs:**
```
[INFO] Scheduler: Selected task api-base-normalization-test
[INFO] Worker: Cloning repository iangreen74/radix
[INFO] Worker: Executing task api-base-normalization-test
[INFO] Worker: Created PR #722
[INFO] Control Plane: Event received: pr.created
```

---

### Idle System

**Indicators:**
- ✅ Control plane healthy
- ✅ Scheduler running
- ⚠️ No ready tasks in backlog
- ⚠️ No worker activity

**Console View:**
```
┌─────────────────────────────────────────────────────────┐
│  Leviathan Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│  Status: Idle                                            │
│  Targets: 1 active, 0 blocked                            │
│  Open PRs: 0/2                                           │
│  Ready Tasks: 0                                          │
│  Last Execution: 2 hours ago                             │
│                                                          │
│  No ready tasks in backlog.                              │
│  Add tasks with ready: true to resume execution.         │
└─────────────────────────────────────────────────────────┘
```

**Logs:**
```
[INFO] Scheduler: No ready tasks found in backlog
[INFO] Scheduler: Exiting cleanly (idle)
```

**Action:** Normal state. Add tasks with `ready: true` to resume execution.

---

### Blocked System

**Indicators:**
- ✅ Control plane healthy
- ✅ Scheduler running
- ⚠️ Ready tasks exist but not being executed
- ⚠️ Max open PRs reached OR circuit breaker tripped

**Console View (Max PRs):**
```
┌─────────────────────────────────────────────────────────┐
│  Leviathan Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│  Status: Blocked (Max PRs) ⚠                             │
│  Targets: 1 active, 0 blocked                            │
│  Open PRs: 2/2 (MAX REACHED)                             │
│  Ready Tasks: 5                                          │
│  Last Execution: 1 hour ago                              │
│                                                          │
│  Execution blocked: Max open PRs reached.                │
│  Merge or close PRs to resume execution.                 │
│                                                          │
│  Open PRs:                                               │
│    • PR #722 (api-base-normalization-test)               │
│    • PR #721 (docs-update)                               │
└─────────────────────────────────────────────────────────┘
```

**Console View (Circuit Breaker):**
```
┌─────────────────────────────────────────────────────────┐
│  Leviathan Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│  Status: Blocked (Circuit Breaker) ⚠                     │
│  Targets: 0 active, 1 blocked                            │
│  Open PRs: 1/2                                           │
│  Ready Tasks: 3                                          │
│  Last Execution: 30 minutes ago                          │
│                                                          │
│  Circuit breaker tripped after 2 consecutive failures.   │
│  Cooldown expires in 30 minutes.                         │
│                                                          │
│  Recent Failures:                                        │
│    ✗ 30m ago: ci-workflow-update (timeout)               │
│    ✗ 45m ago: deps-update (path violation)               │
└─────────────────────────────────────────────────────────┘
```

**Logs:**
```
[WARN] Scheduler: Max open PRs reached (2/2)
[WARN] Scheduler: Skipping task selection
[INFO] Scheduler: Exiting cleanly (blocked)
```

**Action:**
- **Max PRs:** Merge or close open PRs
- **Circuit Breaker:** Wait for cooldown or investigate failures

---

### Failed System

**Indicators:**
- ❌ Control plane not responding
- ❌ Scheduler not running
- ❌ Workers failing repeatedly

**Console View:**
```
┌─────────────────────────────────────────────────────────┐
│  Leviathan Dashboard                                     │
├─────────────────────────────────────────────────────────┤
│  Status: Error ✗                                         │
│  Control Plane: Unreachable                              │
│  Last Contact: 15 minutes ago                            │
│                                                          │
│  Unable to fetch system status.                          │
│  Check control plane health.                             │
└─────────────────────────────────────────────────────────┘
```

**Logs:**
```
[ERROR] Control Plane: Database connection failed
[ERROR] Worker: Failed to clone repository (auth error)
[ERROR] Scheduler: Failed to submit job (API error)
```

**Action:** Investigate control plane, check secrets, verify Kubernetes health.

---

## Operator Controls

### 1. Disable Autonomy (Graceful)

**Method:** Update ConfigMap

```bash
# Edit ConfigMap
kubectl edit configmap leviathan-autonomy-config -n leviathan

# Set autonomy_enabled: false
# Save and exit

# Verify
kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml | grep autonomy_enabled
```

**Effect:**
- Scheduler reads config at start of next cycle
- Logs: `⚠ Autonomy disabled in configuration`
- Scheduler exits without submitting jobs
- No new workers created

**Timeline:** Max 5 minutes (next scheduler tick)

---

### 2. Emergency Stop

**Method:** Suspend CronJob

```bash
# Suspend scheduler
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":true}}'

# Delete running workers (optional)
kubectl delete jobs -n leviathan -l app=leviathan-worker

# Verify
kubectl get cronjob leviathan-dev-scheduler -n leviathan
# Should show SUSPEND: True
```

**Effect:**
- Immediate halt of new scheduler pods
- Running workers continue to completion
- No new tasks selected

**Use Case:** Critical issue requiring immediate halt

---

### 3. Re-enable Autonomy

**Method:** Update ConfigMap + Unsuspend CronJob

```bash
# Update ConfigMap
kubectl edit configmap leviathan-autonomy-config -n leviathan
# Set autonomy_enabled: true

# Unsuspend scheduler (if suspended)
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":false}}'

# Verify
curl -H "Authorization: Bearer $TOKEN" \
  http://leviathan-control-plane:8000/v1/autonomy/status
```

**Effect:**
- Scheduler resumes on next tick
- Tasks selected and executed normally

---

### 4. Manual Task Trigger (Future)

**Method:** Console UI or API

```bash
# Via API (future)
curl -X POST http://control-plane:8000/v1/tasks/trigger \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "target": "iangreen74/radix",
    "task_id": "api-base-normalization-test"
  }'
```

**Effect:**
- Bypasses scheduler
- Creates worker job immediately
- Respects policy guardrails

**Use Case:** Urgent task execution

---

## Monitoring Stack

### Recommended Setup

**Components:**
1. **Prometheus** - Metrics collection
2. **Grafana** - Dashboards and visualization
3. **AlertManager** - Alerting

**Deployment:**
```bash
# Deploy Prometheus Operator
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/main/manifests/setup/
kubectl apply -f https://raw.githubusercontent.com/prometheus-operator/kube-prometheus/main/manifests/

# Configure ServiceMonitor for Spider Node
kubectl apply -f ops/k8s/monitoring/spider-servicemonitor.yaml

# Access Grafana
kubectl -n monitoring port-forward svc/grafana 3001:3000
# Default credentials: admin/admin
```

---

### Key Metrics

**System Health:**
- `up{job="leviathan-control-plane"}` - Control plane availability
- `up{job="leviathan-spider"}` - Spider Node availability
- `leviathan_scheduler_cycles_total` - Scheduler execution count

**Task Execution:**
- `leviathan_attempts_total{status="success"}` - Successful attempts
- `leviathan_attempts_total{status="failure"}` - Failed attempts
- `leviathan_prs_created_total` - PRs created
- `leviathan_tasks_selected_total` - Tasks selected

**Target Health:**
- `leviathan_target_status{target, status}` - Target state
- `leviathan_target_open_prs{target}` - Open PR count per target
- `leviathan_target_ready_tasks{target}` - Ready task count per target

**Resource Usage:**
- `container_memory_usage_bytes{pod=~"leviathan-.*"}` - Memory usage
- `container_cpu_usage_seconds_total{pod=~"leviathan-.*"}` - CPU usage
- `kubelet_volume_stats_used_bytes{persistentvolumeclaim="leviathan-events"}` - Disk usage

---

### Alerting Rules

**Critical Alerts:**

```yaml
# control-plane-down.yaml
- alert: ControlPlaneDown
  expr: up{job="leviathan-control-plane"} == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Control Plane is down"
    description: "Control Plane has been unreachable for 5 minutes"

# circuit-breaker-tripped.yaml
- alert: CircuitBreakerTripped
  expr: leviathan_circuit_breaker_trips_total > 0
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "Circuit breaker tripped for target {{ $labels.target }}"
    description: "Consecutive failures detected, execution halted"
```

**Warning Alerts:**

```yaml
# high-failure-rate.yaml
- alert: HighFailureRate
  expr: rate(leviathan_attempts_total{status="failure"}[1h]) > 0.2
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "High failure rate detected"
    description: "Failure rate >20% over last hour"

# max-prs-reached.yaml
- alert: MaxPRsReached
  expr: leviathan_target_open_prs >= leviathan_target_max_prs
  for: 1h
  labels:
    severity: warning
  annotations:
    summary: "Max PRs reached for target {{ $labels.target }}"
    description: "Target blocked, merge PRs to resume"
```

---

## Grafana Dashboards

### Dashboard: System Overview

**Panels:**
1. **Status** - Current system state (healthy, idle, blocked, error)
2. **Targets** - Active/blocked target count
3. **Open PRs** - Current vs max
4. **Ready Tasks** - Pending task count
5. **Recent Activity** - Timeline of events
6. **Success Rate** - Attempt success rate over time

**Queries:**
```promql
# System status
up{job="leviathan-control-plane"}

# Open PRs
leviathan_target_open_prs

# Success rate
rate(leviathan_attempts_total{status="success"}[1h]) / 
rate(leviathan_attempts_total[1h])
```

### Dashboard: Target Detail

**Panels:**
1. **Target Status** - Current state
2. **Open PRs** - Count and list
3. **Ready Tasks** - Count and queue
4. **Attempt History** - Success/failure timeline
5. **PR Creation Rate** - PRs per hour
6. **Circuit Breaker Status** - Trips and cooldowns

---

## Troubleshooting Guide

### Problem: No Tasks Being Executed

**Symptoms:**
- Scheduler running
- Ready tasks in backlog
- No worker jobs created

**Diagnosis:**
```bash
# Check scheduler logs
kubectl -n leviathan logs -l app=leviathan-dev-scheduler --tail=50

# Check autonomy status
curl http://control-plane:8000/v1/autonomy/status

# Check open PR count
gh pr list --repo iangreen74/radix --state open
```

**Possible Causes:**
1. Autonomy disabled (`autonomy_enabled: false`)
2. Max open PRs reached
3. Circuit breaker tripped
4. All tasks have dependencies

**Resolution:**
- Enable autonomy if disabled
- Merge PRs if at max
- Wait for circuit breaker cooldown
- Remove dependencies or mark them satisfied

---

### Problem: Workers Failing Repeatedly

**Symptoms:**
- Workers created but fail quickly
- Circuit breaker trips
- No PRs created

**Diagnosis:**
```bash
# Check worker logs
kubectl -n leviathan logs -l app=leviathan-worker --tail=100

# Check recent job status
kubectl -n leviathan get jobs -l app=leviathan-worker --sort-by=.metadata.creationTimestamp
```

**Possible Causes:**
1. Invalid GitHub token
2. Path violation (task outside allowed_paths)
3. Repository access denied
4. Timeout (task takes >15 minutes)

**Resolution:**
- Rotate GitHub token
- Fix task allowed_paths
- Grant repository access
- Increase timeout or split task

---

### Problem: Control Plane Unreachable

**Symptoms:**
- Console shows "Error" status
- Workers cannot post events
- API requests timeout

**Diagnosis:**
```bash
# Check control plane pod
kubectl -n leviathan get pods -l app=leviathan-control-plane

# Check logs
kubectl -n leviathan logs -l app=leviathan-control-plane --tail=100

# Check service
kubectl -n leviathan get svc leviathan-control-plane
```

**Possible Causes:**
1. Pod crashed (OOM, disk full)
2. Service misconfigured
3. Network policy blocking traffic

**Resolution:**
- Restart pod if crashed
- Check disk usage (event store)
- Verify service endpoints
- Check network policies

---

## Best Practices

### 1. Monitor Continuously

- Set up Grafana dashboards
- Configure critical alerts
- Review metrics daily
- Investigate anomalies promptly

### 2. Respond to Alerts

- Critical alerts: Respond within 15 minutes
- Warning alerts: Investigate within 1 hour
- Document resolutions in runbook

### 3. Regular Maintenance

- Review open PRs weekly
- Prune old events monthly (future: retention policy)
- Rotate secrets quarterly
- Update dependencies monthly

### 4. Capacity Planning

- Monitor disk usage (event store)
- Track worker job duration
- Plan for target growth
- Scale resources proactively

---

## Future Enhancements

### Phase 2: Enhanced Observability

- Real-time console updates (WebSocket)
- Anomaly detection (ML-based)
- Cost attribution per target
- Performance profiling

### Phase 3: Advanced Controls

- Per-target autonomy toggle (console UI)
- Manual task triggering (console UI)
- Policy editor (console UI)
- Rollback mechanism (revert PR)

---

## References

- [21_OPERATIONS_AUTONOMY.md](21_OPERATIONS_AUTONOMY.md) - Autonomy operations runbook
- [20_SPIDER_NODE.md](20_SPIDER_NODE.md) - Spider Node documentation
- [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Strategic roadmap
- [32_MULTI_TARGET_ARCHITECTURE.md](32_MULTI_TARGET_ARCHITECTURE.md) - Multi-target design

---

**Document Status:** Living document, updated as observability evolves.
