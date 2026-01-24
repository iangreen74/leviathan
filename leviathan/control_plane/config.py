"""
Configuration for Leviathan Graph Control Plane API.

Loads configuration from environment variables.
"""
import os
from pathlib import Path
from typing import Optional


class ControlPlaneConfig:
    """Configuration for control plane API."""
    
    def __init__(self):
        """Load configuration from environment."""
        # Auth token (required)
        self.token = os.getenv("LEVIATHAN_CONTROL_PLANE_TOKEN")
        if not self.token:
            raise ValueError("LEVIATHAN_CONTROL_PLANE_TOKEN environment variable required")
        
        # Backend selection
        self.backend = os.getenv("LEVIATHAN_BACKEND", "ndjson")  # ndjson or postgres
        
        # Postgres configuration
        self.postgres_url = os.getenv(
            "LEVIATHAN_POSTGRES_URL",
            "postgresql://leviathan:leviathan_dev_password@localhost:5432/leviathan"
        )
        
        # Artifacts storage
        artifacts_dir = os.getenv("LEVIATHAN_ARTIFACTS_DIR")
        if artifacts_dir:
            self.artifacts_dir = Path(artifacts_dir)
        else:
            self.artifacts_dir = Path.home() / ".leviathan" / "artifacts"
        
        # API server configuration
        self.host = os.getenv("LEVIATHAN_API_HOST", "0.0.0.0")
        self.port = int(os.getenv("LEVIATHAN_API_PORT", "8000"))
        
        # Event store path (for NDJSON backend)
        events_path = os.getenv("LEVIATHAN_EVENTS_PATH")
        if events_path:
            self.events_path = Path(events_path)
        else:
            self.events_path = Path.home() / ".leviathan" / "graph" / "events.ndjson"


def get_config() -> ControlPlaneConfig:
    """Get control plane configuration."""
    return ControlPlaneConfig()
