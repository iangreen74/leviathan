# Leviathan Stability Improvements

## Summary

This document tracks stability, operability, and "boring-ness" improvements to make Leviathan production-ready.

## ✅ Completed

### 1. CI Stabilization (DONE)

**Problem**: Tests failed when run together due to environment variable pollution and shared state.

**Root Cause**: `test_k8s_job_spec.py` was overwriting `LEVIATHAN_CONTROL_PLANE_TOKEN` to `"test-token"` instead of using the conftest value `"test-token-12345"`.

**Fix**:
- Removed token override in `test_k8s_job_spec.py`
- All tests now use token from `conftest.py`
- Added cleanup in test fixtures with `yield` and `reset_stores()`
- Added try/except in `reset_stores()` for safer cleanup

**Result**: All 241 tests pass consistently ✅

**Files Changed**:
- `tests/unit/test_k8s_job_spec.py`
- `leviathan/control_plane/api.py`
- `tests/unit/test_leviathanctl_api.py`

### 2. Test Isolation (DONE)

**Problem**: Tests shared NDJSON backend state, causing failures like `count==1` when expecting `count==0`.

**Fix**:
- Added `ndjson_dir` parameter to `EventStore.__init__()`
- Added `reset_stores()` and `initialize_stores(ndjson_dir, artifacts_dir)` to API
- All API tests now use `tmp_path` fixtures for isolated storage
- Each test gets fresh storage, no cross-test pollution

**Result**: Tests no longer write to `~/.leviathan`, no shared state ✅

**Files Changed**:
- `leviathan/graph/events.py`
- `leviathan/control_plane/api.py`
- `tests/unit/test_control_plane_api.py`
- `tests/unit/test_api_pr_ingest.py`
- `tests/unit/test_leviathanctl_api.py`

### 3. Documentation (DONE)

**Created**: `docs/HOW_LEVIATHAN_OPERATES.md`

**Content**:
- Clear explanation of Leviathan's purpose (execution, not planning)
- Target registration process (contract, backlog, policy)
- Execution flow with human-in-the-loop guarantees
- Workflow example (dependency updates)
- Safety mechanisms (scope enforcement, invariants, PR review)
- Operational control (monitoring, emergency stop)
- Best practices (small tasks, explicit criteria, narrow scopes)

**Result**: Operators now have clear documentation on how Leviathan works ✅

## ⚠️ Issues Identified (Not Yet Fixed)

### 1. GHCR Image Versioning

**Problem**: `.github/workflows/release-ghcr.yml` uses mutable `latest` tags.

**Issues**:
- `latest` tag is mutable, violates immutability principle
- No guarantee what version `latest` points to
- Rollbacks are difficult
- K8s deployments using `latest` may pull different versions

**Recommendation**:
```yaml
# REMOVE mutable latest tags
tags: |
  ${{ env.IMAGE_PREFIX }}-control-plane:${{ steps.meta.outputs.short_sha }}
  ${{ steps.meta.outputs.is_tag == 'true' && format('{0}-control-plane:{1}', env.IMAGE_PREFIX, steps.meta.outputs.version) || '' }}
  # REMOVE: latest tag

# K8s should use explicit versions:
image: ghcr.io/iangreen74/leviathan-control-plane:v1.2.3
# NOT: ghcr.io/iangreen74/leviathan-control-plane:latest
```

**Impact**: Medium - affects deployment reproducibility

### 2. K8s Control Plane YAML

**Problem**: `ops/k8s/control-plane.yaml` has multiple issues:

1. **Wrong Image**: Uses `leviathan-worker:local` instead of GHCR image
2. **No Resource Limits**: No CPU/memory limits or requests
3. **No Health Checks**: No readiness/liveness probes
4. **Secrets Undocumented**: References `leviathan-secrets` without documentation

**Recommendation**:
```yaml
containers:
  - name: api
    image: ghcr.io/iangreen74/leviathan-control-plane:v1.2.3  # Explicit version
    resources:
      requests:
        memory: "256Mi"
        cpu: "100m"
      limits:
        memory: "512Mi"
        cpu: "500m"
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8000
      initialDelaySeconds: 10
      periodSeconds: 30
    readinessProbe:
      httpGet:
        path: /healthz
        port: 8000
      initialDelaySeconds: 5
      periodSeconds: 10
```

**Impact**: High - affects production stability

### 3. leviathanctl CLI Safety

**Current State**: CLI is functional but needs hardening.

**Issues**:
- `invalidate` command is destructive but has no confirmation prompt
- No `--dry-run` mode for destructive operations
- Error messages could be more helpful

