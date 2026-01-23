# Leviathan Node A Runbook

Production deployment guide for running Leviathan on Node A (Vault Hub PC).

## System Requirements

- Ubuntu/Debian Linux
- Python 3.10+
- Git 2.30+
- GitHub CLI (`gh`) authenticated
- Systemd user services enabled

## Installation

### 1. Clone Repository

```bash
cd /home/ian
git clone git@github.com:iangreen74/leviathan.git
cd leviathan
```

### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Configure Environment

```bash
mkdir -p ~/.leviathan/logs ~/.leviathan/targets

# Copy environment template
cp ops/systemd/env.example ~/.leviathan/env

# Edit with your secrets
nano ~/.leviathan/env
```

Required environment variables in `~/.leviathan/env`:
```bash
LEVIATHAN_CLAUDE_API_KEY=sk-ant-...
LEVIATHAN_CLAUDE_MODEL=claude-3-5-sonnet-latest
GITHUB_TOKEN=ghp_...
```

### 4. Configure Target

```bash
# Create target configuration
cat > ~/.leviathan/targets/radix.yaml <<EOF
name: radix
repo_url: git@github.com:iangreen74/radix.git
default_branch: main
local_cache_dir: ~/.leviathan/targets/radix
contract_path: .leviathan/contract.yaml
backlog_path: .leviathan/backlog.yaml
policy_path: .leviathan/policy.yaml
EOF
```

### 5. Install Systemd Service

```bash
# Copy service file
cp ops/systemd/leviathan.service ~/.config/systemd/user/

# Reload systemd
systemctl --user daemon-reload

# Enable service (start on boot)
systemctl --user enable leviathan

# Start service
systemctl --user start leviathan
```

## Operations

### Check Status

```bash
# Service status
systemctl --user status leviathan

# Live logs
journalctl --user -u leviathan -f

# Log file
tail -f ~/.leviathan/logs/leviathan.log
```

### Restart Service

```bash
systemctl --user restart leviathan
```

### Stop Service

```bash
systemctl --user stop leviathan
```

### Update Leviathan

```bash
# Stop service
systemctl --user stop leviathan

# Pull updates
cd /home/ian/leviathan
git pull

# Restart service
systemctl --user start leviathan
```

### Manual Execution

```bash
cd /home/ian/leviathan

# Dry run (shows next task)
python3 -m leviathan.runner \
  --target ~/.leviathan/targets/radix.yaml \
  --dry-run

# Execute one task
python3 -m leviathan.runner \
  --target ~/.leviathan/targets/radix.yaml \
  --once

# Continuous mode
python3 -m leviathan.runner \
  --target ~/.leviathan/targets/radix.yaml
```

## Monitoring

### Logs

```bash
# Systemd journal
journalctl --user -u leviathan --since "1 hour ago"

# Log file
tail -100 ~/.leviathan/logs/leviathan.log

# Follow logs
tail -f ~/.leviathan/logs/leviathan.log
```

### State Database

```bash
# View execution history
sqlite3 ~/.leviathan/state.db "SELECT * FROM executions ORDER BY timestamp DESC LIMIT 10;"

# Count executions
sqlite3 ~/.leviathan/state.db "SELECT COUNT(*) FROM executions;"
```

### Disk Usage

```bash
# Check target cache size
du -sh ~/.leviathan/targets/

# Clean old worktrees (if any leaked)
find /tmp -name "leviathan-*" -type d -mtime +1 -exec rm -rf {} \;
```

## Troubleshooting

### Service Won't Start

```bash
# Check service status
systemctl --user status leviathan

# Check logs
journalctl --user -u leviathan -n 50

# Verify environment file
cat ~/.leviathan/env

# Test manually
cd /home/ian/leviathan
python3 -m leviathan.runner --target ~/.leviathan/targets/radix.yaml --dry-run
```

### API Errors

```bash
# Check API key
grep LEVIATHAN_CLAUDE_API_KEY ~/.leviathan/env

# Test API manually
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $LEVIATHAN_CLAUDE_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-5-sonnet-latest","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'
```

### Git Errors

```bash
# Check SSH key
ssh -T git@github.com

# Check target repo access
cd ~/.leviathan/targets/radix
git fetch origin
```

### Stale Worktrees

```bash
# List worktrees
cd ~/.leviathan/targets/radix
git worktree list

# Remove stale worktree
git worktree remove /tmp/leviathan-task-id --force
```

## Security

### Secrets Management

- Never commit `~/.leviathan/env` to git
- Rotate API keys regularly
- Use GitHub fine-grained tokens with minimal scopes

### Permissions

```bash
# Secure environment file
chmod 600 ~/.leviathan/env

# Secure state database
chmod 600 ~/.leviathan/state.db
```

### Audit Trail

```bash
# View all Leviathan PRs
gh pr list --repo iangreen74/radix --author leviathan-bot

# View execution history
sqlite3 ~/.leviathan/state.db "SELECT task_id, status, timestamp FROM executions;"
```

## Maintenance

### Weekly Tasks

1. Check logs for errors
2. Review open PRs created by Leviathan
3. Verify disk usage
4. Update Leviathan if new version available

### Monthly Tasks

1. Rotate API keys
2. Clean old target caches
3. Review execution metrics
4. Update documentation

## Emergency Procedures

### Stop All Operations

```bash
systemctl --user stop leviathan
```

### Rollback Update

```bash
systemctl --user stop leviathan
cd /home/ian/leviathan
git reset --hard <previous-commit>
systemctl --user start leviathan
```

### Clean State

```bash
systemctl --user stop leviathan
rm ~/.leviathan/state.db
systemctl --user start leviathan
```

## Contact

For issues or questions, see:
- GitHub Issues: https://github.com/iangreen74/leviathan/issues
- Documentation: https://github.com/iangreen74/leviathan/tree/main/docs
