# Leviathan v0.4.0 — Governed Autonomy & Observability

**Release Date:** 2026-01-28  
**Status:** ACTIVE (Internal Production Use)

---

## Certification Statement

**This release certifies Leviathan as an operational internal platform actively used to develop the Radix research product.**

Leviathan v0.4.0 represents the current production state of the system, not a prototype or demonstration. This release provides formal documentation and evidence for the governed autonomy capabilities that are already deployed and operational.

---

## What Leviathan Does

Leviathan is an autonomous software engineering system that executes pre-defined tasks from target repository backlogs under strict governance and observability.

### Core Capabilities

**Task Execution**
- Executes tasks from target repository backlogs marked with `ready: true`
- Creates pull requests for all changes (PR-based delivery)
- Operates continuously via Kubernetes CronJob scheduler
- Submits worker jobs for task execution

**Governance & Safety**
- Enforces strict invariants via CI (`tools/invariants_check.py`)
- Respects scope restrictions (configurable path prefixes)
- Enforces concurrency limits (max open PRs, max running attempts)
- Implements retry policies with circuit breaker
- Provides explicit autonomy enable/disable switch

**Observability**
- Spider Node: Standalone observability service with Prometheus metrics
- Event forwarding: Control plane forwards events to Spider (non-blocking, best-effort)
- Metrics exposure: Event counters by type, system health indicators
- Authenticated status API: `GET /v1/autonomy/status` with bearer token

**Operational Controls**
- Autonomy status query via authenticated API
- Deterministic disable via ConfigMap update (no restart required)
- Emergency stop via CronJob suspension
- Read-only configuration mounts
- Comprehensive operations runbook

**Auditability**
- Full event history persisted in control plane
- Deterministic operation with auditable state transitions
- Event-sourced graph projection
- Lifecycle tracking for all task attempts

---

## What Leviathan Explicitly Does NOT Do

These constraints are fundamental to Leviathan's design and are non-negotiable:

**No Autonomous Planning**
- Leviathan does NOT invent tasks
- Leviathan does NOT create backlog items
- Leviathan does NOT decide what work should be done
- All tasks must be explicitly defined in target backlogs with `ready: true`

**No Autonomous Merging**
- Leviathan does NOT auto-merge pull requests
- All PRs require human review and approval
- Merge decisions remain under human control

**No Unbounded Execution**
- Leviathan does NOT execute tasks without concurrency limits
- Leviathan does NOT retry indefinitely (max attempts enforced)
- Leviathan does NOT operate without circuit breakers

**No Scope Expansion**
- Leviathan does NOT modify files outside configured path prefixes
- Leviathan does NOT change its own scope without explicit configuration update
- Scope restrictions are enforced at runtime

**No Uncontrolled Autonomy**
- Leviathan does NOT operate when `autonomy_enabled: false`
- Leviathan does NOT bypass the kill switch
- Leviathan does NOT ignore emergency stop signals

---

## Safety & Governance Guarantees

### Invariant Enforcement

**CI-Level Validation**
- `tools/invariants_check.py` validates 15 invariant categories
- CI fails if any invariant is violated
- Prevents configuration drift and packaging errors
- Enforces canonical documentation structure

**Runtime Invariants**
- Scope restrictions enforced by worker
- Concurrency limits enforced by scheduler
- Retry policies enforced per task
- Circuit breaker stops scheduling after consecutive failures

### Autonomy Controls

**Kill Switch**
- ConfigMap-based: Update `autonomy_enabled: false` in `leviathan-autonomy-config`
- Deterministic: Scheduler reads config at start of each cycle
- No restart required: Takes effect on next scheduler tick (max 5 minutes)
- Verifiable: Status API reflects ConfigMap state immediately

**Emergency Stop**
- CronJob suspension: `kubectl patch cronjob leviathan-dev-scheduler -p '{"spec":{"suspend":true}}'`
- Immediate effect: No new scheduler pods created
- Optional job deletion: Remove running workers if needed
- Reversible: Unsuspend CronJob to resume

### Configuration Safety

**Read-Only Mounts**
- Autonomy ConfigMap mounted read-only in control plane
- Prevents accidental modification from within pods
- Configuration changes require explicit `kubectl` operations

**Best-Effort Observability**
- Event forwarding to Spider is non-blocking
- Spider failures do not impact control plane availability
- Metrics collection does not affect task execution
- Observability is additive, not critical path

### Operational Transparency

**Comprehensive Documentation**
- Operations runbook: Step-by-step procedures for all operations
- Integration evidence: Deterministic validation on kind cluster
- Troubleshooting guides: Common failure modes with fixes
- Expected outputs: All verification steps include expected results

---

## Operational Status

### Current Deployment

**Status:** ACTIVE (Internal Production Use)

**Primary Target:** Radix (research product development)

**Deployment Environment:**
- Platform: Kubernetes
- Scheduler: CronJob (every 5 minutes)
- Workers: On-demand Kubernetes Jobs
- Control Plane: Deployment (single replica)
- Spider Node: Deployment (single replica)

### Deployment Modes

**Local Development (Validated)**
- Platform: kind (Kubernetes in Docker)
- Evidence: `docs/23_INTEGRATION_EVIDENCE_KIND.md`
- Status: Fully validated with integration tests
- Use case: Development, testing, integration validation

**Cloud Production (EKS-Ready)**
- Platform: Amazon EKS
- Status: Parity planned (not yet deployed)
- Configuration: Equivalent to kind deployment
- Use case: Production workloads

### Evidence & Documentation

