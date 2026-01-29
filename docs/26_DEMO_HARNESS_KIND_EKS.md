# Leviathan Demo Harness - Live System Walkthrough

**Version:** 1.0  
**Duration:** ~10 minutes  
**Purpose:** Demonstrate the real Leviathan system actively used to build Radix

---

## A. Purpose & Framing

### What This Demo Shows

This walkthrough demonstrates **how Radix is built using Leviathan today**. This is not a simulation, mock, or demo mode. You are observing the actual production system that autonomously creates pull requests for the Radix research product.

**Key Points:**
- ✅ Real system, real target (Radix)
- ✅ Same configuration used for internal development
- ✅ Same guarantees as production operation
- ✅ No special demo flags or mock repositories
- ✅ Observable governance and control mechanisms

### What You Will See

1. **System Status** - Query autonomy state via authenticated API
2. **Observability** - View real-time metrics from Spider Node
3. **Event Flow** - Observe event ingestion and forwarding
4. **Governance Controls** - Disable autonomy deterministically
5. **Emergency Stop** - Suspend scheduler immediately
6. **Recovery** - Re-enable autonomy and restore normal operation

**Timeline:** Each step takes 1-2 minutes. Total walkthrough: ~10 minutes.

---

## B. Environment Selection

### Choose Your Environment

**Option 1: kind (Local)**
- Fastest setup
- No cloud costs
- Suitable for engineering demos
- Reference: [docs/23_INTEGRATION_EVIDENCE_KIND.md](./23_INTEGRATION_EVIDENCE_KIND.md)

**Option 2: EKS (Cloud)**
- Production-equivalent environment
- Suitable for investor/partner demos
- Reference: [docs/24_EKS_DEPLOYMENT_EVIDENCE.md](./24_EKS_DEPLOYMENT_EVIDENCE.md)

**Prerequisites (Either Environment):**
- Leviathan deployed and running
- Control plane and Spider Node healthy
- Scheduler CronJob active
- `kubectl` access to cluster
- Control plane token available

**Verify Prerequisites:**
```bash
# Check all pods are running
kubectl get pods -n leviathan

# Expected output:
# NAME                                      READY   STATUS    RESTARTS   AGE
# leviathan-control-plane-xxxxx-xxxxx       1/1     Running   0          <time>
# leviathan-spider-xxxxx-xxxxx              1/1     Running   0          <time>

# Check CronJob exists
kubectl get cronjob -n leviathan

# Expected output:
# NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
# leviathan-dev-scheduler     */5 * * * *   False     0        <time>          <time>
```

**Set Environment Variables:**
```bash
# Your control plane token (from deployment)
export CONTROL_PLANE_TOKEN="your_token_here"

# Verify token is set
echo $CONTROL_PLANE_TOKEN
```

---

## C. Demo Walkthrough

### Step 1: Show System Status (2 minutes)

**Purpose:** Demonstrate authenticated API access and autonomy state query.

**Port-forward control plane:**
```bash
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &
```

**Query autonomy status:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq
```

**Expected Response:**
```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

**Explain to Audience:**

> "This endpoint shows the current autonomy state. The system reads this configuration from a Kubernetes ConfigMap at the start of each scheduling cycle."
>
> **Fields:**
> - `autonomy_enabled: true` - Scheduler will execute ready tasks
> - `source` - Configuration source (ConfigMap mounted read-only)
>
> **Key Point:** This is the same API we use internally to verify system state before and after operations.

**Alternative (if no auth):**
```bash
curl http://localhost:8000/v1/autonomy/status
# Response: {"detail":"Not authenticated"}
```

> "Notice: All endpoints require bearer token authentication. No unauthenticated access is permitted."

---

### Step 2: Show Observability (2 minutes)

**Purpose:** Demonstrate non-blocking observability via Spider Node.

**Port-forward Spider Node:**
```bash
kubectl port-forward -n leviathan svc/leviathan-spider 8001:8001 &
```

**Check Spider health:**
```bash
curl http://localhost:8001/health | jq
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "spider"
}
```

**View Prometheus metrics:**
```bash
curl -s http://localhost:8001/metrics | head -20
```

