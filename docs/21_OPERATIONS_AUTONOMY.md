# Leviathan Autonomy Operations Runbook

**Version:** 1.0  
**Audience:** Platform operators, SREs  
**Scope:** DEV autonomy control plane operations

---

## Overview

Leviathan autonomy enables closed-loop task execution with strict guardrails. This runbook provides operational procedures for monitoring, controlling, and troubleshooting autonomous operations.

**Key Components:**
- **Control Plane:** Exposes autonomy status via API
- **Scheduler:** Reads autonomy config and schedules work
- **ConfigMap:** Single source of truth for autonomy configuration

---

## Query Autonomy Status

### Endpoint

```
GET /v1/autonomy/status
```

**Authentication:** Bearer token required

### Example Request

```bash
# Set your control plane token
export CONTROL_PLANE_TOKEN="your-secret-token"

# Query status
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://leviathan-control-plane:8000/v1/autonomy/status
```

### Expected Response

```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

**Fields:**
- `autonomy_enabled` (bool): Current autonomy state
- `source` (string): Where the value was read from

**Source Values:**
- `configmap:<path>`: Read from mounted ConfigMap (normal)
- `default (config not mounted)`: ConfigMap not available, using default
- `default (error reading config)`: Error reading config, using fail-safe default

---

## Disable Autonomy (Graceful)

### Method: Update ConfigMap

This is the **deterministic** method for disabling autonomy.

#### Step 1: Edit ConfigMap

```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

Change:
```yaml
autonomy_enabled: true
```

To:
```yaml
autonomy_enabled: false
```

#### Step 2: Verify ConfigMap Update

```bash
kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml | grep autonomy_enabled
```

Expected output:
```
autonomy_enabled: false
```

#### Step 3: Wait for Scheduler to Pick Up Change

**Behavior:**
- Scheduler reads config at the **start of each scheduling cycle**
- Next scheduler tick will see `autonomy_enabled: false`
- Scheduler will log: `⚠ Autonomy disabled in configuration (autonomy_enabled: false)`
- Scheduler will exit cleanly **without submitting any jobs**

**Timeline:**
- Default schedule: Every 5 minutes (`*/5 * * * *`)
- Max wait time: 5 minutes for next tick
- No restart required

#### Step 4: Verify Autonomy Disabled

**Check scheduler logs:**
```bash
kubectl logs -n leviathan -l app=leviathan-dev-scheduler --tail=50
```

Look for:
```
⚠ Autonomy disabled in configuration (autonomy_enabled: false)
✓ Scheduler exiting cleanly without submitting jobs
```

**Check job creation:**
```bash
# No new worker jobs should be created
kubectl get jobs -n leviathan -l app=leviathan-worker --sort-by=.metadata.creationTimestamp
```

