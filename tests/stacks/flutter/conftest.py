"""Shared fixtures for flutter stack tests."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.utils.templates import get_template_env

# 4 levels up from tests/stacks/flutter/ → project root → src/…
_STACK_CONFIG_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "src"
    / "model_generator"
    / "stacks"
    / "flutter"
    / "config.yaml"
)


@pytest.fixture
def flutter_config() -> dict[str, Any]:
    """The real flutter stack config.yaml (the type table lives here)."""
    with _STACK_CONFIG_PATH.open(encoding="utf-8") as f:
        config: dict[str, Any] = yaml.safe_load(f)
    return config


@pytest.fixture
def env() -> Any:
    """A Jinja2 environment bound to the flutter templates."""
    return get_template_env("flutter")