**Expected Output:**
```
# HELP leviathan_spider_up Spider node availability
# TYPE leviathan_spider_up gauge
leviathan_spider_up 1.0

# HELP leviathan_events_received_total Total events received by type
# TYPE leviathan_events_received_total counter
leviathan_events_received_total{event_type="pr.opened"} 5.0
leviathan_events_received_total{event_type="pr.closed"} 2.0
leviathan_events_received_total{event_type="task.started"} 8.0
leviathan_events_received_total{event_type="task.completed"} 7.0
...
```

**Explain to Audience:**

> "Spider Node is our observability service. It receives events from the control plane via non-blocking HTTP forwarding."
>
> **Key Metrics:**
> - `leviathan_spider_up` - Spider availability (1.0 = healthy)
> - `leviathan_events_received_total` - Event counters by type
>
> **Event Types You're Seeing:**
> - `pr.opened` - Pull requests created by workers
> - `pr.closed` - Pull requests merged or closed
> - `task.started` - Worker began executing a task
> - `task.completed` - Worker finished a task
>
> **Critical Guarantee:** Spider failures never block the control plane. Event forwarding is best-effort. If Spider is down, the control plane continues operating normally.

**Show specific metric:**
```bash
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="pr.opened"}'
```

**Example Output:**
```
leviathan_events_received_total{event_type="pr.opened"} 5.0
```

> "This counter shows 5 pull requests have been opened by Leviathan on the Radix repository. These are real PRs created by the system."

---

### Step 3: Trigger Real Activity (3 minutes)

**Purpose:** Demonstrate event ingestion and forwarding in real-time.

**Option A: Let Scheduler Pick Next Real Task (Preferred)**

> "We're going to manually trigger the scheduler to pick the next ready task from the Radix backlog. This is the same process that runs automatically every 5 minutes."

**Capture baseline metrics:**
```bash
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="task.started"}'
```

**Example Output:**
```
leviathan_events_received_total{event_type="task.started"} 8.0
```

**Manually trigger scheduler:**
```bash
kubectl create job --from=cronjob/leviathan-dev-scheduler demo-trigger-1 -n leviathan
```

**Expected Output:**
```
job.batch/demo-trigger-1 created
```

**Watch job progress:**
```bash
kubectl get jobs -n leviathan -l job-name=demo-trigger-1 -w
```

**Wait for completion (~30-60 seconds):**
```
NAME              COMPLETIONS   DURATION   AGE
demo-trigger-1    0/1           0s         0s
demo-trigger-1    0/1           5s         5s
demo-trigger-1    1/1           45s        45s
```

Press `Ctrl+C` to stop watching.

**Check scheduler logs:**
```bash
kubectl logs job/demo-trigger-1 -n leviathan --tail=30
```

**Possible Outcomes:**

**Outcome 1: Task Executed**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T20:30:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

✓ Found 3 ready tasks in backlog
✓ Selected task: implement-feature-x (priority: high)
✓ Submitted worker job: leviathan-worker-abc123
✓ Scheduling cycle complete
```

> "The scheduler found a ready task in the Radix backlog and submitted a worker job. The worker will clone the Radix repository, execute the task, and create a pull request."

**Check for worker job:**
```bash
kubectl get jobs -n leviathan -l app=leviathan-worker
```

**Outcome 2: No Ready Tasks**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T20:30:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

ℹ No executable tasks found
  Reasons:
  - 0 tasks with ready: true
  - 2 tasks blocked by dependencies
✓ Scheduling cycle complete (no action)
```

> "The scheduler found no tasks marked `ready: true` in the Radix backlog. This is normal—Leviathan only executes tasks explicitly marked as ready. It does not invent work."

**Outcome 3: Max Open PRs Reached**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T20:30:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

