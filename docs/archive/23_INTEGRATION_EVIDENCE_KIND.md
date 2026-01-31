# Leviathan Integration Evidence Pack - kind Cluster

**Version:** 1.0  
**Purpose:** Deterministic integration testing of Leviathan components on local kind cluster  
**Scope:** Control Plane + Scheduler + Worker + Spider + Autonomy controls

---

## Overview

This document provides step-by-step instructions for deploying and verifying the complete Leviathan stack on a local kind cluster. All commands are copy-paste friendly and include expected outputs.

**Components Deployed:**
- Control Plane API (event ingestion, graph queries, autonomy status)
- Spider Node (observability, metrics)
- DEV Autonomy Scheduler (CronJob)
- Worker (Kubernetes Jobs, on-demand)

---

## A. Preconditions

### Required Tools

```bash
# Verify installations
kind version
kubectl version --client
docker --version
```

**Expected versions:**
- kind: v0.20.0 or later
- kubectl: v1.27.0 or later
- docker: 20.10.0 or later

### Required Secrets

You will need:
1. **GitHub Token** with repo access (for worker to clone repos)
2. **Control Plane Token** (any secure random string)

Generate control plane token:
```bash
# Generate a secure random token
export CONTROL_PLANE_TOKEN=$(openssl rand -hex 32)
echo "Control Plane Token: $CONTROL_PLANE_TOKEN"

# Set your GitHub token
export GITHUB_TOKEN="ghp_your_github_token_here"
```

**Save these values** - you'll need them for verification steps.

### Repository Root

All commands assume you're in the repository root:
```bash
cd /path/to/leviathan
pwd  # Should show: /path/to/leviathan
```

---

## B. Clean Start

### Step 1: Create kind Cluster

```bash
kind create cluster --name leviathan
```

**Expected output:**
```
Creating cluster "leviathan" ...
 ✓ Ensuring node image (kindest/node:v1.27.3) 🖼
 ✓ Preparing nodes 📦  
 ✓ Writing configuration 📜 
 ✓ Starting control-plane 🕹️ 
 ✓ Installing CNI 🔌 
 ✓ Installing StorageClass 💾 
Set kubectl context to "kind-leviathan"
```

Verify cluster:
```bash
kubectl cluster-info --context kind-leviathan
kubectl get nodes
```

### Step 2: Build Docker Images

**Control Plane:**
```bash
docker build -t leviathan-control-plane:local -f ops/docker/control-plane.Dockerfile .
```

**Worker (also used by Spider):**
```bash
docker build -t leviathan-worker:local -f ops/docker/worker.Dockerfile .
```

**Expected output for each:**
```
Successfully built <image-id>
Successfully tagged leviathan-control-plane:local
```

Verify images:
```bash
docker images | grep leviathan
```

**Expected:**
```
leviathan-control-plane   local   <id>   <time>   <size>
leviathan-worker          local   <id>   <time>   <size>
```

### Step 3: Load Images into kind

```bash
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
```

**Expected output:**
```
Image: "leviathan-control-plane:local" with ID "<id>" not yet present on node "leviathan-control-plane", loading...
Image: "leviathan-worker:local" with ID "<id>" not yet present on node "leviathan-control-plane", loading...
```

---

## C. Kubernetes Bootstrap

### Step 1: Create Namespace

```bash
kubectl create namespace leviathan
```

**Expected output:**
```
namespace/leviathan created
```

### Step 2: Create Secrets

```bash
kubectl create secret generic leviathan-secrets \
  --namespace=leviathan \
  --from-literal=LEVIATHAN_CONTROL_PLANE_TOKEN="$CONTROL_PLANE_TOKEN" \
  --from-literal=GITHUB_TOKEN="$GITHUB_TOKEN"
```

**Expected output:**
```
secret/leviathan-secrets created
```

Verify secret:
```bash
kubectl get secret leviathan-secrets -n leviathan
```

**Expected:**
```
NAME                 TYPE     DATA   AGE
leviathan-secrets    Opaque   2      <time>
```

### Step 3: Create ConfigMap

The autonomy ConfigMap is already defined in `ops/k8s/control-plane.yaml`, so it will be created when we apply that manifest. No separate step needed.

---

## D. Build and Load Images

### Step 1: Build Control Plane Image

```bash
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
```

### Step 2: Build Worker Image

```bash
docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
```

### Step 3: Build Console Image

```bash
docker build -f ops/docker/console.Dockerfile -t leviathan-console:local .
```

### Step 4: Load Images into kind

```bash
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan
kind load docker-image leviathan-console:local --name leviathan
```

