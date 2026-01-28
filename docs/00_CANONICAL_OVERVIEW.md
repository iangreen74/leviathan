# Leviathan: Canonical Documentation

**Last Updated:** 2026-01-28  
**Status:** Canonical (Authoritative)

---

## What is Leviathan?

Leviathan is an **autonomous software engineering system** that executes tasks from target repository backlogs and creates pull requests automatically.

**Current State:**
- ✅ PR Proof v1 (local execution)
- ✅ PR Proof v1 on Kubernetes (kind)
- ✅ Autonomy v1 (DEV-only, closed-loop operation)
- ✅ Deterministic, invariant-enforced operation
- ✅ Continuous autonomous PR creation under strict guardrails

---

## Core Principles

### 1. No Autonomous Planning
Leviathan does NOT invent tasks. It only executes tasks already present in target backlogs with `ready: true`.

### 2. PR-Based Delivery
All changes are delivered via GitHub pull requests. No direct commits to main. No auto-merge (unless explicitly enabled per target).

### 3. Deterministic Operation
Every action produces deterministic, auditable events. Full event history is persisted in the control plane.

### 4. Invariant Enforcement
Runtime packaging invariants are enforced at commit time via `tools/invariants_check.py`. CI fails if invariants are violated.

### 5. Strict Guardrails (DEV)
- Scope restrictions: Only `.leviathan/**` and `docs/**` paths
- Concurrency limits: Max 1 open PR at a time
- Retry policy: Max 2 attempts per task
- Circuit breaker: Stops after consecutive failures

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                    │
│                                                          │
│  ┌────────────────┐         ┌──────────────────┐       │
│  │   CronJob      │         │  Control Plane   │       │
│  │   (Scheduler)  │────────▶│  (Deployment)    │       │
│  │   Every 5min   │  events │  Port 8000       │       │
│  └────────┬───────┘         └──────────────────┘       │
│           │                                              │
│           │ creates                                      │
│           ▼                                              │
│  ┌────────────────┐                                     │
│  │   Worker Job   │                                     │
│  │   (Pod)        │─────────────────────────┐          │
│  └────────────────┘                         │          │
│                                              │          │
└──────────────────────────────────────────────┼──────────┘
                                               │
                                               ▼
                                    ┌──────────────────┐
                                    │  GitHub API      │
                                    │  - Clone repo    │
                                    │  - Create PR     │
                                    └──────────────────┘
```

### Components

1. **Scheduler** (`leviathan.scheduler.dev_autonomy`)
   - Runs as Kubernetes CronJob (every 5 minutes)
   - Selects next executable task from target backlog
   - Enforces guardrails (scope, concurrency, retry limits)
   - Submits worker jobs to Kubernetes

2. **Worker** (`leviathan.executor.backlog_propose_worker`)
   - Runs as Kubernetes Job (one per task attempt)
   - Clones target repo, modifies backlog, creates PR
   - Posts lifecycle events to control plane
   - Exits after PR creation

3. **Control Plane** (`leviathan.control_plane`)
   - FastAPI service (Deployment)
   - Ingests events from workers
   - Persists event history (NDJSON backend)
   - Provides query API for graph state

---

## Documentation Index

### Getting Started
- [01_QUICKSTART.md](01_QUICKSTART.md) - Run Autonomy v1 on kind in 5 minutes
- [02_LOCAL_DEVELOPMENT.md](02_LOCAL_DEVELOPMENT.md) - Local development setup

### Architecture
- [10_ARCHITECTURE.md](10_ARCHITECTURE.md) - System architecture and design
- [11_EVENT_MODEL.md](11_EVENT_MODEL.md) - Event schema and lifecycle
- [12_BACKLOG_FORMAT.md](12_BACKLOG_FORMAT.md) - Target backlog specification

### Operations
- [20_KUBERNETES_DEPLOYMENT.md](20_KUBERNETES_DEPLOYMENT.md) - K8s deployment guide
- [21_AUTONOMY_OPERATIONS.md](21_AUTONOMY_OPERATIONS.md) - Running Autonomy v1
- [22_MONITORING.md](22_MONITORING.md) - Observability and debugging

### Development
- [30_CONTRIBUTING.md](30_CONTRIBUTING.md) - Development workflow
- [31_TESTING.md](31_TESTING.md) - Testing strategy
- [32_INVARIANTS.md](32_INVARIANTS.md) - Invariant checks

### Reference
- [40_API_REFERENCE.md](40_API_REFERENCE.md) - Control plane API
- [41_CONFIGURATION.md](41_CONFIGURATION.md) - Configuration reference
- [42_TROUBLESHOOTING.md](42_TROUBLESHOOTING.md) - Common issues

---

## Quick Commands

### Run Autonomy v1 on kind

```bash
# Bootstrap (one-time)
./ops/k8s/kind-bootstrap.sh

