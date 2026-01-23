#!/usr/bin/env python3
"""
Leviathan Kanban Dashboard Generator

Reads agent_backlog.yaml and state.db to generate a markdown dashboard
showing MVP progress and task status.
"""
import os
import sys
import yaml
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


def load_backlog(backlog_path: Path) -> Dict[str, Any]:
    """Load agent backlog YAML."""
    with open(backlog_path, 'r') as f:
        return yaml.safe_load(f)


def load_state_db(db_path: Path) -> Optional[sqlite3.Connection]:
    """Load SQLite state database if it exists."""
    if not db_path.exists():
        return None
    return sqlite3.connect(db_path)


def get_task_counts(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count tasks by status."""
    counts = {
        'ready': 0,
        'in_progress': 0,
        'pr_opened': 0,
        'completed': 0,
        'blocked': 0,
        'not_ready': 0
    }
    
    for task in tasks:
        status = task.get('status', '')
        ready = task.get('ready', False)
        
        if status == 'completed':
            counts['completed'] += 1
        elif status == 'pr_opened':
            counts['pr_opened'] += 1
        elif status == 'blocked':
            counts['blocked'] += 1
        elif ready:
            counts['ready'] += 1
        else:
            counts['not_ready'] += 1
    
    return counts


def get_recent_executions(conn: Optional[sqlite3.Connection], limit: int = 25) -> List[Dict[str, Any]]:
    """Get recent task executions from state DB."""
    if not conn:
        return []
    
    cursor = conn.cursor()
    cursor.execute('''
        SELECT task_id, status, pr_number, pr_url, timestamp
        FROM task_executions
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    return [
        {
            'task_id': row[0],
            'status': row[1],
            'pr_number': row[2],
            'pr_url': row[3],
            'timestamp': row[4]
        }
        for row in rows
    ]


def get_ready_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get tasks that are ready to work on."""
    ready = []
    for task in tasks:
        if task.get('ready', False) and task.get('status', '') not in ['completed', 'pr_opened']:
            ready.append({
                'id': task['id'],
                'title': task['title'],
                'scope': task['scope'],
                'priority': task.get('priority', 'medium')
            })
    return ready


def get_blocked_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Get tasks that are blocked."""
    blocked = []
    for task in tasks:
        if task.get('status', '') == 'blocked':
            blocked.append({
                'id': task['id'],
                'title': task['title'],
                'depends_on': task.get('dependencies', [])
            })
    return blocked


def get_open_prs_from_github() -> Optional[List[Dict[str, Any]]]:
    """Fetch open PRs from GitHub API if token available."""
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        return None
    
    try:
        import requests
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.get(
            'https://api.github.com/repos/iangreen74/radix/pulls?state=open',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            prs = response.json()
            return [
                {
                    'number': pr['number'],
                    'title': pr['title'],
                    'branch': pr['head']['ref'],
                    'url': pr['html_url']
                }
                for pr in prs
            ]
    except Exception:
        pass
    
    return None


def generate_dashboard(backlog_path: Path, state_db_path: Path, output_path: Path):
    """Generate Kanban dashboard markdown."""
    
    # Load data
    backlog = load_backlog(backlog_path)
    tasks = backlog.get('tasks', [])
    max_open_prs = backlog.get('max_open_prs', 2)
    
    conn = load_state_db(state_db_path)
    
    # Compute stats
    counts = get_task_counts(tasks)
    recent_executions = get_recent_executions(conn, limit=25)
    ready_tasks = get_ready_tasks(tasks)
    blocked_tasks = get_blocked_tasks(tasks)
    open_prs = get_open_prs_from_github()
    
    # Generate markdown
    timestamp = datetime.utcnow().isoformat() + 'Z'
    
    md = f"""# Leviathan Kanban Dashboard

**Generated:** {timestamp}

---

## Summary

| Status | Count |
|--------|-------|
| ✅ Completed | {counts['completed']} |
| 🚀 PR Open | {counts['pr_opened']} / {max_open_prs} (capacity) |
| 🔄 Ready | {counts['ready']} |
| 🚫 Blocked | {counts['blocked']} |
| ⏸️  Not Ready | {counts['not_ready']} |

**Total Tasks:** {len(tasks)}

---

## Open PRs

"""
    
    if open_prs is None:
        md += "_GitHub token not available. Set GITHUB_TOKEN to fetch open PRs._\n\n"
    elif len(open_prs) == 0:
        md += "_No open PRs_\n\n"
    else:
        md += "| # | Title | Branch |\n"
        md += "|---|-------|--------|\n"
        for pr in open_prs:
            md += f"| [{pr['number']}]({pr['url']}) | {pr['title']} | `{pr['branch']}` |\n"
        md += "\n"
    
    md += "---\n\n## Ready Tasks\n\n"
    
    if len(ready_tasks) == 0:
        md += "_No tasks ready_\n\n"
    else:
        md += "| ID | Title | Scope | Priority |\n"
        md += "|----|-------|-------|----------|\n"
        for task in ready_tasks:
            md += f"| `{task['id']}` | {task['title']} | {task['scope']} | {task['priority']} |\n"
        md += "\n"
    
    md += "---\n\n## Blocked Tasks\n\n"
    
    if len(blocked_tasks) == 0:
        md += "_No blocked tasks_\n\n"
    else:
        md += "| ID | Title | Depends On |\n"
        md += "|----|-------|------------|\n"
        for task in blocked_tasks:
            deps = ', '.join(f"`{d}`" for d in task['depends_on']) if task['depends_on'] else '_none_'
            md += f"| `{task['id']}` | {task['title']} | {deps} |\n"
        md += "\n"
    
    md += "---\n\n## Recent Executions (Last 25)\n\n"
    
    if len(recent_executions) == 0:
        if conn is None:
            md += "_State database not found at `~/.leviathan/state.db`_\n\n"
        else:
            md += "_No executions recorded yet_\n\n"
    else:
        md += "| Task ID | Status | PR | Timestamp |\n"
        md += "|---------|--------|----|-----------|\n"
        for exec in recent_executions:
            pr_link = f"[#{exec['pr_number']}]({exec['pr_url']})" if exec['pr_number'] else '_n/a_'
            ts = exec['timestamp'][:19] if exec['timestamp'] else '_n/a_'
            md += f"| `{exec['task_id']}` | {exec['status']} | {pr_link} | {ts} |\n"
        md += "\n"
    
    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(md)
    
    if conn:
        conn.close()
    
    print(f"✅ Dashboard generated: {output_path}")


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent.parent
    
    backlog_path = repo_root / 'docs/reports/agent_backlog.yaml'
    state_db_path = Path.home() / '.leviathan/state.db'
    output_path = Path.home() / '.leviathan/dashboard/LEVIATHAN_KANBAN.md'
    
    if not backlog_path.exists():
        print(f"❌ Backlog not found: {backlog_path}")
        sys.exit(1)
    
    generate_dashboard(backlog_path, state_db_path, output_path)
    print(f"\n📊 Dashboard written to: {output_path}")


if __name__ == '__main__':
    main()