⚠ Max open PRs reached (1/1)
✓ Scheduling cycle complete (no action)
```

> "The scheduler detected that the maximum number of open PRs has been reached. This is a concurrency limit to prevent overwhelming the repository with PRs. Once a PR is merged or closed, the scheduler will resume."

**Verify Spider metrics updated:**
```bash
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="task.started"}'
```

**Expected (if task executed):**
```
leviathan_events_received_total{event_type="task.started"} 9.0
```

> "Notice the counter incremented from 8 to 9. The control plane forwarded the `task.started` event to Spider, and Spider updated its metrics."

---

**Option B: POST Synthetic Event (Alternative)**

> "If no real tasks are ready, we can demonstrate event flow with a synthetic event. This is clearly labeled as synthetic and does not affect Radix."

**Capture baseline:**
```bash
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="demo.synthetic"}'
```

**Expected (first time):**
```
# No output (metric doesn't exist yet)
```

**Create synthetic event:**
```bash
cat > /tmp/demo_event.json <<'EOF'
{
  "events": [
    {
      "event_id": "demo-synthetic-001",
      "event_type": "demo.synthetic",
      "timestamp": "2026-01-28T20:30:00Z",
      "payload": {
        "purpose": "demonstration",
        "note": "This is a synthetic event for demo purposes only"
      }
    }
  ]
}
EOF
```

**Ingest event:**
```bash
curl -X POST \
  -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/demo_event.json \
  http://localhost:8000/v1/events/ingest | jq
```

**Expected Response (immediate):**
```json
{
  "status": "success",
  "events_ingested": 1,
  "events_projected": 1
}
```

> "The control plane returned immediately. Event forwarding to Spider happens asynchronously in the background."

**Wait 2-3 seconds, then check Spider:**
```bash
sleep 3
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="demo.synthetic"}'
```

**Expected:**
```
leviathan_events_received_total{event_type="demo.synthetic"} 1.0
```

> "The Spider received the event and created a new metric counter. This demonstrates non-blocking event forwarding."

---

### Step 4: Demonstrate Governance (2 minutes)

**Purpose:** Show deterministic autonomy disable via ConfigMap.

> "We're going to disable autonomy using the kill switch. This is the same procedure we use internally when we need to pause autonomous operation."

**Verify current state:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq '.autonomy_enabled'
```

**Expected:**
```
true
```

**Disable autonomy:**
```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

In the editor, change:
```yaml
autonomy_enabled: true
```

To:
```yaml
autonomy_enabled: false
```

Save and exit (`:wq` in vim).

**Verify ConfigMap updated:**
```bash
kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml | grep autonomy_enabled
```

**Expected:**
```
    autonomy_enabled: false
```

**Verify status API reflects change:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq
```

**Expected:**
```json
{
  "autonomy_enabled": false,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

> "The status API immediately reflects the ConfigMap change. The control plane reads the ConfigMap on every request."

**Trigger scheduler with autonomy disabled:**
```bash
kubectl create job --from=cronjob/leviathan-dev-scheduler demo-trigger-disabled -n leviathan
```

**Wait for completion:**
```bash
kubectl wait --for=condition=complete job/demo-trigger-disabled -n leviathan --timeout=60s
```

**Check scheduler logs:**
```bash
kubectl logs job/demo-trigger-disabled -n leviathan
```

**Expected Output:**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T20:35:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

⚠ Autonomy disabled in configuration (autonomy_enabled: false)
✓ Scheduler exiting cleanly without submitting jobs
```

> "The scheduler detected `autonomy_enabled: false` and exited immediately without submitting any worker jobs. This is deterministic—no tasks will be executed while autonomy is disabled."

**Verify no worker jobs created:**
```bash
kubectl get jobs -n leviathan -l app=leviathan-worker --field-selector status.successful=0
```

**Expected:**
```
No resources found in leviathan namespace.
```

**Explain to Audience:**

> "This demonstrates the autonomy kill switch. Key properties:"
>
> - **Deterministic:** Scheduler reads config at cycle start
> - **No restart required:** Takes effect on next scheduler tick (max 5 minutes)
> - **Immediate API reflection:** Status API shows change instantly
> - **Clean exit:** Scheduler logs clearly state why it's not executing
>
> "This is how we pause Leviathan when needed—for maintenance, testing, or operational reasons."

---

### Step 5: Emergency Stop (1 minute)

**Purpose:** Demonstrate immediate scheduler suspension.

> "If we need to stop the scheduler immediately—not just disable autonomy, but prevent any scheduler pods from running—we suspend the CronJob."

**Suspend CronJob:**
```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":true}}'
```

**Expected:**
```
cronjob.batch/leviathan-dev-scheduler patched
```

**Verify suspension:**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

**Expected:**
```
NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
leviathan-dev-scheduler     */5 * * * *   True      0        <time>          <time>
```

