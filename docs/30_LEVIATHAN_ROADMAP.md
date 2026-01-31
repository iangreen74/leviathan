# Leviathan Roadmap

**Last Updated:** 2026-01-31  
**Status:** Canonical (Strategic)

---

## Mission

**Leviathan is an autonomous platform engineering system that executes software engineering tasks under strict policy-based guardrails, delivering changes via pull requests for human review.**

Leviathan automates repetitive, well-defined engineering work (documentation, tests, dependency updates, infrastructure maintenance) while maintaining human oversight through PR-based delivery and policy enforcement.

---

## Philosophy

### What Leviathan IS

1. **Task Executor, Not Planner**
   - Executes tasks from target repository backlogs with `ready: true`
   - Does NOT invent, create, or prioritize tasks
   - Human operators define the backlog; Leviathan executes it

2. **PR-Based Delivery System**
   - All changes delivered via GitHub pull requests
   - No direct commits to main branches
   - No auto-merge (unless explicitly enabled per target with approval)
   - Human review is the final gate

3. **Policy-Bounded Autonomy**
   - Every target has a policy defining allowed scopes, concurrency limits, retry behavior
   - Guardrails enforced at runtime: scope restrictions, max open PRs, circuit breakers
   - Violations halt execution immediately

4. **Deterministic and Auditable**
   - Full event history persisted in control plane
   - Every action produces structured events (attempt.created, pr.created, etc.)
   - Reproducible: same task + same repo state = same output

5. **Multi-Target Platform**
   - Manages multiple target repositories simultaneously
   - Per-target policies and backlogs
   - Scheduler selects tasks across targets based on priority and readiness

### What Leviathan IS NOT

1. **NOT an AI Agent with Unbounded Autonomy**
   - No autonomous planning or goal-setting
   - No self-directed product decisions
   - No scope expansion beyond configured policies

2. **NOT a Replacement for Engineers**
   - Automates repetitive tasks, not creative work
   - Requires human-defined backlogs and acceptance criteria
   - Human review required for all changes

3. **NOT a CI/CD System**
   - Does not build, test, or deploy code
   - Creates PRs; CI/CD runs on those PRs
   - Complements existing CI/CD, does not replace it

---

## Current Capabilities (Autonomy v1)

### Implemented ✅

1. **Core Execution Loop**
   - Scheduler (CronJob) runs every 5 minutes
   - Selects next ready task from target backlog
   - Submits Kubernetes Job for worker execution
   - Worker clones repo, executes task, creates PR, posts events

2. **Task Executors**
   - **Docs Executor:** Generates markdown documentation from task specs
   - **Tests Executor:** Generates pytest test stubs from acceptance criteria
   - Deterministic output based on task specification

3. **Backlog Writeback**
   - Worker updates `.leviathan/backlog.yaml` in same PR
   - Marks task as `status: completed`, `ready: false`
   - Records attempt metadata (attempt_id, branch_name, completed_at)
   - Prevents infinite re-execution

4. **Control Plane**
   - FastAPI service ingesting events from workers
   - NDJSON event store (file-based, durable)
   - Query API for graph state and event history
   - Autonomy status endpoint (`/v1/autonomy/status`)

5. **Spider Node v1 (Observability)**
   - Standalone FastAPI service
   - Health check endpoint (`/health`)
   - Prometheus metrics endpoint (`/metrics`)
   - No control plane integration yet (static metrics)

6. **Guardrails (DEV Environment)**
   - Scope restrictions: Only `.leviathan/**`, `docs/**`, `tests/**` paths
   - Max 1 open PR at a time
   - Max 2 attempts per task
   - Circuit breaker: stops after 2 consecutive failures
   - 15-minute timeout per attempt

7. **Operator Console**
   - Web UI for viewing graph state
   - Event stream visualization
   - Target and task status display
   - Deployed as Kubernetes service

8. **Invariant Enforcement**
   - 12 invariant checks in CI (`tools/invariants_check.py`)
   - Namespace consistency, image pull policies, module execution patterns
   - CI fails if invariants violated

9. **Deployment**
   - Kustomize-based deployment (base + overlays)
   - Local development: kind cluster
   - Production: AWS EKS
   - All components containerized

### Current Limitations ⚠️

1. **Single Target Only**
   - Hardcoded to `iangreen74/radix` in DEV
   - Multi-target architecture exists but not fully operational

2. **Limited Executors**
   - Only docs and tests scopes implemented
   - No core code, CI, or infrastructure executors

3. **No Auto-Merge**
   - All PRs require manual review and merge
   - No per-target auto-merge configuration

4. **Static Observability**
   - Spider Node metrics are static (no control plane integration)
   - No alerting or anomaly detection

5. **File-Based Event Store**
   - NDJSON files, not scalable for high-volume production
   - No PostgreSQL backend yet

