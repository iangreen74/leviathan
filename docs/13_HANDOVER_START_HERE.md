# ⚠️ START HERE — DO NOT SKIP

This document is the authoritative handover for Leviathan.

**If you are continuing work in a new chat or session:**

1. **Read this file fully.**
2. **Do NOT act on assumptions not explicitly stated here.**
3. **Treat all archived docs as non-authoritative.**

---

## System Summary

**Leviathan** is a closed-loop autonomous software engineering system that executes tasks from target repository backlogs and creates pull requests automatically under strict guardrails.

**Problem it solves:** Automate repetitive software engineering tasks (documentation updates, backlog management, dependency updates) while maintaining human oversight through PR-based delivery.

**Current operational state:** Autonomy v1 is implemented and operational in DEV environments (kind clusters). The system continuously monitors target backlogs, selects ready tasks, and creates PRs automatically with strict scope restrictions and concurrency limits.

---

## Current State Checklist

- ✅ **PR Proof v1 (local):** DONE - Local execution of backlog propose workflow
- ✅ **PR Proof v1 (K8s):** DONE - Kubernetes Job-based execution on kind
- ✅ **Autonomy v1 (DEV):** IMPLEMENTED - Closed-loop scheduler + worker with guardrails
- ✅ **Control Plane:** OPERATIONAL - FastAPI service ingesting events, persisting to NDJSON
- ✅ **Scheduler:** OPERATIONAL - CronJob running every 5 minutes, selecting ready tasks
- ✅ **Worker:** OPERATIONAL - Kubernetes Jobs creating PRs to target repos
- ✅ **Invariants:** ENFORCED - 12 invariant checks in CI, all passing
- ✅ **Tests:** PASSING - 369 unit tests, all green
- ✅ **Documentation:** CANONICAL - Authoritative docs in `docs/`, legacy archived

---

## What Leviathan MUST NOT Do

### 1. No Autonomous Planning
Leviathan does NOT invent tasks. It only executes tasks already present in target backlogs with `ready: true`.

### 2. No Auto-Merge
All changes are delivered via GitHub pull requests. No direct commits to main. No automatic merging (unless explicitly enabled per target with human approval).

### 3. No PROD Infrastructure Mutation
DEV mode is restricted to `.leviathan/**` and `docs/**` paths. Production autonomy requires explicit scope configuration and approval.

### 4. No Unbounded Execution
Strict guardrails enforce:
- Max 1 open PR at a time (DEV)
- Max 2 attempts per task
- Circuit breaker after 2 consecutive failures
- 15-minute timeout per attempt

---

## The NEXT PHASE

### Phase 1: Spider Node v1 (Observer + Telemetry)

**Purpose:** Add observability and metrics collection without changing execution behavior.

**Components:**
- Spider Node service (FastAPI)
- Metrics collection (Prometheus format)
- Event stream observer
- Health checks and status endpoints

**Deliverables:**
- `leviathan/spider/` module
- `ops/k8s/spider/` manifests
- Metrics exposition on `/metrics`
- Integration with control plane event stream

### Phase 2: Full Autonomy Mode (Production-Ready)

**Definition of "Full Autonomy Mode":**

1. **Continuous Scheduling:** Scheduler runs continuously (every 5 minutes or configurable interval)
2. **Backlog-Governed Execution:** Only executes tasks with `ready: true` from target backlogs
3. **No Task Invention:** Leviathan does NOT create, modify, or prioritize tasks
4. **No Scope Expansion:** Tasks must have `allowed_paths` within configured scope prefixes
5. **PR-Based Delivery:** All changes via pull requests with human review
6. **Guardrails Enforced:** Max open PRs, retry limits, circuit breakers, timeouts
7. **Deterministic Evidence:** Full event history persisted and queryable

**What Full Autonomy Mode IS:**
- Continuous execution of pre-approved tasks
- Automated PR creation for approved changes
- Scope-limited, guardrail-protected operation

**What Full Autonomy Mode IS NOT:**
- Autonomous planning or task creation
- Self-directed product work
- Unbounded scope expansion
- Auto-merge without approval

---

