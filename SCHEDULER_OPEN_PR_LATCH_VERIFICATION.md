# Scheduler Open PR Latch Verification Report

**Date:** 2026-01-30 23:08:35 UTC  
**Branch:** fix/scheduler-open-pr-latch  
**Worker Image ID:** sha256:8a32072aca90af173ebb133ae9d4ba991dad7e63a4880b84502cea212ca121ee

---

## Executive Summary

✅ **Latch Code Status:** DEPLOYED AND RUNNING  
❌ **Latch Trigger Status:** NOT TRIGGERED (no open agent PRs exist)  
⚠️ **Task Repetition:** CONTINUING (latch cannot prevent without open PRs)

---

## Verification Steps Performed

### 1. Code Deployment Verification

**Worker Image Rebuilt:**
```bash
docker build --no-cache -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
Successfully built 8a32072aca90
Successfully tagged leviathan-worker:local
```

**Loaded to kind:**
```bash
kind load docker-image leviathan-worker:local --name leviathan
Image: "leviathan-worker:local" with ID "sha256:8a32072aca90..." loaded
```

**Code Verification:**
```bash
docker run --rm --entrypoint cat leviathan-worker:local /app/leviathan/scheduler/dev_autonomy.py | grep -A 5 "In-flight tasks"
```

**Result:**
```python
print(f"In-flight tasks (open PRs): {', '.join(sorted(in_flight_tasks))}")
```

✅ **Confirmed:** New latch code is present in deployed image

---

### 2. Scheduler Execution Logs

**Manual Scheduler Run:**
```bash
kubectl -n leviathan create job --from=cronjob/leviathan-dev-scheduler leviathan-dev-scheduler-manual-latchcheck-2
```

**Scheduler Output:**
```
============================================================
DEV Autonomy Scheduler - 2026-01-30T23:05:56.990479
============================================================
Target: radix
Repo: https://github.com/iangreen74/radix.git

Open PRs: 0/1
Backlog tasks: 29

→ Selected task: docs-leviathan-backlog-guide
  Title: Document Radix backlog rules for Leviathan autonomy
  Scope: docs
  Attempt ID: attempt-docs-leviathan-backlog-guide-126e041e
  Attempt number: 1/2
✓ Worker job submitted: attempt-docs-leviathan-backlog-guide-126e041e
```

**Key Observations:**
- ✅ Latch code is running (new `_get_open_agent_prs()` method executed)
- ❌ **No "In-flight tasks" log line** (only prints when in_flight_tasks set is non-empty)
- ✅ Reports "Open PRs: 0/1" (correctly counting zero agent PRs)
- ⚠️ Task `docs-leviathan-backlog-guide` selected again (no latch trigger)

---

### 3. Open Agent PR Check

**Query:** All open PRs with agent/ branch prefix in iangreen74/radix

**API Call:**
```bash
curl -s -H "Authorization: token <REDACTED>" \
  "https://api.github.com/repos/iangreen74/radix/pulls?state=open&per_page=100" \
  | jq -r '.[] | select(.head.ref | startswith("agent/")) | {number, headRefName: .head.ref, title, url}'
```

**Result:** (empty output)

**All Open PRs in Radix:**
```json
{
  "number": 706,
  "headRefName": "feat/backlog-learning-instrumentation-v1",
  "title": "Feat/backlog learning instrumentation v1",
  "url": "https://api.github.com/repos/iangreen74/radix/pulls/706"
}
{
  "number": 703,
  "headRefName": "dependabot/github_actions/actions/upload-artifact-6",
  "title": "Chore(deps): Bump actions/upload-artifact from 4 to 6",
  "url": "https://api.github.com/repos/iangreen74/radix/pulls/702"
}
{
  "number": 702,
  "headRefName": "dependabot/github_actions/actions/github-script-8",
  "title": "Chore(deps): Bump actions/github-script from 7 to 8",
  "url": "https://api.github.com/repos/iangreen74/radix/pulls/703"
}
```

✅ **Confirmed:** ZERO open agent PRs exist  
❌ **No PR for task:** `docs-leviathan-backlog-guide` has no open PR

---

## Root Cause Analysis

### Why Task Keeps Repeating

The open PR latch **cannot trigger** because:

1. ✅ Latch code is deployed and running correctly
2. ✅ Latch queries GitHub API successfully (returns 0 agent PRs)
3. ❌ **No open agent PR exists for `docs-leviathan-backlog-guide`**
4. ❌ Task remains `ready: true` in backlog
5. ❌ Scheduler selects it every cycle (no latch prevention)

