# Handover: Next Engineering Phase

**Date:** 2026-01-31  
**Status:** Canonical (Handover)

---

## Executive Summary

Leviathan Autonomy v1 is **operational and stable**. The system continuously executes tasks from target backlogs, creates PRs automatically, and operates under strict policy-based guardrails.

**This document provides a clean handover for the next engineering phase.**

---

## Current State (Facts)

### What Works ✅

1. **Core Execution Loop**
   - Scheduler runs every 5 minutes (CronJob)
   - Selects ready tasks from target backlog
   - Submits Kubernetes Jobs for execution
   - Workers create PRs to target repos
   - Backlog writeback prevents re-execution

2. **Task Executors**
   - Docs executor: Generates markdown from task specs
   - Tests executor: Generates pytest stubs from acceptance criteria
   - Both executors are deterministic and idempotent

3. **Control Plane**
   - FastAPI service on port 8000
   - Ingests events from workers
   - NDJSON event store (file-based)
   - Query API for graph state
   - Autonomy status endpoint

4. **Spider Node v1**
   - Standalone observability service on port 8001
   - Health check endpoint
   - Prometheus metrics endpoint (static metrics)
   - No control plane integration yet

5. **Operator Console**
   - Web UI on port 3000
   - Event stream visualization
   - Graph state display
   - No authentication (internal use only)

6. **Guardrails (DEV Environment)**
   - Scope: `.leviathan/**`, `docs/**`, `tests/**` only
   - Max 1 open PR at a time
   - Max 2 attempts per task
   - Circuit breaker after 2 consecutive failures
   - 15-minute timeout per attempt

7. **Deployment**
   - Kustomize-based (base + overlays)
   - Local: kind cluster
   - Production: AWS EKS (tested, documented)
   - All components containerized

8. **Quality**
   - 478 unit tests (all passing)
   - 12 invariant checks (all passing)
   - CI enforces tests and invariants
   - Documentation is canonical and up-to-date

### What Doesn't Work Yet ⚠️

1. **Multi-Target Architecture**
   - Architecture exists but not operational
   - Scheduler hardcoded to single target (`iangreen74/radix`)
   - No dynamic target discovery

2. **Spider Node Integration**
   - Spider Node deployed but not connected to control plane
   - Metrics are static (no real-time updates)
   - No alerting or anomaly detection

3. **Authentication**
   - Control plane has no auth
   - Console has no auth
   - Suitable for internal networks only

4. **Auto-Merge**
   - All PRs require manual review and merge
   - No per-target auto-merge configuration

5. **PostgreSQL Backend**
   - Event store is NDJSON files (not scalable)
   - No PostgreSQL migration yet

---

## What Was Just Completed

### 1. Allowed Paths Boundary Hardening (PR #63)

**Problem:** Naive string prefix check allowed bypasses (e.g., `docs/` matched `docs2/`).

**Solution:** Implemented boundary-safe validation preserving trailing slashes.

**Status:** ✅ Merged, all tests passing

**Impact:** Security improvement, prevents path traversal bypasses

---

### 2. Documentation Overhaul (This Session)

**Created:**
- `docs/30_LEVIATHAN_ROADMAP.md` - Strategic vision and roadmap
- `docs/31_DEPLOYMENT_STRATEGY.md` - EC2 + k3s deployment guide
- `docs/32_MULTI_TARGET_ARCHITECTURE.md` - Multi-target design
- `docs/33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md` - Operator experience
- `docs/34_LEVIATHAN_AS_SRE.md` - SRE vision
- `docs/35_HANDOVER_NEXT_PHASE.md` - This document

**Updated:**
- `docs/00_CANONICAL_OVERVIEW.md` - Links to new strategic docs

**Archived:**
- Obsolete docs moved to `docs/archive/`

**Impact:** Complete, accurate documentation reflecting current reality and future direction

---

## Locked-In Assumptions (DO NOT BREAK)

