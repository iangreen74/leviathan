"""
Console output and status display for Leviathan runner.
"""
from typing import Optional
from datetime import datetime


class Console:
    """Handles console output with formatting."""
    
    @staticmethod
    def header(text: str):
        """Print a header."""
        print(f"\n{'=' * 70}")
        print(f"  {text}")
        print(f"{'=' * 70}\n")
    
    @staticmethod
    def section(text: str):
        """Print a section header."""
        print(f"\n{'─' * 70}")
        print(f"  {text}")
        print(f"{'─' * 70}")
    
    @staticmethod
    def info(text: str):
        """Print info message."""
        print(f"ℹ️  {text}")
    
    @staticmethod
    def success(text: str):
        """Print success message."""
        print(f"✅ {text}")
    
    @staticmethod
    def warning(text: str):
        """Print warning message."""
        print(f"⚠️  {text}")
    
    @staticmethod
    def error(text: str):
        """Print error message."""
        print(f"❌ {text}")
    
    @staticmethod
    def task_info(task_id: str, title: str, scope: str, priority: str, size: str):
        """Print task information."""
        print(f"\n📋 Task: {task_id}")
        print(f"   Title: {title}")
        print(f"   Scope: {scope}")
        print(f"   Priority: {priority}")
        print(f"   Size: {size}")
    
    @staticmethod
    def task_details(allowed_paths: list, acceptance_criteria: list):
        """Print task details."""
        print(f"\n📁 Allowed paths:")
        for path in allowed_paths:
            print(f"   - {path}")
        
        print(f"\n✓ Acceptance criteria:")
        for i, criterion in enumerate(acceptance_criteria, 1):
            print(f"   {i}. {criterion}")
    
    @staticmethod
    def step(step_num: int, total_steps: int, description: str):
        """Print step progress."""
        print(f"\n[{step_num}/{total_steps}] {description}")
    
    @staticmethod
    def timestamp():
        """Print current timestamp."""
        print(f"\n🕐 {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    @staticmethod
    def capacity_status(open_prs: int, max_prs: int):
        """Print capacity status."""
        if open_prs >= max_prs:
            Console.warning(f"Capacity reached: {open_prs}/{max_prs} PRs open")
        else:
            Console.info(f"Capacity available: {open_prs}/{max_prs} PRs open")
    
    @staticmethod
    def pr_created(pr_number: Optional[int], pr_url: str):
        """Print PR creation status."""
        if pr_number:
            Console.success(f"PR #{pr_number} created: {pr_url}")
        else:
            Console.info(f"PR creation URL: {pr_url}")
    
    @staticmethod
    def ci_status(status: str, details: Optional[str] = None):
        """Print CI status."""
        if status == 'pending':
            print(f"⏳ CI checks pending...")
        elif status == 'success':
            Console.success("CI checks passed")
        elif status == 'failure':
            Console.error(f"CI checks failed: {details}")
        else:
            Console.info(f"CI status: {status}")
