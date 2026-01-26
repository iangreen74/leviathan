#!/usr/bin/env python3
"""
leviathanctl - Leviathan Control Plane Operator CLI

Query and operate Leviathan control plane via API.
"""
import argparse
import os
import sys
import json
from typing import Optional, Dict, Any
import requests


class LeviathanCLI:
    """Leviathan control plane CLI client."""
    
    def __init__(self, api_url: str, token: str):
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
    
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make GET request to API."""
        url = f"{self.api_url}{path}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def _post(self, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make POST request to API."""
        url = f"{self.api_url}{path}"
        response = self.session.post(url, json=data)
        response.raise_for_status()
        return response.json()
    
    def graph_summary(self) -> None:
        """Display graph summary statistics."""
        data = self._get('/v1/graph/summary')
        
        print("Graph Summary")
        print("=" * 50)
        print(f"Total Nodes: {data.get('total_nodes', 0)}")
        print(f"Total Edges: {data.get('total_edges', 0)}")
        print()
        
        if 'node_types' in data:
            print("Node Types:")
            for node_type, count in data['node_types'].items():
                print(f"  {node_type}: {count}")
            print()
        
        if 'edge_types' in data:
            print("Edge Types:")
            for edge_type, count in data['edge_types'].items():
                print(f"  {edge_type}: {count}")
    
    def attempts_list(self, target: Optional[str] = None, limit: int = 10) -> None:
        """List recent attempts."""
        params = {'limit': limit}
        if target:
            params['target'] = target
        
        data = self._get('/v1/attempts', params=params)
        attempts = data.get('attempts', [])
        
        if not attempts:
            print("No attempts found.")
            return
        
        print(f"Recent Attempts (limit: {limit})")
        print("=" * 80)
        
        for attempt in attempts:
            attempt_id = attempt.get('attempt_id', 'unknown')
            task_id = attempt.get('task_id', 'unknown')
            target_name = attempt.get('target', 'unknown')
            status = attempt.get('status', 'unknown')
            timestamp = attempt.get('timestamp', 'unknown')
            
            print(f"Attempt: {attempt_id}")
            print(f"  Task: {task_id}")
            print(f"  Target: {target_name}")
            print(f"  Status: {status}")
            print(f"  Timestamp: {timestamp}")
            
            if 'pr_url' in attempt:
                print(f"  PR: {attempt['pr_url']}")
            
            print()
    
    def attempts_show(self, attempt_id: str) -> None:
        """Show detailed information about an attempt."""
        data = self._get(f'/v1/attempts/{attempt_id}')
        
        print(f"Attempt Details: {attempt_id}")
        print("=" * 80)
        print(json.dumps(data, indent=2))
    
    def failures_recent(self, target: Optional[str] = None, limit: int = 10) -> None:
        """List recent failures."""
        params = {'limit': limit}
        if target:
            params['target'] = target
        
        data = self._get('/v1/failures', params=params)
        failures = data.get('failures', [])
        
        if not failures:
            print("No failures found.")
            return
        
        print(f"Recent Failures (limit: {limit})")
        print("=" * 80)
        
        for failure in failures:
            attempt_id = failure.get('attempt_id', 'unknown')
            task_id = failure.get('task_id', 'unknown')
            target_name = failure.get('target', 'unknown')
            error = failure.get('error', 'unknown')
            timestamp = failure.get('timestamp', 'unknown')
            
            print(f"Attempt: {attempt_id}")
            print(f"  Task: {task_id}")
            print(f"  Target: {target_name}")
            print(f"  Error: {error}")
            print(f"  Timestamp: {timestamp}")
            print()
    
    def invalidate_attempt(self, attempt_id: str, reason: str) -> None:
        """Invalidate an attempt."""
        data = self._post(f'/v1/attempts/{attempt_id}/invalidate', {'reason': reason})
        
        print(f"Invalidated attempt: {attempt_id}")
        print(f"Reason: {reason}")
        print(f"Status: {data.get('status', 'unknown')}")
    
    def backlog_suggest(self, target: str) -> None:
        """
        Generate and propose backlog tasks for a target.
        
        Creates a PR with proposed tasks based on bootstrap artifacts.
        """
        # Trigger backlog suggestion via API
        data = self._post('/v1/backlog/suggest', {
            'target': target
        })
        
        print(f"Backlog Suggestion for {target}")
        print("=" * 80)
        print(f"Status: {data.get('status', 'unknown')}")
        
        if 'attempt_id' in data:
            print(f"Attempt ID: {data['attempt_id']}")
        
        if 'pr_url' in data:
            print(f"PR URL: {data['pr_url']}")
        
        if 'tasks_proposed' in data:
            print(f"Tasks Proposed: {data['tasks_proposed']}")
        
        if 'message' in data:
            print(f"\n{data['message']}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Leviathan Control Plane Operator CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--api-url',
        default=os.environ.get('LEVIATHAN_API_URL', 'http://localhost:8000'),
        help='Control plane API URL (default: $LEVIATHAN_API_URL or http://localhost:8000)'
    )
    
    parser.add_argument(
        '--token',
        default=os.environ.get('LEVIATHAN_CONTROL_PLANE_TOKEN'),
        help='Control plane authentication token (default: $LEVIATHAN_CONTROL_PLANE_TOKEN)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # graph summary
    subparsers.add_parser('graph-summary', help='Display graph summary statistics')
    
    # attempts list
    attempts_list_parser = subparsers.add_parser('attempts-list', help='List recent attempts')
    attempts_list_parser.add_argument('--target', help='Filter by target name')
    attempts_list_parser.add_argument('--limit', type=int, default=10, help='Number of attempts to show (default: 10)')
    
    # attempts show
    attempts_show_parser = subparsers.add_parser('attempts-show', help='Show detailed attempt information')
    attempts_show_parser.add_argument('attempt_id', help='Attempt ID to show')
    
    # failures recent
    failures_parser = subparsers.add_parser('failures-recent', help='List recent failures')
    failures_parser.add_argument('--target', help='Filter by target name')
    failures_parser.add_argument('--limit', type=int, default=10, help='Number of failures to show (default: 10)')
    
    # invalidate
    invalidate_parser = subparsers.add_parser('invalidate', help='Invalidate an attempt')
    invalidate_parser.add_argument('attempt_id', help='Attempt ID to invalidate')
    invalidate_parser.add_argument('--reason', required=True, help='Reason for invalidation')
    
    # backlog-suggest
    backlog_suggest_parser = subparsers.add_parser('backlog-suggest', help='Generate backlog task proposals for a target')
    backlog_suggest_parser.add_argument('target', help='Target name (e.g., radix)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if not args.token:
        print("Error: LEVIATHAN_CONTROL_PLANE_TOKEN not set", file=sys.stderr)
        print("Set via --token or LEVIATHAN_CONTROL_PLANE_TOKEN environment variable", file=sys.stderr)
        sys.exit(1)
    
    cli = LeviathanCLI(args.api_url, args.token)
    
    try:
        if args.command == 'graph-summary':
            cli.graph_summary()
        elif args.command == 'attempts-list':
            cli.attempts_list(target=args.target, limit=args.limit)
        elif args.command == 'attempts-show':
            cli.attempts_show(args.attempt_id)
        elif args.command == 'failures-recent':
            cli.failures_recent(target=args.target, limit=args.limit)
        elif args.command == 'invalidate':
            cli.invalidate_attempt(args.attempt_id, args.reason)
        elif args.command == 'backlog-suggest':
            cli.backlog_suggest(args.target)
        else:
            parser.print_help()
            sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"API Error: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