**Expected output for each:**
```
Image: "leviathan-<component>:local" with ID "sha256:..." not yet present on node "leviathan-control-plane", loading...
```

---

## E. Deploy Components with Kustomize

### Deploy Entire Stack

Use Kustomize to deploy all components at once:

```bash
kubectl apply -k ops/k8s/overlays/kind
```

**Expected output:**
```
service/leviathan-control-plane created
configmap/leviathan-autonomy-config created
deployment.apps/leviathan-control-plane created
deployment.apps/leviathan-spider created
service/leviathan-spider created
deployment.apps/leviathan-console created
service/leviathan-console created
cronjob.batch/leviathan-dev-scheduler created
configmap/job-template created
```

### Verify All Pods

Wait for all pods to be ready:
```bash
kubectl wait --for=condition=ready pod --all -n leviathan --timeout=120s
```

Check pod status:
```bash
kubectl get pods -n leviathan
```

**Expected:**
```
NAME                                      READY   STATUS    RESTARTS   AGE
leviathan-control-plane-<id>              1/1     Running   0          <time>
leviathan-spider-<id>                     1/1     Running   0          <time>
leviathan-console-<id>                    1/1     Running   0          <time>
```

---

## F. Verify Components

### Step 1: Verify Control Plane

```bash
kubectl apply -f ops/k8s/scheduler/dev-autonomy.yaml
```

**Expected output:**
```
cronjob.batch/leviathan-dev-scheduler created
```

Verify CronJob:
```bash
kubectl get cronjob -n leviathan
```

**Expected:**
```
NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
leviathan-dev-scheduler     */5 * * * *   False     0        <none>          <time>
```

**Note:** Scheduler runs every 5 minutes. Wait for first execution or manually trigger:
```bash
kubectl create job --from=cronjob/leviathan-dev-scheduler manual-trigger-1 -n leviathan
```

---

## E. Verification Steps

### 1. Control Plane Health

**Port-forward control plane:**
```bash
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &
```

**Test health endpoint:**
```bash
curl http://localhost:8000/health
```

**Expected response:**
```json
{"status":"healthy"}
```

### 2. Autonomy Status Endpoint

**Query autonomy status:**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status
```

**Expected response:**
```json
{
  "autonomy_enabled": true,
  "source": "configmap:/etc/leviathan/autonomy/dev.yaml"
}
```

**Verify fields:**
- `autonomy_enabled`: Should be `true` (from ConfigMap)
- `source`: Should reference the mounted ConfigMap path

### 3. Spider Health + Metrics

**Port-forward spider (in new terminal or background):**
```bash
kubectl port-forward -n leviathan svc/leviathan-spider 8001:8001 &
```

**Test health endpoint:**
```bash
curl http://localhost:8001/health
```

**Expected response:**
```json
{"status":"healthy","service":"spider"}
```

**Check metrics endpoint:**
```bash
curl http://localhost:8001/metrics
```

**Expected output (Prometheus format):**
```
# HELP leviathan_spider_up Spider node availability
# TYPE leviathan_spider_up gauge
leviathan_spider_up 1.0

# HELP leviathan_events_received_total Total events received by type
# TYPE leviathan_events_received_total counter
leviathan_events_received_total{event_type="pr.opened"} 0.0
leviathan_events_received_total{event_type="pr.closed"} 0.0
...
```

**Verify metrics:**
- `leviathan_spider_up` should be `1.0`
- Event counters should be present (initially `0.0`)

### 4. Event Forwarding Proof

**Step 4a: Capture baseline metrics**
```bash
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="pr.opened"}'
```

**Expected baseline:**
```
leviathan_events_received_total{event_type="pr.opened"} 0.0
```

**Step 4b: Ingest synthetic event**

Create test event payload:
```bash
cat > /tmp/test_event.json <<'EOF'
{
  "events": [
    {
      "event_id": "test-event-001",
      "event_type": "pr.opened",
      "timestamp": "2026-01-28T18:00:00Z",
      "payload": {
        "pr_number": 999,
        "repository": "test/repo",
        "title": "Test PR for integration evidence"
      }
    }
  ]
}
EOF
```

**Ingest event:**
```bash
curl -X POST \
  -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/test_event.json \
  http://localhost:8000/v1/events/ingest
