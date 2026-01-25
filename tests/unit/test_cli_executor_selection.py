"""
Unit tests for CLI executor selection.
"""
import pytest
import sys
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import the main module
from leviathan.control_plane.__main__ import main


class TestCLIExecutorSelection:
    """Test CLI argparse and executor selection."""
    
    def test_argparse_accepts_k8s_executor(self):
        """Should accept 'k8s' as valid executor choice."""
        with patch('sys.argv', ['prog', '--target', 'test', '--executor', 'k8s', '--once']):
            with patch('leviathan.control_plane.__main__.resolve_target_config') as mock_resolve:
                with patch('leviathan.control_plane.__main__.EventStore'):
                    with patch('leviathan.control_plane.__main__.GraphStore'):
                        with patch('leviathan.control_plane.__main__.ArtifactStore'):
                            with patch('leviathan.control_plane.__main__.K8sExecutor') as mock_k8s:
                                with patch('leviathan.control_plane.__main__.Scheduler') as mock_scheduler:
                                    # Mock target config
                                    mock_resolve.return_value = {'name': 'test'}
                                    
                                    # Mock scheduler to avoid actual execution
                                    mock_scheduler_instance = MagicMock()
                                    mock_scheduler_instance.run_once.return_value = True
                                    mock_scheduler.return_value = mock_scheduler_instance
                                    
                                    # Run main (expect sys.exit(0))
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()
                                    
                                    assert exc_info.value.code == 0
                                    
                                    # Verify K8sExecutor was instantiated
                                    mock_k8s.assert_called_once()
                                    call_kwargs = mock_k8s.call_args[1]
                                    assert call_kwargs['namespace'] == 'leviathan'
                                    assert 'artifact_store' in call_kwargs
    
    def test_argparse_accepts_k8s_stub_executor(self):
        """Should accept 'k8s-stub' as valid executor choice."""
        with patch('sys.argv', ['prog', '--target', 'test', '--executor', 'k8s-stub', '--once']):
            with patch('leviathan.control_plane.__main__.resolve_target_config') as mock_resolve:
                with patch('leviathan.control_plane.__main__.EventStore'):
                    with patch('leviathan.control_plane.__main__.GraphStore'):
                        with patch('leviathan.control_plane.__main__.ArtifactStore'):
                            with patch('leviathan.control_plane.__main__.K8sExecutorStub') as mock_stub:
                                with patch('leviathan.control_plane.__main__.Scheduler') as mock_scheduler:
                                    # Mock target config
                                    mock_resolve.return_value = {'name': 'test'}
                                    
                                    # Mock scheduler
                                    mock_scheduler_instance = MagicMock()
                                    mock_scheduler_instance.run_once.return_value = True
                                    mock_scheduler.return_value = mock_scheduler_instance
                                    
                                    # Run main (expect sys.exit(0))
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()
                                    
                                    assert exc_info.value.code == 0
                                    
                                    # Verify K8sExecutorStub was instantiated
                                    mock_stub.assert_called_once()
    
    def test_argparse_accepts_local_executor(self):
        """Should accept 'local' as valid executor choice (default)."""
        with patch('sys.argv', ['prog', '--target', 'test', '--executor', 'local', '--once']):
            with patch('leviathan.control_plane.__main__.resolve_target_config') as mock_resolve:
                with patch('leviathan.control_plane.__main__.EventStore'):
                    with patch('leviathan.control_plane.__main__.GraphStore'):
                        with patch('leviathan.control_plane.__main__.ArtifactStore'):
                            with patch('leviathan.control_plane.__main__.LocalWorktreeExecutor') as mock_local:
                                with patch('leviathan.control_plane.__main__.Scheduler') as mock_scheduler:
                                    # Mock target config
                                    mock_resolve.return_value = {'name': 'test'}
                                    
                                    # Mock scheduler
                                    mock_scheduler_instance = MagicMock()
                                    mock_scheduler_instance.run_once.return_value = True
                                    mock_scheduler.return_value = mock_scheduler_instance
                                    
                                    # Run main (expect sys.exit(0))
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()
                                    
                                    assert exc_info.value.code == 0
                                    
                                    # Verify LocalWorktreeExecutor was instantiated
                                    mock_local.assert_called_once()
    
    def test_argparse_rejects_invalid_executor(self):
        """Should reject invalid executor choice."""
        with patch('sys.argv', ['prog', '--target', 'test', '--executor', 'invalid', '--once']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            # argparse exits with code 2 for invalid arguments
            assert exc_info.value.code == 2
    
    def test_k8s_executor_instantiation_with_namespace(self):
        """Should instantiate K8sExecutor with correct namespace."""
        with patch('sys.argv', ['prog', '--target', 'test', '--executor', 'k8s', '--once']):
            with patch('leviathan.control_plane.__main__.resolve_target_config') as mock_resolve:
                with patch('leviathan.control_plane.__main__.EventStore'):
                    with patch('leviathan.control_plane.__main__.GraphStore'):
                        with patch('leviathan.control_plane.__main__.ArtifactStore') as mock_artifact_store:
                            with patch('leviathan.control_plane.__main__.K8sExecutor') as mock_k8s:
                                with patch('leviathan.control_plane.__main__.Scheduler') as mock_scheduler:
                                    # Mock target config
                                    mock_resolve.return_value = {'name': 'test'}
                                    
                                    # Mock artifact store instance
                                    artifact_store_instance = MagicMock()
                                    mock_artifact_store.return_value = artifact_store_instance
                                    
                                    # Mock scheduler
                                    mock_scheduler_instance = MagicMock()
                                    mock_scheduler_instance.run_once.return_value = True
                                    mock_scheduler.return_value = mock_scheduler_instance
                                    
                                    # Run main (expect sys.exit(0))
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()
                                    
                                    assert exc_info.value.code == 0
                                    
                                    # Verify K8sExecutor was called with correct args
                                    mock_k8s.assert_called_once_with(
                                        namespace='leviathan',
                                        artifact_store=artifact_store_instance
                                    )
    
    def test_executor_choices_in_help(self):
        """Should show all executor choices in help text."""
        with patch('sys.argv', ['prog', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                with patch('sys.stdout') as mock_stdout:
                    main()
            
            # Help exits with code 0
            assert exc_info.value.code == 0
    
    def test_default_executor_is_local(self):
        """Should default to local executor when not specified."""
        with patch('sys.argv', ['prog', '--target', 'test', '--once']):
            with patch('leviathan.control_plane.__main__.resolve_target_config') as mock_resolve:
                with patch('leviathan.control_plane.__main__.EventStore'):
                    with patch('leviathan.control_plane.__main__.GraphStore'):
                        with patch('leviathan.control_plane.__main__.ArtifactStore'):
                            with patch('leviathan.control_plane.__main__.LocalWorktreeExecutor') as mock_local:
                                with patch('leviathan.control_plane.__main__.Scheduler') as mock_scheduler:
                                    # Mock target config
                                    mock_resolve.return_value = {'name': 'test'}
                                    
                                    # Mock scheduler
                                    mock_scheduler_instance = MagicMock()
                                    mock_scheduler_instance.run_once.return_value = True
                                    mock_scheduler.return_value = mock_scheduler_instance
                                    
                                    # Run main (expect sys.exit(0))
                                    with pytest.raises(SystemExit) as exc_info:
                                        main()
                                    
                                    assert exc_info.value.code == 0
                                    
                                    # Verify LocalWorktreeExecutor was instantiated (default)
                                    mock_local.assert_called_once()
