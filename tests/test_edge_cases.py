"""Tests for edge cases: missing files, invalid JSON, partial generation."""

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from model_generator.generate import generate, load_model
from model_generator.utils.loaders import (
    deep_merge,
    load_config,
    load_shared_constraints,
    load_shared_enums,
)
from model_generator.utils.parser import scan_api_model_files, scan_model_files
from model_generator.utils.quality import _find_ruff, run_quality_tools


class TestLoadModelEdgeCases:
    """Test model loading edge cases."""

    def test_json_with_comments(self, tmp_path: Path) -> None:
        """Model files with // comments should parse correctly."""
        model_content = """{
    // This is a comment
    "domain": "test",
    "description": "Test domain",
    "entities": {
        "TestEntity": {
            "table": "test_entities",
            "fields": {
                "id": {"type": "uuid", "primary_key": true}  // inline comment
            }
        }
    }
}"""
        model_path = tmp_path / "test.model.json"
        model_path.write_text(model_content)

        data = load_model(model_path)
        assert data["domain"] == "test"
        assert "TestEntity" in data["entities"]

    def test_invalid_json_exits(self, tmp_path: Path) -> None:
        """Malformed JSON should cause sys.exit."""
        model_path = tmp_path / "bad.model.json"
        model_path.write_text("{invalid json content")

        with pytest.raises(SystemExit):
            load_model(model_path)

    def test_empty_entities(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Model with empty entities dict should load (with validation warning)."""
        model = {
            "domain": "empty",
            "description": "Empty domain",
            "entities": {},
        }
        model_path = tmp_path / "empty.model.json"
        model_path.write_text(json.dumps(model))

        data = load_model(model_path)
        assert data["domain"] == "empty"
        assert data["entities"] == {}

    def test_invalid_json_exits_with_code_1(self, tmp_path: Path) -> None:
        """sys.exit is called with exit code 1 on malformed JSON."""
        model_path = tmp_path / "bad.model.json"
        model_path.write_text("{invalid json content")

        with pytest.raises(SystemExit) as exc_info:
            load_model(model_path)
        assert exc_info.value.code == 1

    def test_error_on_last_line_is_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Error on the last line (lineno == len(lines)) still prints the line."""
        model_path = tmp_path / "bad.model.json"
        # Single-line JSON with trailing comma: error is at lineno=1, len(lines)=1
        model_path.write_text('{"key": 1,}')

        with pytest.raises(SystemExit):
            load_model(model_path)
        captured = capsys.readouterr()
        assert "Line 1:" in captured.out

    def test_error_line_content_is_correct_line(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prints e.lineno-1 index (correct line), not e.lineno-2 (previous line)."""
        model_path = tmp_path / "bad.model.json"
        # Error is on line 2; line 1 is "{", line 2 is '  "bad": ,'
        model_path.write_text('{\n  "bad": ,\n}')

        with pytest.raises(SystemExit):
            load_model(model_path)
        captured = capsys.readouterr()
        assert '"bad": ,' in captured.out


class TestLoadConfigEdgeCases:
    """Test config loading edge cases."""

    def test_missing_project_config_uses_defaults(self, tmp_path: Path) -> None:
        """When no .model-generator.yaml exists, stack defaults are used."""
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # No .model-generator.yaml exists
            config = load_config("python-fastapi")
            assert "paths" in config
            assert "project" in config
        finally:
            os.chdir(original_cwd)

    def test_default_stack_arg_is_python_fastapi(self, tmp_path: Path) -> None:
        """Calling load_config() with no args uses 'python-fastapi' as default."""
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config()  # default stack argument
            assert "paths" in config
        finally:
            os.chdir(original_cwd)

    def test_project_config_stack_key_is_used(self, tmp_path: Path) -> None:
        """'stack' key in .model-generator.yaml overrides the function default."""
        (tmp_path / ".model-generator.yaml").write_text(
            yaml.dump({"stack": "python-fastapi"})
        )
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Would fail if "stack" key is not read from project config
            config = load_config("WRONG-STACK")
            assert "paths" in config
        finally:
            os.chdir(original_cwd)

    def test_paths_base_derives_from_overridden_database_models(
        self, tmp_path: Path
    ) -> None:
        """If project config overrides paths.database_models but not paths.base,
        the merged config derives paths.base from the new database_models —
        without this, the stack default's paths.base wins on deep-merge and
        the two paths diverge (silent broken state caught by _validate_paths_base).
        """
        (tmp_path / ".model-generator.yaml").write_text(
            yaml.dump(
                {
                    "stack": "python-fastapi",
                    "paths": {"database_models": "lib/db/models"},
                }
            )
        )
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["paths"]["base"] == "lib/db/models/base.py"
            assert config["paths"]["database_models"] == "lib/db/models"
        finally:
            os.chdir(original_cwd)

    def test_paths_base_explicit_override_is_preserved(self, tmp_path: Path) -> None:
        """If project config sets paths.base explicitly, the loader does not
        rewrite it — even when paths.database_models is also overridden."""
        (tmp_path / ".model-generator.yaml").write_text(
            yaml.dump(
                {
                    "stack": "python-fastapi",
                    "paths": {
                        "database_models": "lib/db/models",
                        "base": "lib/db/models/base.py",  # explicit
                    },
                }
            )
        )
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["paths"]["base"] == "lib/db/models/base.py"
        finally:
            os.chdir(original_cwd)

    def test_default_project_keys_inserted(self, tmp_path: Path) -> None:
        """When stack config has no 'project' key, sensible defaults are inserted."""
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["project"]["name"] == "Your Project"
            assert config["project"]["description"] == (
                "Database models and API for your application"
            )
            assert config["project"]["version"] == "0.1.0"
        finally:
            os.chdir(original_cwd)

    def test_default_generation_layout_inserted(self, tmp_path: Path) -> None:
        """When project config does not pin generation.layout, default is per-entity."""
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["generation"]["layout"] == "per-entity"
        finally:
            os.chdir(original_cwd)

    def test_project_config_can_pin_generation_layout(self, tmp_path: Path) -> None:
        """generation.layout in .model-generator.yaml overrides the default."""
        (tmp_path / ".model-generator.yaml").write_text(
            yaml.dump({"generation": {"layout": "per-domain"}})
        )
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["generation"]["layout"] == "per-domain"
        finally:
            os.chdir(original_cwd)

    def test_project_config_overrides_stack(self, tmp_path: Path) -> None:
        """Project config overrides stack defaults."""
        project_config = {
            "stack": "python-fastapi",
            "paths": {"database_models": "custom/db/models"},
        }
        (tmp_path / ".model-generator.yaml").write_text(yaml.dump(project_config))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            config = load_config("python-fastapi")
            assert config["paths"]["database_models"] == "custom/db/models"
        finally:
            os.chdir(original_cwd)

    def test_invalid_stack_exits_with_code_1(self, tmp_path: Path) -> None:
        """load_config with non-existent stack exits with code 1."""
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with pytest.raises(SystemExit) as exc_info:
                load_config("nonexistent-stack-xyz")
            assert exc_info.value.code == 1
        finally:
            os.chdir(original_cwd)


class TestDeepMerge:
    """Test deep merge utility."""

    def test_override_wins(self) -> None:
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_non_overlapping_keys(self) -> None:
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_merge(self) -> None:
        base = {"nested": {"x": 1, "y": 2}}
        override = {"nested": {"y": 3, "z": 4}}
        result = deep_merge(base, override)
        assert result == {"nested": {"x": 1, "y": 3, "z": 4}}

    def test_override_dict_with_non_dict(self) -> None:
        """Non-dict override replaces dict."""
        result = deep_merge({"a": {"b": 1}}, {"a": "flat"})
        assert result == {"a": "flat"}

    def test_empty_base(self) -> None:
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_empty_override(self) -> None:
        assert deep_merge({"a": 1}, {}) == {"a": 1}


class TestValidateModelSchema:
    """Test _validate_model_schema warning output."""

    def test_validation_error_path_uses_arrow_separator(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Validation warning joins path components with ' -> '."""
        from collections import deque

        import jsonschema

        model = {"domain": "test", "entities": {}}
        model_path = tmp_path / "test.model.json"
        model_path.write_text(json.dumps(model))

        mock_error = jsonschema.ValidationError(
            "Invalid value",
            path=deque(["entities", "Foo"]),
        )
        with patch(
            "model_generator.utils.loaders.jsonschema.validate",
            side_effect=mock_error,
        ):
            load_model(model_path)

        captured = capsys.readouterr()
        assert " -> " in captured.out
        assert "entities -> Foo" in captured.out

    def test_validation_error_path_uses_str_of_component(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Path components are converted with str(), not replaced with None."""
        from collections import deque

        import jsonschema

        model = {"domain": "test", "entities": {}}
        model_path = tmp_path / "test.model.json"
        model_path.write_text(json.dumps(model))

        mock_error = jsonschema.ValidationError(
            "Some error",
            path=deque(["my_field"]),
        )
        with patch(
            "model_generator.utils.loaders.jsonschema.validate",
            side_effect=mock_error,
        ):
            load_model(model_path)

        captured = capsys.readouterr()
        assert "my_field" in captured.out
        assert "None" not in captured.out


class TestLoadSharedEnums:
    """Test shared enum loading."""

    def test_no_shared_dir(self, tmp_path: Path) -> None:
        """Returns empty dict when _shared/enums.json doesn't exist."""
        result = load_shared_enums(tmp_path / "nonexistent.json")
        assert result == {}

    def test_loads_enums(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        enums = {
            "enums": {"Status": {"values": [{"name": "ACTIVE", "value": "ACTIVE"}]}}
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums))

        # Create a model file so is_file() returns True
        model_file = tmp_path / "model.json"
        model_file.write_text("{}")
        result = load_shared_enums(model_file)
        assert "Status" in result

    def test_loads_from_directory(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        enums = {"enums": {"Color": {"values": [{"name": "RED", "value": "RED"}]}}}
        (shared_dir / "enums.json").write_text(json.dumps(enums))

        result = load_shared_enums(tmp_path)  # Pass directory, not file
        assert "Color" in result

    def test_no_enums_key_returns_empty(self, tmp_path: Path) -> None:
        """JSON without 'enums' key returns {} (not None)."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        (shared_dir / "enums.json").write_text(json.dumps({"other_key": {}}))
        result = load_shared_enums(tmp_path)
        assert result == {}


class TestLoadSharedConstraints:
    """Test shared constraint loading."""

    def test_no_constraints_file(self, tmp_path: Path) -> None:
        result = load_shared_constraints(tmp_path)
        assert result == {}

    def test_loads_constraints(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "models" / "_shared"
        shared_dir.mkdir(parents=True)
        constraints = {
            "constraints": {
                "USERNAME": {
                    "description": "Username constraints",
                    "min": {
                        "name": "USERNAME_MIN_LENGTH",
                        "type": "length",
                        "value": 3,
                    },
                    "max": {
                        "name": "USERNAME_MAX_LENGTH",
                        "type": "length",
                        "value": 50,
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))

        result = load_shared_constraints(tmp_path / "models")
        assert "USERNAME_MIN_LENGTH" in result
        assert "USERNAME_MAX_LENGTH" in result
        assert result["USERNAME_MIN_LENGTH"]["value"] == 3

    def test_loads_pattern_constraint(self, tmp_path: Path) -> None:
        """Constraints with a 'pattern' key are included in results."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        constraints = {
            "constraints": {
                "EMAIL": {
                    "description": "Email format",
                    "pattern": {
                        "name": "EMAIL_PATTERN",
                        "type": "regex",
                        "value": r"^[^@]+@[^@]+\.[^@]+$",
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))
        result = load_shared_constraints(tmp_path)
        assert "EMAIL_PATTERN" in result
        assert result["EMAIL_PATTERN"]["type"] == "regex"

    def test_constraint_type_and_description_from_defn(self, tmp_path: Path) -> None:
        """Result has 'type' key and 'description' taken from defn when present."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        constraints = {
            "constraints": {
                "USERNAME": {
                    "description": "Group-level description",
                    "min": {
                        "name": "USERNAME_MIN",
                        "type": "length",
                        "value": 3,
                        "description": "Min length for username",
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))
        result = load_shared_constraints(tmp_path)
        assert result["USERNAME_MIN"]["type"] == "length"
        assert result["USERNAME_MIN"]["description"] == "Min length for username"

    def test_constraint_description_falls_back_to_group(self, tmp_path: Path) -> None:
        """description falls back to group-level when not in defn."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        constraints = {
            "constraints": {
                "USERNAME": {
                    "description": "Group description",
                    "min": {
                        "name": "USERNAME_MIN",
                        "type": "length",
                        "value": 3,
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))
        result = load_shared_constraints(tmp_path)
        assert result["USERNAME_MIN"]["description"] == "Group description"

    def test_no_constraints_key_returns_empty(self, tmp_path: Path) -> None:
        """JSON without 'constraints' key returns {} (not crash)."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        (shared_dir / "constraints.json").write_text(json.dumps({"other": {}}))
        result = load_shared_constraints(tmp_path)
        assert result == {}

    def test_loads_constraints_when_given_file_path(self, tmp_path: Path) -> None:
        """load_shared_constraints resolves _shared/ relative to a file's parent."""
        model_file = tmp_path / "model.json"
        model_file.write_text("{}")
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        constraints = {
            "constraints": {
                "NAME": {
                    "description": "Name constraints",
                    "min": {
                        "name": "NAME_MIN",
                        "type": "length",
                        "value": 3,
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))

        result = load_shared_constraints(model_file)
        assert "NAME_MIN" in result

    def test_description_empty_string_when_no_description_anywhere(
        self, tmp_path: Path
    ) -> None:
        """description defaults to '' when neither defn nor group has a description."""
        shared_dir = tmp_path / "_shared"
        shared_dir.mkdir()
        constraints = {
            "constraints": {
                "NAME": {
                    "min": {
                        "name": "NAME_MIN",
                        "type": "length",
                        "value": 3,
                    }
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints))

        result = load_shared_constraints(tmp_path)
        assert result["NAME_MIN"]["description"] == ""


class TestScanModelFiles:
    """Test model file scanning."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = scan_model_files(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        result = scan_model_files(tmp_path / "nonexistent")
        assert result == []

    def test_skips_special_files(self, tmp_path: Path) -> None:
        """__init__.py, base.py, constraints.py, enums.py are skipped."""
        for name in ["__init__.py", "base.py", "constraints.py", "enums.py"]:
            (tmp_path / name).write_text("# skip me")

        result = scan_model_files(tmp_path)
        assert result == []

    @pytest.mark.parametrize(
        "name", ["__init__.py", "base.py", "constraints.py", "enums.py"]
    )
    def test_skips_each_special_file_even_with_base_class(
        self, tmp_path: Path, name: Any
    ) -> None:
        """Each skip file is ignored even if it defines a Base-inheriting class."""
        (tmp_path / name).write_text("class Foo(Base):\n    pass\n")
        result = scan_model_files(tmp_path)
        assert result == []

    def test_continue_on_skip_not_break(self, tmp_path: Path) -> None:
        """Files after a skip file must still be processed (continue, not break)."""
        (tmp_path / "base.py").write_text("class B(Base):\n    pass\n")
        (tmp_path / "items.py").write_text("class Item(Base):\n    pass\n")
        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "items"

    def test_finds_model_classes(self, tmp_path: Path) -> None:
        (tmp_path / "users.py").write_text(
            "from .base import Base\n\nclass User(Base):\n    __tablename__ = 'users'\n"
        )

        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "users"
        assert result[0]["file"] == "users"
        assert "User" in result[0]["entities"]

    def test_ignores_non_base_classes(self, tmp_path: Path) -> None:
        """Classes without a Base superclass must not be collected."""
        (tmp_path / "helpers.py").write_text("class Helper:\n    pass\n")
        result = scan_model_files(tmp_path)
        assert result == []

    def test_ignores_non_base_superclass(self, tmp_path: Path) -> None:
        """Classes inheriting from a non-Base name must not be collected."""
        (tmp_path / "items.py").write_text("class Item(BaseModel):\n    pass\n")
        result = scan_model_files(tmp_path)
        assert result == []

    def test_extracts_section_header(self, tmp_path: Path) -> None:
        """Section header comment is extracted and returned as section."""
        (tmp_path / "users.py").write_text(
            "# ==================================\n"
            "# USERS\n"
            "class User(Base):\n"
            "    pass\n"
        )
        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["section"] == "USERS"
        assert result[0]["file"] == "users"

    def test_section_none_when_no_header(self, tmp_path: Path) -> None:
        """section is None when no section comment is present."""
        (tmp_path / "items.py").write_text("class Item(Base):\n    pass\n")
        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["section"] is None

    def test_skips_syntax_errors(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("def incomplete(")
        result = scan_model_files(tmp_path)
        assert result == []

    def test_continues_after_syntax_error(self, tmp_path: Path) -> None:
        """A file with a syntax error must not stop processing of later files."""
        (tmp_path / "broken.py").write_text("def incomplete(")
        (tmp_path / "valid.py").write_text("class Item(Base):\n    pass\n")
        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "valid"

    def test_continues_after_general_exception(self, tmp_path: Path) -> None:
        """A file raising a non-SyntaxError Exception must not stop later files."""
        # Invalid UTF-8 bytes cause UnicodeDecodeError on read_text(), caught by
        # `except Exception` — "aaa_" prefix ensures it sorts before "valid.py"
        broken = tmp_path / "aaa_broken.py"
        broken.write_bytes(b"\xff\xfe invalid utf-8 content")
        (tmp_path / "valid.py").write_text("class Item(Base):\n    pass\n")

        result = scan_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "valid"


class TestScanApiModelFiles:
    """Test API model file scanning."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = scan_api_model_files(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        result = scan_api_model_files(tmp_path / "nonexistent")
        assert result == []

    def test_finds_response_models(self, tmp_path: Path) -> None:
        (tmp_path / "users_response.py").write_text(
            "from pydantic import BaseModel\n\n"
            "class UserResponse(BaseModel):\n"
            "    pass\n"
        )

        result = scan_api_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "users"
        assert "UserResponse" in result[0]["response_models"]

    def test_finds_request_models(self, tmp_path: Path) -> None:
        (tmp_path / "users_requests.py").write_text(
            "from pydantic import BaseModel\n\n"
            "class CreateUserRequest(BaseModel):\n"
            "    pass\n"
            "class UpdateUserRequest(BaseModel):\n"
            "    pass\n"
        )

        result = scan_api_model_files(tmp_path)
        assert len(result) == 1
        assert "CreateUserRequest" in result[0]["request_models"]
        assert "UpdateUserRequest" in result[0]["request_models"]

    def test_skips_init_py_even_with_response_class(self, tmp_path: Path) -> None:
        """__init__.py is ignored even if it defines a Response class."""
        (tmp_path / "__init__.py").write_text("class InitResponse:\n    pass\n")
        result = scan_api_model_files(tmp_path)
        assert result == []

    def test_section_value_format(self, tmp_path: Path) -> None:
        """section is 'DOMAIN MODELS' with underscores replaced by spaces, UPPERCASE."""
        (tmp_path / "user_types_response.py").write_text(
            "class UserTypeResponse:\n    pass\n"
        )
        result = scan_api_model_files(tmp_path)
        assert len(result) == 1
        assert result[0]["section"] == "USER TYPES MODELS"

    def test_finds_response_models_section_key(self, tmp_path: Path) -> None:
        """Result dict has 'section' key (not 'SECTION' or 'XXsectionXX')."""
        (tmp_path / "users_response.py").write_text("class UserResponse:\n    pass\n")
        result = scan_api_model_files(tmp_path)
        assert len(result) == 1
        assert "section" in result[0]
        assert result[0]["section"] == "USERS MODELS"

    def test_init_py_skip_does_not_stop_domain_discovery(self, tmp_path: Path) -> None:
        """__init__.py being skipped uses continue, not break, so other files found."""
        (tmp_path / "__init__.py").touch()
        (tmp_path / "users_response.py").write_text("class UserResponse:\n    pass\n")
        # Force __init__.py first in the glob iteration order
        original_glob = Path.glob

        def sorted_init_first(self: Any, pattern: Any) -> list[Path]:
            files = list(original_glob(self, pattern))
            return sorted(files, key=lambda f: 0 if f.name == "__init__.py" else 1)

        with patch.object(Path, "glob", sorted_init_first):
            result = scan_api_model_files(tmp_path)

        assert len(result) == 1
        assert result[0]["name"] == "users"


class TestPartialGeneration:
    """Test generating specific targets only."""

    def test_database_only(self, tmp_path: Path) -> None:
        """Generate only database target."""
        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "generation": {"layout": "per-domain"},
            "paths": {
                "database_models": "src/db/models",
                "factories": "src/db/models/factories",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
                "base": "src/db/models/base.py",
                "engine": "src/db/engine.py",
                "main": "src/main.py",
                "errors": "src/api/errors.py",
                "validators": "src/api/validators.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }
        (tmp_path / ".model-generator.yaml").write_text(yaml.dump(config))

        model = {
            "domain": "widgets",
            "entities": {
                "Widget": {
                    "table": "widgets",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "required": True, "max_length": 100},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "widgets.model.json"
        model_path.write_text(json.dumps(model))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate(model_path=model_path, target="database")

            # Database model should exist
            assert (tmp_path / "src/db/models/widgets.py").exists()
            # API routes should NOT exist
            assert not (tmp_path / "src/api/routes/widgets.py").exists()
        finally:
            os.chdir(original_cwd)

    def test_api_tests_only(self, tmp_path: Path) -> None:
        """Generate only api-tests target."""
        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "generation": {"layout": "per-domain"},
            "paths": {
                "database_models": "src/db/models",
                "factories": "src/db/models/factories",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
                "base": "src/db/models/base.py",
                "engine": "src/db/engine.py",
                "main": "src/main.py",
                "errors": "src/api/errors.py",
                "validators": "src/api/validators.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }
        (tmp_path / ".model-generator.yaml").write_text(yaml.dump(config))

        model = {
            "domain": "widgets",
            "entities": {
                "Widget": {
                    "table": "widgets",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "required": True, "max_length": 100},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "widgets.model.json"
        model_path.write_text(json.dumps(model))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate(model_path=model_path, target="api-tests")

            # Test file should exist
            assert (tmp_path / "tests/api/test_widgets_api.py").exists()
            # Database model should NOT exist
            assert not (tmp_path / "src/db/models/widgets.py").exists()
        finally:
            os.chdir(original_cwd)


class TestConstraintExtraction:
    """Test constraint reference extraction from models."""

    def test_extract_refs(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "name": {
                            "type": "text",
                            "constraints": [{"type": "length", "min_ref": "NAME_MIN"}],
                        }
                    }
                }
            }
        }
        shared = {"NAME_MIN": {"type": "length", "value": 3}}
        refs = extract_constraint_refs(model, shared)
        assert len(refs) == 1
        assert refs[0]["name"] == "NAME_MIN"
        assert refs[0]["value"] == 3

    def test_no_duplicate_refs(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model = {
            "entities": {
                "A": {
                    "fields": {
                        "x": {
                            "type": "text",
                            "constraints": [{"type": "length", "min_ref": "SAME_REF"}],
                        },
                        "y": {
                            "type": "text",
                            "constraints": [{"type": "length", "min_ref": "SAME_REF"}],
                        },
                    }
                }
            }
        }
        shared = {"SAME_REF": {"type": "length", "value": 1}}
        refs = extract_constraint_refs(model, shared)
        assert len(refs) == 1  # Deduplicated

    def test_no_entities_key_returns_empty(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        refs = extract_constraint_refs({}, {})
        assert refs == []

    def test_entity_without_fields_returns_empty(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model: dict[str, Any] = {"entities": {"Thing": {}}}
        refs = extract_constraint_refs(model, {})
        assert refs == []

    def test_is_min_distinguishes_min_from_max(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "price": {
                            "type": "decimal",
                            "constraints": [
                                {
                                    "type": "decimal",
                                    "min_ref": "PRICE_MIN",
                                    "max_ref": "PRICE_MAX",
                                }
                            ],
                        }
                    }
                }
            }
        }
        refs = extract_constraint_refs(model, {})
        assert len(refs) == 2
        min_ref = next(r for r in refs if r["name"] == "PRICE_MIN")
        max_ref = next(r for r in refs if r["name"] == "PRICE_MAX")
        assert min_ref["is_min"] is True
        assert min_ref["field"] == "price"
        assert max_ref["is_min"] is False
        assert max_ref["field"] == "price"

    def test_extract_ref_type_from_shared(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "name": {
                            "type": "text",
                            "constraints": [{"type": "length", "min_ref": "NAME_MIN"}],
                        }
                    }
                }
            }
        }
        shared = {"NAME_MIN": {"type": "length", "value": 3, "description": "Min name"}}
        refs = extract_constraint_refs(model, shared)
        assert len(refs) == 1
        assert refs[0]["type"] == "length"
        assert refs[0]["is_min"] is True
        assert refs[0]["field"] == "name"
        assert refs[0]["description"] == "Min name"

    def test_regex_ref_extracted_correctly(self) -> None:
        from model_generator.generators.constraints import extract_constraint_refs

        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "code": {
                            "type": "text",
                            "constraints": [{"regex_ref": "CODE_PATTERN"}],
                        }
                    }
                }
            }
        }
        shared = {
            "CODE_PATTERN": {
                "value": r"^[A-Z]{3}$",
                "description": "Three uppercase letters",
            }
        }
        refs = extract_constraint_refs(model, shared)
        assert len(refs) == 1
        assert refs[0]["name"] == "CODE_PATTERN"
        assert refs[0]["type"] == "pattern"
        assert refs[0]["field"] == "code"
        assert refs[0]["value"] == r"^[A-Z]{3}$"
        assert refs[0]["description"] == "Three uppercase letters"


class TestEnumParsing:
    """Test existing enum file parsing."""

    def test_get_existing_enums(self, tmp_path: Path) -> None:
        from model_generator.generators.enums import get_existing_enums

        (tmp_path / "enums.py").write_text(
            "from enum import StrEnum\n\n"
            "class UserStatus(StrEnum):\n"
            "    ACTIVE = 'ACTIVE'\n\n"
            "class OrderType(StrEnum):\n"
            "    BUY = 'BUY'\n"
        )

        result = get_existing_enums(tmp_path / "enums.py")
        assert result == {"UserStatus", "OrderType"}

    def test_no_existing_file(self, tmp_path: Path) -> None:
        from model_generator.generators.enums import get_existing_enums

        result = get_existing_enums(tmp_path / "nonexistent.py")
        assert result == set()


class TestConstraintParsing:
    """Test existing constraint file parsing."""

    def test_get_existing_constraints(self, tmp_path: Path) -> None:
        from model_generator.generators.constraints import get_existing_constraints

        (tmp_path / "constraints.py").write_text(
            "USERNAME_MIN_LENGTH = 3\n"
            "USERNAME_MAX_LENGTH = 50\n"
            "# Not a constant\n"
            "some_var = 'nope'\n"
        )

        result = get_existing_constraints(tmp_path / "constraints.py")
        assert "USERNAME_MIN_LENGTH" in result
        assert "USERNAME_MAX_LENGTH" in result
        assert "some_var" not in result  # Doesn't match ALL_CAPS pattern

    def test_no_existing_file(self, tmp_path: Path) -> None:
        from model_generator.generators.constraints import get_existing_constraints

        result = get_existing_constraints(tmp_path / "nonexistent.py")
        assert result == set()


class TestFindRuff:
    """Test _find_ruff venv discovery."""

    def test_finds_dotenv_ruff(self, tmp_path: Path) -> None:
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / ".venv" / "bin" / "ruff").touch()
        assert _find_ruff(tmp_path) == str(tmp_path / ".venv" / "bin" / "ruff")

    def test_finds_venv_ruff(self, tmp_path: Path) -> None:
        (tmp_path / "venv" / "bin").mkdir(parents=True)
        (tmp_path / "venv" / "bin" / "ruff").touch()
        assert _find_ruff(tmp_path) == str(tmp_path / "venv" / "bin" / "ruff")

    def test_prefers_dotenv_over_venv(self, tmp_path: Path) -> None:
        for venv in [".venv", "venv"]:
            (tmp_path / venv / "bin").mkdir(parents=True)
            (tmp_path / venv / "bin" / "ruff").touch()
        assert _find_ruff(tmp_path) == str(tmp_path / ".venv" / "bin" / "ruff")

    def test_falls_back_to_system_ruff(self, tmp_path: Path) -> None:
        assert _find_ruff(tmp_path) == "ruff"


class TestRunQualityTools:
    """Test run_quality_tools subprocess invocations."""

    def test_returns_early_for_empty_files(self) -> None:
        with patch("model_generator.utils.quality.subprocess.run") as mock_run:
            run_quality_tools({}, Path("/tmp"), [])
        mock_run.assert_not_called()

    def test_runs_format_and_check(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.py"
        file2 = tmp_path / "b.py"
        expected_paths = f"{file1} {file2}"
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch("model_generator.utils.quality._find_ruff", return_value="ruff"),
        ):
            run_quality_tools({}, tmp_path, [file1, file2])
        assert mock_run.call_count == 2
        format_cmd = mock_run.call_args_list[0].args[0]
        check_cmd = mock_run.call_args_list[1].args[0]
        assert format_cmd == f"ruff format {expected_paths}"
        assert check_cmd == f"ruff check --fix {expected_paths}"

    def test_subprocess_cwd_and_capture(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.py"
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch("model_generator.utils.quality._find_ruff", return_value="ruff"),
        ):
            run_quality_tools({}, tmp_path, [file1])
        for c in mock_run.call_args_list:
            assert c.kwargs["shell"] is True
            assert c.kwargs["cwd"] == tmp_path
            assert c.kwargs["capture_output"] is True

    def test_prints_progress_messages(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Prints exact status messages before each ruff command."""
        file1 = tmp_path / "a.py"
        with (
            patch("model_generator.utils.quality.subprocess.run"),
            patch("model_generator.utils.quality._find_ruff", return_value="ruff"),
        ):
            run_quality_tools({}, tmp_path, [file1])
        captured = capsys.readouterr()
        expected = "\n  Running ruff format...\n  Running ruff check --fix...\n"
        assert captured.out == expected