```

**Expected response (immediate 200):**
```json
{
  "status": "success",
  "events_ingested": 1,
  "events_projected": 1
}
```

**Step 4c: Verify Spider received event**

Wait 2-3 seconds for async forwarding, then check metrics:
```bash
sleep 3
curl -s http://localhost:8001/metrics | grep 'leviathan_events_received_total{event_type="pr.opened"}'
```

**Expected (counter incremented):**
```
leviathan_events_received_total{event_type="pr.opened"} 1.0
```

**Verification:**
- Control plane returned 200 immediately (non-blocking)
- Spider metrics show counter incremented
- Event forwarding is working

### 5. Autonomy Kill Switch Proof

**Step 5a: Verify current state**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq '.autonomy_enabled'
```

**Expected:**
```
true
```

**Step 5b: Disable autonomy via ConfigMap**

Edit ConfigMap:
```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

Change line:
```yaml
autonomy_enabled: true
```

To:
```yaml
autonomy_enabled: false
```

Save and exit (`:wq` in vim).

**Step 5c: Verify ConfigMap update**
```bash
kubectl get configmap leviathan-autonomy-config -n leviathan -o yaml | grep autonomy_enabled
```

**Expected:**
```
    autonomy_enabled: false
```

**Step 5d: Verify status API reflects change**
```bash
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
  http://localhost:8000/v1/autonomy/status | jq '.autonomy_enabled'
```

**Expected:**
```
false
```

**Step 5e: Trigger scheduler and verify behavior**

Manually trigger scheduler:
```bash
kubectl create job --from=cronjob/leviathan-dev-scheduler manual-trigger-disabled -n leviathan
```

Wait for job to complete:
```bash
kubectl wait --for=condition=complete job/manual-trigger-disabled -n leviathan --timeout=60s
```

Check scheduler logs:
```bash
kubectl logs job/manual-trigger-disabled -n leviathan
```

**Expected log output:**
```
============================================================
DEV Autonomy Scheduler - 2026-01-28T18:00:00.000000
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

⚠ Autonomy disabled in configuration (autonomy_enabled: false)
✓ Scheduler exiting cleanly without submitting jobs
```

**Step 5f: Verify no worker jobs created**
```bash
kubectl get jobs -n leviathan -l app=leviathan-worker
```

**Expected:**
```
No resources found in leviathan namespace.
```

**Verification:**
- Scheduler detected `autonomy_enabled: false`
- Scheduler exited cleanly without submitting jobs
- No worker jobs created

### 6. Emergency Stop (Runbook Alignment)

**Step 6a: Suspend CronJob**
```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":true}}'
```

**Expected:**
```
cronjob.batch/leviathan-dev-scheduler patched
```

**Step 6b: Verify suspension**
```bash
kubectl get cronjob leviathan-dev-scheduler -n leviathan
```

**Expected:**
```
NAME                        SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
leviathan-dev-scheduler     */5 * * * *   True      0        <time>          <time>
```

Note `SUSPEND: True`

**Step 6c: (Optional) Delete running worker jobs**
```bash
kubectl delete jobs -n leviathan -l app=leviathan-worker
```

**Step 6d: Resume CronJob**
```bash
kubectl patch cronjob leviathan-dev-scheduler -n leviathan -p '{"spec":{"suspend":false}}'
```

**Expected:**
```
cronjob.batch/leviathan-dev-scheduler patched
```

**Step 6e: Re-enable autonomy**

Edit ConfigMap to set `autonomy_enabled: true`:
```bash
kubectl edit configmap leviathan-autonomy-config -n leviathan
```

Change back to:
```yaml
autonomy_enabled: true
```

**Verification:**
- CronJob can be suspended/resumed
- Worker jobs can be deleted
- Autonomy can be re-enabled via ConfigMap

---

## F. Troubleshooting

### Problem: 401 Unauthorized

**Symptom:**
```bash
curl http://localhost:8000/v1/autonomy/status
# Response: {"detail":"Not authenticated"}
```

**Cause:** Missing or incorrect bearer token

**Fix:**
```bash
# Verify token is set
echo $CONTROL_PLANE_TOKEN

# Get token from secret if lost
kubectl get secret leviathan-secrets -n leviathan -o jsonpath='{.data.LEVIATHAN_CONTROL_PLANE_TOKEN}' | base64 -d

# Use correct token in request
curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" http://localhost:8000/v1/autonomy/status
```

### Problem: ImagePullBackOff

**Symptom:**
```bash
kubectl get pods -n leviathan
# STATUS: ImagePullBackOff or ErrImagePull
```

**Cause:** Image not loaded into kind cluster

**Fix:**
```bash
# Verify images exist locally
docker images | grep leviathan

# Load images into kind
kind load docker-image leviathan-control-plane:local --name leviathan
kind load docker-image leviathan-worker:local --name leviathan

