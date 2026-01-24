"""
Content-addressed artifact storage.

Artifacts are stored by SHA256 hash for immutability and deduplication.
"""
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class ArtifactStore:
    """
    Content-addressed artifact storage.
    
    Stores artifacts by SHA256 hash in filesystem.
    Metadata tracked in database.
    """
    
    def __init__(self, storage_root: Optional[Path] = None):
        """
        Initialize artifact store.
        
        Args:
            storage_root: Root directory for artifacts (default: ~/.leviathan/artifacts)
        """
        if storage_root is None:
            storage_root = Path.home() / ".leviathan" / "artifacts"
        
        self.storage_root = storage_root
        self.storage_root.mkdir(parents=True, exist_ok=True)
    
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
        
        # Create storage path (sharded by first 2 chars of hash)
        shard_dir = self.storage_root / sha256[:2]
        shard_dir.mkdir(exist_ok=True)
        storage_path = shard_dir / sha256
        
        # Write content if not already exists (deduplication)
        if not storage_path.exists():
            storage_path.write_bytes(content)
        
        # Build metadata
        artifact_metadata = {
            'artifact_id': sha256,
            'sha256': sha256,
            'artifact_type': artifact_type,
            'size_bytes': len(content),
            'storage_path': str(storage_path),
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
        storage_path = self.storage_root / sha256[:2] / sha256
        
        if storage_path.exists():
            return storage_path.read_bytes()
        
        return None
    
    def exists(self, sha256: str) -> bool:
        """Check if artifact exists."""
        storage_path = self.storage_root / sha256[:2] / sha256
        return storage_path.exists()