**Recommendations**:
```python
# Add confirmation for destructive operations
def invalidate(attempt_id, reason):
    print(f"WARNING: This will invalidate attempt {attempt_id}")
    print(f"Reason: {reason}")
    confirm = input("Continue? [y/N]: ")
    if confirm.lower() != 'y':
        print("Cancelled")
        return
    # ... proceed with invalidation

# Add --dry-run mode
@click.option('--dry-run', is_flag=True, help='Show what would be done without doing it')
def invalidate(attempt_id, reason, dry_run):
    if dry_run:
        print(f"[DRY RUN] Would invalidate attempt {attempt_id}")
        print(f"[DRY RUN] Reason: {reason}")
        return
    # ... actual invalidation
```

**Impact**: Medium - affects operator safety

### 4. Missing Operational Docs

**Gaps**:
- No runbook for common operations (restart, scale, troubleshoot)
- No disaster recovery procedures
- No backup/restore documentation for event store
- No monitoring/alerting setup guide

**Recommendation**: Create `docs/OPERATIONS_RUNBOOK.md` with:
- Common operations (restart, scale, update)
- Troubleshooting guide (common errors, solutions)
- Disaster recovery (backup event store, restore)
- Monitoring setup (metrics, alerts, dashboards)

**Impact**: Medium - affects operational readiness

## 🔮 Future Work (Deferred)

### 1. Event Store Backup

**Need**: Automated backup of NDJSON event store to S3/GCS.

**Why Deferred**: Current NDJSON backend is for development. Production should use Postgres with standard backup tools.

### 2. Metrics and Observability

**Need**: Prometheus metrics, Grafana dashboards, alerting.

**Why Deferred**: Wait until production deployment to determine actual metrics needs.

### 3. Multi-Tenancy

**Need**: Support multiple targets in single control plane instance.

**Why Deferred**: Current single-target model is simpler and sufficient for initial deployment.

### 4. Scheduler Improvements

**Need**: More sophisticated scheduling (time windows, dependencies, retries).

**Why Deferred**: Current simple scheduler (priority-based) is sufficient. Add complexity only when needed.

## Testing Status

```
Total Tests: 241
Passing: 241 ✅
Failing: 0 ✅
Flaky: 0 ✅

Test Coverage:
- API endpoints: ✅
- Event ingestion: ✅
- Graph operations: ✅
- CLI commands: ✅
- Executor logic: ✅
- Policy validation: ✅
```

## CI/CD Status

```
GitHub Actions:
- ci.yml: ✅ All tests pass
- release-ghcr.yml: ⚠️ Builds images but uses mutable tags

Required Fixes:
- Remove `latest` tags from GHCR workflow
- Update K8s YAML to use explicit image versions
```

## Deployment Readiness

| Component | Status | Blocker |
|-----------|--------|---------|
| Control Plane API | ✅ Ready | None |
| Event Store (NDJSON) | ✅ Ready | Dev only, use Postgres for prod |
| K8s Executor | ⚠️ Needs work | K8s YAML issues |
| leviathanctl CLI | ✅ Ready | Minor UX improvements recommended |
| Documentation | ✅ Ready | None |
| CI/CD | ⚠️ Needs work | Image versioning issues |

## Recommendations

### Immediate (Before Production)

1. **Fix K8s YAML**: Update control-plane.yaml with proper image, resources, probes
2. **Fix GHCR Workflow**: Remove mutable `latest` tags
3. **Document Secrets**: Create example secrets.yaml with required keys
4. **Add Runbook**: Create operations runbook for common tasks

### Short-Term (First Month)

1. **Add CLI Confirmations**: Protect destructive operations
2. **Setup Monitoring**: Basic metrics and alerts
3. **Backup Strategy**: Document event store backup/restore
4. **Load Testing**: Verify control plane can handle expected load

### Long-Term (As Needed)

1. **Postgres Backend**: Migrate from NDJSON to Postgres for production
2. **Multi-Tenancy**: Support multiple targets if needed
3. **Advanced Scheduling**: Add time windows, dependencies if needed
4. **Observability**: Full metrics, tracing, dashboards

## Principles Maintained

✅ **Explicit over Implicit**: All configuration is explicit, no hidden defaults
✅ **Auditable**: All actions logged to event store
✅ **PR-Based**: Every change creates a PR for human review
✅ **Scoped**: Tasks can only modify allowed files
✅ **Boring**: No autonomous planning, no surprises, predictable behavior

## Conclusion

Leviathan is now **stable and testable** with:
- All tests passing consistently
- Proper test isolation
- Clear documentation
- Identified issues with remediation plans

Remaining work is **operational hardening** (K8s config, image versioning, runbooks) rather than core functionality.

The system is **boring by design**: it executes explicit tasks, creates PRs, and waits for human approval. No magic, no surprises.