### 1. PR-Based Delivery (Non-Negotiable)

**Rule:** All changes MUST be delivered via GitHub pull requests.

**Rationale:**
- Human review is the final gate
- Integrates with existing workflows
- Provides audit trail
- Enables rollback

**DO NOT:**
- Implement direct commits to main
- Bypass PR creation
- Auto-merge without explicit configuration

---

### 2. Policy-Bounded Autonomy (Non-Negotiable)

**Rule:** Every target MUST have a policy defining allowed scopes and guardrails.

**Rationale:**
- Prevents runaway behavior
- Builds operator trust
- Enables safe autonomy

**DO NOT:**
- Allow tasks outside `allowed_paths`
- Bypass policy enforcement
- Weaken guardrails without approval

---

### 3. No Autonomous Planning (Non-Negotiable)

**Rule:** Leviathan MUST NOT invent, create, or prioritize tasks.

**Rationale:**
- Human operators define the backlog
- Leviathan executes predefined tasks only
- Clear separation of planning and execution

**DO NOT:**
- Implement task generation
- Modify task priorities autonomously
- Create tasks based on system state

---

### 4. Deterministic Operation (Non-Negotiable)

**Rule:** Same task + same repo state = same output.

**Rationale:**
- Reproducibility
- Debuggability
- Predictability

**DO NOT:**
- Introduce randomness in executors
- Use non-deterministic APIs
- Depend on external state

---

### 5. Invariant Enforcement (Non-Negotiable)

**Rule:** All invariants in `tools/invariants_check.py` MUST pass before merge.

**Rationale:**
- Prevents runtime errors
- Enforces consistency
- Catches misconfigurations early

**DO NOT:**
- Skip invariant checks
- Weaken invariant rules without justification
- Merge PRs with failing invariants

---

## Next Engineering Tasks (Priority Order)

### Task 1: Provision AWS EC2 Instance

**Goal:** Deploy Leviathan to AWS for first production deployment.

**Steps:**
1. Provision EC2 instance (t3.medium, Ubuntu 22.04)
2. Configure security groups (SSH, HTTPS, K8s API)
3. Attach Elastic IP (optional, for stable console access)
4. Configure IAM role for Secrets Manager access

**Acceptance Criteria:**
- EC2 instance running and accessible via SSH
- Security groups configured correctly
- IAM role attached

**Estimated Time:** 30 minutes

**Reference:** [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md)

---

### Task 2: Install k3s on EC2

**Goal:** Set up single-node Kubernetes cluster.

**Steps:**
1. SSH into EC2 instance
2. Run k3s installation script
3. Verify k3s is running
4. Copy kubeconfig for local access
5. Test kubectl connectivity

**Acceptance Criteria:**
- k3s running on EC2
- kubectl can connect from local machine
- Node shows as Ready

**Estimated Time:** 15 minutes

**Reference:** [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md)

---

### Task 3: Configure AWS Secrets Manager

**Goal:** Store GitHub token and control plane token securely.

**Steps:**
1. Create secret for GitHub token
2. Create secret for control plane token
3. Configure IAM permissions
4. Test secret retrieval from EC2

**Acceptance Criteria:**
- Secrets stored in AWS Secrets Manager
- EC2 instance can retrieve secrets
- Secrets not hardcoded anywhere

**Estimated Time:** 20 minutes

**Reference:** [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md)

---

### Task 4: Build and Push Docker Images

**Goal:** Make Leviathan images available for k3s deployment.

**Steps:**
1. Build worker image locally
2. Tag for registry (ECR or Docker Hub)
3. Push to registry
4. Verify image is accessible from EC2

**Acceptance Criteria:**
- Worker image built and pushed
- Image pullable from k3s cluster

**Estimated Time:** 15 minutes

**Reference:** [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md)

---

### Task 5: Deploy Leviathan to k3s

