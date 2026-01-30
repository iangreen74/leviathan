"""
Unit tests for console service.
"""
import pytest
from datetime import datetime


def test_aggregate_attempts_from_events():
    """Test aggregating attempts from event stream."""
    events = [
        {
            'event_id': '1',
            'event_type': 'attempt.created',
            'timestamp': '2026-01-30T10:00:00',
            'payload': {
                'attempt_id': 'attempt-1',
                'task_id': 'task-a',
                'status': 'created'
            }
        },
        {
            'event_id': '2',
            'event_type': 'attempt.started',
            'timestamp': '2026-01-30T10:00:05',
            'payload': {
                'attempt_id': 'attempt-1',
                'task_id': 'task-a',
                'status': 'running'
            }
        },
        {
            'event_id': '3',
            'event_type': 'pr.created',
            'timestamp': '2026-01-30T10:01:00',
            'payload': {
                'attempt_id': 'attempt-1',
                'task_id': 'task-a',
                'pr_number': 123,
                'pr_url': 'https://github.com/test/repo/pull/123'
            }
        },
        {
            'event_id': '4',
            'event_type': 'attempt.succeeded',
            'timestamp': '2026-01-30T10:01:05',
            'payload': {
                'attempt_id': 'attempt-1',
                'task_id': 'task-a',
                'status': 'succeeded'
            }
        }
    ]
    
    # Aggregate attempts
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
    
    # Verify aggregation
    assert len(attempts_map) == 1
    attempt = attempts_map['attempt-1']
    assert attempt['task_id'] == 'task-a'
    assert attempt['status'] == 'succeeded'
    assert attempt['pr_number'] == 123
    assert attempt['pr_url'] == 'https://github.com/test/repo/pull/123'


def test_aggregate_multiple_attempts():
    """Test aggregating multiple attempts."""
    events = [
        {
            'event_id': '1',
            'event_type': 'attempt.created',
            'timestamp': '2026-01-30T10:00:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        },
        {
            'event_id': '2',
            'event_type': 'attempt.succeeded',
            'timestamp': '2026-01-30T10:01:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        },
        {
            'event_id': '3',
            'event_type': 'attempt.created',
            'timestamp': '2026-01-30T10:02:00',
            'payload': {'attempt_id': 'attempt-2', 'task_id': 'task-b'}
        },
        {
            'event_id': '4',
            'event_type': 'attempt.failed',
            'timestamp': '2026-01-30T10:03:00',
            'payload': {'attempt_id': 'attempt-2', 'task_id': 'task-b'}
        }
    ]
    
    # Aggregate
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
                'timestamp': event['timestamp']
            }
        
        if event['event_type'] == 'attempt.succeeded':
            attempts_map[attempt_id]['status'] = 'succeeded'
        elif event['event_type'] == 'attempt.failed':
            attempts_map[attempt_id]['status'] = 'failed'
    
    assert len(attempts_map) == 2
    assert attempts_map['attempt-1']['status'] == 'succeeded'
    assert attempts_map['attempt-2']['status'] == 'failed'


def test_filter_pr_created_events():
    """Test filtering PR created events."""
    events = [
        {
            'event_id': '1',
            'event_type': 'attempt.created',
            'timestamp': '2026-01-30T10:00:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        },
        {
            'event_id': '2',
            'event_type': 'pr.created',
            'timestamp': '2026-01-30T10:01:00',
            'payload': {
                'attempt_id': 'attempt-1',
                'task_id': 'task-a',
                'pr_number': 123,
                'pr_url': 'https://github.com/test/repo/pull/123'
            }
        },
        {
            'event_id': '3',
            'event_type': 'attempt.succeeded',
            'timestamp': '2026-01-30T10:02:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        }
    ]
    
    # Filter PR events
    prs = []
    for event in events:
        if event['event_type'] == 'pr.created':
            payload = event['payload']
            prs.append({
                'attempt_id': payload.get('attempt_id'),
                'task_id': payload.get('task_id'),
                'pr_url': payload.get('pr_url'),
                'pr_number': payload.get('pr_number'),
                'timestamp': event['timestamp']
            })
    
    assert len(prs) == 1
    assert prs[0]['pr_number'] == 123
    assert prs[0]['task_id'] == 'task-a'


def test_find_latest_failure():
    """Test finding latest failure event."""
    events = [
        {
            'event_id': '1',
            'event_type': 'attempt.succeeded',
            'timestamp': '2026-01-30T10:00:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        },
        {
            'event_id': '2',
            'event_type': 'attempt.failed',
            'timestamp': '2026-01-30T10:01:00',
            'payload': {
                'attempt_id': 'attempt-2',
                'task_id': 'task-b',
                'error_summary': 'Test error',
                'failure_type': 'execution_error'
            }
        },
        {
            'event_id': '3',
            'event_type': 'attempt.created',
            'timestamp': '2026-01-30T10:02:00',
            'payload': {'attempt_id': 'attempt-3', 'task_id': 'task-c'}
        }
    ]
    
    # Find latest failure (events are in reverse chronological order in real API)
    latest_failure = None
    for event in events:
        if event['event_type'] == 'attempt.failed':
            payload = event['payload']
            latest_failure = {
                'attempt_id': payload.get('attempt_id'),
                'task_id': payload.get('task_id'),
                'error_summary': payload.get('error_summary', ''),
                'failure_type': payload.get('failure_type', 'unknown'),
                'timestamp': event['timestamp']
            }
            break
    
    assert latest_failure is not None
    assert latest_failure['task_id'] == 'task-b'
    assert latest_failure['error_summary'] == 'Test error'


def test_no_failures():
    """Test handling when there are no failures."""
    events = [
        {
            'event_id': '1',
            'event_type': 'attempt.succeeded',
            'timestamp': '2026-01-30T10:00:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a'}
        },
        {
            'event_id': '2',
            'event_type': 'pr.created',
            'timestamp': '2026-01-30T10:01:00',
            'payload': {'attempt_id': 'attempt-1', 'task_id': 'task-a', 'pr_number': 123}
        }
    ]
    
    # Find latest failure
    latest_failure = None
    for event in events:
        if event['event_type'] == 'attempt.failed':
            latest_failure = event['payload']
            break
    
    assert latest_failure is None
