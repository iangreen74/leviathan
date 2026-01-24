"""
Executor abstraction for running attempts.

Executors implement the strategy for running task attempts:
- LocalWorktreeExecutor: runs in local git worktree
- K8sExecutor: submits Kubernetes Job (future)
"""
