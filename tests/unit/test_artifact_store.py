"""
Unit tests for artifact store (content-addressed storage).
"""
import pytest
import hashlib
import tempfile
import shutil
from pathlib import Path

from leviathan.artifacts.store import ArtifactStore


class TestArtifactStore:
    """Test content-addressed artifact storage."""
    
    def setup_method(self):
        """Create temporary storage directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.store = ArtifactStore(storage_root=self.temp_dir)
    
    def teardown_method(self):
        """Clean up temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_store_artifact(self):
        """Should store artifact and return metadata."""
        content = b"Test log output\nLine 2\nLine 3"
        
        metadata = self.store.store(content, "log")
        
        assert metadata['artifact_type'] == "log"
        assert metadata['size_bytes'] == len(content)
        assert len(metadata['sha256']) == 64
        assert metadata['artifact_id'] == metadata['sha256']
    
    def test_sha256_is_correct(self):
        """SHA256 should match actual hash of content."""
        content = b"Test content"
        expected_sha256 = hashlib.sha256(content).hexdigest()
        
        metadata = self.store.store(content, "test")
        
        assert metadata['sha256'] == expected_sha256
    
    def test_retrieve_artifact(self):
        """Should retrieve artifact by SHA256."""
        content = b"Test content for retrieval"
        
        metadata = self.store.store(content, "test")
        retrieved = self.store.retrieve(metadata['sha256'])
        
        assert retrieved == content
    
    def test_retrieve_nonexistent_artifact(self):
        """Should return None for nonexistent artifact."""
        fake_sha256 = "a" * 64
        
        retrieved = self.store.retrieve(fake_sha256)
        
        assert retrieved is None
    
    def test_deduplication(self):
        """Same content stored twice should only be stored once."""
        content = b"Duplicate content"
        
        metadata1 = self.store.store(content, "log")
        metadata2 = self.store.store(content, "log")
        
        # Should have same SHA256
        assert metadata1['sha256'] == metadata2['sha256']
        
        # Should only exist once on disk
        # Storage path is now a URI (file://...), extract the path
        storage_uri = metadata1['storage_path']
        if storage_uri.startswith('file://'):
            storage_path = Path(storage_uri[7:])  # Remove 'file://' prefix
        else:
            storage_path = Path(storage_uri)
        assert storage_path.exists()
        
        # File should only contain content once
        assert storage_path.read_bytes() == content
    
    def test_sharding_by_hash_prefix(self):
        """Artifacts should be sharded by first 2 chars of hash."""
        content = b"Test sharding"
        
        metadata = self.store.store(content, "test")
        sha256 = metadata['sha256']
        
        # Storage path should include shard directory
        expected_shard = sha256[:2]
        storage_path = Path(metadata['storage_path'])
        
        assert expected_shard in str(storage_path)
        assert storage_path.parent.name == expected_shard
    
    def test_exists_check(self):
        """Should correctly check if artifact exists."""
        content = b"Test existence"
        
        metadata = self.store.store(content, "test")
        sha256 = metadata['sha256']
        
        assert self.store.exists(sha256) is True
        assert self.store.exists("a" * 64) is False
    
    def test_store_with_metadata(self):
        """Should store additional metadata."""
        content = b"Test with metadata"
        extra_metadata = {
            'source': 'test',
            'attempt_id': 'attempt-001'
        }
        
        metadata = self.store.store(content, "log", metadata=extra_metadata)
        
        assert metadata['metadata'] == extra_metadata
    
    def test_store_different_types(self):
        """Should handle different artifact types."""
        types = ["log", "test_output", "diff", "model_output", "patch"]
        
        for artifact_type in types:
            content = f"Content for {artifact_type}".encode()
            metadata = self.store.store(content, artifact_type)
            
            assert metadata['artifact_type'] == artifact_type
            retrieved = self.store.retrieve(metadata['sha256'])
            assert retrieved == content
    
    def test_store_empty_content(self):
        """Should handle empty content."""
        content = b""
        
        metadata = self.store.store(content, "empty")
        
        assert metadata['size_bytes'] == 0
        retrieved = self.store.retrieve(metadata['sha256'])
        assert retrieved == b""
    
    def test_store_large_content(self):
        """Should handle large content."""
        # 1MB of data
        content = b"x" * (1024 * 1024)
        
        metadata = self.store.store(content, "large")
        
        assert metadata['size_bytes'] == 1024 * 1024
        retrieved = self.store.retrieve(metadata['sha256'])
        assert retrieved == content
    
    def test_storage_path_format(self):
        """Storage path should follow expected format."""
        content = b"Test path format"
        
        metadata = self.store.store(content, "test")
        # Storage path is now a URI (file://...), extract the path
        storage_uri = metadata['storage_path']
        if storage_uri.startswith('file://'):
            storage_path = Path(storage_uri[7:])  # Remove 'file://' prefix
        else:
            storage_path = Path(storage_uri)
        
        # Should be: storage_root / shard / sha256
        assert storage_path.parent.parent == self.temp_dir
        assert storage_path.name == metadata['sha256']