**Goal:** Deploy all Leviathan components to k3s cluster.

**Steps:**
1. Create `ops/k8s/overlays/aws-k3s/` overlay (if needed)
2. Update image references
3. Apply manifests via Kustomize
4. Verify all pods are running
5. Check logs for errors

**Acceptance Criteria:**
- Control plane pod running
- Scheduler CronJob created
- Spider Node pod running
- Console pod running
- All health checks passing

**Estimated Time:** 30 minutes

**Reference:** [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md)

---

### Task 6: Validate Console Access

**Goal:** Ensure console is accessible and functional.

**Steps:**
1. Port-forward console service (or configure Elastic IP + nginx)
2. Access console in browser
3. Verify dashboard loads
4. Verify event stream displays
5. Verify graph visualization works

**Acceptance Criteria:**
- Console accessible via browser
- Dashboard shows system status
- No errors in console logs

**Estimated Time:** 15 minutes

**Reference:** [33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md](33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md)

---

### Task 7: Prepare Cognito OIDC Path (Future)

**Goal:** Plan authentication for console and control plane.

**Steps:**
1. Research AWS Cognito OIDC integration
2. Design authentication flow
3. Document implementation plan
4. Create backlog tasks for implementation

**Acceptance Criteria:**
- Authentication design documented
- Implementation plan clear
- Backlog tasks created

**Estimated Time:** 2 hours

