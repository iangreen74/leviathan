"""
Pytest configuration for unit tests.

Sets up test-wide fixtures and environment configuration.
"""
import pytest
import os

# Set environment variables at module import time (before any test modules import control plane)
# This ensures the token is available when control plane modules are imported
os.environ["LEVIATHAN_CONTROL_PLANE_TOKEN"] = "test-token-12345"
os.environ["LEVIATHAN_BACKEND"] = "ndjson"


@pytest.fixture
def auth_headers():
    """Provide authentication headers for control plane API tests."""
    return {"Authorization": "Bearer test-token-12345"}


@pytest.fixture
def control_plane_token():
    """Provide the control plane token for tests."""
    return "test-token-12345"
