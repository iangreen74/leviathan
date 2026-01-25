"""
Unit tests for leviathanctl CLI.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from leviathan.cli.leviathanctl import LeviathanCLI


class TestLeviathanCLI:
    """Test leviathanctl CLI commands."""
    
    def setup_method(self):
        """Set up test client."""
        self.cli = LeviathanCLI(
            api_url="http://test-api:8000",
            token="test-token"
        )
    
    @patch('requests.Session.get')
    def test_graph_summary_request(self, mock_get):
        """Should make correct GET request to /v1/graph/summary."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'total_nodes': 100,
            'total_edges': 50,
            'node_types': {'task': 10, 'attempt': 20},
            'edge_types': {'EXECUTES': 15}
        }
        mock_get.return_value = mock_response
        
        self.cli.graph_summary()
        
        # Verify request
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == 'http://test-api:8000/v1/graph/summary'
        
        # Verify headers set in session
        assert self.cli.session.headers['Authorization'] == 'Bearer test-token'
    
    @patch('requests.Session.get')
    def test_attempts_list_without_filter(self, mock_get):
        """Should list attempts without target filter."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'attempts': [
                {
                    'attempt_id': 'attempt-1',
                    'task_id': 'task-1',
                    'target': 'test-target',
                    'status': 'succeeded',
                    'timestamp': '2024-01-01T00:00:00'
                }
            ],
            'count': 1
        }
        mock_get.return_value = mock_response
        
        self.cli.attempts_list(limit=10)
        
        # Verify request
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == 'http://test-api:8000/v1/attempts'
        assert call_args[1]['params'] == {'limit': 10}
    
    @patch('requests.Session.get')
    def test_attempts_list_with_target_filter(self, mock_get):
        """Should list attempts with target filter."""
        mock_response = Mock()
        mock_response.json.return_value = {'attempts': [], 'count': 0}
        mock_get.return_value = mock_response
        
        self.cli.attempts_list(target='my-target', limit=5)
        
        # Verify request includes target param
        call_args = mock_get.call_args
        assert call_args[1]['params'] == {'limit': 5, 'target': 'my-target'}
    
    @patch('requests.Session.get')
    def test_attempts_show(self, mock_get):
        """Should show attempt details."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'attempt_node': {'node_id': 'attempt-123'},
            'events': [],
            'artifacts': []
        }
        mock_get.return_value = mock_response
        
        self.cli.attempts_show('attempt-123')
        
        # Verify request
        call_args = mock_get.call_args
        assert call_args[0][0] == 'http://test-api:8000/v1/attempts/attempt-123'
    
    @patch('requests.Session.get')
    def test_failures_recent_without_filter(self, mock_get):
        """Should list failures without target filter."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'failures': [
                {
                    'attempt_id': 'attempt-2',
                    'task_id': 'task-2',
                    'target': 'test-target',
                    'error': 'Test failed',
                    'timestamp': '2024-01-01T00:00:00'
                }
            ],
            'count': 1
        }
        mock_get.return_value = mock_response
        
        self.cli.failures_recent(limit=10)
        
        # Verify request
        call_args = mock_get.call_args
        assert call_args[0][0] == 'http://test-api:8000/v1/failures'
        assert call_args[1]['params'] == {'limit': 10}
    
    @patch('requests.Session.get')
    def test_failures_recent_with_target_filter(self, mock_get):
        """Should list failures with target filter."""
        mock_response = Mock()
        mock_response.json.return_value = {'failures': [], 'count': 0}
        mock_get.return_value = mock_response
        
        self.cli.failures_recent(target='my-target', limit=20)
        
        # Verify request includes target param
        call_args = mock_get.call_args
        assert call_args[1]['params'] == {'limit': 20, 'target': 'my-target'}
    
    @patch('requests.Session.post')
    def test_invalidate_attempt(self, mock_post):
        """Should invalidate attempt with reason."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'attempt_id': 'attempt-456',
            'invalidated': True,
            'reason': 'Test reason'
        }
        mock_post.return_value = mock_response
        
        self.cli.invalidate_attempt('attempt-456', 'Test reason')
        
        # Verify request
        call_args = mock_post.call_args
        assert call_args[0][0] == 'http://test-api:8000/v1/attempts/attempt-456/invalidate'
        assert call_args[1]['json'] == {'reason': 'Test reason'}
    
    def test_session_headers(self):
        """Should set correct headers in session."""
        assert self.cli.session.headers['Authorization'] == 'Bearer test-token'
        assert self.cli.session.headers['Content-Type'] == 'application/json'
    
    def test_api_url_normalization(self):
        """Should strip trailing slash from API URL."""
        cli = LeviathanCLI("http://test:8000/", "token")
        assert cli.api_url == "http://test:8000"
