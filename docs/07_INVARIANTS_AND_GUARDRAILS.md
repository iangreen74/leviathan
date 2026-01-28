# Invariants and Guardrails

**Last Updated:** 2026-01-28  
**Status:** Canonical

---

## Why Invariants Exist

Invariants are **first-class system memory**. They exist to prevent forgetting, ensure determinism, and enforce safety.

**The Problem:**
- Systems evolve through many commits and conversations
- Context is lost between sessions
- Assumptions drift
- Runtime surprises emerge in production

**The Solution:**
- Codify critical constraints as invariants
- Enforce them at commit time (CI)
- Make violations fail fast, not at runtime

**Philosophy:**
> "If it's not enforced by code, it will eventually be violated."

Invariants are Leviathan's **anti-forgetting mechanism**. They encode decisions that must never be reversed silently.

---

## The Invariants System

### Machine-Enforced Truth

**File:** `ops/invariants.yaml`

This YAML file defines all invariants that must hold for the system to operate correctly. It is the **single source of truth** for constraints.

**Enforcement:** `tools/invariants_check.py`

This Python script reads `ops/invariants.yaml` and validates that the repository state matches all declared invariants. It runs in CI and fails the build if any invariant is violated.

**Integration:**
- CI workflow (`.github/workflows/ci.yml`) runs `python3 tools/invariants_check.py`
- Developers run it locally before committing
- No PR can merge if invariants fail

---

## Classes of Invariants

### 1. Naming Invariants

**Purpose:** Ensure consistent naming across Kubernetes resources.

**Examples:**
- All K8s resources must use namespace `leviathan` (not `default`)
- Secrets must follow naming convention: `leviathan-*`
- Image tags must be explicit (`:local` for dev, `:v1.2.3` for prod)

**Why This Matters:**
- Prevents accidental deployment to wrong namespace
- Avoids secret name collisions
- Makes image provenance traceable

**Real Failure Prevented:**
```
# Before invariant:
metadata:
  namespace: default  # ❌ Wrong namespace

# After invariant enforcement:
metadata:
  namespace: leviathan  # ✅ Correct namespace
```

**Enforcement:** `tools/invariants_check.py::check_namespace_consistency()`

---

### 2. Packaging Invariants

**Purpose:** Ensure Kubernetes jobs execute code via Python modules, not shell scripts.

**Examples:**
- K8s Job containers must use `command: ["python3", "-m", "module.name"]`
- No inline shell scripts in Job manifests
- No `bash -c` or `sh -c` commands

**Why This Matters:**
- Module execution is deterministic and testable
- Shell scripts are opaque to static analysis
- Errors in modules produce stack traces
- Unit tests can validate module behavior

**Real Failure Prevented:**
```yaml
# Before invariant:
command: ["bash", "-c", "cd /app && python3 script.py"]  # ❌ Shell script

# After invariant enforcement:
command: ["python3", "-m", "leviathan.executor.worker"]  # ✅ Module execution
```

**Enforcement:** `tools/invariants_check.py::check_k8s_worker_job()`

---

### 3. Runtime Invariants (Guardrails)

**Purpose:** Prevent runaway execution and resource exhaustion.

**Examples:**
- `max_open_prs: 1` - Only 1 open PR at a time
- `max_attempts_per_task: 2` - Retry limit per task
- `circuit_breaker_failures: 2` - Stop after consecutive failures
- `attempt_timeout_seconds: 900` - 15-minute timeout per attempt

**Why This Matters:**
- Prevents overwhelming reviewers with PRs
- Prevents infinite retry loops
- Stops cascading failures early
- Limits resource consumption

**Real Failure Prevented:**
```
# Without guardrails:
- Task fails → retry
- Task fails → retry
- Task fails → retry
- ... (infinite loop, exhausts resources)

# With guardrails:
- Task fails → retry (attempt 1)
- Task fails → retry (attempt 2)
- Task fails → mark blocked, stop (max_attempts_per_task: 2)
```

**Enforcement:** `leviathan.scheduler.dev_autonomy::DevAutonomyScheduler`

---

### 4. Autonomy Invariants

**Purpose:** Ensure autonomous operation stays within safe boundaries.

**Examples:**
- Tasks must have `ready: true` to be executable
- Tasks must have `allowed_paths` within scope prefixes
- Scope prefixes in DEV: `[.leviathan/, docs/]`
- No autonomous planning (no task invention)

