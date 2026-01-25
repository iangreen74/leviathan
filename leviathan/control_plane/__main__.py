"""
CLI entrypoint for scheduler.

Usage:
    python -m leviathan.control_plane.scheduler --target radix --once
    python -m leviathan.control_plane.scheduler --target leviathan --once
    python -m leviathan.control_plane.scheduler --target /path/to/target.yaml --once
"""
import argparse
import sys
import os
import yaml
from pathlib import Path

from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.artifacts.store import ArtifactStore
from leviathan.control_plane.scheduler import Scheduler, RetryPolicy
from leviathan.executors.local_worktree import LocalWorktreeExecutor
from leviathan.executors.k8s_stub import K8sExecutorStub
from leviathan.executors.k8s_executor import K8sExecutor


def resolve_target_config(target_arg: str) -> dict:
    """
    Resolve target configuration from name or path.
    
    Args:
        target_arg: Target name (e.g., 'leviathan') or path to YAML file
        
    Returns:
        Target configuration dict
        
    Raises:
        FileNotFoundError: If target file doesn't exist
        ValueError: If target config is invalid
    """
    target_path = Path(target_arg)
    
    # Check if argument is an existing file path
    if target_path.exists() and target_path.is_file():
        config_file = target_path
    else:
        # Treat as target name, resolve to ~/.leviathan/targets/<name>.yaml
        home = Path.home()
        config_file = home / ".leviathan" / "targets" / f"{target_arg}.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Target config not found: {config_file}\n\n"
                f"To create a target config:\n"
                f"  1. mkdir -p ~/.leviathan/targets\n"
                f"  2. Create {config_file} with:\n"
                f"     name: {target_arg}\n"
                f"     repo_url: git@github.com:org/{target_arg}.git\n"
                f"     default_branch: main\n"
                f"     local_cache_dir: ~/.leviathan/targets/{target_arg}\n"
            )
    
    # Load YAML config
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    if not isinstance(config, dict):
        raise ValueError(f"Invalid target config in {config_file}: must be a YAML dict")
    
    # Ensure required fields
    if 'name' not in config:
        config['name'] = target_arg
    
    # Expand local_cache_dir if present
    if 'local_cache_dir' in config:
        cache_dir = Path(config['local_cache_dir']).expanduser()
        config['local_cache_dir'] = str(cache_dir)
        
        # Set paths to contract/backlog/policy relative to cache dir
        if 'contract_path' not in config:
            config['contract_path'] = str(cache_dir / ".leviathan" / "contract.yaml")
        if 'backlog_path' not in config:
            config['backlog_path'] = str(cache_dir / ".leviathan" / "backlog.yaml")
        if 'policy_path' not in config:
            config['policy_path'] = str(cache_dir / ".leviathan" / "policy.yaml")
    
    return config


def main():
    """Run scheduler CLI."""
    parser = argparse.ArgumentParser(description="Leviathan Graph Scheduler")
    parser.add_argument(
        "--target",
        required=True,
        help="Target identifier (e.g., 'radix')"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (default: run continuously)"
    )
    parser.add_argument(
        "--backend",
        choices=["ndjson", "postgres"],
        default="ndjson",
        help="Storage backend (default: ndjson)"
    )
    parser.add_argument(
        "--executor",
        choices=["local", "k8s", "k8s-stub"],
        default="local",
        help="Executor type: local (worktree), k8s (real K8s Jobs), k8s-stub (mock K8s)"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts per task (default: 3)"
    )
    
    args = parser.parse_args()
    
    # Resolve target configuration
    try:
        target_config = resolve_target_config(args.target)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading target config: {e}", file=sys.stderr)
        sys.exit(1)
    
    target_id = target_config.get('name', args.target)
    
    # Initialize stores
    if args.backend == "postgres":
        postgres_url = "postgresql://leviathan:leviathan_dev_password@localhost:5432/leviathan"
        event_store = EventStore(backend="postgres", postgres_url=postgres_url)
        graph_store = GraphStore(backend="postgres", postgres_url=postgres_url)
    else:
        event_store = EventStore(backend="ndjson")
        graph_store = GraphStore(backend="memory")
    
    artifact_store = ArtifactStore()
    
    # Initialize executor
    if args.executor == "k8s":
        executor = K8sExecutor(
            namespace="leviathan",
            artifact_store=artifact_store
        )
    elif args.executor == "k8s-stub":
        executor = K8sExecutorStub()
    else:
        executor = LocalWorktreeExecutor(artifact_store=artifact_store)
    
    # Initialize retry policy
    retry_policy = RetryPolicy(max_attempts_per_task=args.max_attempts)
    
    # Initialize scheduler
    scheduler = Scheduler(
        event_store=event_store,
        graph_store=graph_store,
        artifact_store=artifact_store,
        executor=executor,
        retry_policy=retry_policy
    )
    
    print(f"Leviathan Scheduler")
    print(f"Target: {target_id}")
    print(f"Backend: {args.backend}")
    print(f"Executor: {args.executor}")
    print(f"Max attempts: {args.max_attempts}")
    if 'backlog_path' in target_config:
        print(f"Backlog: {target_config['backlog_path']}")
    print()
    
    if args.once:
        # Run once and exit
        executed = scheduler.run_once(target_id, target_config)
        
        if executed:
            print("\n✅ Scheduler run completed")
            sys.exit(0)
        else:
            print("\n⚠️  No tasks ready")
            sys.exit(0)
    else:
        # Run continuously (future enhancement)
        print("Continuous mode not yet implemented")
        print("Use --once to run scheduler once")
        sys.exit(1)


if __name__ == "__main__":
    main()
