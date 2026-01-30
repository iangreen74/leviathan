# Console Fix Evidence

**Date:** 2026-01-30
**Issue:** Console "Recent Attempts" and "Recent PRs" showing error loading
**Root Cause:** Control plane image was outdated and missing `/v1/events/recent` endpoint

---

## Problem Diagnosis

### Initial Error (500 Internal Server Error)

```bash
$ curl -i http://localhost:8080/api/recent/attempts
HTTP/1.1 500 Internal Server Error
{"detail":"Client error '404 Not Found' for url 'http://leviathan-control-plane:8000/v1/events/recent?limit=200'"}
```

### Root Cause Analysis

1. Console code was correctly calling `/v1/events/recent` with Authorization header
2. Console deployment had correct env vars (CONTROL_PLANE_TOKEN from secret)
3. Control plane **code** had the endpoint (added in feat/operator-console-v1 branch)
4. Control plane **deployed image** was old and didn't have the endpoint

---

## Fix Applied

### Step 1: Rebuild Control Plane Image

```bash
docker build -f ops/docker/control-plane.Dockerfile -t leviathan-control-plane:local .
```

### Step 2: Load into kind

```bash
kind load docker-image leviathan-control-plane:local --name leviathan
```

### Step 3: Restart Deployment

```bash
kubectl -n leviathan rollout restart deployment/leviathan-control-plane
kubectl -n leviathan wait --for=condition=ready pod -l app=leviathan-control-plane --timeout=60s
```

---

## Verification

### Control Plane Endpoint Test (with auth)

```bash
$ export TOKEN=$(kubectl -n leviathan get secret leviathan-secrets -o jsonpath='{.data.LEVIATHAN_CONTROL_PLANE_TOKEN}' | base64 -d)
$ curl -i -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/events/recent?limit=5

HTTP/1.1 200 OK
date: Fri, 30 Jan 2026 22:08:52 GMT
server: uvicorn
content-length: 2
content-type: application/json

[]
```

### Control Plane Endpoint Test (without auth)

```bash
$ curl -i http://localhost:8000/v1/events/recent?limit=5

HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Not authenticated"}
```

✅ **Auth working correctly**

### Console Endpoints Test

```bash
$ curl -i http://localhost:8080/api/recent/attempts

HTTP/1.1 200 OK
date: Fri, 30 Jan 2026 22:10:21 GMT
server: uvicorn
content-length: 198
content-type: application/json

[{"attempt_id":"attempt-docs-leviathan-backlog-guide-6ddde33d","task_id":"docs-leviathan-backlog-guide","status":"succeeded","timestamp":"2026-01-30T22:10:12.496731","pr_url":null,"pr_number":null}]
```

```bash
$ curl -i http://localhost:8080/api/recent/prs

HTTP/1.1 200 OK
date: Fri, 30 Jan 2026 22:10:25 GMT
server: uvicorn
content-length: 2
content-type: application/json

[]
```

```bash
$ curl -i http://localhost:8080/api/recent/failure

HTTP/1.1 200 OK
date: Fri, 30 Jan 2026 22:10:30 GMT
server: uvicorn
content-length: 16
content-type: application/json

{"failure":null}
```

✅ **All console endpoints returning 200 OK**

---

## Summary

**Before Fix:**
- Console endpoints: 500 Internal Server Error
- Control plane missing `/v1/events/recent` endpoint (old image)
- UI panels showing "Error loading attempts"

**After Fix:**
- Console endpoints: 200 OK with data
- Control plane has `/v1/events/recent` endpoint (new image)
- UI panels loading successfully

**No Code Changes Required:**
- Console code already had correct Authorization header forwarding
- Console deployment already had correct env vars and secrets
- Control plane code already had the endpoint (just needed image rebuild)

**Action Taken:**
- Rebuilt and redeployed control plane image with latest code
- Verified all endpoints working with proper authentication
- Console UI now loads attempts, PRs, and failures correctly