> "Notice `SUSPEND: True`. The CronJob will not create any new scheduler pods. This is an emergency stop—no scheduling cycles will run until we resume."

**Explain to Audience:**

> "Emergency stop is used when:"
> - Critical issue detected in scheduler or worker
> - Need to perform urgent maintenance
> - External dependency (GitHub API) is down
>
> "This is immediate—no new scheduler pods are created. Existing worker jobs continue to completion, but no new jobs are submitted."

**Optional: Delete running workers (if any):**
```bash
kubectl delete jobs -n leviathan -l app=leviathan-worker
```

> "We can also delete running worker jobs if needed. This is a hard stop."

---

### Step 6: Recovery (1 minute)

**Purpose:** Restore normal operation.

> "Now we'll restore the system to normal operation. This is a two-step process: resume the CronJob and re-enable autonomy."

**Resume CronJob:**
```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":false}}'
```

**Expected:**
```
cronjob.batch/leviathan-dev-scheduler patched
```

**Verify resumption:**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

**Expected:**
```
NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
leviathan-dev-scheduler     */5 * * * *   False     0        <time>          <time>
```

> "CronJob is now active again. Scheduler pods will be created on the next 5-minute tick."

**Re-enable autonomy:**
```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

Change back to:
```yaml
autonomy_enabled: true
```

Save and exit.

**Verify status API:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq
```

**Expected:**
```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

> "System is now restored to normal operation. The next scheduler cycle will execute ready tasks from the Radix backlog."

**Explain to Audience:**

> "Recovery is deterministic and reversible. We've demonstrated:"
> - **Graceful disable:** ConfigMap update, scheduler respects flag
> - **Emergency stop:** CronJob suspension, no new pods
> - **Clean recovery:** Resume CronJob, re-enable autonomy
>
> "At no point did we lose control of the system. All operations are auditable and reversible."

---

## D. What the Demo Proves

### Governance & Control

✅ **Autonomy is bounded**
- Scheduler only executes tasks marked `ready: true` in Radix backlog
- No task invention or autonomous planning
- Explicit concurrency limits (max open PRs)

✅ **Autonomy is governable**
- Kill switch via ConfigMap (deterministic, no restart)
- Emergency stop via CronJob suspension (immediate)
- Status API provides real-time visibility

✅ **Observability is non-blocking**
- Spider Node receives events asynchronously
- Spider failures do not impact control plane
- Metrics provide real-time system visibility

✅ **Operators have full control**
- Authenticated API access required
- All operations are reversible
- System state is auditable

### Operational Transparency

✅ **Real system, real target**
- Radix development continues uninterrupted
- Same configuration used for internal production
- No demo mode or mock workflows

✅ **Deterministic behavior**
- Scheduler logs clearly state decisions
- ConfigMap changes take effect predictably
- No hidden control paths or backdoors

✅ **Safety guarantees**
- Read-only ConfigMap mounts
- Bearer token authentication on all endpoints
- Scope restrictions enforced at runtime

---

## E. What This Demo Does NOT Show

### Explicit Constraints

❌ **No autonomous planning**
- Leviathan does NOT invent tasks
- Leviathan does NOT decide what work to do
- All tasks must be explicitly defined in Radix backlog with `ready: true`

❌ **No auto-merge**
- Leviathan does NOT merge pull requests
- All PRs require human review and approval
- Merge decisions remain under human control

❌ **No scope expansion**
- Leviathan does NOT modify files outside configured path prefixes
- Scope restrictions are enforced by worker at runtime
- Configuration changes require explicit operator action

❌ **No hidden control paths**
- All operations go through documented APIs
- No backdoors or special access modes
- Authentication required for all endpoints

### Why These Constraints Matter

> "These constraints are fundamental to Leviathan's design. They ensure that autonomy remains bounded, governable, and transparent. The system is a tool for executing pre-defined work, not an autonomous agent that decides what work should be done."

---

## F. Audience Variants

### Internal Engineering Walkthrough

**Focus:**
- Technical implementation details
- Event flow and architecture
- Troubleshooting and debugging
- Integration with Radix development workflow

**Additional Steps:**
- Show control plane logs: `kubectl logs -n leviathan -l app=leviathan-control-plane --tail=50`
- Show worker job logs: `kubectl logs -n leviathan job/<job-name>`
- Demonstrate event projection: Query control plane for task history
- Show backlog structure: Inspect `.leviathan/backlog.yaml` in Radix repo

### Investor / Partner Walkthrough

**Focus:**
- Business value and productivity gains
- Safety guarantees and governance
- Operational maturity and reliability
- Roadmap and future capabilities

**Emphasis:**
- "Leviathan is actively used to build Radix—this is not a prototype"
- "System has created X pull requests on Radix over Y months"
- "Autonomy is bounded by explicit task definitions and concurrency limits"
- "Operators can stop the system instantly with emergency stop"

**Metrics to Highlight:**
- Number of PRs created on Radix
- Task completion rate
- Time savings vs manual execution
- Zero incidents with autonomous operation

### Audit / Compliance Walkthrough

**Focus:**
- Security controls and authentication
- Auditability and event logging
- Change management and rollback procedures
- Compliance with internal policies

**Additional Steps:**
- Show bearer token authentication: Demonstrate 401 without token
- Show event persistence: Control plane stores full event history
- Show ConfigMap audit trail: `kubectl describe configmap leviathan-autonomy-config -n leviathan`
- Show RBAC policies: `kubectl get rolebindings -n leviathan`

**Emphasis:**
- "All API access requires bearer token authentication"
- "All events are persisted with timestamps and payloads"
- "All configuration changes are auditable via Kubernetes API"
- "Emergency stop procedures are documented and tested"

---

## G. Cleanup & Restoration

### Return to Normal State

**Verify autonomy is enabled:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq '.autonomy_enabled'
```

