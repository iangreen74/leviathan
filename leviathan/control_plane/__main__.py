"""
CLI entrypoint for scheduler.

Usage:
    python -m leviathan.control_plane.scheduler --target radix --once
"""
import argparse
import sys
import yaml
from pathlib import Path

from leviathan.graph.events import EventStore, Event, EventType
from leviathan.graph.store import GraphStore
from leviathan.artifacts.store import ArtifactStore
from leviathan.control_plane.scheduler import Scheduler, RetryPolicy
from leviathan.executors.local_worktree import LocalWorktreeExecutor
from leviathan.executors.k8s_stub import K8sExecutorStub


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
        choices=["local", "k8s-stub"],
        default="local",
        help="Executor type (default: local)"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts per task (default: 3)"
    )
    
    args = parser.parse_args()
    
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
    if args.executor == "k8s-stub":
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
    
    # Target configuration (simplified for now)
    target_config = {
        'target_id': args.target,
        'name': args.target,
        'repo_url': f'git@github.com:iangreen74/{args.target}.git',
        'default_branch': 'main'
    }
    
    print(f"Leviathan Scheduler")
    print(f"Target: {args.target}")
    print(f"Backend: {args.backend}")
    print(f"Executor: {args.executor}")
    print(f"Max attempts: {args.max_attempts}")
    print()
    
    if args.once:
        # Run once and exit
        executed = scheduler.run_once(args.target, target_config)
        
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
