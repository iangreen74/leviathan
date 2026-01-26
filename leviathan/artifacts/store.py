"""
Content-addressed artifact storage.

Artifacts are stored by SHA256 hash for immutability and deduplication.
Supports file and S3 backends for failover scenarios.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class ArtifactStoreBackend:
    """Abstract base for artifact storage backends."""
    
    def store(self, sha256: str, content: bytes) -> str:
        """Store artifact and return storage URI."""
        raise NotImplementedError
    
    def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve artifact by SHA256."""
        raise NotImplementedError
    
    def exists(self, sha256: str) -> bool:
        """Check if artifact exists."""
        raise NotImplementedError


class FileBackend(ArtifactStoreBackend):
    """File-based artifact storage backend."""
    
    def __init__(self, storage_root: Path):
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
    
    def store(self, sha256: str, content: bytes) -> str:
        """Store artifact in filesystem."""
        shard_dir = self.storage_root / sha256[:2]
        shard_dir.mkdir(exist_ok=True)
        storage_path = shard_dir / sha256
        
        # Write content if not already exists (deduplication)
        if not storage_path.exists():
            storage_path.write_bytes(content)
        
        return f"file://{storage_path}"
    
    def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve artifact from filesystem."""
        storage_path = self.storage_root / sha256[:2] / sha256
        
        if storage_path.exists():
            return storage_path.read_bytes()
        
        return None
    
    def exists(self, sha256: str) -> bool:
        """Check if artifact exists in filesystem."""
        storage_path = self.storage_root / sha256[:2] / sha256
        return storage_path.exists()


class S3Backend(ArtifactStoreBackend):
    """S3-based artifact storage backend for failover."""
    
    def __init__(self, bucket: str, prefix: str = "artifacts"):
        """
        Initialize S3 backend.
        
        Args:
            bucket: S3 bucket name
            prefix: Key prefix for artifacts
        """
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 required for S3 backend. Install with: pip install boto3")
        
        self.bucket = bucket
        self.prefix = prefix.rstrip('/')
        self.s3_client = boto3.client('s3')
    
    def _get_key(self, sha256: str) -> str:
        """Get S3 key for artifact (sharded by first 2 chars)."""
        return f"{self.prefix}/{sha256[:2]}/{sha256}"
    
    def store(self, sha256: str, content: bytes) -> str:
        """Store artifact in S3."""
        key = self._get_key(sha256)
        
        # Check if already exists (deduplication)
        if not self.exists(sha256):
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType='application/octet-stream',
                Metadata={
                    'sha256': sha256,
                    'size': str(len(content))
                }
            )
        
        return f"s3://{self.bucket}/{key}"
    
    def retrieve(self, sha256: str) -> Optional[bytes]:
        """Retrieve artifact from S3."""
        key = self._get_key(sha256)
        
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            return response['Body'].read()
        except self.s3_client.exceptions.NoSuchKey:
            return None
        except Exception:
            return None
    
    def exists(self, sha256: str) -> bool:
        """Check if artifact exists in S3."""
        key = self._get_key(sha256)
        
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except:
            return False


class ArtifactStore:
    """
    Content-addressed artifact storage with pluggable backends.
    
    Supports file and S3 backends for failover scenarios.
    Backend selected via environment variables:
    - LEVIATHAN_ARTIFACT_BACKEND=file|s3 (default: file)
    - LEVIATHAN_ARTIFACT_S3_BUCKET (required for s3 backend)
    - LEVIATHAN_ARTIFACT_S3_PREFIX (optional, default: artifacts)
    """
    
    def __init__(self, storage_root: Optional[Path] = None, backend: Optional[ArtifactStoreBackend] = None):
        """
        Initialize artifact store.
        
        Args:
            storage_root: Root directory for file backend (default: ~/.leviathan/artifacts)
            backend: Custom backend (or None to auto-detect from env)
        """
        if backend is not None:
            self.backend = backend
        else:
            # Auto-detect backend from environment
            backend_type = os.getenv('LEVIATHAN_ARTIFACT_BACKEND', 'file')
            
            if backend_type == 's3':
                bucket = os.getenv('LEVIATHAN_ARTIFACT_S3_BUCKET')
                if not bucket:
                    raise ValueError("LEVIATHAN_ARTIFACT_S3_BUCKET required for S3 backend")
                prefix = os.getenv('LEVIATHAN_ARTIFACT_S3_PREFIX', 'artifacts')
                self.backend = S3Backend(bucket=bucket, prefix=prefix)
            elif backend_type == 'file':
                if storage_root is None:
                    storage_root = Path.home() / ".leviathan" / "artifacts"
                self.backend = FileBackend(storage_root=Path(storage_root))
            else:
                raise ValueError(f"Unknown artifact backend: {backend_type}")
    
    def store(self, content: bytes, artifact_type: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Store artifact and return metadata.
        
        Args:
            content: Artifact content (bytes)
            artifact_type: Type of artifact (log, test_output, diff, model_output, patch)
            metadata: Additional metadata
            
        Returns:
            Artifact metadata including sha256 and storage_path
        """
        # Compute SHA256
        sha256 = hashlib.sha256(content).hexdigest()
        
        # Store via backend
        storage_uri = self.backend.store(sha256, content)
        
        # Build metadata
        artifact_metadata = {
            'artifact_id': sha256,
            'sha256': sha256,
            'artifact_type': artifact_type,
            'size_bytes': len(content),
            'storage_path': storage_uri,
            'created_at': datetime.utcnow().isoformat(),
            'metadata': metadata or {}
        }
        
        return artifact_metadata
    
    def retrieve(self, sha256: str) -> Optional[bytes]:
        """
        Retrieve artifact by SHA256.
        
        Args:
            sha256: SHA256 hash of artifact
            
        Returns:
            Artifact content or None if not found
        """
        return self.backend.retrieve(sha256)
    
    def exists(self, sha256: str) -> bool:
        """Check if artifact exists."""
        return self.backend.exists(sha256)
