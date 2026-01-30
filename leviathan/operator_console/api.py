"""
Leviathan Operator Console API.

Minimal FastAPI service for observability dashboard.
Proxies control plane and spider endpoints.
"""
import os
from typing import Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
import uvicorn


app = FastAPI(title="Leviathan Console", version="1.0.0")

# Configuration
CONTROL_PLANE_URL = os.getenv('CONTROL_PLANE_URL', 'http://leviathan-control-plane:8000')
CONTROL_PLANE_TOKEN = os.getenv('CONTROL_PLANE_TOKEN', '')
SPIDER_URL = os.getenv('SPIDER_URL', 'http://leviathan-spider:8001')


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the console dashboard."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Leviathan Operator Console</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            font-size: 28px;
            margin-bottom: 10px;
            color: #58a6ff;
        }
        .subtitle {
            color: #8b949e;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 20px;
        }
        .card h2 {
            font-size: 18px;
            margin-bottom: 15px;
            color: #58a6ff;
            border-bottom: 1px solid #21262d;
            padding-bottom: 10px;
        }
        .status-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .status-enabled { background: #238636; color: #fff; }
        .status-disabled { background: #da3633; color: #fff; }
        .status-running { background: #1f6feb; color: #fff; }
        .status-succeeded { background: #238636; color: #fff; }
        .status-failed { background: #da3633; color: #fff; }
        .attempt-list {
            list-style: none;
            max-height: 400px;
            overflow-y: auto;
        }
        .attempt-item {
            padding: 12px;
            margin-bottom: 8px;
            background: #0d1117;
            border: 1px solid #21262d;
            border-radius: 4px;
        }
        .attempt-item:hover {
            border-color: #58a6ff;
        }
        .attempt-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 6px;
        }
        .attempt-id {
            font-family: 'Courier New', monospace;
            font-size: 12px;
            color: #8b949e;
        }
        .attempt-task {
            font-weight: 600;
            color: #c9d1d9;
            margin-bottom: 4px;
        }
        .attempt-time {
            font-size: 11px;
            color: #6e7681;
        }
        .pr-link {
            color: #58a6ff;
            text-decoration: none;
            font-size: 12px;
        }
        .pr-link:hover {
            text-decoration: underline;
        }
        .error-box {
            background: #1c1917;
            border: 1px solid #da3633;
            border-radius: 4px;
            padding: 12px;
            margin-top: 8px;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            color: #ffa198;
            max-height: 200px;
            overflow-y: auto;
        }
        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
        }
        .metric-row:last-child {
            border-bottom: none;
        }
        .metric-label {
            color: #8b949e;
            font-size: 13px;
        }
        .metric-value {
            font-weight: 600;
            color: #58a6ff;
        }
        .loading {
            text-align: center;
            padding: 40px;
            color: #6e7681;
        }
        .refresh-btn {
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .refresh-btn:hover {
            background: #30363d;
            border-color: #58a6ff;
        }
        .header-controls {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .last-update {
            color: #6e7681;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Leviathan Operator Console</h1>
        <p class="subtitle">Real-time observability for autonomous task execution</p>
        
        <div class="header-controls">
            <button class="refresh-btn" onclick="loadAll()">🔄 Refresh</button>
            <span class="last-update" id="lastUpdate">Loading...</span>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Autonomy Status</h2>
                <div id="autonomyStatus" class="loading">Loading...</div>
            </div>

            <div class="card">
                <h2>Graph Summary</h2>
                <div id="graphSummary" class="loading">Loading...</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>Recent Attempts</h2>
                <ul id="recentAttempts" class="attempt-list">
                    <li class="loading">Loading...</li>
                </ul>
            </div>

            <div class="card">
                <h2>Recent PRs</h2>
                <ul id="recentPRs" class="attempt-list">
                    <li class="loading">Loading...</li>
                </ul>
            </div>
        </div>

        <div class="card">
            <h2>Latest Failure</h2>
            <div id="latestFailure" class="loading">Loading...</div>
        </div>
    </div>

    <script>
        async function loadAutonomyStatus() {
            try {
                const resp = await fetch('/api/autonomy/status');
                const data = await resp.json();
                
                const badge = data.autonomy_enabled 
                    ? '<span class="status-badge status-enabled">ENABLED</span>'
                    : '<span class="status-badge status-disabled">DISABLED</span>';
                
                document.getElementById('autonomyStatus').innerHTML = `
                    <div class="metric-row">
                        <span class="metric-label">Status</span>
                        <span>${badge}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Source</span>
                        <span class="metric-value">${data.source}</span>
                    </div>
                `;
            } catch (e) {
                document.getElementById('autonomyStatus').innerHTML = 
                    '<div style="color: #da3633;">Error loading status</div>';
            }
        }

        async function loadGraphSummary() {
            try {
                const resp = await fetch('/api/graph/summary');
                const data = await resp.json();
                
                let html = '<div>';
                for (const [type, count] of Object.entries(data.nodes_by_type)) {
                    html += `
                        <div class="metric-row">
                            <span class="metric-label">${type} nodes</span>
                            <span class="metric-value">${count}</span>
                        </div>
                    `;
                }
                html += '</div>';
                
                document.getElementById('graphSummary').innerHTML = html;
            } catch (e) {
                document.getElementById('graphSummary').innerHTML = 
                    '<div style="color: #da3633;">Error loading summary</div>';
            }
        }

        async function loadRecentAttempts() {
            try {
                const resp = await fetch('/api/recent/attempts');
                const attempts = await resp.json();
                
                if (attempts.length === 0) {
                    document.getElementById('recentAttempts').innerHTML = 
                        '<li class="attempt-item">No attempts yet</li>';
                    return;
                }
                
                let html = '';
                for (const att of attempts) {
                    const statusBadge = att.status === 'succeeded' 
                        ? '<span class="status-badge status-succeeded">SUCCEEDED</span>'
                        : att.status === 'failed'
                        ? '<span class="status-badge status-failed">FAILED</span>'
                        : '<span class="status-badge status-running">RUNNING</span>';
                    
                    const prLink = att.pr_url 
                        ? `<a href="${att.pr_url}" target="_blank" class="pr-link">PR #${att.pr_number}</a>`
                        : '';
                    
                    html += `
                        <li class="attempt-item">
                            <div class="attempt-header">
                                <span class="attempt-task">${att.task_id}</span>
                                ${statusBadge}
                            </div>
                            <div class="attempt-id">${att.attempt_id}</div>
                            <div class="attempt-time">${new Date(att.timestamp).toLocaleString()}</div>
                            ${prLink ? '<div style="margin-top: 6px;">' + prLink + '</div>' : ''}
                        </li>
                    `;
                }
                
                document.getElementById('recentAttempts').innerHTML = html;
            } catch (e) {
                document.getElementById('recentAttempts').innerHTML = 
                    '<li class="attempt-item" style="color: #da3633;">Error loading attempts</li>';
            }
        }

        async function loadRecentPRs() {
            try {
                const resp = await fetch('/api/recent/prs');
                const prs = await resp.json();
                
                if (prs.length === 0) {
                    document.getElementById('recentPRs').innerHTML = 
                        '<li class="attempt-item">No PRs yet</li>';
                    return;
                }
                
                let html = '';
                for (const pr of prs) {
                    html += `
                        <li class="attempt-item">
                            <div class="attempt-header">
                                <span class="attempt-task">${pr.task_id}</span>
                                <a href="${pr.pr_url}" target="_blank" class="pr-link">PR #${pr.pr_number}</a>
                            </div>
                            <div class="attempt-id">${pr.attempt_id}</div>
                            <div class="attempt-time">${new Date(pr.timestamp).toLocaleString()}</div>
                        </li>
                    `;
                }
                
                document.getElementById('recentPRs').innerHTML = html;
            } catch (e) {
                document.getElementById('recentPRs').innerHTML = 
                    '<li class="attempt-item" style="color: #da3633;">Error loading PRs</li>';
            }
        }

        async function loadLatestFailure() {
            try {
                const resp = await fetch('/api/recent/failure');
                const data = await resp.json();
                
                if (!data.failure) {
                    document.getElementById('latestFailure').innerHTML = 
                        '<div style="color: #238636;">No recent failures ✓</div>';
                    return;
                }
                
                const f = data.failure;
                document.getElementById('latestFailure').innerHTML = `
                    <div class="metric-row">
                        <span class="metric-label">Task</span>
                        <span class="metric-value">${f.task_id}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Attempt</span>
                        <span class="metric-value">${f.attempt_id}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Time</span>
                        <span class="metric-value">${new Date(f.timestamp).toLocaleString()}</span>
                    </div>
                    <div class="error-box">${f.error_summary || 'No error details'}</div>
                `;
            } catch (e) {
                document.getElementById('latestFailure').innerHTML = 
                    '<div style="color: #da3633;">Error loading failure</div>';
            }
        }

        async function loadAll() {
            document.getElementById('lastUpdate').textContent = 'Refreshing...';
            
            await Promise.all([
                loadAutonomyStatus(),
                loadGraphSummary(),
                loadRecentAttempts(),
                loadRecentPRs(),
                loadLatestFailure()
            ]);
            
            document.getElementById('lastUpdate').textContent = 
                'Last updated: ' + new Date().toLocaleTimeString();
        }

        // Initial load
        loadAll();
        
        // Auto-refresh every 30 seconds
        setInterval(loadAll, 30000);
    </script>
</body>
</html>
"""


@app.get("/api/autonomy/status")
async def get_autonomy_status():
    """Proxy autonomy status from control plane."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{CONTROL_PLANE_URL}/v1/autonomy/status",
                headers={'Authorization': f'Bearer {CONTROL_PLANE_TOKEN}'},
                timeout=10.0
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/graph/summary")
async def get_graph_summary():
    """Proxy graph summary from control plane."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{CONTROL_PLANE_URL}/v1/graph/summary",
                headers={'Authorization': f'Bearer {CONTROL_PLANE_TOKEN}'},
                timeout=10.0
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recent/attempts")
async def get_recent_attempts():
    """Get recent attempts aggregated from events."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{CONTROL_PLANE_URL}/v1/events/recent?limit=200",
                headers={'Authorization': f'Bearer {CONTROL_PLANE_TOKEN}'},
                timeout=10.0
            )
            resp.raise_for_status()
            events = resp.json()
            
            # Group events by attempt_id
            attempts_map = {}
            for event in events:
                payload = event.get('payload', {})
                attempt_id = payload.get('attempt_id')
                if not attempt_id:
                    continue
                
                if attempt_id not in attempts_map:
                    attempts_map[attempt_id] = {
                        'attempt_id': attempt_id,
                        'task_id': payload.get('task_id', 'unknown'),
                        'status': 'running',
                        'timestamp': event['timestamp'],
                        'pr_url': None,
                        'pr_number': None
                    }
                
                # Update with latest info
                if event['event_type'] == 'attempt.succeeded':
                    attempts_map[attempt_id]['status'] = 'succeeded'
                elif event['event_type'] == 'attempt.failed':
                    attempts_map[attempt_id]['status'] = 'failed'
                
                if event['event_type'] == 'pr.created':
                    attempts_map[attempt_id]['pr_url'] = payload.get('pr_url')
                    attempts_map[attempt_id]['pr_number'] = payload.get('pr_number')
            
            # Sort by timestamp descending
            attempts = sorted(attempts_map.values(), 
                            key=lambda x: x['timestamp'], 
                            reverse=True)
            
            return attempts[:20]  # Return last 20
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recent/prs")
async def get_recent_prs():
    """Get recent PRs from events."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{CONTROL_PLANE_URL}/v1/events/recent?limit=200",
                headers={'Authorization': f'Bearer {CONTROL_PLANE_TOKEN}'},
                timeout=10.0
            )
            resp.raise_for_status()
            events = resp.json()
            
            # Filter pr.created events
            prs = []
            for event in events:
                if event['event_type'] == 'pr.created':
                    payload = event['payload']
                    prs.append({
                        'attempt_id': payload.get('attempt_id', 'unknown'),
                        'task_id': payload.get('task_id', 'unknown'),
                        'pr_url': payload.get('pr_url'),
                        'pr_number': payload.get('pr_number'),
                        'timestamp': event['timestamp']
                    })
            
            # Sort by timestamp descending
            prs.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return prs[:15]  # Return last 15
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recent/failure")
async def get_latest_failure():
    """Get latest failure from events."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{CONTROL_PLANE_URL}/v1/events/recent?limit=200",
                headers={'Authorization': f'Bearer {CONTROL_PLANE_TOKEN}'},
                timeout=10.0
            )
            resp.raise_for_status()
            events = resp.json()
            
            # Find most recent attempt.failed event
            for event in events:
                if event['event_type'] == 'attempt.failed':
                    payload = event['payload']
                    return {
                        'failure': {
                            'attempt_id': payload.get('attempt_id', 'unknown'),
                            'task_id': payload.get('task_id', 'unknown'),
                            'error_summary': payload.get('error_summary', ''),
                            'failure_type': payload.get('failure_type', 'unknown'),
                            'timestamp': event['timestamp']
                        }
                    }
            
            return {'failure': None}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/healthz")
async def healthz():
    """Health check endpoint."""
    return {"status": "ok"}


def main():
    """Run the console server."""
    port = int(os.getenv('PORT', '8080'))
    uvicorn.run(
        "leviathan.operator_console.api:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()