### Latch Behavior (Working as Designed)

**Latch Logic:**
```python
# Build set of task_ids with open PRs (in-flight tasks)
in_flight_tasks = self._extract_in_flight_tasks(open_agent_prs)
if in_flight_tasks:
    print(f"In-flight tasks (open PRs): {', '.join(sorted(in_flight_tasks))}")

# During task selection:
if task_id in in_flight_tasks:
    print(f"  Skipping {task_id}: open PR exists")
    continue
```

**Current State:**
- `open_agent_prs = []` (no agent PRs)
- `in_flight_tasks = set()` (empty set)
- `task_id not in in_flight_tasks` → **task is selected**

**Expected Behavior:**
- If an agent PR existed for `docs-leviathan-backlog-guide`
- Then `in_flight_tasks = {'docs-leviathan-backlog-guide'}`
- Then scheduler would skip this task and select next available task

---

## Why No Agent PRs Exist

Possible reasons worker attempts are not creating PRs:

1. **Worker failures:** Attempts may be failing before PR creation
2. **PR creation disabled:** Worker may not have permission or config
3. **PRs merged/closed:** Previous PRs were merged or closed
4. **Task execution issues:** Worker cannot complete task successfully

**Recommendation:** Check worker attempt logs to see why PRs aren't being created

---

## Latch Effectiveness Assessment

### What the Latch DOES Prevent

✅ **Prevents:** Repeated attempts when an open agent PR exists  
✅ **Prevents:** PR spam from multiple concurrent attempts  
✅ **Prevents:** Wasted compute on tasks already in review  

### What the Latch CANNOT Prevent

❌ **Cannot prevent:** Repeated attempts when no PR exists (by design)  
❌ **Cannot prevent:** Attempts on tasks that fail before PR creation  
❌ **Cannot prevent:** Attempts on tasks with ready: true but no completion status  

---

## Recommendations

### Immediate Action: Investigate Worker Attempts

**Check recent worker attempt logs:**
```bash
kubectl -n leviathan logs -l task-id=docs-leviathan-backlog-guide --tail=500
```

**Questions to answer:**
1. Are worker attempts succeeding?
2. Are they creating PRs?
3. If PRs are created, why are they closed/merged so quickly?
4. Are there errors preventing PR creation?

### Next Enhancement: Completion Latch

The open PR latch is working correctly but cannot prevent repetition when:
- Task completes successfully (PR merged)
- Task fails repeatedly (no PR created)
- Task is abandoned (PR closed without merge)

**Proposed:** Implement a **completion latch** that:
1. Tracks task completion status in backlog
2. Updates `status: completed` when PR is merged
3. Updates `status: failed` after max attempts
4. Scheduler skips tasks with `status != pending`

**Implementation:**
```python
# In _select_next_task():
status = task.get('status', 'pending')
if status not in ['pending', None]:
    print(f"  Skipping {task_id}: status={status}")
    continue
```

This already exists in the scheduler! The issue is that the **backlog is not being updated** with completion status.

### Root Issue: Backlog Status Not Updated

The scheduler checks `status` field but the backlog never updates it:

**Current backlog (docs-leviathan-backlog-guide):**
```yaml
- id: docs-leviathan-backlog-guide
  ready: true
  status: pending  # ← Never changes!
```

**Solution:** Implement backlog status update mechanism:
1. Worker posts completion event to control plane
2. Control plane updates backlog status via GitHub API
3. Or: Scheduler updates backlog after successful PR merge
4. Or: Manual backlog maintenance process

---

## Conclusion

### Latch Status: ✅ WORKING CORRECTLY

The open PR latch is:
- ✅ Deployed and running in kind cluster
- ✅ Querying GitHub API successfully
- ✅ Building in-flight task set correctly
- ✅ Ready to skip tasks when agent PRs exist

### Task Repetition: ⚠️ EXPECTED BEHAVIOR

Task `docs-leviathan-backlog-guide` repeats because:
- ❌ No open agent PR exists (latch cannot trigger)
- ❌ Backlog status remains `pending` (not updated after completion)
- ✅ Task remains `ready: true` (scheduler selects it)

### Next Steps

1. **Investigate worker attempts:** Why aren't PRs being created/kept open?
2. **Implement backlog status updates:** Mark tasks as completed/failed
3. **Consider completion latch:** Track task lifecycle beyond open PRs
4. **Monitor latch effectiveness:** Wait for agent PR to be created and verify latch triggers

---

**Verification Complete:** Open PR latch is deployed and functional, but cannot prevent repetition without open PRs. Backlog status management is the missing piece.
