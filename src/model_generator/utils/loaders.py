"""
Model and configuration loading utilities.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft7Validator

from .templates import path_to_import

_JSON_COMMENT_RE = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*')


def strip_json_comments(text: str) -> str:
    """Strip ``//`` line and inline comments from JSON text.

    Skips over double-quoted string literals so a ``//`` inside a value (a URL,
    a description) is preserved — only comments *outside* strings are removed.
    Shared so every reader (generator, validator, conftest generation) parses
    the same dialect.
    """
    return _JSON_COMMENT_RE.sub(
        lambda m: m.group(1) if m.group(1) is not None else "", text
    )


def parse_model_file(model_path: Path) -> dict[str, Any]:
    """Read, comment-strip, parse and *normalize* a model file (no validation).

    Applies the same comment handling and alias/index normalization as
    :func:`load_model` but does **not** validate against the schema and does
    **not** exit on error — it raises ``json.JSONDecodeError`` so callers can
    decide how to report. Use this anywhere that needs the canonical model dict
    without the generator's print-and-exit behaviour (e.g. ``model-val``).
    """
    with model_path.open(encoding="utf-8") as f:
        json_content = strip_json_comments(f.read())

    data = json.loads(json_content)
    # Normalization expects an object; for non-dict JSON (a list/primitive),
    # skip it and let the schema validator report the type error cleanly.
    if isinstance(data, dict):
        _normalize_field_types(data)
        _normalize_indexes(data)
    return cast(dict[str, Any], data)


def load_model(model_path: Path) -> dict[str, Any]:
    """
    Load and parse model JSON file.

    Supports:
    - Standard .json files
    - JSON with // comments (stripped before parsing)

    Validates the model against the schema definition.
    """
    try:
        data = parse_model_file(model_path)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON in {model_path}: {e}")
        with model_path.open(encoding="utf-8") as f:
            lines = strip_json_comments(f.read()).splitlines()
        if e.lineno <= len(lines):
            print(f"Line {e.lineno}: {lines[e.lineno - 1]}")
        sys.exit(1)

    _validate_model_schema(data, model_path)
    return data


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

    with schema_path.open(encoding="utf-8") as f:
        schema = json.load(f)

    validator = Draft7Validator(schema)
    errors = sorted(
        validator.iter_errors(data), key=lambda e: tuple(str(p) for p in e.path)
    )
    for e in errors:
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
        with project_config_path.open(encoding="utf-8") as f:
            project_config = yaml.safe_load(f) or {}

    # Get stack name from project config or use default
    stack_name = project_config.get("stack", stack)

    # Load stack technical config
    config_path = script_dir / "stacks" / stack_name / "config.yaml"
    if not config_path.exists():
        print(f"Error: Stack config not found at {config_path}")
        sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        stack_config = yaml.safe_load(f)

    merged_config = deep_merge(stack_config, project_config)

    # Guard: top-level sections that must be dicts. A project config entry like
    # `paths: "invalid"` would AttributeError deep in a generator — catch it here.
    for _section in ("paths", "auth", "generation", "style"):
        _val = merged_config.get(_section)
        if _val is not None and not isinstance(_val, dict):
            print(
                f"Error: config.{_section} must be a mapping (got"
                f" {type(_val).__name__!r}). Check your .model-generator.yaml."
            )
            sys.exit(1)

    # If the project overrode paths.database_models but not paths.base,
    # derive base from the new database_models so the two stay consistent.
    # (Generated model files import base with a relative `from .base import
    # Base` — see _validate_paths_base for the full constraint.)
    project_paths = project_config.get("paths") or {}
    if "base" not in project_paths and "database_models" in project_paths:
        db_models = merged_config["paths"]["database_models"]
        merged_config["paths"]["base"] = f"{db_models}/base.py"

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

    # Auto-wire auth.dependency_path to the emitted auth dependency when the
    # adopter has set auth.strategy but not dependency_path. The dependency
    # differs per strategy: bcrypt-session injects ``get_current_user`` (router
    # module), api-key gates with ``require_api_key`` (api_key module). The §9
    # owner-scoped routes/tests read the dotted path at render time; wiring it
    # here means every load_config() caller sees the same processed config
    # (including generate() which re-loads from disk per-model). Explicit
    # dependency_path values are preserved.
    auth = merged_config.get("auth") or {}
    strategy = auth.get("strategy")
    if strategy and not auth.get("dependency_path"):
        python_root = merged_config.get("python_root", "")
        auth_path = auth.get("path", "backend/src/auth/router.py")
        if strategy == "api-key":
            # as_posix() so path_to_import gets forward slashes on Windows too.
            module_path = (Path(auth_path).parent / "api_key").as_posix()
            func = "require_api_key"
        else:
            module_path = auth_path[:-3] if auth_path.endswith(".py") else auth_path
            func = "get_current_user"
        module_import = path_to_import(module_path, python_root=python_root)
        merged_config.setdefault("auth", {})
        merged_config["auth"]["dependency_path"] = f"{module_import}.{func}"

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

    with shared_enums_file.open(encoding="utf-8") as f:
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

    with shared_constraints_file.open(encoding="utf-8") as f:
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
