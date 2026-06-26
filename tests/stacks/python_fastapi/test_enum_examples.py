"""Tests for how enum-typed fields render in OpenAPI examples.

The Pydantic response and request models emit a `json_schema_extra.example`
dict used for OpenAPI documentation. Enum fields in that example must use a
real value from the referenced enum — previously the response template
fell back to a hardcoded `'active'` string, which silently produced invalid
examples for any enum that didn't happen to include that value.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.generators import generate_api_models
from model_generator.utils import get_template_env, load_config

_PATHS: dict[str, str] = {
    "database_models": "src/database/models",
    "factories": "src/database/models/factories",
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
    "migrations": "alembic",
}


@pytest.fixture
def stack_env(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
    """Minimal project config + Jinja2 env, without a pinned layout.

    Omitting the ``generation`` key exercises the default (per-entity)
    layout — the fixture intentionally differs from the conftest's
    ``project_env``, which pins to per-domain.
    """
    config_data: dict[str, Any] = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
        "paths": _PATHS,
    }
    (tmp_path / ".model-generator.yaml").write_text(yaml.dump(config_data))

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        config = load_config("python-fastapi")
        env = get_template_env("python-fastapi")
    finally:
        os.chdir(original_cwd)

    return tmp_path, config, env


def _write_shared_enums(models_dir: Path, enums: dict[str, Any]) -> Path:
    """Write a _shared/enums.json alongside a models directory."""
    shared_dir = models_dir / "_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    enums_file = shared_dir / "enums.json"
    enums_file.write_text(json.dumps({"enums": enums}, indent=2))
    return enums_file


def _priority_enum() -> dict[str, Any]:
    """A generic enum that does NOT contain the value 'active'.

    Using an enum without 'active' tightly verifies the fix — a broken
    template that still hardcoded 'active' would fail the assertions below
    because none of the enum values match.
    """
    return {
        "Priority": {
            "description": "Priority level",
            "values": [
                {"name": "HIGH", "value": "HIGH"},
                {"name": "MEDIUM", "value": "MEDIUM"},
                {"name": "LOW", "value": "LOW"},
            ],
        }
    }


class TestResponseExampleUsesFirstEnumValue:
    """The response template must derive the example value from the actual
    enum, not hardcode a fallback string.
    """

    def test_first_enum_value_used_when_no_default(
        self, stack_env: Any, tmp_path: Path
    ) -> None:
        project_root, config, env = stack_env

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        model_file = models_dir / "items.model.json"
        _write_shared_enums(models_dir, _priority_enum())

        model = {
            "domain": "items",
            "description": "Items domain",
            "entities": {
                "Item": {
                    "table": "items",
                    "description": "An item",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "priority": {
                            "type": "enum",
                            "enum_name": "Priority",
                            "required": True,
                        },
                    },
                }
            },
        }
        model_file.write_text(json.dumps(model))

        results = generate_api_models(
            model, config, env, project_root, model_path=model_file
        )
        assert results is not None

        response = next(r for r in results if "response" in r["path"].name)
        content = response["content"]

        assert "'active'" not in content, (
            "response template must not emit a hardcoded 'active' fallback"
        )
        assert '"active"' not in content, (
            "response example must not contain 'active' when the enum"
            " is {HIGH, MEDIUM, LOW}"
        )
        assert '"HIGH"' in content, (
            "response example should use the first enum value ('HIGH')"
        )

    def test_explicit_default_wins_over_enum_lookup(
        self, stack_env: Any, tmp_path: Path
    ) -> None:
        """If `field.default` is set, the template uses it verbatim (upper-cased)
        instead of looking up the first enum value.
        """
        project_root, config, env = stack_env

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        model_file = models_dir / "items.model.json"
        _write_shared_enums(models_dir, _priority_enum())

        model = {
            "domain": "items",
            "entities": {
                "Item": {
                    "table": "items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "priority": {
                            "type": "enum",
                            "enum_name": "Priority",
                            "default": "LOW",
                        },
                    },
                }
            },
        }
        model_file.write_text(json.dumps(model))

        results = generate_api_models(
            model, config, env, project_root, model_path=model_file
        )
        assert isinstance(results, list)
        response = next(r for r in results if "response" in r["path"].name)
        assert '"LOW"' in response["content"]

    def test_missing_enums_file_falls_back_to_unknown(
        self, stack_env: Any, tmp_path: Path
    ) -> None:
        """When no _shared/enums.json exists and no default is set, the
        template emits 'UNKNOWN' rather than crashing — consistent with the
        request template's behavior.
        """
        project_root, config, env = stack_env

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        model_file = models_dir / "items.model.json"
        # No _shared/enums.json written.

        model = {
            "domain": "items",
            "entities": {
                "Item": {
                    "table": "items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "priority": {
                            "type": "enum",
                            "enum_name": "Priority",
                        },
                    },
                }
            },
        }
        model_file.write_text(json.dumps(model))

        results = generate_api_models(
            model, config, env, project_root, model_path=model_file
        )
        assert isinstance(results, list)
        response = next(r for r in results if "response" in r["path"].name)
        assert '"UNKNOWN"' in response["content"]
        assert "'active'" not in response["content"]