## Exact Next Engineering Steps

### 1. Build Spider Node v1 (Observer + Telemetry)

**Tasks:**
- [ ] Create `leviathan/spider/` module structure
- [ ] Implement Spider Node FastAPI service
- [ ] Add Prometheus metrics exposition
- [ ] Implement event stream observer
- [ ] Add health check endpoints
- [ ] Create Kubernetes manifests (`ops/k8s/spider/`)
- [ ] Add unit tests for Spider Node
- [ ] Update invariants for Spider Node manifests

**Acceptance Criteria:**
- Spider Node deploys to kind cluster
- Metrics available at `/metrics`
- Event stream observable via Spider API
- Health checks return 200 OK
- All tests passing

### 2. Integrate Spider Node with Control Plane

**Tasks:**
- [ ] Add event stream subscription to control plane
- [ ] Implement event forwarding to Spider Node
- [ ] Add Spider Node discovery (service DNS)
- [ ] Add retry logic for Spider Node communication
- [ ] Update control plane to expose event stream endpoint

**Acceptance Criteria:**
- Control plane forwards events to Spider Node
- Spider Node receives and processes events
- Metrics reflect event processing
- Failure to reach Spider Node does not block worker execution

### 3. Add Explicit Autonomy ON/OFF Switch

**Tasks:**
- [ ] Add `autonomy_enabled: true/false` to `ops/autonomy/dev.yaml`
- [ ] Implement scheduler check for autonomy flag
- [ ] Add API endpoint to query autonomy status
- [ ] Add API endpoint to toggle autonomy (admin only)
- [ ] Update documentation for autonomy control

**Acceptance Criteria:**
- Scheduler respects `autonomy_enabled` flag
- Setting to `false` stops scheduling (graceful)
- API endpoint returns current status
- Toggle requires authentication

### 4. Prepare for AWS Spider Node Deployment

**Tasks:**
- [ ] Create AWS deployment manifests (EKS)
- [ ] Add Terraform/CloudFormation for Spider Node
- [ ] Configure AWS secrets management
- [ ] Add AWS-specific invariants
- [ ] Document AWS deployment runbook

**Acceptance Criteria:**
- Spider Node deployable to EKS
- Secrets managed via AWS Secrets Manager
- Metrics exportable to CloudWatch
- Deployment documented in runbook

---

## How to Safely Start Work

### 1. Read These Docs (In Order)

1. **[00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md)** - System overview and current state
2. **[01_QUICKSTART.md](01_QUICKSTART.md)** - Run Autonomy v1 on kind in 5 minutes
3. **[10_ARCHITECTURE.md](10_ARCHITECTURE.md)** - Complete system architecture
4. **[07_INVARIANTS_AND_GUARDRAILS.md](07_INVARIANTS_AND_GUARDRAILS.md)** - Invariants philosophy and enforcement

### 2. Inspect These Configs

1. **`ops/autonomy/dev.yaml`** - Autonomy configuration (guardrails, scope, limits)
2. **`ops/invariants.yaml`** - Machine-enforced invariants
3. **`ops/k8s/scheduler/dev-autonomy.yaml`** - Scheduler CronJob manifest
4. **`ops/k8s/control-plane.yaml`** - Control plane deployment

### 3. Understand These Invariants (MUST NOT VIOLATE)

1. **Namespace:** All K8s resources use `namespace: leviathan`
2. **Image Pull Policy:** Local images (`:local`) must have `imagePullPolicy: IfNotPresent`
3. **Module Execution:** K8s Jobs use `command: ["python3", "-m", "module"]`, no shell scripts
4. **Scope Restrictions:** DEV tasks limited to `.leviathan/**` and `docs/**`
5. **Concurrency:** Max 1 open PR at a time (DEV)
6. **Retry Limits:** Max 2 attempts per task
7. **No Autonomous Planning:** Tasks must have `ready: true` in backlog
8. **PR-Based Delivery:** No direct commits, no auto-merge

### 4. Run These Commands to Validate