**Expected:**
```
true
```

**Verify CronJob is active:**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan -o jsonpath='{.spec.suspend}'
```

**Expected:**
```
false
```

**Clean up demo jobs:**
```bash
kubectl delete job demo-trigger-1 -n leviathan --ignore-not-found
kubectl delete job demo-trigger-disabled -n leviathan --ignore-not-found
```

**Stop port-forwards:**
```bash
pkill -f "kubectl port-forward"
```

**Verify system health:**
```bash
kubectl get pods -n leviathan
```

**Expected:**
```
NAME                                      READY   STATUS    RESTARTS   AGE
leviathan-control-plane-xxxxx-xxxxx       1/1     Running   0          <time>
leviathan-spider-xxxxx-xxxxx              1/1     Running   0          <time>
```

**Final Status Check:**
```bash
# Port-forward control plane
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &

# Verify status
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq

# Stop port-forward
pkill -f "kubectl port-forward"
```

**Expected:**
```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

> "System is restored to normal operation. Radix development continues uninterrupted."

---

## H. Summary

### What You Observed

In this 10-minute walkthrough, you observed:

1. **Authenticated API access** - Status query with bearer token
2. **Real-time observability** - Spider Node metrics showing actual Radix events
3. **Event flow** - Control plane ingestion and Spider forwarding
4. **Governance controls** - Autonomy disable via ConfigMap
5. **Emergency stop** - CronJob suspension for immediate halt
6. **Clean recovery** - Deterministic restoration to normal operation

### Key Takeaways

**This is a real system:**
- Actively used to build Radix research product
- No demo mode or simulated components
- Same configuration and behavior as internal production

**Autonomy is bounded:**
- Only executes tasks marked `ready: true` in Radix backlog
- No autonomous planning or task invention
- Explicit concurrency limits and circuit breakers

**Operators have full control:**
- Kill switch via ConfigMap (deterministic)
- Emergency stop via CronJob suspension (immediate)
- All operations are reversible and auditable

**Safety is paramount:**
- Bearer token authentication required
- Read-only configuration mounts
- Non-blocking observability
- Scope restrictions enforced at runtime

---

## Related Documentation

- [Integration Evidence (kind)](./23_INTEGRATION_EVIDENCE_KIND.md)
- [EKS Deployment Evidence](./24_EKS_DEPLOYMENT_EVIDENCE.md)
- [Operations Runbook](./21_OPERATIONS_AUTONOMY.md)
- [Invariants and Guardrails](./07_INVARIANTS_AND_GUARDRAILS.md)
- [Canonical Overview](./00_CANONICAL_OVERVIEW.md)
