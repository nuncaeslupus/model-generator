"""
Action: Setup or update project settings (.model-generator.yaml).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..prompts import confirm, select, text
from ._common import find_project_root as _find_project_root


def _scan_stacks() -> list[str]:
    """Scan available stacks from the stacks directory."""
    stacks_dir = Path(__file__).parent.parent / "stacks"
    if not stacks_dir.exists():
        return ["python-fastapi"]
    return sorted(
        d.name
        for d in stacks_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )


_PATH_LAYOUTS: dict[str, dict[str, str]] = {
    "full-stack (backend/src/)": {
        "database_models": "backend/src/database/models",
        "factories": "backend/tests/factories",
        "api_models": "backend/src/api/models",
        "api_routes": "backend/src/api/routes",
        "api_tests": "tests/contract/api",
        "base": "backend/src/database/models/base.py",
        "engine": "backend/src/database/engine.py",
        "main": "backend/src/main.py",
        "errors": "backend/src/api/errors.py",
        "validators": "backend/src/api/validators.py",
        "test_conftest_root": "tests/conftest.py",
        "enums": "backend/src/database/models/enums.py",
        "constraints": "backend/src/database/models/constraints.py",
    },
    "backend-only (src/)": {
        "database_models": "src/database/models",
        "factories": "tests/factories",
        "api_models": "src/api/models",
        "api_routes": "src/api/routes",
        "api_tests": "tests/api",
        "base": "src/database/models/base.py",
        "engine": "src/database/engine.py",
        "main": "src/main.py",
        "errors": "src/api/errors.py",
        "validators": "src/api/validators.py",
        "test_conftest_root": "tests/conftest.py",
        "enums": "src/database/models/enums.py",
        "constraints": "src/database/models/constraints.py",
    },
}


def run_setup() -> None:
    """Create or update .model-generator.yaml interactively."""
    project_root = _find_project_root()
    config_path = project_root / ".model-generator.yaml"

    if config_path.exists():
        _update_config(config_path)
    else:
        _create_config(config_path, project_root)


def _create_config(config_path: Path, project_root: Path) -> None:
    """Guide user through creating a new config."""
    print("\n--- Create Project Settings ---\n")

    name = text("Project name:", default=project_root.name)
    description = text("Description (optional):", default="")
    version = text("Version:", default="0.1.0")

    stacks = _scan_stacks()
    stack = select("Stack:", choices=stacks, default="python-fastapi")

    layout_choices = [*_PATH_LAYOUTS, "custom"]
    layout = select("Path layout:", choices=layout_choices, default=layout_choices[0])

    config: dict[str, Any] = {
        "project": {"name": name, "version": version},
        "stack": stack,
    }
    if description:
        config["project"]["description"] = description

    if layout != "custom" and layout in _PATH_LAYOUTS:
        config["paths"] = _PATH_LAYOUTS[layout]

    config_path.write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    print(f"\nCreated: {config_path}")

    # Create models directory
    models_dir = project_root / "models"
    if not models_dir.exists() and confirm("Create models/ directory?"):
        models_dir.mkdir(parents=True)
        print(f"Created: {models_dir}")


def _update_config(config_path: Path) -> None:
    """Show current config and offer updates."""
    print("\n--- Update Project Settings ---\n")

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    print("Current configuration:")
    print(yaml.dump(config, default_flow_style=False))

    if not confirm("Update settings?", default=False):
        return

    project = config.get("project", {})
    project["name"] = text("Project name:", default=project.get("name", ""))
    project["version"] = text("Version:", default=project.get("version", "0.1.0"))
    config["project"] = project

    stacks = _scan_stacks()
    config["stack"] = select(
        "Stack:", choices=stacks, default=config.get("stack", "python-fastapi")
    )

    config_path.write_text(
        yaml.dump(config, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )
    print(f"\nUpdated: {config_path}")
