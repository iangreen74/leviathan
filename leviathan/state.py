#!/usr/bin/env python3
"""
SQLite-based persistent state storage for Leviathan.

Stores task execution history, PR tracking, and error logs.
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List


class LeviathanState:
    """Manages persistent state in SQLite."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize state manager.
        
        Args:
            db_path: Path to SQLite database (default: ~/.leviathan/state.db)
        """
        if db_path is None:
            db_path = Path.home() / '.leviathan' / 'state.db'
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Task executions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS task_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                pr_number INTEGER,
                pr_url TEXT,
                branch_name TEXT,
                ci_status TEXT,
                error_class TEXT,
                error_message TEXT,
                metadata TEXT
            )
        ''')
        
        # Create index for faster lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_task_id 
            ON task_executions(task_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON task_executions(timestamp DESC)
        ''')
        
        conn.commit()
        conn.close()
    
    def record_task_execution(
        self,
        task_id: str,
        status: str,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        ci_status: Optional[str] = None,
        error_class: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record a task execution.
        
        Args:
            task_id: Task identifier
            status: Execution status (started, completed, failed, pr_opened, etc.)
            pr_number: PR number if created
            pr_url: PR URL if created
            branch_name: Git branch name
            ci_status: CI check status (pending, success, failure)
            error_class: Error class name if failed
            error_message: Error message if failed
            metadata: Additional metadata as dict
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.utcnow().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        
        cursor.execute('''
            INSERT INTO task_executions 
            (task_id, status, timestamp, pr_number, pr_url, branch_name, 
             ci_status, error_class, error_message, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id, status, timestamp, pr_number, pr_url, branch_name,
            ci_status, error_class, error_message, metadata_json
        ))
        
        conn.commit()
        conn.close()
    
    def get_task_history(self, task_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get execution history for a task.
        
        Args:
            task_id: Task identifier
            limit: Maximum number of records to return
            
        Returns:
            List of execution records (newest first)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_executions 
            WHERE task_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (task_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            record = dict(row)
            if record['metadata']:
                record['metadata'] = json.loads(record['metadata'])
            results.append(record)
        
        return results
    
    def get_recent_executions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent task executions.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of execution records (newest first)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_executions 
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            record = dict(row)
            if record['metadata']:
                record['metadata'] = json.loads(record['metadata'])
            results.append(record)
        
        return results
    
    def get_failed_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent failed task executions.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of failed execution records (newest first)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM task_executions 
            WHERE status = 'failed' OR error_class IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            record = dict(row)
            if record['metadata']:
                record['metadata'] = json.loads(record['metadata'])
            results.append(record)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics.
        
        Returns:
            Dictionary with stats (total_executions, success_count, failure_count, etc.)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total executions
        cursor.execute('SELECT COUNT(*) FROM task_executions')
        total = cursor.fetchone()[0]
        
        # By status
        cursor.execute('''
            SELECT status, COUNT(*) as count 
            FROM task_executions 
            GROUP BY status
        ''')
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Recent failures
        cursor.execute('''
            SELECT COUNT(*) FROM task_executions 
            WHERE (status = 'failed' OR error_class IS NOT NULL)
            AND timestamp > datetime('now', '-7 days')
        ''')
        recent_failures = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_executions': total,
            'status_counts': status_counts,
            'recent_failures_7d': recent_failures
        }