6. **No Authentication**
   - Control plane and console have no auth
   - Suitable for internal networks only

---

## Roadmap

### Phase 1: Foundation Hardening (Current → Q1 2026)

**Goal:** Make Autonomy v1 production-ready for internal use.

**Deliverables:**

1. **Multi-Target Architecture (Operational)**
   - Remove hardcoded target references
   - Implement target discovery from graph
   - Per-target policy enforcement
   - Scheduler selects tasks across multiple targets

2. **Observability Integration**
   - Connect Spider Node to control plane event stream
   - Real-time metrics updates (attempts, PRs, failures)
   - Alerting on circuit breaker trips and consecutive failures

3. **Operator Experience**
   - Console shows per-target status (idle, active, blocked)
   - Task queue visibility
   - Manual task triggering (admin only)
   - Autonomy ON/OFF toggle per target

4. **Deployment Automation**
   - EC2 + k3s deployment runbook (preferred first AWS deployment)
   - Terraform/CloudFormation for infrastructure
   - Secrets management via AWS Secrets Manager
   - Upgrade and rollback procedures

5. **Documentation Overhaul**
   - Strategic roadmap (this document)
   - Deployment strategy guide
   - Multi-target architecture guide
   - Observability and operator experience guide
   - Leviathan-as-SRE vision document

**Success Criteria:**
- Leviathan manages 2+ target repos simultaneously
- Operators can monitor and control autonomy per target
- Deployed to AWS EC2 + k3s with production-grade observability
- All documentation reflects current reality

---

### Phase 2: Platform Productization (Q2 2026)

**Goal:** Transform Leviathan from internal tool to multi-tenant platform.

**Deliverables:**

1. **Authentication and Authorization**
   - AWS Cognito OIDC integration
   - Role-based access control (RBAC)
   - Per-target permissions (view, trigger, admin)
   - API key management for programmatic access

2. **Target Onboarding**
   - Self-service target registration via console
   - Backlog template generation
   - Policy wizard (scope, concurrency, retry limits)
   - GitHub App installation flow

3. **PostgreSQL Event Store**
   - Migrate from NDJSON to PostgreSQL
   - Indexed queries for fast graph traversal
   - Event retention policies
   - Backup and restore procedures

4. **Additional Executors**
   - **CI Executor:** Update GitHub Actions workflows
   - **Dependency Executor:** Update requirements.txt, package.json
   - **Infrastructure Executor:** Terraform/CloudFormation updates
   - Pluggable executor framework

5. **Auto-Merge (Per-Target)**
   - Configurable auto-merge policy per target
   - Requires passing CI checks
   - Configurable approval requirements
   - Audit trail for auto-merged PRs

6. **Advanced Scheduling**
   - Priority-based task selection
   - Dependency resolution (blocked tasks)
   - Time-based scheduling (cron-like)
   - Fairness across targets

**Success Criteria:**
- 5+ teams using Leviathan for their repos
- Self-service onboarding without manual intervention
- Auto-merge enabled for low-risk targets
- PostgreSQL handling 10k+ events/day

---

### Phase 3: Product Launch (Q3-Q4 2026)

**Goal:** Launch Leviathan as a SaaS product for external customers.

**Deliverables:**

1. **SaaS Infrastructure**
   - Multi-tenant isolation (namespace per customer)
   - Usage metering and billing integration
   - Rate limiting and quotas
   - Customer-specific secrets and credentials

2. **Leviathan-as-SRE**
   - Self-healing: Leviathan monitors and remediates its own issues
   - Customer workload SRE: Leviathan monitors customer apps and creates remediation PRs
   - Runbook automation: Execute runbooks as backlog tasks
   - Incident response: Automated triage and PR creation

3. **Advanced Observability**
   - Real-time dashboards (Grafana)
   - Anomaly detection (ML-based)
   - Cost attribution per target
   - Performance profiling

4. **Marketplace and Integrations**
   - Pre-built executor library (docs, tests, CI, deps)
   - Third-party executor plugins
   - Slack/Discord notifications
   - Jira/Linear integration for backlog sync

5. **Enterprise Features**
   - SSO (SAML, Okta, Azure AD)
   - Audit logs and compliance reporting
   - Custom SLAs and support tiers
   - Private deployment options (VPC, on-prem)

**Success Criteria:**
- 50+ paying customers
- 99.9% uptime SLA
- Leviathan self-heals without human intervention
- Revenue-positive with clear unit economics

---

## Non-Goals

### What We Will NOT Build

1. **Autonomous Planning or Goal-Setting**
   - Leviathan will never invent tasks or set its own goals
   - Human-defined backlogs are the contract

2. **Code Generation from Natural Language**
   - No "build me a feature" prompts
   - Tasks must have clear acceptance criteria and allowed paths

3. **Direct Commits or Auto-Deploy**
   - All changes via PRs (non-negotiable)
   - No direct pushes to main branches
   - No automatic deployment to production

