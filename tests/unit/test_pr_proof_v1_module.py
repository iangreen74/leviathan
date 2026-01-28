"""
Unit tests for PR Proof v1 module entrypoint.

Tests the leviathan.executor.pr_proof_v1 module without network calls.
"""
import pytest
import tempfile
import shutil
import uuid
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from leviathan.executor.pr_proof_v1.__main__ import main, post_event_to_control_plane


class TestPRProofV1Module:
    """Test PR Proof v1 module entrypoint."""
    
    def test_module_requires_env_vars(self):
        """Should fail if required env vars are missing."""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1
    
    def test_post_event_includes_required_fields(self):
        """Posted events should include event_id, actor_id, timestamp."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = Mock(status_code=200)
            
            post_event_to_control_plane(
                event_type='attempt.created',
                payload={'attempt_id': 'test-123', 'task_id': 'task-456', 'target_id': 'radix'},
                control_plane_url='http://localhost:8000',
                token='test-token',
                actor_id='pr-proof-worker-test-123'
            )
            
            # Verify request was made
            assert mock_post.called
            call_args = mock_post.call_args
            
            # Check bundle structure
            bundle = call_args[1]['json']
            assert 'events' in bundle
            assert len(bundle['events']) == 1
            
            event = bundle['events'][0]
            assert 'event_id' in event
            assert 'event_type' in event
            assert 'timestamp' in event
            assert 'actor_id' in event
            assert 'payload' in event
            
            # Verify event_id is UUID
            uuid.UUID(event['event_id'])
            
            # Verify actor_id
            assert event['actor_id'] == 'pr-proof-worker-test-123'
    
    def test_module_main_with_mocked_execution(self):
        """Test full execution flow with mocked dependencies."""
        env_vars = {
            'GITHUB_TOKEN': 'test-token',
            'TARGET_NAME': 'radix',
            'TARGET_REPO_URL': 'https://github.com/test/repo.git',
            'TARGET_BRANCH': 'main',
            'ATTEMPT_ID': 'attempt-test-123',
            'CONTROL_PLANE_URL': 'http://localhost:8000',
            'CONTROL_PLANE_TOKEN': 'cp-token',
            'LEVIATHAN_WORKSPACE_DIR': '/tmp/test-workspace'
        }
        
        with patch.dict('os.environ', env_vars):
            with patch('requests.post') as mock_post:
                mock_post.return_value = Mock(status_code=200)
                
                with patch('leviathan.executor.pr_proof_v1.__main__.BacklogProposer') as mock_proposer:
                    # Mock proposer.propose() to return PR data
                    mock_instance = Mock()
                    mock_instance.propose.return_value = (
                        'https://github.com/test/repo/pull/1',
                        1,
                        'abc123def456'
                    )
                    mock_proposer.return_value = mock_instance
                    
                    # Run main
                    main()
                    
                    # Verify BacklogProposer was created
                    assert mock_proposer.called
                    
                    # Verify propose was called
                    assert mock_instance.propose.called
                    
                    # Verify events were posted (4 events: created, started, pr.created, succeeded)
                    assert mock_post.call_count == 4
    
    def test_module_handles_failure(self):
        """Test that failures post attempt.failed event."""
        env_vars = {
            'GITHUB_TOKEN': 'test-token',
            'TARGET_NAME': 'radix',
            'TARGET_REPO_URL': 'https://github.com/test/repo.git',
            'TARGET_BRANCH': 'main',
            'ATTEMPT_ID': 'attempt-test-456',
            'CONTROL_PLANE_URL': 'http://localhost:8000',
            'CONTROL_PLANE_TOKEN': 'cp-token',
            'LEVIATHAN_WORKSPACE_DIR': '/tmp/test-workspace'
        }
        
        with patch.dict('os.environ', env_vars):
            with patch('requests.post') as mock_post:
                mock_post.return_value = Mock(status_code=200)
                
                with patch('leviathan.executor.pr_proof_v1.__main__.BacklogProposer') as mock_proposer:
                    # Mock proposer to raise exception
                    mock_instance = Mock()
                    mock_instance.propose.side_effect = Exception("Test error")
                    mock_proposer.return_value = mock_instance
                    
                    # Run main (should exit with error)
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    
                    assert exc_info.value.code == 1
                    
                    # Verify attempt.failed was posted (3 events: created, started, failed)
                    assert mock_post.call_count == 3
                    
                    # Check last call was attempt.failed
                    last_call = mock_post.call_args_list[-1]
                    bundle = last_call[1]['json']
                    event = bundle['events'][0]
                    assert event['event_type'] == 'attempt.failed'
                    assert 'error_summary' in event['payload']
    
    def test_actor_id_format(self):
        """Actor ID should be pr-proof-worker-<attempt_id>."""
        env_vars = {
            'GITHUB_TOKEN': 'test-token',
            'TARGET_NAME': 'radix',
            'TARGET_REPO_URL': 'https://github.com/test/repo.git',
            'TARGET_BRANCH': 'main',
            'ATTEMPT_ID': 'attempt-pr-proof-k8s',
            'CONTROL_PLANE_URL': 'http://localhost:8000',
            'CONTROL_PLANE_TOKEN': 'cp-token',
            'LEVIATHAN_WORKSPACE_DIR': '/tmp/test-workspace'
        }
        
        with patch.dict('os.environ', env_vars):
            with patch('requests.post') as mock_post:
                mock_post.return_value = Mock(status_code=200)
                
                with patch('leviathan.executor.pr_proof_v1.__main__.BacklogProposer') as mock_proposer:
                    mock_instance = Mock()
                    mock_instance.propose.return_value = ('url', 1, 'sha')
                    mock_proposer.return_value = mock_instance
                    
                    main()
                    
                    # Check actor_id in first event
                    first_call = mock_post.call_args_list[0]
                    bundle = first_call[1]['json']
                    event = bundle['events'][0]
                    
                    assert event['actor_id'] == 'pr-proof-worker-attempt-pr-proof-k8s'