# Restart deployment
kubectl rollout restart deployment leviathan-control-plane -n leviathan
kubectl rollout restart deployment leviathan-spider -n leviathan
```

### Problem: Spider Not Receiving Events

**Symptom:**
- Control plane returns 200
- Spider metrics don't increment

**Diagnosis:**
```bash
# Check Spider pod logs
kubectl logs -n leviathan -l app=leviathan-spider --tail=50

# Check control plane logs for forwarding errors
kubectl logs -n leviathan -l app=leviathan-control-plane --tail=50 | grep -i spider
```

**Possible Causes:**

1. **Spider URL not set:**
   ```bash
   # Check control plane env vars
   kubectl get deployment leviathan-control-plane -n leviathan -o yaml | grep SPIDER
   ```
   
   Expected: `LEVIATHAN_SPIDER_ENABLED: "true"` and `LEVIATHAN_SPIDER_URL`

2. **Service DNS not resolving:**
   ```bash
   # Test DNS from control plane pod
   kubectl exec -n leviathan deployment/leviathan-control-plane -- nslookup leviathan-spider.leviathan.svc.cluster.local
   ```

3. **Spider not healthy:**
   ```bash
   kubectl get pods -n leviathan -l app=leviathan-spider
   # Check READY column is 1/1
   ```

**Fix:**
- Ensure Spider deployment is running and healthy
- Verify service exists: `kubectl get svc leviathan-spider -n leviathan`
- Check control plane has Spider forwarding enabled (env vars)

### Problem: Scheduler Running But Idle

**Symptom:**
- Scheduler job completes successfully
- No worker jobs created
- Logs show "No executable tasks found"

**Possible Causes:**

1. **Autonomy disabled:**
   ```bash
   curl -H "Authorization: Bearer $CONTROL_PLANE_TOKEN" \
     http://localhost:8000/v1/autonomy/status
   ```
   If `autonomy_enabled: false`, re-enable via ConfigMap.

2. **No ready tasks in backlog:**
   - Scheduler only executes tasks with `ready: true`
   - Check target backlog has tasks marked ready

3. **Max open PRs reached:**
   - Scheduler logs show: "Max open PRs reached"
   - Close existing PRs or increase `max_open_prs` in ConfigMap

4. **Circuit breaker tripped:**
   - Scheduler logs show: "Circuit breaker tripped"
   - Indicates consecutive failures
   - Reset by waiting or manually clearing failure state

**Diagnosis:**
```bash
# Check scheduler logs
kubectl logs -n leviathan job/manual-trigger-1 --tail=100

# Look for specific messages
kubectl logs -n leviathan job/manual-trigger-1 | grep -E "(autonomy disabled|Max open PRs|Circuit breaker|No executable tasks)"
```

### Problem: Port-forward Connection Refused

**Symptom:**
```bash
curl http://localhost:8000/health
# curl: (7) Failed to connect to localhost port 8000: Connection refused
```

**Cause:** Port-forward not running or terminated

**Fix:**
```bash
# Kill existing port-forwards
pkill -f "kubectl port-forward"

# Restart port-forward
kubectl port-forward -n leviathan svc/leviathan-control-plane 8000:8000 &
kubectl port-forward -n leviathan svc/leviathan-spider 8001:8001 &

# Verify port-forwards are running
ps aux | grep "kubectl port-forward"
```

---

## G. Cleanup

**Delete kind cluster:**
```bash
kind delete cluster --name leviathan
```

**Expected:**
```
Deleting cluster "leviathan" ...
```

**Remove Docker images (optional):**
```bash
docker rmi leviathan-control-plane:local
docker rmi leviathan-worker:local
```

---

## Summary

This integration evidence pack demonstrates:

✅ **Full stack deployment** on kind cluster  
✅ **Control plane** serving API with authentication  
✅ **Autonomy status API** reading from ConfigMap  
✅ **Spider Node** receiving events and exposing metrics  
✅ **Event forwarding** from control plane to Spider (non-blocking)  
✅ **Autonomy kill switch** via ConfigMap (deterministic)  
✅ **Emergency stop** via CronJob suspension  
✅ **Scheduler behavior** respects autonomy flag  

All verification steps include expected outputs for deterministic validation.

---

## Related Documentation

- [Operations Runbook](./21_OPERATIONS_AUTONOMY.md)
- [Canonical Overview](./00_CANONICAL_OVERVIEW.md)
- [Quickstart](./01_QUICKSTART.md)
- [Spider Node](./20_SPIDER_NODE.md)
