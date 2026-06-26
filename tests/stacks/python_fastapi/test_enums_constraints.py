"""Tests for enum and constraint generators."""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from model_generator.generators import (
    generate_constraints,
    generate_enums,
)
from model_generator.generators.constraints import (
    _extract_ref,
    _extract_regex_ref,
    extract_constraint_refs,
)


class TestEnumsGenerator:
    """Test enum generation."""

    def test_creates_enums_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Generate enums when _shared/enums.json exists."""
        project_root, config, env = project_env

        # Create model dir with shared enums
        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [
                        {"name": "STANDARD", "value": "STANDARD"},
                        {"name": "PREMIUM", "value": "PREMIUM"},
                    ],
                }
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)

        assert result is not None
        assert result["mode"] == "write"
        assert result["skipped"] == 0
        assert result["new_count"] == 1
        enums_file = project_root / config["paths"]["database_models"] / "enums.py"
        assert result["path"] == enums_file
        assert "class ItemType(StrEnum):" in result["content"]
        assert "STANDARD" in result["content"]

    def test_append_mode_adds_new_enums(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Append mode: existing enums skipped, new ones included in result."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [{"name": "STANDARD", "value": "STANDARD"}],
                },
                "OrderStatus": {
                    "description": "Status of order",
                    "values": [{"name": "PENDING", "value": "PENDING"}],
                },
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        enums_file = output_dir / "enums.py"
        enums_file.write_text(
            "from enum import StrEnum\n"
            "class ItemType(StrEnum):\n"
            "    STANDARD = 'STANDARD'\n"
        )

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)

        assert result is not None
        assert result["mode"] == "append"
        assert result["path"] == enums_file
        assert result["new_count"] == 1
        assert result["skipped"] == 1
        assert "class OrderStatus(StrEnum):" in result["content"]
        assert "ItemType" not in result["content"]

    def test_no_enums_returns_none(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Generate enums when no _shared/enums.json exists."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        models_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is None

    def test_append_mode_skips_existing(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Enums that already exist in file are skipped."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [{"name": "STANDARD", "value": "STANDARD"}],
                }
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        # Create existing enums file
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\n"
            "class ItemType(StrEnum):\n"
            "    STANDARD = 'STANDARD'\n"
        )

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is None  # All enums already exist

    def _setup_enums(
        self,
        project_root: Any,
        config: Any,
        minimal_model: dict[str, Any],
        enums_data: Any,
    ) -> Path:
        """Helper: create model file and shared enums.json, return model_file path."""
        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))
        assert isinstance(model_file, Path)
        return model_file

    def test_create_mode_includes_imports(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Create mode output includes StrEnum import."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                }
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)
        assert result is not None
        assert "from enum import StrEnum" in result["content"]

    def test_create_mode_includes_section_header(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Create mode output includes ENUMS section divider."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                }
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_append_content_starts_with_newline(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Append mode content starts with newline separator."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                },
                "OtherType": {
                    "description": "Other",
                    "values": [{"name": "B", "value": "B"}],
                },
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\nclass ItemType(StrEnum):\n    A = 'A'\n"
        )
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)
        assert result is not None
        assert result["content"].startswith("\n")

    def test_append_includes_enums_section_header(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Append mode content includes ENUMS section divider."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                },
                "OtherType": {
                    "description": "Other",
                    "values": [{"name": "B", "value": "B"}],
                },
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\nclass ItemType(StrEnum):\n    A = 'A'\n"
        )
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert isinstance(result, dict)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_no_enums_prints_message(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When no enums file exists, prints informational message."""
        project_root, config, env = project_env
        models_dir = project_root / "models"
        models_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))
        # No _shared dir → load_shared_enums returns {}

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        captured = capsys.readouterr()
        assert result is None
        expected = "  ℹ️  No enums found in models/_shared/enums.json"
        assert captured.out.rstrip("\n") == expected