**Reference:** [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Phase 2

---

## Critical Files and Locations

### Code (DO NOT BREAK)

**Scheduler:**
- `leviathan/scheduler/dev_autonomy.py` - Main scheduler logic
- `ops/k8s/scheduler/dev-autonomy.yaml` - CronJob manifest

**Worker:**
- `leviathan/executor/backlog_propose_worker/__main__.py` - Worker entrypoint
- `leviathan/executor/backlog_propose.py` - PR creation logic
- `leviathan/executor/task_exec.py` - Task executors (docs, tests)

**Control Plane:**
- `leviathan/control_plane/api.py` - FastAPI service
- `leviathan/control_plane/scheduler.py` - Scheduler integration
- `leviathan/graph/store.py` - Event store (NDJSON)

**Spider Node:**
- `leviathan/spider/api.py` - Spider Node service
- `leviathan/spider/metrics.py` - Prometheus metrics

**Console:**
- `leviathan/operator_console/api.py` - Console backend
- `ops/k8s/console/deployment.yaml` - Console manifest

### Configuration (DO NOT BREAK)

**Autonomy Config:**
- `ops/autonomy/dev.yaml` - Guardrails, scope, limits

**Invariants:**
- `ops/invariants.yaml` - Machine-enforced invariants
- `tools/invariants_check.py` - Invariant checker

**Kubernetes:**
- `ops/k8s/base/` - Base manifests
- `ops/k8s/overlays/kind/` - kind overlay
- `ops/k8s/overlays/eks/` - EKS overlay

### Documentation (ALWAYS UPDATE)

**Canonical Docs:**
- `docs/00_CANONICAL_OVERVIEW.md` - System overview
- `docs/13_HANDOVER_START_HERE.md` - Session handover
- `docs/30_LEVIATHAN_ROADMAP.md` - Strategic roadmap
- `docs/31_DEPLOYMENT_STRATEGY.md` - Deployment guide
- `docs/32_MULTI_TARGET_ARCHITECTURE.md` - Multi-target design
- `docs/33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md` - Operator experience
- `docs/34_LEVIATHAN_AS_SRE.md` - SRE vision
- `docs/35_HANDOVER_NEXT_PHASE.md` - This document

**Archived Docs:**
- `docs/archive/pre_autonomy_docs/` - Historical, non-authoritative

---

## Common Pitfalls (AVOID THESE)

### 1. Referencing Archived Documentation

**DON'T:** Use information from `docs/archive/`  
**DO:** Use canonical docs in `docs/`

**Why:** Archived docs describe old system versions and may be incorrect.

---

### 2. Hardcoding Secrets

**DON'T:** Put tokens or passwords in code, manifests, or environment variables  
**DO:** Use Kubernetes Secrets or AWS Secrets Manager

**Why:** Security, auditability, rotation.

---

### 3. Violating Invariants

**DON'T:** Skip `tools/invariants_check.py` or weaken checks  
**DO:** Run invariants before every commit

**Why:** Prevents runtime errors and misconfigurations.

---

### 4. Bypassing Guardrails

**DON'T:** Remove or weaken `max_open_prs`, retry limits, circuit breakers  
**DO:** Respect guardrails, adjust configuration if needed

**Why:** Guardrails prevent runaway behavior and build trust.

---

### 5. Assuming Autonomous Planning

**DON'T:** Implement features that invent tasks  
**DO:** Execute tasks from backlog with `ready: true`

**Why:** Human operators define the backlog; Leviathan executes it.

---

### 6. Using Shell Scripts in K8s Jobs

**DON'T:** `command: ["bash", "-c", "python3 script.py"]`  
**DO:** `command: ["python3", "-m", "leviathan.module"]`

**Why:** Invariant enforcement, consistency, debuggability.

---

## Emergency Procedures

### Stop Autonomy Immediately

```bash
# Suspend scheduler (stops new jobs)
kubectl -n leviathan patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":true}}'

# Delete running workers (optional)
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

# Recent workers
kubectl -n leviathan get jobs -l app=leviathan-worker --sort-by=.metadata.creationTimestamp
```

---

## Quality Checklist (Before Any Merge)

- [ ] All unit tests pass (`pytest tests/unit -q`)
- [ ] All invariants pass (`python3 tools/invariants_check.py`)
- [ ] Documentation updated (if behavior changed)
- [ ] No secrets hardcoded
- [ ] No shell scripts in K8s Jobs
- [ ] Guardrails respected
- [ ] PR-based delivery maintained

---

## Success Metrics (Next Phase)

**Phase 1 Goals (Q1 2026):**
- ✅ Deploy to AWS EC2 + k3s
- ✅ Console accessible and functional
- ✅ Multi-target architecture operational (2+ targets)
- ✅ Spider Node integrated with control plane
- ✅ Real-time metrics and alerting

**Key Metrics:**
- Uptime: 95%+ (DEV environment)
- PRs Created: 50+ (cumulative)
- Targets Managed: 2+
- Operator Satisfaction: Positive feedback

---

## Resources

### Documentation
- [00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md) - Start here
- [13_HANDOVER_START_HERE.md](13_HANDOVER_START_HERE.md) - Session handover
- [30_LEVIATHAN_ROADMAP.md](30_LEVIATHAN_ROADMAP.md) - Strategic roadmap
- [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md) - Deployment guide

### Code
- Repository: https://github.com/iangreen74/leviathan
- CI: `.github/workflows/ci.yml`
- Tests: `tests/unit/`
- Invariants: `tools/invariants_check.py`

### Deployment
- Local: `./ops/k8s/kind-bootstrap.sh`
- kind: `kubectl apply -k ops/k8s/overlays/kind`
- EKS: `kubectl apply -k ops/k8s/overlays/eks`

---

## Final Notes

**Leviathan is operational and ready for the next phase.**

**Your job:**
1. Deploy to AWS EC2 + k3s
2. Validate console in production
3. Implement multi-target architecture
4. Integrate Spider Node with control plane

**Your constraints:**
- No autonomous planning
- No auto-merge (unless explicitly configured)
- No unbounded execution
- No invariant violations
- PR-based delivery always

**Your resources:**
- 478 passing tests
- 12 enforced invariants
- Canonical documentation
- Operational DEV environment

**Start with Task 1 (Provision EC2), follow the plan, ship incrementally.**

---

**Document Status:** Handover document for next engineering phase.
