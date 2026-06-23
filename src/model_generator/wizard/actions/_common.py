"""Shared helpers for wizard actions."""

from pathlib import Path


def find_project_root() -> Path:
    """Find project root by looking for .model-generator.yaml.

    Checks the current working directory first, then its parent.
    Falls back to the current directory if neither has the marker file.
    """
    cwd = Path.cwd()
    if (cwd / ".model-generator.yaml").exists():
        return cwd
    parent = cwd.parent
    if (parent / ".model-generator.yaml").exists():
        return parent
    return cwd