class TestConstraintsGenerator:
    """Test constraint generation."""

    def test_no_constraints_returns_none(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Model without constraints returns None."""
        project_root, config, env = project_env
        # No _shared/constraints.json and no field constraints
        result = generate_constraints(minimal_model, config, env, project_root)
        assert result is None

    def test_generates_constraints(self, project_env: Any) -> None:
        """Model with constraint refs generates constraints file."""
        project_root, config, env = project_env

        model = {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "label": {
                            "type": "text",
                            "max_length": 50,
                            "required": True,
                            "constraints": [
                                {"type": "length", "min_ref": "LABEL_MIN_LENGTH"}
                            ],
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        # Create shared constraints
        shared_dir = project_root / "models" / "_shared"
        shared_dir.mkdir(parents=True)
        constraints_data = {
            "constraints": {
                "LABEL": {
                    "description": "Label length constraints",
                    "min": {
                        "name": "LABEL_MIN_LENGTH",
                        "type": "length",
                        "value": 2,
                        "description": "Minimum label length",
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints_data))

        original_cwd = os.getcwd()
        os.chdir(project_root)
        try:
            result = generate_constraints(model, config, env, project_root)
            assert isinstance(result, dict)
        finally:
            os.chdir(original_cwd)

        assert result is not None
        assert "LABEL_MIN_LENGTH" in result["content"]
        assert result["mode"] == "write"
        output_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == output_dir / "constraints.py"
        assert result["new_count"] == 1
        assert result["skipped"] == 0
        assert "# CONSTRAINTS" in result["content"]
        assert "from decimal import Decimal" in result["content"]
        # Helper functions are not emitted (they were never imported by any
        # generated file; SQL CHECKs are inlined in model.py.j2).
        assert "def validate_percentage" not in result["content"]

    def test_append_mode_for_existing_file(self, project_env: Any) -> None:
        """When constraints.py already exists, new refs are appended, not full file."""
        project_root, config, env = project_env

        model = {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "price": {
                            "type": "decimal",
                            "constraints": [
                                {
                                    "type": "decimal",
                                    "min_ref": "PRICE_MIN",
                                    "max_ref": "PRICE_MAX",
                                }
                            ],
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        shared_dir = project_root / "models" / "_shared"
        shared_dir.mkdir(parents=True)
        constraints_data: dict[str, Any] = {"constraints": {}}
        (shared_dir / "constraints.json").write_text(json.dumps(constraints_data))

        # Create an existing constraints.py (but without the refs we need)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True, exist_ok=True)
        constraints_file = output_dir / "constraints.py"
        constraints_file.write_text("# existing\nSOME_OTHER = 1\n")

        original_cwd = os.getcwd()
        os.chdir(project_root)
        try:
            result = generate_constraints(model, config, env, project_root)
            assert isinstance(result, dict)
        finally:
            os.chdir(original_cwd)

        assert result is not None
        assert result["mode"] == "append"
        assert result["path"] == constraints_file
        assert result["content"].startswith("\n")
        assert result["new_count"] == 2
        assert result["skipped"] == 0
        assert "# CONSTRAINTS" in result["content"]
        # Helpers should NOT be included when appending
        assert "validate_percentage" not in result["content"]


class TestConstraintExtraction:
    """Unit tests for constraint extraction helpers."""

    def _make_refs(self) -> tuple[list[Any], set[Any]]:
        return [], set()

    def test_extract_ref_type_from_ref_def(self) -> None:
        """When ref_def has 'type', it takes priority over constraint type."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF", "type": "decimal"},
            "min_ref",
            {"MY_REF": {"type": "length", "value": 3}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "length"

    def test_extract_ref_type_from_constraint(self) -> None:
        """When ref_def lacks 'type', falls back to constraint type."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF", "type": "range"},
            "min_ref",
            {"MY_REF": {}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "range"

    def test_extract_ref_type_default_decimal(self) -> None:
        """When neither ref_def nor constraint has 'type', defaults to 'decimal'."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF"},
            "min_ref",
            {"MY_REF": {}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "decimal"

    def test_extract_regex_ref_unknown_ref_ok(self) -> None:
        """When regex_ref is not in shared_constraints, falls back to empty dict."""
        refs, seen = self._make_refs()
        _extract_regex_ref(
            {"regex_ref": "UNKNOWN_PATTERN"},
            {},
            "my_field",
            refs,
            seen,
        )
        assert len(refs) == 1
        assert refs[0]["field"] == "my_field"
        assert refs[0]["name"] == "UNKNOWN_PATTERN"

    def test_extract_regex_ref_deduplication(self) -> None:
        """Same regex_ref is only extracted once."""
        refs, seen = self._make_refs()
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field1", refs, seen)
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field2", refs, seen)
        assert len(refs) == 1

    def test_extract_constraint_refs_field_name_propagates(self) -> None:
        """Field name from model is correctly propagated to extracted refs."""
        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "price": {
                            "constraints": [{"type": "decimal", "min_ref": "PRICE_MIN"}]
                        }
                    }
                }
            }
        }
        refs = extract_constraint_refs(model, {})
        assert len(refs) == 1
        assert refs[0]["field"] == "price"