**Integration Evidence**
- [Integration Evidence Pack](docs/23_INTEGRATION_EVIDENCE_KIND.md)
  - Complete kind cluster deployment guide
  - 6 comprehensive verification procedures
  - Event forwarding proof
  - Autonomy kill switch demonstration
  - Emergency stop procedures

**Operations**
- [Operations Runbook](docs/21_OPERATIONS_AUTONOMY.md)
  - Query autonomy status
  - Disable/enable autonomy (deterministic)
  - Emergency stop procedures
  - Troubleshooting guide

**Architecture & Governance**
- [Invariants and Guardrails](docs/07_INVARIANTS_AND_GUARDRAILS.md)
  - Invariant philosophy
  - Enforcement mechanisms
  - Safety guarantees
- [Canonical Overview](docs/00_CANONICAL_OVERVIEW.md)
  - System architecture
  - Core principles
  - Documentation index

**Observability**
- [Spider Node](docs/20_SPIDER_NODE.md)
  - Architecture and design
  - Metrics specification
  - Integration with control plane

---

## Technical Specifications

### Components

**Control Plane**
- Technology: FastAPI (Python 3.10)
- Deployment: Kubernetes Deployment
- Port: 8000
- Authentication: Bearer token (required for all endpoints)
- Backend: NDJSON (file-based event store)
- Key endpoints:
  - `POST /v1/events/ingest` - Event ingestion
  - `GET /v1/autonomy/status` - Autonomy status query
  - `GET /health` - Health check

**Scheduler**
- Technology: Python 3.10
- Deployment: Kubernetes CronJob
- Schedule: Every 5 minutes (`*/5 * * * *`)
- Configuration: ConfigMap (`leviathan-autonomy-config`)
- Behavior: Reads config at cycle start, respects `autonomy_enabled` flag

**Worker**
- Technology: Python 3.10
- Deployment: Kubernetes Job (on-demand)
- Lifecycle: One job per task attempt
- Capabilities: Git operations, PR creation, event posting
- Timeout: Configurable (default 15 minutes)

**Spider Node**
- Technology: FastAPI (Python 3.10)
- Deployment: Kubernetes Deployment
- Port: 8001
- Metrics: Prometheus-compatible
- Key endpoints:
  - `GET /health` - Health check
  - `GET /metrics` - Prometheus metrics

### Configuration

**Autonomy Configuration** (`ops/autonomy/dev.yaml`)
- `autonomy_enabled`: Master switch (true/false)
- `target_id`: Target repository identifier
- `allowed_path_prefixes`: Scope restrictions
- `max_open_prs`: Concurrency limit
- `max_attempts_per_task`: Retry limit
- `circuit_breaker_failures`: Consecutive failure threshold

**Secrets** (Kubernetes Secret: `leviathan-secrets`)
- `LEVIATHAN_CONTROL_PLANE_TOKEN`: API authentication
- `GITHUB_TOKEN`: Repository access for workers

### Test Coverage

**Unit Tests:** 397 passing
- Control plane API tests
- Scheduler logic tests
- Worker execution tests
- Spider Node tests
- Event forwarding tests
- Autonomy control tests
- Invariants validation tests

**Invariant Checks:** 15 categories
- Control plane manifests
- Worker job templates
- CI workflows
- Requirements consistency
- Namespace consistency
- Topology artifacts
- API endpoints
- Failover documentation
- K8s packaging
- Autonomy configuration
- Scheduler manifest
- Spider manifests
- Documentation structure
- Control plane autonomy mount

---

## Versioning Statement

**This is a certification tag, not a feature freeze.**

Leviathan v0.4.0 certifies the current operational state of the system. Development continues on the `main` branch without interruption.

### Version Semantics

- **v0.4.0** reflects the current feature set and operational maturity
- This tag provides a stable reference point for auditing and certification
- Future releases will extend capabilities without weakening safety guarantees
- Breaking changes will be clearly documented and versioned accordingly

### Development Continuity

- Active development continues on `main` branch
- Internal use for Radix development is unaffected by this release
- New features will be merged to `main` as they are completed
- Future releases will follow semantic versioning

### Compatibility Commitment

Future versions will maintain:
- Invariant enforcement mechanisms
- Autonomy control interfaces
- Safety guarantees and guardrails
- Operational procedures
- Event schema compatibility (with versioning)

---

## Release Artifacts

### Git Tag
- Tag: `v0.4.0-autonomy`
- Type: Annotated
- Branch: `main`
- Commit: Latest on main at release time

### Documentation
- All documentation in `docs/` directory
- Integration evidence pack
- Operations runbook
- Architecture documentation
- API reference

### Container Images
- `leviathan-control-plane:local`
- `leviathan-worker:local`
- Spider Node uses worker image

### Kubernetes Manifests
- `ops/k8s/control-plane.yaml`
- `ops/k8s/scheduler/dev-autonomy.yaml`
- `ops/k8s/spider/deployment.yaml`
- `ops/k8s/spider/service.yaml`

---

## Acknowledgments

This release represents the culmination of rigorous engineering focused on safety, governance, and operational transparency. Leviathan is actively used as the internal development platform for Radix, demonstrating its reliability and production readiness.

---

## Contact & Support

For questions about this release or Leviathan's operational status, refer to:
- Documentation: `docs/00_CANONICAL_OVERVIEW.md`
- Operations: `docs/21_OPERATIONS_AUTONOMY.md`
- Integration: `docs/23_INTEGRATION_EVIDENCE_KIND.md`
