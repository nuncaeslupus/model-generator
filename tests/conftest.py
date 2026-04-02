"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the model-generator project root."""
    return Path(__file__).parent.parent