# Deploy
kubectl apply -f ops/k8s/control-plane.yaml
kubectl apply -f ops/k8s/scheduler/dev-autonomy.yaml

# Observe
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=100
kubectl -n leviathan logs -l app=leviathan-worker --tail=100
```

### Run Tests

```bash
# Unit tests
python3 -m pytest tests/unit -q

# Invariants
python3 tools/invariants_check.py
```

### Local PR Proof

```bash
# Set environment variables
export GITHUB_TOKEN=<your-token>
export TARGET_REPO_URL=https://github.com/iangreen74/radix.git

# Run PR proof
python3 -m leviathan.executor.pr_proof_v1
```

---

## Safety Guarantees

### Scope Isolation
Tasks modifying files outside `.leviathan/**` or `docs/**` are automatically skipped in DEV mode.

### Concurrency Control
Only 1 open PR at a time prevents overwhelming reviewers.

### Retry Limits
Max 2 attempts per task prevents infinite retry loops.

### Circuit Breaker
After 2 consecutive failures, scheduler stops to prevent cascading failures.

### No Auto-Merge
All changes delivered via PR. Human review required before merge (unless explicitly enabled).

### Deterministic Evidence
Full event history persisted:
- `attempt.created`
- `attempt.started`
- `pr.created`
- `attempt.succeeded` / `attempt.failed`

---

## Repository Structure

```
leviathan/
├── docs/                           # Canonical documentation (THIS)
│   ├── 00_CANONICAL_OVERVIEW.md    # You are here
│   ├── 01_QUICKSTART.md
│   ├── 10_ARCHITECTURE.md
│   └── archive/                    # Historical docs (non-canonical)
├── leviathan/                      # Python package
│   ├── control_plane/              # Control plane API
│   ├── executor/                   # Worker execution modules
│   │   ├── backlog_propose.py      # PR creation logic
│   │   ├── backlog_propose_worker/ # K8s worker entrypoint
│   │   └── pr_proof_v1/            # PR proof module
│   ├── scheduler/                  # Scheduler modules
│   │   └── dev_autonomy.py         # DEV autonomy scheduler
│   ├── graph/                      # Event graph and store
│   └── bootstrap/                  # Target indexing
├── ops/                            # Operations and deployment
│   ├── autonomy/                   # Autonomy configurations
│   │   └── dev.yaml                # DEV autonomy config
│   ├── k8s/                        # Kubernetes manifests
│   │   ├── control-plane.yaml      # Control plane deployment
│   │   ├── scheduler/              # Scheduler manifests
│   │   └── jobs/                   # Job templates
│   └── docker/                     # Dockerfiles
├── tests/                          # Test suite
│   └── unit/                       # Unit tests (369 tests)
├── tools/                          # Development tools
│   └── invariants_check.py         # Invariant enforcement
└── requirements.txt                # Python dependencies
```

---

## Next Steps

1. **New to Leviathan?** Start with [01_QUICKSTART.md](01_QUICKSTART.md)
2. **Want to understand the system?** Read [10_ARCHITECTURE.md](10_ARCHITECTURE.md)
3. **Ready to deploy?** Follow [20_KUBERNETES_DEPLOYMENT.md](20_KUBERNETES_DEPLOYMENT.md)
4. **Contributing?** See [30_CONTRIBUTING.md](30_CONTRIBUTING.md)

---

## Archive Notice

All documentation prior to 2026-01-28 has been archived to `docs/archive/pre_autonomy_docs/`.

These files are preserved for historical context but do NOT describe the current system.

**If you are starting a new conversation or task, begin here.**

---

## Support

- **Issues:** https://github.com/iangreen74/leviathan/issues
- **Discussions:** https://github.com/iangreen74/leviathan/discussions
- **CI Status:** See `.github/workflows/ci.yml`
