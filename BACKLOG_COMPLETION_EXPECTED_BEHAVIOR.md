# Backlog Completion Writeback - Expected Behavior

**Feature:** Durable backlog status management  
**Branch:** feat/backlog-completion-writeback-v1  
**PR:** https://github.com/iangreen74/leviathan/pull/new/feat/backlog-completion-writeback-v1

---

## What This Fixes

**Problem:** Tasks with `ready: true` and `status: pending` are selected repeatedly by the scheduler, even after successful PR creation and merge, leading to:
- Infinite reruns of the same task
- PR spam
- Wasted compute resources
- No true autonomy (system never "completes" work)

**Root Cause:** Backlog status is never updated after task execution. The scheduler checks `status` field but it always remains `pending`.

**Solution:** Worker updates the target repo's `.leviathan/backlog.yaml` in the same PR to mark the task as completed.

---

## How It Works

### Execution Flow

1. **Scheduler selects task** with `ready: true` and `status: pending`
2. **Worker clones target repo** and executes task
3. **Worker marks task completed** in `.leviathan/backlog.yaml`:
   ```yaml
   - id: docs-leviathan-backlog-guide
     status: completed        # ← Changed from 'pending'
     ready: false            # ← Changed from 'true'
     last_attempt_id: attempt-docs-leviathan-backlog-guide-abc123
     branch_name: agent/task-exec-attempt-abc123
     pr_number: null         # ← Set after PR creation (or in PR body)
     completed_at: 2026-01-30T23:15:00.123456
   ```
4. **Worker commits** both task changes AND backlog update
5. **Worker creates PR** with all changes
6. **PR merges to main**
7. **Scheduler fetches updated backlog** on next cycle
8. **Scheduler skips task** (status: completed, ready: false)

---

## Expected Behavior in kind

### Before Deployment

**Scheduler logs:**
```
Open PRs: 0/1
Backlog tasks: 29

→ Selected task: docs-leviathan-backlog-guide
  Attempt ID: attempt-docs-leviathan-backlog-guide-abc123
✓ Worker job submitted
```

**Radix backlog (.leviathan/backlog.yaml):**
```yaml
- id: docs-leviathan-backlog-guide
  ready: true
  status: pending
```

**Behavior:** Task selected every 5 minutes (infinite loop)

### After Deployment

**Worker logs (first successful execution):**
```
Executing task: docs-leviathan-backlog-guide
✓ Task executed successfully
  Changed files: docs/LEVIATHAN_BACKLOG.md
✓ Marked task as completed in backlog
✓ Created branch: agent/task-exec-attempt-abc123
✓ Committed changes: 1a2b3c4d
✓ Pushed branch: agent/task-exec-attempt-abc123
✓ Created PR #707: https://github.com/iangreen74/radix/pull/707
✅ Worker Complete
```

**PR #707 changes:**
```diff
+ docs/LEVIATHAN_BACKLOG.md (task execution changes)

.leviathan/backlog.yaml:
- id: docs-leviathan-backlog-guide
-  ready: true
-  status: pending
+  ready: false
+  status: completed
+  last_attempt_id: attempt-docs-leviathan-backlog-guide-abc123
+  branch_name: agent/task-exec-attempt-abc123
+  pr_number: null
+  completed_at: 2026-01-30T23:15:00.123456
```

**After PR merges:**

**Scheduler logs (next cycle):**
```
Open PRs: 0/1
Backlog tasks: 29

  Skipping docs-leviathan-backlog-guide: status=completed
→ Selected task: next-available-task
  Attempt ID: attempt-next-available-task-def456
✓ Worker job submitted
```

**Behavior:** Task skipped, scheduler moves to next task ✅

---

## Edge Cases Handled

### 1. No-Op Task Execution

**Scenario:** Task execution produces no file changes (task already satisfied)

**Behavior:**
- Worker still marks task completed in backlog
- Backlog update creates a commit
- PR is created with only backlog change
- Task won't be re-selected after merge

**Why:** Prevents infinite reruns even for idempotent tasks

### 2. Task Already Completed

**Scenario:** Backlog already shows `status: completed` (race condition or manual update)