```bash
# Run unit tests (must pass)
python3 -m pytest tests/unit -q

# Run invariants check (must pass)
python3 tools/invariants_check.py

# Check current git branch
git branch --show-current

# Check for uncommitted changes
git status --short
```

### 5. Before Making Changes

1. **Create a feature branch:** `git checkout -b feat/your-feature`
2. **Read relevant code:** Start with module `__init__.py` and `__main__.py`
3. **Check existing tests:** Look for `tests/unit/test_your_module.py`
4. **Verify invariants:** Ensure your changes don't violate invariants
5. **Run tests frequently:** `python3 -m pytest tests/unit -q`

---

## Critical Files and Locations

### Code
- **Scheduler:** `leviathan/scheduler/dev_autonomy.py`
- **Worker:** `leviathan/executor/backlog_propose_worker/__main__.py`
- **Control Plane:** `leviathan/control_plane/api.py`
- **Backlog Propose:** `leviathan/executor/backlog_propose.py`

### Configuration
- **Autonomy Config:** `ops/autonomy/dev.yaml`
- **Invariants:** `ops/invariants.yaml`
- **K8s Manifests:** `ops/k8s/`

### Documentation
- **Canonical Docs:** `docs/00_*.md`, `docs/01_*.md`, `docs/10_*.md`
- **Archived Docs:** `docs/archive/pre_autonomy_docs/` (non-authoritative)

### Tests
- **Unit Tests:** `tests/unit/`
- **Invariants Tests:** `tests/unit/test_invariants_*.py`

### Tools
- **Invariants Check:** `tools/invariants_check.py`

---

## Common Pitfalls to Avoid

### 1. Referencing Archived Documentation
**DON'T:** Use information from `docs/archive/pre_autonomy_docs/`  
**DO:** Use canonical docs in `docs/`

### 2. Assuming Autonomous Planning
**DON'T:** Implement features that invent tasks  
**DO:** Execute tasks from backlog with `ready: true`

### 3. Violating Scope Restrictions
**DON'T:** Allow tasks to modify files outside `.leviathan/**` and `docs/**` (DEV)  
**DO:** Enforce scope checks in scheduler

### 4. Bypassing Guardrails
**DON'T:** Remove or weaken max_open_prs, retry limits, circuit breakers  
**DO:** Respect guardrails, adjust configuration if needed

### 5. Using Shell Scripts in K8s Jobs
**DON'T:** `command: ["bash", "-c", "python3 script.py"]`  
**DO:** `command: ["python3", "-m", "leviathan.module"]`

### 6. Hardcoding Secrets
**DON'T:** Put tokens or passwords in code or manifests  
**DO:** Use Kubernetes Secrets, inject as environment variables

---

## Emergency Procedures

### Stop Autonomy Immediately

```bash
# Suspend scheduler (stops new jobs)
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":true}}'

# Delete running worker jobs
kubectl -n leviathan delete jobs -l app=leviathan-worker
```

### Resume Autonomy

```bash
# Resume scheduler
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":false}}'
```

### Check System Health

```bash
# Control plane
kubectl -n leviathan get pods -l app=leviathan-control-plane

# Scheduler
kubectl -n leviathan get cronjobs

# Recent worker jobs
kubectl -n leviathan get jobs -l app=leviathan-worker --sort-by=.metadata.creationTimestamp
```

---

## Questions to Ask Before Proceeding

1. **Is this change documented?** If not, update canonical docs.
2. **Does this violate any invariants?** Run `python3 tools/invariants_check.py`.
3. **Are there tests?** Add unit tests for new code.
4. **Is this scope-safe?** Verify changes respect guardrails.
5. **Is this reversible?** Ensure changes can be rolled back.

---

## Summary

**Leviathan is operational.** Autonomy v1 works. The next phase is Spider Node v1 (observability) and Full Autonomy Mode (production-ready).

**Your job:** Build Spider Node, integrate with control plane, add autonomy controls, prepare for AWS deployment.

**Your constraints:** No autonomous planning, no auto-merge, no unbounded execution, no invariant violations.

**Your resources:** Canonical docs, 369 passing tests, 12 enforced invariants, operational DEV environment.

**Start here, stay safe, ship incrementally.**