4. **Unbounded Scope**
   - Policies define allowed paths and scopes
   - Violations halt execution immediately
   - No "escape hatches" for policy bypass

5. **Replacement for Human Engineers**
   - Leviathan automates repetitive tasks, not creative work
   - Human review and approval remain critical

---

## Strategic Bets

### 1. PR-Based Delivery is the Right Model

**Why:** Pull requests are the universal interface for code review. By delivering all changes via PRs, Leviathan integrates seamlessly with existing workflows and maintains human oversight.

**Risk:** PR overhead may slow down high-volume targets.

**Mitigation:** Auto-merge for low-risk targets, batching for bulk updates.

---

### 2. Policy-Bounded Autonomy Scales

**Why:** Strict policies prevent runaway behavior and build trust. Operators can confidently enable autonomy knowing guardrails are enforced.

**Risk:** Overly restrictive policies may limit usefulness.

**Mitigation:** Policy templates, gradual relaxation based on trust, per-target customization.

---

### 3. Multi-Target is the Product Unlock

**Why:** Managing a single repo is a tool; managing many repos is a platform. Multi-target architecture enables SaaS business model.

**Risk:** Complexity in scheduling, fairness, and resource allocation.

**Mitigation:** Start with simple round-robin, iterate based on customer feedback.

---

### 4. Leviathan-as-SRE is the Long-Term Vision

**Why:** Self-healing systems are the future of operations. Leviathan monitoring and remediating its own issues (and customer workloads) is a compelling value proposition.

**Risk:** Requires deep integration with monitoring and incident management tools.

**Mitigation:** Start with self-SRE (dogfooding), expand to customer workloads incrementally.

---

## Success Metrics

### Phase 1 (Foundation Hardening)
- **Targets Managed:** 2+
- **Uptime:** 95%+ (DEV environment)
- **PRs Created:** 50+ (cumulative)
- **Operator Satisfaction:** Positive feedback from internal users

### Phase 2 (Platform Productization)
- **Targets Managed:** 10+
- **Teams Onboarded:** 5+
- **Uptime:** 99%+ (production environment)
- **PRs Created:** 500+ (cumulative)
- **Auto-Merge Adoption:** 30%+ of targets

### Phase 3 (Product Launch)
- **Paying Customers:** 50+
- **Uptime:** 99.9%+ (SLA)
- **PRs Created:** 10k+/month
- **Revenue:** $100k+ MRR
- **Self-Healing Events:** 100+ (Leviathan fixes itself)

---

## Dependencies and Risks

### Critical Dependencies

1. **GitHub API Stability**
   - Leviathan depends on GitHub for repo access and PR creation
   - Mitigation: Rate limiting, retry logic, fallback to manual mode

2. **Kubernetes Availability**
   - Scheduler and workers run on Kubernetes
   - Mitigation: Multi-AZ deployment, pod disruption budgets

3. **AWS Infrastructure**
   - Production deployment on AWS (EC2, EKS, Secrets Manager)
   - Mitigation: Terraform for reproducible infrastructure, disaster recovery plan

### Key Risks

1. **Runaway Behavior**
   - Risk: Bug causes infinite PR creation or scope violations
   - Mitigation: Circuit breakers, max open PRs, scope enforcement, emergency stop

2. **Security Breach**
   - Risk: Compromised credentials allow unauthorized repo access
   - Mitigation: Secrets rotation, least-privilege IAM, audit logs

3. **Customer Trust**
   - Risk: Customers hesitant to grant repo access to autonomous system
   - Mitigation: Transparent policies, audit trails, gradual rollout, PR-based delivery

4. **Scalability Bottlenecks**
   - Risk: NDJSON event store or single-replica control plane can't handle load
   - Mitigation: PostgreSQL migration, horizontal scaling, caching

---

## Next Steps (Immediate)

1. **Complete Documentation Overhaul** ✅ (this document)
2. **Deploy to AWS EC2 + k3s** (next engineering task)
3. **Validate Console in Production**
4. **Integrate Spider Node with Control Plane**
5. **Implement Multi-Target Scheduler**

---

## References

- [00_CANONICAL_OVERVIEW.md](00_CANONICAL_OVERVIEW.md) - System overview
- [31_DEPLOYMENT_STRATEGY.md](31_DEPLOYMENT_STRATEGY.md) - Deployment guide
- [32_MULTI_TARGET_ARCHITECTURE.md](32_MULTI_TARGET_ARCHITECTURE.md) - Multi-target design
- [33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md](33_OBSERVABILITY_AND_OPERATOR_EXPERIENCE.md) - Observability
- [34_LEVIATHAN_AS_SRE.md](34_LEVIATHAN_AS_SRE.md) - SRE vision

---

**Document Status:** Living document, updated as roadmap evolves.
