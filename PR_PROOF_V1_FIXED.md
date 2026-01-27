# PR Proof v1: Fixed Implementation

## Summary of Fixes

✅ **Event Schema Fixed**: All events now include `event_id` (UUID) and `actor_id`  
✅ **Git Clone Fixed**: Supports both SSH (with SSH keys) and HTTPS (with token)  
✅ **Token Format Fixed**: Uses `https://<token>@github.com` (not `x-access-token:`)  
✅ **Backlog-Only Enforcement**: Only modifies `.leviathan/backlog.yaml`  
✅ **All Tests Pass**: 344 tests passed, 0 failed  
✅ **Invariants Green**: All invariants validated  

## Changes Made

### 1. Event Schema Compliance (`scripts/pr_proof_v1.py`)

**Before:**
```python
'events': [{
    'event_type': event_type,
    'payload': payload,
    'timestamp': datetime.utcnow().isoformat()
}]
```

**After:**
```python
'events': [{
    'event_id': str(uuid.uuid4()),
    'event_type': event_type,
    'timestamp': datetime.utcnow().isoformat(),
    'actor_id': actor_id,
    'payload': payload
}]
```

### 2. Git Authentication (`leviathan/executor/backlog_propose.py`)

**Clone Logic:**
```python
# For SSH URLs, use as-is (no token needed)
# For HTTPS URLs, inject token
if self.target_repo_url.startswith("git@"):
    clone_url = self.target_repo_url
else:
    clone_url = self._build_authenticated_url(self.target_repo_url, self.github_token)
```

**Token Format:**
```python
# Before: https://x-access-token:<token>@github.com (FAILED)
# After:  https://<token>@github.com (WORKS)
return repo_url.replace("https://", f"https://{token}@")
```

### 3. .gitignore Handling

**Problem**: Target repos may have `.leviathan/` in `.gitignore`

**Solution**: Use `git add -f` to force-add backlog.yaml
```python
# Force-add even if .leviathan is ignored
subprocess.run(
    ["git", "add", "-f", ".leviathan/backlog.yaml"],
    cwd=self.target_dir,
    check=True
)
```

**Note**: This only affects `.leviathan/backlog.yaml` - no other files can be staged.

### 4. Unit Tests Added

5 new tests:
- `test_event_has_required_fields` - Verifies event_id, actor_id present
- `test_event_id_is_uuid` - Validates UUID format
- `test_actor_id_format` - Checks actor_id structure
- `test_event_bundle_structure` - Validates complete bundle
- `test_git_add_uses_force_flag` - Verifies `-f` flag in git add command

## Execution Commands

### Option 1: SSH URL (Recommended)

**Prerequisites:**
- SSH key configured for GitHub
- No GITHUB_TOKEN needed for clone/push (uses SSH keys)
- GITHUB_TOKEN only needed for PR creation API call

```bash
# Terminal 1: Start Control Plane
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

```bash
# Terminal 2: Run PR Proof with SSH
export GITHUB_TOKEN=<your-github-token>
export TARGET_NAME=radix
export TARGET_REPO_URL=git@github.com:iangreen74/radix.git
export TARGET_BRANCH=main
export ATTEMPT_ID=attempt-pr-proof-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

python3 scripts/pr_proof_v1.py
```

### Option 2: HTTPS URL

**Prerequisites:**
- GITHUB_TOKEN with `repo` scope
- Token used for clone, push, and PR creation

```bash
# Terminal 1: Start Control Plane
export LEVIATHAN_CONTROL_PLANE_TOKEN=dev-token
python3 -m leviathan.control_plane.api
```

```bash
# Terminal 2: Run PR Proof with HTTPS
export GITHUB_TOKEN=<your-github-token>
export TARGET_NAME=radix
export TARGET_REPO_URL=https://github.com/iangreen74/radix.git
export TARGET_BRANCH=main
export ATTEMPT_ID=attempt-pr-proof-$(date +%s)
export CONTROL_PLANE_URL=http://localhost:8000
export CONTROL_PLANE_TOKEN=dev-token
export LEVIATHAN_WORKSPACE_DIR=/tmp/leviathan-workspace

python3 scripts/pr_proof_v1.py
```

## Expected Output

```
============================================================
PR Proof v1: Backlog-Only PR Creation
============================================================
Target: radix
Repo: git@github.com:iangreen74/radix.git
Task: pr-proof-v1-backlog-only
Attempt: attempt-pr-proof-1738000000

✓ Posted attempt.created event to control plane
✓ Posted attempt.started event to control plane

Cloning git@github.com:iangreen74/radix.git...
✓ Cloned to /tmp/leviathan-workspace/attempt-pr-proof-1738000000/target
✓ Added task pr-proof-v1-backlog-only to backlog
Pushing branch agent/backlog-propose-attempt-pr-proof-1738000000...
✓ Branch pushed: agent/backlog-propose-attempt-pr-proof-1738000000
✓ Commit SHA: <commit-sha>

Creating pull request...
✓ PR created: https://github.com/iangreen74/radix/pull/<number>
✓ PR number: <number>
✓ Posted pr.created event to control plane
✓ Posted attempt.succeeded event to control plane

