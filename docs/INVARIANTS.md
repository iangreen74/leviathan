# Leviathan Invariants Gate

## Overview

The **Invariants Gate** is an anti-forgetting mechanism that prevents configuration drift and repeated failures in Leviathan. It enforces canonical truths about the system's deployment, naming conventions, and dependencies.

## Problem Statement

As systems evolve, configuration files can drift from their intended state:
- Container names get changed inconsistently across manifests
- Image names diverge between development and production
- Required environment variables get forgotten
- CI workflows lose critical validation steps
- Labels and selectors fall out of sync

These drifts lead to:
- Deployment failures
- Debugging time wasted on "it worked before" issues
- Repeated mistakes across different parts of the codebase
- Loss of institutional knowledge

## Solution: Invariants as Code

The invariants gate defines **canonical truths** in `ops/invariants.yaml` and validates them automatically in CI via `tools/invariants_check.py`.

### Canonical Truths Enforced

**Kubernetes Configuration:**
- Namespace: `leviathan`
- Control plane service: `leviathan-control-plane` on port `8000`
- Control plane container name: `control-plane`
- Worker container name: `worker`
- Control plane image: `leviathan-control-plane` (never `leviathan-worker`)
- Worker image: `leviathan-worker`

**Image Tagging:**
- Local dev images may use `:local` tag with `imagePullPolicy: IfNotPresent`
- Production images must be immutable (no `:latest` allowed)

**Labels and Selectors:**
- Control plane: `app=leviathan-control-plane`
- Worker jobs: `app=leviathan`, `target=<target>`, `task=<task>`, `attempt=<attempt_id>`

**Secrets and Environment Variables:**
- Control plane requires: `LEVIATHAN_CONTROL_PLANE_TOKEN`
- Worker jobs require: `CONTROL_PLANE_URL`, `CONTROL_PLANE_TOKEN`, `GITHUB_TOKEN`, `LEVIATHAN_CLAUDE_API_KEY`, `LEVIATHAN_CLAUDE_MODEL`

**CI Requirements:**
- Must run `invariants_check.py` before tests
- Must install `pytest`, `pyyaml`, `httpx` from `requirements-dev.txt`

## How It Works

### 1. Define Invariants (`ops/invariants.yaml`)

This file is the **single source of truth** for canonical configuration values. It's human-readable YAML that documents what MUST be true.

Example:
```yaml
kubernetes:
  namespace: leviathan
  control_plane:
    service_name: leviathan-control-plane
    port: 8000
    container_name: control-plane
```

### 2. Validate Invariants (`tools/invariants_check.py`)

Pure Python script (no external deps beyond stdlib + PyYAML) that:
- Reads `ops/invariants.yaml`
- Validates all K8s manifests in `ops/k8s/`
- Checks CI workflows in `.github/workflows/`
- Verifies `requirements-dev.txt` has required dependencies
- Ensures namespace consistency across all manifests

**Exit codes:**
- `0` - All invariants validated successfully ✅
- `1` - One or more invariants failed ❌

### 3. Enforce in CI (`.github/workflows/ci.yml`)

The invariants check runs **before** unit tests in CI:

```yaml
- name: Check invariants
  run: |
    python3 tools/invariants_check.py

- name: Run unit tests
  run: |
    python3 -m pytest tests/unit -v
```

This ensures that configuration drift is caught immediately, before it can cause deployment failures.

## Usage

### Running Locally

Before committing changes to K8s manifests or CI workflows:

```bash
python3 tools/invariants_check.py
```

If all checks pass:
```
✅ SUCCESS: All invariants validated
```

If checks fail:
```
❌ FAILED: 3 invariant(s) violated

Failures:
  1. Control plane container name must be 'control-plane', got 'api'
  2. Worker image must start with 'leviathan-worker', got 'worker:latest'
  3. Worker image uses forbidden ':latest' tag: worker:latest
```

### Modifying Invariants

Changes to `ops/invariants.yaml` require:
1. **Explicit PR review** - This file defines system truths
2. **Update validation logic** in `tools/invariants_check.py` if needed
3. **Update affected manifests** to match new invariants
4. **Document the reason** for the change in the PR description

### Adding New Invariants

To add a new invariant:

1. **Define it** in `ops/invariants.yaml`:
   ```yaml
   new_component:
     required_label: my-value
   ```

2. **Add validation** in `tools/invariants_check.py`:
   ```python
   def check_new_component(self):
       """Validate new component configuration."""
       # ... validation logic ...
   ```

3. **Call it** from `run_all_checks()`:
   ```python
   def run_all_checks(self):
       self.check_k8s_control_plane()
       self.check_new_component()  # Add here
       # ...
   ```

4. **Test it** locally:
   ```bash
   python3 tools/invariants_check.py
   ```

## Benefits

✅ **Prevents Drift** - Configuration stays consistent across all manifests  
✅ **Catches Errors Early** - Fails in CI, not in production  
✅ **Documents Intent** - `invariants.yaml` is living documentation  
✅ **Reduces Debugging** - No more "why did this break?" questions  
✅ **Enforces Standards** - Naming conventions are automatically validated  
✅ **Institutional Memory** - Knowledge is codified, not tribal  

## Design Principles

1. **Minimal** - No mega-framework, just YAML + Python stdlib
2. **Deterministic** - Same input always produces same output
3. **Fast** - Runs in <1 second
4. **Clear** - Failure messages explain exactly what's wrong
5. **Enforceable** - Runs in CI, blocks PRs on failure

## Examples

### Valid Configuration

Control plane deployment with correct container name and image:
```yaml
spec:
  template:
    spec:
      containers:
      - name: control-plane  # ✅ Matches invariant
        image: leviathan-control-plane:local  # ✅ Correct image name
```

### Invalid Configuration

Worker job with wrong container name:
```yaml
spec:
  template:
    spec:
      containers:
      - name: executor  # ❌ Should be 'worker'
        image: leviathan-worker:latest  # ❌ :latest forbidden
```

Invariants check will fail:
```
FAIL: Worker container name must be 'worker', got 'executor'
FAIL: Worker image uses forbidden ':latest' tag: leviathan-worker:latest
```

## Troubleshooting

**Q: Invariants check fails but I don't see the issue**  
A: Read the failure message carefully - it tells you exactly what's wrong and what it should be.

**Q: I need to change an invariant**  
A: Update `ops/invariants.yaml` first, then update manifests to match. Get PR review.

**Q: Can I skip the invariants check?**  
A: No. It's required in CI. If you need to change something, update the invariants properly.

**Q: The check is too strict**  
A: That's the point. Strictness prevents drift. If a rule doesn't make sense, propose changing the invariant with justification.

## Related Files

- `ops/invariants.yaml` - Canonical truths (single source of truth)
- `tools/invariants_check.py` - Validation script
- `.github/workflows/ci.yml` - CI enforcement
- `ops/k8s/*.yaml` - Kubernetes manifests (validated)
- `requirements-dev.txt` - Dev dependencies (validated)

## Future Enhancements

Potential additions to the invariants gate:
- Validate Docker image build arguments
- Check Helm chart values consistency
- Verify API endpoint paths match documentation
- Validate database schema migrations
- Enforce code style conventions

The invariants gate is extensible - add new checks as patterns emerge.
