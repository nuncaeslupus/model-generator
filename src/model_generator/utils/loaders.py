"""
Model and configuration loading utilities.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from .templates import path_to_import


def load_model(model_path: Path) -> dict[str, Any]:
    """
    Load and parse model JSON file.

    Supports:
    - Standard .json files
    - JSON with // comments (stripped before parsing)

    Validates the model against the schema definition.
    """
    with open(model_path) as f:
        json_content = f.read()

    # Strip // comments
    json_content = re.sub(r"^\s*//.*$", "", json_content, flags=re.MULTILINE)
    # Strip inline // comments (naive approach - doesn't handle strings)
    json_content = re.sub(r"\s+//.*$", "", json_content, flags=re.MULTILINE)

    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON in {model_path}: {e}")
        lines = json_content.splitlines()
        if e.lineno <= len(lines):
            print(f"Line {e.lineno}: {lines[e.lineno - 1]}")
        sys.exit(1)

    _normalize_field_types(data)
    _normalize_indexes(data)
    _validate_model_schema(data, model_path)
    return cast(dict[str, Any], data)


def _normalize_indexes(data: dict[str, Any]) -> None:
    """Normalize legacy index shapes to canonical form.

    Early docs showed ``{"type": "single"|"composite"|"unique", ...}`` but the
    schema (and downstream templates) only accept ``{"fields": [...],
    "unique": bool}``. Convert legacy entries in place so validation and
    generation both see the canonical shape:

        {"type": "single", "field": "x"}          → {"fields": ["x"]}
        {"type": "composite", "fields": [...]}    → {"fields": [...]}
        {"type": "unique", "field": "x"}          → {"fields": ["x"], "unique": True}
        {"type": "unique", "fields": [...]}       → {"fields": [...], "unique": True}
    """
    for entity in data.get("entities", {}).values():
        indexes = entity.get("indexes")
        if not isinstance(indexes, list):
            continue
        for idx in indexes:
            if not isinstance(idx, dict):
                continue
            legacy_type = idx.pop("type", None)
            if "field" in idx and "fields" not in idx:
                idx["fields"] = [idx.pop("field")]
            if legacy_type == "unique":
                idx.setdefault("unique", True)


def _normalize_field_types(data: dict[str, Any]) -> None:
    """Normalize field type aliases and constraints.

    Currently:
    - Normalizes "integer" → "counter".
    - Moves "timestamp_after" from constraints array to direct field property.
    """
    aliases: dict[str, str] = {"integer": "counter"}
    for entity in data.get("entities", {}).values():
        fields = entity.get("fields", {})
        if not isinstance(fields, dict):
            continue
        for field in fields.values():
            # Type aliases
            original = field.get("type", "")
            if original in aliases:
                field["type"] = aliases[original]

            # Standardize timestamp_after constraint
            if "constraints" in field and isinstance(field["constraints"], list):
                # Find timestamp_after in constraints
                ts_after_idx = -1
                ts_after_val = None
                for i, c in enumerate(field["constraints"]):
                    if (
                        isinstance(c, dict)
                        and c.get("type") == "timestamp_after"
                        and "after" in c
                    ):
                        ts_after_idx = i
                        ts_after_val = c["after"]
                        break

                if ts_after_idx != -1:
                    # Move to direct property if not already set
                    if "timestamp_after" not in field:
                        field["timestamp_after"] = ts_after_val
                    # Remove from constraints array to avoid redundant handling
                    field["constraints"].pop(ts_after_idx)


def _validate_model_schema(data: dict[str, Any], model_path: Path) -> None:
    """Validate model data against JSON schema."""
    script_dir = Path(__file__).parent.parent
    schema_path = script_dir / "schema" / "model.schema.json"

    if not schema_path.exists():
        print(f"  ⚠️  Schema file not found at {schema_path}, skipping validation")
        return

    with open(schema_path) as f:
        schema = json.load(f)

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        print(f"  ⚠️  Model validation warning in {model_path.name}:")
        print(f"     {e.message} at path: {' -> '.join(str(p) for p in e.path)}")
        # Warn but don't exit - allow partial/WIP models


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries.

    Override values take precedence. Nested dicts are merged recursively.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(stack: str = "python-fastapi") -> dict[str, Any]:
    """
    Load stack configuration and merge with project config.

    Reads from:
    1. <project-root>/.model-generator.yaml (if exists) - project config
    2. stacks/{stack}/config.yaml - stack technical config

    Project config takes precedence for overlapping keys.
    """
    script_dir = Path(__file__).parent.parent
    project_root = Path.cwd()
    project_config_path = project_root / ".model-generator.yaml"

    # Load project config if it exists
    project_config: dict[str, Any] = {}
    if project_config_path.exists():
        with open(project_config_path) as f:
            project_config = yaml.safe_load(f) or {}

    # Get stack name from project config or use default
    stack_name = project_config.get("stack", stack)

    # Load stack technical config
    config_path = script_dir / "stacks" / stack_name / "config.yaml"
    if not config_path.exists():
        print(f"Error: Stack config not found at {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        stack_config = yaml.safe_load(f)

    merged_config = deep_merge(stack_config, project_config)

    # Ensure project defaults exist
    if "project" not in merged_config:
        merged_config["project"] = {
            "name": "Your Project",
            "description": "Database models and API for your application",
            "version": "0.1.0",
        }

    # Generation defaults. `layout` controls whether per-domain emitters
    # produce one file per domain ("per-domain") or one file per entity
    # ("per-entity", default).
    merged_config.setdefault("generation", {})
    merged_config["generation"].setdefault("layout", "per-entity")

    # Auto-wire auth.dependency_path to the emitted get_current_user
    # when the adopter has set auth.strategy but not dependency_path.
    # The §9 owner-scoped routes/tests read the dotted path at render
    # time; wiring it here means every load_config() caller sees the
    # same processed config (including generate() which re-loads from
    # disk per-model). Explicit dependency_path values are preserved.
    auth = merged_config.get("auth") or {}
    if auth.get("strategy") and not auth.get("dependency_path"):
        auth_path = auth.get("path", "backend/src/auth/router.py")
        module_path = auth_path[:-3] if auth_path.endswith(".py") else auth_path
        module_import = path_to_import(
            module_path, python_root=merged_config.get("python_root", "")
        )
        merged_config.setdefault("auth", {})
        merged_config["auth"]["dependency_path"] = f"{module_import}.get_current_user"

    return merged_config


def get_layout(config: dict[str, Any]) -> str:
    """Return the configured generation layout (defaulting to per-entity).

    `load_config` already injects the default, but this helper guards
    against ad-hoc config dicts (e.g. test fixtures) that bypass it.
    """
    return cast(str, config.get("generation", {}).get("layout", "per-entity"))


def load_shared_enums(model_path: Path) -> dict[str, Any]:
    """
    Load enum definitions from _shared/enums.json.

    Args:
        model_path: Path to a model file or models directory.
    """
    if model_path.is_file():
        shared_enums_file = model_path.parent / "_shared" / "enums.json"
    else:
        shared_enums_file = model_path / "_shared" / "enums.json"

    if not shared_enums_file.exists():
        return {}

    with open(shared_enums_file) as f:
        data = json.load(f)
        return cast(dict[str, Any], data.get("enums", {}))


def load_shared_constraints(model_path: Path) -> dict[str, Any]:
    """
    Load constraint definitions from _shared/constraints.json.

    Args:
        model_path: Path to a model file or models directory.

    Returns a flattened dict of constraint constants.
    """
    if model_path.is_file():
        shared_constraints_file = model_path.parent / "_shared" / "constraints.json"
    else:
        shared_constraints_file = model_path / "_shared" / "constraints.json"

    if not shared_constraints_file.exists():
        return {}

    with open(shared_constraints_file) as f:
        data = json.load(f)

    # Flatten constraint groups into a flat dict
    flattened = {}
    for group_data in data.get("constraints", {}).values():
        for key in ("min", "max", "pattern"):
            if key in group_data:
                defn = group_data[key]
                flattened[defn["name"]] = {
                    "type": defn["type"],
                    "value": defn["value"],
                    "description": defn.get(
                        "description", group_data.get("description", "")
                    ),
                }

    return flattened