**Why This Matters:**
- Prevents Leviathan from inventing tasks
- Limits blast radius of changes
- Ensures human approval before execution
- Makes autonomy predictable and auditable

**Real Failure Prevented:**
```yaml
# Task outside allowed scope:
tasks:
  - id: task-1
    ready: true
    allowed_paths:
      - src/main.py  # ❌ Outside .leviathan/ and docs/

# Scheduler behavior:
# → Task skipped with log: "scope outside allowed prefixes"
# → No PR created
# → No code changes
```

**Enforcement:** `leviathan.scheduler.dev_autonomy::DevAutonomyScheduler._is_scope_allowed()`

---

### 5. Image Pull Policy Invariants

**Purpose:** Ensure local images are used correctly in kind clusters.

**Examples:**
- Images with `:local` tag must have `imagePullPolicy: IfNotPresent`
- Production images must have explicit version tags (no `:latest`)

**Why This Matters:**
- `IfNotPresent` prevents pulling from remote registry (faster, deterministic)
- Explicit tags prevent accidental version drift
- Local images are guaranteed to be the ones loaded into kind

**Real Failure Prevented:**
```yaml
# Before invariant:
image: leviathan-worker:local
imagePullPolicy: Always  # ❌ Tries to pull from remote (fails)

# After invariant enforcement:
image: leviathan-worker:local
imagePullPolicy: IfNotPresent  # ✅ Uses local image
```

**Enforcement:** `tools/invariants_check.py::check_k8s_packaging()`

---

## Why Kubernetes Makes Invariants Non-Optional

**Kubernetes amplifies the cost of mistakes:**

1. **Namespace mistakes** → Resources in wrong namespace, invisible to operators
2. **Image tag mistakes** → Wrong version deployed, hard to debug
3. **Secret name mistakes** → Pods fail to start, cryptic errors
4. **Resource limit mistakes** → OOM kills, cascading failures

**In local development:**
- Mistakes are annoying but recoverable
- You can `rm -rf` and start over
- Feedback is immediate

**In Kubernetes:**
- Mistakes are expensive and persistent
- Resources may linger (Jobs, Pods, Secrets)
- Debugging requires kubectl, logs, events
- Rollback is manual and error-prone

**Invariants prevent these mistakes at commit time, not runtime.**

---

## Concrete Examples from Recent Work

### Example 1: PR Proof v1 Namespace Fix

**Problem:**
```yaml
# ops/k8s/jobs/pr-proof-v1.yaml
metadata:
  namespace: default  # ❌ Wrong namespace
```

**Symptom:**
- Job created in `default` namespace
- Not visible with `kubectl -n leviathan get jobs`
- Secrets not accessible (wrong namespace)

**Fix:**
```yaml
metadata:
  namespace: leviathan  # ✅ Correct namespace
```

**Invariant Added:**
```python
# tools/invariants_check.py
def check_k8s_packaging(self):
    namespace = job.get('metadata', {}).get('namespace')
    if namespace != 'leviathan':
        self.fail(f"Job must use namespace: leviathan")
```

**Result:** CI now fails if any Job uses wrong namespace.

---

### Example 2: Git Clone Authentication

**Problem:**
```python
# leviathan/executor/backlog_propose.py
clone_url = f"https://{token}@github.com/..."  # ❌ Wrong format
```

**Symptom:**
- Git clone fails with exit code 128
- Error: "Authentication failed"

**Fix:**
```python
clone_url = f"https://x-access-token:{token}@github.com/..."  # ✅ Correct format
```

**Invariant Added:**
```python
# tests/unit/test_backlog_propose.py
def test_build_authenticated_url_https(self):
    url = proposer._build_authenticated_url(...)
    assert url == 'https://x-access-token:test-token@github.com/...'
```

**Result:** Unit tests now validate URL format.

---

### Example 3: Image Pull Policy

**Problem:**
```yaml
# ops/k8s/jobs/pr-proof-v1.yaml
image: leviathan-worker:local
imagePullPolicy: Always  # ❌ Tries to pull from remote
```

**Symptom:**
- Pod stuck in `ImagePullBackOff`
- Error: "Failed to pull image"

**Fix:**
```yaml
image: leviathan-worker:local
imagePullPolicy: IfNotPresent  # ✅ Uses local image
```

**Invariant Added:**
```python
# tools/invariants_check.py
if ':local' in image and pull_policy != 'IfNotPresent':
    self.fail(f"Local image must have imagePullPolicy: IfNotPresent")
```

