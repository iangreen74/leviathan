# Leviathan

**Autonomous AI Agent for Repository Management**

Leviathan is an autonomous AI agent that executes tasks from a backlog, creates PRs, and manages repository workflows. It operates on target repositories via a contract-based interface.

## Architecture

- **Control Plane**: Orchestrator that reads target contracts, selects tasks, and coordinates execution
- **Executor Backends**: Pluggable backends for different execution environments
  - WorktreeExecutor: Git worktree-based execution (default)
  - K8sJobExecutor: Kubernetes job-based execution (future)
- **Target Contract**: Each target repository defines its own contract, backlog, and policies

## Quick Start

### Prerequisites

- Python 3.10+
- Git
- GitHub CLI (`gh`) authenticated
- Claude API key (set in `~/.leviathan/env`)

### Installation

```bash
# Clone repository
git clone git@github.com:iangreen74/leviathan.git
cd leviathan

# Install dependencies
pip install -r requirements.txt

# Configure target
mkdir -p ~/.leviathan/targets
cp examples/target-radix.yaml ~/.leviathan/targets/radix.yaml
# Edit ~/.leviathan/targets/radix.yaml with your settings

# Configure environment
cp ops/systemd/env.example ~/.leviathan/env
# Edit ~/.leviathan/env with your API keys
```

### Running Leviathan

```bash
# Dry run (shows next task without executing)
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml --dry-run

# Execute one task
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml --once

# Continuous mode (daemon)
python -m leviathan.runner --target ~/.leviathan/targets/radix.yaml
```

### Systemd Service (Node A)

```bash
# Install service
cp ops/systemd/leviathan.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable leviathan
systemctl --user start leviathan

# Check status
systemctl --user status leviathan
journalctl --user -u leviathan -f
```

## Target Contract

Each target repository must provide:

1. **`.leviathan/contract.yaml`** - Repository metadata and configuration
2. **`.leviathan/backlog.yaml`** - Task backlog with priorities and dependencies
3. **`.leviathan/policy.yaml`** - Allowed paths per scope and invariants

See `docs/TARGET_CONTRACT.md` for details.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [Target Contract](docs/TARGET_CONTRACT.md) - Contract format specification
- [Runbook Node A](docs/RUNBOOK_NODE_A.md) - Production deployment guide
- [Development](docs/DEVELOPMENT.md) - Contributing and testing

## Security

- Never commits secrets to repositories
- Uses environment files for sensitive configuration
- Operates in ephemeral worktrees (no persistent state in target repos)
- All actions logged with timestamps for auditability

## License

MIT License - See LICENSE file