**Behavior:**
- Worker detects task is completed
- Exits without creating duplicate PR
- Posts `attempt.succeeded` event
- Logs: "Task already marked completed in backlog"

**Why:** Prevents duplicate PRs for already-completed tasks

### 3. Task Not Found in Backlog

**Scenario:** Task ID doesn't exist in backlog (data inconsistency)

**Behavior:**
- Worker logs warning: "Task {task_id} not found in backlog for status update"
- Continues with task execution
- Creates PR without backlog update
- Task may be re-selected (degraded mode)

**Why:** Fail gracefully, don't block task execution

### 4. PR Number Unknown at Commit Time

**Scenario:** PR number only known after GitHub API call

**Behavior:**
- Worker sets `pr_number: null` in backlog initially
- Creates PR with backlog showing null
- PR number is recorded in control plane events
- Future enhancement: Update backlog in follow-up commit or PR body

**Why:** Can't know PR number before creating PR

---

## Verification Steps

### 1. Build and Deploy Worker Image

```bash
cd /home/ian/leviathan
docker build --no-cache -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
kind load docker-image leviathan-worker:local --name leviathan
```

### 2. Trigger Manual Scheduler Run

```bash
kubectl -n leviathan delete job -l app=leviathan-scheduler --ignore-not-found=true
kubectl -n leviathan create job --from=cronjob/leviathan-dev-scheduler leviathan-scheduler-manual-backlog-test
```

### 3. Monitor Worker Execution

```bash
# Wait for worker job to start
kubectl -n leviathan get jobs -l task-id=docs-leviathan-backlog-guide

# Check worker logs
kubectl -n leviathan logs -l task-id=docs-leviathan-backlog-guide --tail=100
```

**Expected log line:**
```
✓ Marked task as completed in backlog
```

### 4. Verify PR Created

```bash
# Check for new agent PR
curl -s -H "Authorization: token <GITHUB_TOKEN>" \
  "https://api.github.com/repos/iangreen74/radix/pulls?state=open&per_page=10" \
  | jq -r '.[] | select(.head.ref | startswith("agent/")) | {number, title, url}'
```

**Expected:** New PR with backlog update included

### 5. Check PR Diff

Navigate to PR URL and verify:
- Task execution changes (e.g., `docs/LEVIATHAN_BACKLOG.md`)
- Backlog update in `.leviathan/backlog.yaml`:
  - `status: completed`
  - `ready: false`
  - `last_attempt_id: <attempt_id>`
  - `completed_at: <timestamp>`

### 6. Merge PR (Manual)

Merge the PR to main in Radix repo

### 7. Verify Scheduler Skips Task

```bash
# Trigger another scheduler run
kubectl -n leviathan create job --from=cronjob/leviathan-dev-scheduler leviathan-scheduler-manual-verify

# Check scheduler logs
kubectl -n leviathan logs -l app=leviathan-scheduler --tail=50
```

**Expected log line:**
```
Skipping docs-leviathan-backlog-guide: status=completed
```

**Expected behavior:** Scheduler selects a different task

---

## Success Criteria

✅ Worker marks task completed in backlog  
✅ Backlog update included in PR  
✅ PR merges successfully  
✅ Scheduler skips completed task on next cycle  
✅ Scheduler selects next available task  
✅ No infinite reruns  

---

## Rollback Plan

If issues occur:

1. **Revert worker image:**
   ```bash
   git checkout feat/kustomize-bundles-and-console-image-v1
   docker build -f ops/docker/worker.Dockerfile -t leviathan-worker:local .
   kind load docker-image leviathan-worker:local --name leviathan
   ```

2. **Manual backlog fix (if needed):**
   - Edit `.leviathan/backlog.yaml` in Radix
   - Set task `status: pending` and `ready: true`
   - Commit and push to main

---

## Future Enhancements

1. **Update PR number in backlog:** After PR creation, update backlog with actual PR number
2. **Backlog sync service:** Automated service to sync backlog status with PR state
3. **Completion events:** Post `task.completed` event to control plane for analytics
4. **Backlog validation:** Ensure backlog status matches PR/merge state

---

**Status:** Ready for deployment and verification in kind cluster
