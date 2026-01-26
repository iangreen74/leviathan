"""
Unit tests for S3 artifact backend (failover mode).
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from leviathan.artifacts.store import S3Backend, ArtifactStore


class TestS3Backend:
    """Test S3 artifact backend."""
    
    @pytest.fixture
    def mock_s3_client(self):
        """Create mock S3 client."""
        with patch('boto3.client') as mock_boto3:
            mock_client = MagicMock()
            mock_boto3.return_value = mock_client
            yield mock_client
    
    def test_s3_backend_init(self, mock_s3_client):
        """Test S3 backend initialization."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        assert backend.bucket == 'test-bucket'
        assert backend.prefix == 'artifacts'
        assert backend.s3_client is not None
    
    def test_s3_backend_get_key(self, mock_s3_client):
        """Test S3 key generation (sharded)."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        sha256 = 'abc123def456'
        key = backend._get_key(sha256)
        
        # Should be sharded by first 2 chars
        assert key == 'artifacts/ab/abc123def456'
    
    def test_s3_backend_store_new(self, mock_s3_client):
        """Test storing new artifact in S3."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock exists check (not exists)
        mock_s3_client.head_object.side_effect = Exception("Not found")
        
        sha256 = 'abc123'
        content = b'test content'
        
        uri = backend.store(sha256, content)
        
        # Should call put_object
        mock_s3_client.put_object.assert_called_once()
        call_args = mock_s3_client.put_object.call_args
        assert call_args[1]['Bucket'] == 'test-bucket'
        assert call_args[1]['Key'] == 'artifacts/ab/abc123'
        assert call_args[1]['Body'] == content
        
        # Should return S3 URI
        assert uri == 's3://test-bucket/artifacts/ab/abc123'
    
    def test_s3_backend_store_existing(self, mock_s3_client):
        """Test storing existing artifact (deduplication)."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock exists check (exists)
        mock_s3_client.head_object.return_value = {'ContentLength': 100}
        
        sha256 = 'abc123'
        content = b'test content'
        
        uri = backend.store(sha256, content)
        
        # Should NOT call put_object (already exists)
        mock_s3_client.put_object.assert_not_called()
        
        # Should still return URI
        assert uri == 's3://test-bucket/artifacts/ab/abc123'
    
    def test_s3_backend_retrieve(self, mock_s3_client):
        """Test retrieving artifact from S3."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock get_object response
        mock_body = MagicMock()
        mock_body.read.return_value = b'test content'
        mock_s3_client.get_object.return_value = {'Body': mock_body}
        
        sha256 = 'abc123'
        content = backend.retrieve(sha256)
        
        # Should call get_object
        mock_s3_client.get_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='artifacts/ab/abc123'
        )
        
        assert content == b'test content'
    
    def test_s3_backend_retrieve_not_found(self, mock_s3_client):
        """Test retrieving non-existent artifact."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock NoSuchKey exception
        mock_s3_client.exceptions.NoSuchKey = Exception
        mock_s3_client.get_object.side_effect = mock_s3_client.exceptions.NoSuchKey()
        
        sha256 = 'notfound'
        content = backend.retrieve(sha256)
        
        assert content is None
    
    def test_s3_backend_exists(self, mock_s3_client):
        """Test checking if artifact exists."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock head_object (exists)
        mock_s3_client.head_object.return_value = {'ContentLength': 100}
        
        sha256 = 'abc123'
        exists = backend.exists(sha256)
        
        assert exists is True
        mock_s3_client.head_object.assert_called_once_with(
            Bucket='test-bucket',
            Key='artifacts/ab/abc123'
        )
    
    def test_s3_backend_not_exists(self, mock_s3_client):
        """Test checking if artifact does not exist."""
        backend = S3Backend(bucket='test-bucket', prefix='artifacts')
        
        # Mock head_object (not exists)
        mock_s3_client.head_object.side_effect = Exception("Not found")
        
        sha256 = 'notfound'
        exists = backend.exists(sha256)
        
        assert exists is False


class TestArtifactStoreS3Integration:
    """Test ArtifactStore with S3 backend."""
    
    @pytest.fixture
    def mock_s3_backend(self):
        """Create mock S3 backend."""
        with patch('leviathan.artifacts.store.S3Backend') as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            yield mock_backend
    
    def test_artifact_store_s3_env(self, mock_s3_backend, monkeypatch):
        """Test ArtifactStore with S3 backend from env vars."""
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_BACKEND', 's3')
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_S3_BUCKET', 'test-bucket')
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_S3_PREFIX', 'my-artifacts')
        
        with patch('leviathan.artifacts.store.S3Backend') as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend_class.return_value = mock_backend
            
            store = ArtifactStore()
            
            # Should create S3 backend with correct params
            mock_backend_class.assert_called_once_with(
                bucket='test-bucket',
                prefix='my-artifacts'
            )
    
    def test_artifact_store_s3_missing_bucket(self, monkeypatch):
        """Test ArtifactStore with S3 backend but missing bucket."""
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_BACKEND', 's3')
        monkeypatch.delenv('LEVIATHAN_ARTIFACT_S3_BUCKET', raising=False)
        
        with pytest.raises(ValueError, match="LEVIATHAN_ARTIFACT_S3_BUCKET required"):
            ArtifactStore()
    
    def test_artifact_store_s3_store(self, mock_s3_backend, monkeypatch):
        """Test storing artifact via S3 backend."""
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_BACKEND', 's3')
        monkeypatch.setenv('LEVIATHAN_ARTIFACT_S3_BUCKET', 'test-bucket')
        
        with patch('leviathan.artifacts.store.S3Backend') as mock_backend_class:
            mock_backend = MagicMock()
            mock_backend.store.return_value = 's3://test-bucket/artifacts/ab/abc123'
            mock_backend_class.return_value = mock_backend
            
            store = ArtifactStore()
            
            content = b'test content'
            metadata = store.store(content, 'log', {'test': 'meta'})
            
            # Should compute SHA256
            assert 'sha256' in metadata
            assert metadata['artifact_type'] == 'log'
            
            # Should call backend.store
            mock_backend.store.assert_called_once()
            
            # Storage path should be S3 URI
            assert metadata['storage_path'].startswith('s3://')
