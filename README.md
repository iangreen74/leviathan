# Leviathan

**Autonomous Software Engineering System**

Leviathan is a closed-loop autonomous system that executes tasks from target repository backlogs and creates pull requests automatically under strict guardrails.

**Current State:**
- ✅ PR Proof v1 (local execution)
- ✅ PR Proof v1 on Kubernetes (kind)
- ✅ Autonomy v1 (DEV-only, closed-loop operation)
- ✅ Deterministic, invariant-enforced operation
- ✅ 369 tests passing, all invariants validated

---

## Quick Start

Run Autonomy v1 on kind in 5 minutes:

```bash
# 1. Create kind cluster
kind create cluster --name leviathan

# 2. Build and load images
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan

# 3. Create namespace and secrets
kubectl create namespace leviathan
kubectl -n leviathan create secret generic leviathan-control-plane-secret \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
kubectl -n leviathan create secret generic leviathan-secrets \
  --from-literal=github-token=<your-token>

# 4. Create autonomy config
kubectl -n leviathan create configmap leviathan-autonomy-config \
  --from-file=dev.yaml=ops/autonomy/dev.yaml

# 5. Deploy
kubectl apply -f ops/k8s/control-plane.yaml
kubectl apply -f ops/k8s/scheduler/dev-autonomy.yaml

# 6. Observe
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=100 -f
kubectl -n leviathan logs -l app=leviathan-worker --tail=100 -f
```

**See [docs/01_QUICKSTART.md](docs/01_QUICKSTART.md) for detailed instructions.**

---

## Documentation

**📚 START HERE:** [docs/00_CANONICAL_OVERVIEW.md](docs/00_CANONICAL_OVERVIEW.md)

### Getting Started
- [01_QUICKSTART.md](docs/01_QUICKSTART.md) - Run Autonomy v1 on kind in 5 minutes

### Architecture
- [10_ARCHITECTURE.md](docs/10_ARCHITECTURE.md) - System architecture and design

### Operations
- [20_KUBERNETES_DEPLOYMENT.md](docs/20_KUBERNETES_DEPLOYMENT.md) - K8s deployment guide (coming soon)
- [21_AUTONOMY_OPERATIONS.md](docs/21_AUTONOMY_OPERATIONS.md) - Running Autonomy v1 (coming soon)

### Development
- [30_CONTRIBUTING.md](docs/30_CONTRIBUTING.md) - Development workflow (coming soon)
- [31_TESTING.md](docs/31_TESTING.md) - Testing strategy (coming soon)

### Reference
- [40_API_REFERENCE.md](docs/40_API_REFERENCE.md) - Control plane API (coming soon)
- [41_CONFIGURATION.md](docs/41_CONFIGURATION.md) - Configuration reference (coming soon)

**📦 Archive:** Historical documentation is in [docs/archive/pre_autonomy_docs/](docs/archive/pre_autonomy_docs/)

---

## Core Principles

1. **No Autonomous Planning:** Leviathan does NOT invent tasks. It only executes tasks with `ready: true`.
2. **PR-Based Delivery:** All changes via pull requests. No direct commits. No auto-merge (unless explicitly enabled).
3. **Deterministic Operation:** Full event audit trail. Every action produces events.
4. **Invariant Enforcement:** Runtime checks at commit time. CI fails if invariants violated.
5. **Strict Guardrails:** Scope restrictions, concurrency limits, retry policies, circuit breakers.

---

## Safety Guarantees

- ✅ **Scope Isolation:** Tasks outside `.leviathan/**` or `docs/**` are skipped (DEV mode)
- ✅ **Concurrency Control:** Max 1 open PR at a time
- ✅ **Retry Limits:** Max 2 attempts per task
- ✅ **Circuit Breaker:** Stops after consecutive failures
- ✅ **No Auto-Merge:** Human review required
- ✅ **Deterministic Evidence:** Full event history persisted

---

## Testing

```bash
# Run unit tests (369 tests)
python3 -m pytest tests/unit -q

# Run invariants check
python3 tools/invariants_check.py
```

---

## License

MIT License - See LICENSE file
