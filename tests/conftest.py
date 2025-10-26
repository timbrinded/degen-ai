"""Pytest configuration and fixtures."""

import gc

import pytest


@pytest.fixture(scope="module", autouse=True)
def cleanup_after_module():
    """Ensure proper cleanup after each test module."""
    yield
    # Force garbage collection to clean up any lingering resources
    gc.collect()
    gc.collect()  # Run twice to catch circular references
