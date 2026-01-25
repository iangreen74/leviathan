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