**Query control plane:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://leviathan-control-plane:8000/v1/autonomy/status
```

Expected:
```json
{
  "autonomy_enabled": false,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

---

## Emergency Stop

Use when immediate halt is required (e.g., runaway behavior detected).

### Step 1: Suspend Scheduler CronJob

```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":true}}'
```

**Effect:** No new scheduler pods will be created.

### Step 2: Verify Suspension

```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

Expected output:
```
NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
leviathan-dev-scheduler     */5 * * * *   True      0        2m              1d
```

Note `SUSPEND: True`

### Step 3: (Optional) Delete Running Worker Jobs

If workers are currently executing tasks:

```bash
# List running workers
kubectl get jobs -n leviathan -l app=leviathan-worker

# Delete specific job
kubectl delete job <job-name> -n leviathan

# Or delete all worker jobs (use with caution)
kubectl delete jobs -n leviathan -l app=leviathan-worker
```

### Step 4: Verify No Active Work

```bash
# No running scheduler pods
kubectl get pods -n leviathan -l app=leviathan-dev-scheduler

# No running worker pods
kubectl get pods -n leviathan -l app=leviathan-worker
```

---

## Re-enable Autonomy

### Step 1: Update ConfigMap

```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

Change:
```yaml
autonomy_enabled: false
```

To:
```yaml
autonomy_enabled: true
```

### Step 2: Unsuspend Scheduler (if suspended)

```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":false}}'
```

### Step 3: Verify Re-enablement

**Check CronJob:**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

Expected: `SUSPEND: False`

**Wait for next scheduler tick** (max 5 minutes)

**Check scheduler logs:**
```bash
kubectl logs -n leviathan -l app=leviathan-dev-scheduler --tail=50
```

Look for normal scheduling activity (no "autonomy disabled" message).

**Query control plane:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://leviathan-control-plane:8000/v1/autonomy/status
```

Expected:
```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

---

## Troubleshooting

### Problem: Control Plane Returns `default (config not mounted)`

**Cause:** ConfigMap not mounted in control plane pod.

**Fix:**
1. Check control plane deployment:
   ```bash
   kubectl get deployment leviathan-control-plane -n leviathan -o yaml | grep -A 10 volumes
   ```

2. Verify ConfigMap exists:
   ```bash
   kubectl get configmap leviathan-autonomy-config -n leviathan
   ```

3. If missing, apply manifests:
   ```bash
   kubectl apply -f ops/k8s/control-plane.yaml
   ```

4. Restart control plane:
   ```bash
   kubectl rollout restart deployment leviathan-control-plane -n leviathan
   ```

### Problem: Scheduler Still Creating Jobs After Disabling

**Diagnosis:**
1. Check ConfigMap value:
   ```bash
   kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml | grep autonomy_enabled
   ```

2. Check scheduler logs for config read:
   ```bash
   kubectl logs -n leviathan -l app=leviathan-dev-scheduler --tail=100
   ```

**Possible Causes:**
- ConfigMap not updated correctly
- Scheduler using cached config (wait for next tick)
- Scheduler not reading from ConfigMap (check mount)

**Fix:**
1. Verify ConfigMap update applied
2. Wait for next scheduler tick (max 5 minutes)
3. If still creating jobs, use emergency stop procedure

### Problem: Autonomy Status API Returns 401

**Cause:** Invalid or missing bearer token.

**Fix:**
1. Verify token is set:
   ```bash
   echo $CONTROL_PLANE_TOKEN
   ```

2. Get correct token from secret:
   ```bash
   kubectl get secret leviathan-secrets -n leviathan -o jsonpath='{.data.LEVIATHAN_CONTROL_PLANE_TOKEN}' | base64 -d
   ```

3. Use correct token in request

### Problem: Scheduler Logs Show Errors Reading Config

**Diagnosis:**
```bash
kubectl logs -n leviathan -l app=leviathan-dev-scheduler --tail=100 | grep -i error
```

**Possible Causes:**
- ConfigMap not mounted in scheduler pod
- Invalid YAML in ConfigMap
- File permissions issue

**Fix:**
1. Check scheduler deployment for volume mount:
   ```bash
   kubectl get cronjob leviathan-dev-scheduler -n leviathan -o yaml | grep -A 10 volumes
   ```

2. Validate ConfigMap YAML:
   ```bash
   kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml
   ```

3. Check for YAML syntax errors

---

## Failure Modes

### ConfigMap Unavailable

**Behavior:**
- Control plane: Returns `autonomy_enabled: true` with source `default (config not mounted)`
- Scheduler: Falls back to default behavior (may vary by implementation)

**Impact:** Fail-safe defaults prevent complete failure

**Mitigation:** Apply ConfigMap, restart affected pods

### Scheduler CronJob Suspended Accidentally

**Behavior:**
- No scheduler pods created
- No new tasks scheduled
- Existing workers continue to completion

**Impact:** Autonomy effectively disabled

**Detection:**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

**Mitigation:** Unsuspend CronJob

### Control Plane Unavailable

**Behavior:**
- Status API unreachable
- Scheduler continues based on last read config
- Workers continue executing

**Impact:** Cannot query status, but autonomy continues

**Mitigation:** Restart control plane deployment

---

## Best Practices

1. **Always use ConfigMap method** for planned disablement
2. **Reserve emergency stop** for critical situations
3. **Monitor scheduler logs** after configuration changes
4. **Verify status via API** after changes
5. **Document reason** when disabling autonomy (e.g., in runbook or incident log)
6. **Test re-enablement** in non-production first

---

## Quick Reference

| Action | Command |
|--------|---------|
| Query status | `curl -H "Authorization: Bearer $TOKEN" http://leviathan-control-plane:8000/v1/autonomy/status` |
| Disable (graceful) | `kubectl edit configmap leviathan-autonomy-config -n leviathan` → set `autonomy_enabled: false` |
| Emergency stop | `kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":true}}'` |
| Re-enable | Set `autonomy_enabled: true` in ConfigMap + unsuspend CronJob |
| Check scheduler logs | `kubectl logs -n leviathan -l app=leviathan-dev-scheduler --tail=50` |
| List worker jobs | `kubectl get jobs -n leviathan -l app=leviathan-worker` |

---

## Related Documentation

- [Autonomy Overview](./00_CANONICAL_OVERVIEW.md)
- [Quickstart](./01_QUICKSTART.md)
- [Invariants and Guardrails](./07_INVARIANTS_AND_GUARDRAILS.md)
- [Spider Node](./20_SPIDER_NODE.md)