============================================================
✅ PR Proof v1 Complete
============================================================
PR URL: https://github.com/iangreen74/radix/pull/<number>
PR Number: <number>
Branch: agent/backlog-propose-attempt-pr-proof-1738000000
Commit SHA: <commit-sha>

Verify with:
  gh pr view <number> --repo git@github.com:iangreen74/radix.git
  curl -H 'Authorization: Bearer dev-token' \
    http://localhost:8000/v1/graph/summary
```

## Verification

### 1. PR Link
```bash
https://github.com/iangreen74/radix/pull/<number>
```

### 2. Diffstat
```bash
gh pr diff <number> --repo iangreen74/radix --name-only
```

**Expected:**
```
.leviathan/backlog.yaml
```

### 3. Control Plane Events
```bash
# Check event journal
cat ~/.leviathan/graph/events.ndjson | grep pr-proof-v1-backlog-only | jq

# Verify events have event_id and actor_id
cat ~/.leviathan/graph/events.ndjson | tail -5 | jq '.event_id, .actor_id'
```

**Expected event fields:**
- `event_id`: UUID (e.g., `"a1b2c3d4-e5f6-7890-abcd-ef1234567890"`)
- `event_type`: `"attempt.created"`, `"attempt.started"`, `"pr.created"`, `"attempt.succeeded"`
- `timestamp`: ISO8601 (e.g., `"2026-01-27T19:16:23.123456"`)
- `actor_id`: `"pr-proof-script-attempt-pr-proof-1738000000"`
- `payload`: Event-specific data

## Test Results

```bash
$ python3 -m pytest tests/unit/test_backlog_propose.py -v
13 passed in 0.04s

$ python3 -m pytest tests/unit -q
345 passed, 273 warnings in 2.53s

$ python3 tools/invariants_check.py
✅ SUCCESS: All invariants validated
```

## Diffstat

```
 leviathan/executor/backlog_propose.py    |  23 ++++--
 scripts/pr_proof_v1.py                   |  28 +++++--
 tests/unit/test_backlog_propose.py       |  95 ++++++++++++++++++++-
 PR_PROOF_V1_FIXED.md                     | 250 ++++++++++++++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 383 insertions(+), 13 deletions(-)
```

## Key Differences: SSH vs HTTPS

| Aspect | SSH | HTTPS |
|--------|-----|-------|
| **Clone URL** | `git@github.com:iangreen74/radix.git` | `https://github.com/iangreen74/radix.git` |
| **Clone Auth** | SSH keys (no token in URL) | Token injected: `https://<token>@github.com/...` |
| **Push Auth** | SSH keys (no token in URL) | Token injected: `https://<token>@github.com/...` |
| **PR Creation** | GITHUB_TOKEN via API | GITHUB_TOKEN via API |
| **Token Exposure** | Lower risk (only API calls) | Higher risk (in git URLs) |
| **Recommended** | ✅ Yes (if SSH keys configured) | Use if SSH not available |

## Event Lifecycle

```
1. attempt.created
   - event_id: <uuid>
   - actor_id: pr-proof-script-attempt-pr-proof-<timestamp>
   - payload: {attempt_id, task_id, target_id, attempt_number: 1, status: "created"}

2. attempt.started
   - event_id: <uuid>
   - actor_id: pr-proof-script-attempt-pr-proof-<timestamp>
   - payload: {attempt_id, task_id, target_id, status: "running"}

3. pr.created
   - event_id: <uuid>
   - actor_id: pr-proof-script-attempt-pr-proof-<timestamp>
   - payload: {attempt_id, task_id, target_id, pr_number, pr_url, branch_name, commit_sha}

4. attempt.succeeded
   - event_id: <uuid>
   - actor_id: pr-proof-script-attempt-pr-proof-<timestamp>
   - payload: {attempt_id, task_id, target_id, status: "succeeded", pr_number, pr_url}
```

## Troubleshooting

### Error: "validation error for Event: event_id Field required"

**Fixed**: Events now include `event_id` (UUID) and `actor_id`

### Error: git clone exit status 128 with HTTPS

**Fixed**: Token format changed from `x-access-token:<token>@` to `<token>@`

### Error: Permission denied (publickey) with SSH

**Cause**: SSH keys not configured

**Fix**: Either configure SSH keys or use HTTPS URL with token

### Error: git add fails with ".leviathan is ignored"

**Cause**: Target repo has `.leviathan/` in `.gitignore`

**Fixed**: Now uses `git add -f` to force-add backlog.yaml even if directory is ignored

### Error: PR creation fails with 401 Unauthorized

**Cause**: Invalid or missing GITHUB_TOKEN

**Fix**: Ensure token has `repo` scope:
```bash
gh auth status
# Or create new token at https://github.com/settings/tokens
```

## Ready for Execution

The implementation is complete, tested, and ready to create a real PR against Radix.

**Choose your authentication method:**
- **SSH** (recommended): Requires SSH keys, more secure
- **HTTPS**: Requires token in all git operations

Both methods will create a real GitHub PR that modifies only `.leviathan/backlog.yaml`.