**Result:** CI now fails if local images have wrong pull policy.

---

## Invariants as Documentation

Invariants serve dual purposes:

1. **Enforcement:** Prevent violations at commit time
2. **Documentation:** Explain why constraints exist

**Example:**
```yaml
# ops/invariants.yaml
kubernetes:
  namespace: leviathan
  # Why: All Leviathan resources must be in dedicated namespace
  # to avoid conflicts with other workloads and enable clean teardown.
```

The invariant file is **executable documentation**. It's not just a description—it's enforced by CI.

---

## How to Add a New Invariant

### 1. Identify the Constraint

Ask:
- What must always be true?
- What mistake would be expensive?
- What assumption must never be violated?

### 2. Add to `ops/invariants.yaml`

```yaml
# Example: Enforce control plane replicas
kubernetes:
  control_plane:
    min_replicas: 1
    max_replicas: 3
```

### 3. Implement Check in `tools/invariants_check.py`

```python
def check_control_plane_replicas(self):
    """Validate control plane replica count."""
    print("\n=== Checking Control Plane Replicas ===")
    
    manifest = self.repo_root / "ops/k8s/control-plane.yaml"
    with open(manifest, 'r') as f:
        docs = yaml.safe_load_all(f)
    
    for doc in docs:
        if doc.get('kind') == 'Deployment':
            replicas = doc.get('spec', {}).get('replicas', 1)
            if replicas < 1 or replicas > 3:
                self.fail(f"Control plane replicas must be 1-3, got {replicas}")
    
    print("✓ Control plane replicas valid")
```

### 4. Add to `run_all_checks()`

```python
def run_all_checks(self):
    # ... existing checks ...
    self.check_control_plane_replicas()
```

### 5. Add Unit Test

```python
# tests/unit/test_invariants_control_plane.py
def test_control_plane_replicas_enforced(self):
    """Control plane must have 1-3 replicas."""
    checker = InvariantsChecker(repo_root)
    checker.check_control_plane_replicas()
    assert len(checker.failures) == 0
```

### 6. Run Tests

```bash
python3 -m pytest tests/unit/test_invariants_control_plane.py -v
python3 tools/invariants_check.py
```

---

## Invariants vs. Tests

**Tests** validate behavior:
- "Does this function return the correct result?"
- "Does this API endpoint respond with 200?"

**Invariants** validate structure:
- "Is this configuration correct?"
- "Does this manifest follow conventions?"
- "Are constraints satisfied?"

**Both are necessary:**
- Tests ensure code works
- Invariants ensure code is packaged correctly

---

## Current Invariants

### Enforced by `tools/invariants_check.py`

1. **Control Plane K8s Manifests** - Namespace, image tags, secrets
2. **Worker Job Template** - Module execution, no shell scripts
3. **CI Workflows** - Required jobs, no dangerous commands
4. **Requirements** - Dependency versions, no conflicts
5. **Namespace Consistency** - All resources use `leviathan` namespace
6. **Topology Artifacts** - Required artifact backends exist
7. **Topology API Endpoints** - Required endpoints implemented
8. **Failover Documentation** - Required docs exist (archived)
9. **Failover Backends** - Required backends implemented
10. **K8s Packaging Invariants** - Namespace, image pull policy
11. **Autonomy Configuration** - Required fields, valid values
12. **Scheduler Manifest** - CronJob exists, correct namespace

### Enforced by Runtime Code

1. **Task Selection** - `ready: true` required
2. **Scope Restrictions** - `allowed_paths` within prefixes
3. **Max Open PRs** - Limit enforced by scheduler
4. **Retry Limits** - `max_attempts_per_task` enforced
5. **Circuit Breaker** - `circuit_breaker_failures` enforced

---

## References

- **Invariants Definition:** `ops/invariants.yaml`
- **Enforcement Code:** `tools/invariants_check.py`
- **CI Integration:** `.github/workflows/ci.yml`
- **Autonomy Config:** `ops/autonomy/dev.yaml`
- **Scheduler Code:** `leviathan/scheduler/dev_autonomy.py`

---

## Next Steps

- **Understand the system:** [10_ARCHITECTURE.md](10_ARCHITECTURE.md)
- **See guardrails in action:** [01_QUICKSTART.md](01_QUICKSTART.md)
- **Configure autonomy:** [41_CONFIGURATION.md](41_CONFIGURATION.md) (coming soon)
