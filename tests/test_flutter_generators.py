"""Tests for the Flutter (Dart) stack generators — Phase 1.

Renders the Phase-1 templates against fixture specs and asserts the emitted Dart
is correct (freezed classes, JsonKey/JsonValue annotations, the abstract→Dart
type table, camelCase fields, nullability) AND project-agnostic (no hardcoded
entity names, paths, or imports leak into the templates).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.generators.flutter import (
    FLUTTER_STACK,
    generate_converters,
    generate_flutter_enums,
    generate_flutter_models,
    generate_flutter_models_index,
    generate_pubspec,
)
from model_generator.generators.flutter.fields import resolve_fields
from model_generator.generators.flutter.paths import resolve_path
from model_generator.generators.registry import STACKS, get_stack
from model_generator.utils.templates import get_template_env

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_STACK_CONFIG_PATH = (
    Path(__file__).parent.parent
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


@pytest.fixture
def model() -> dict[str, Any]:
    """A small multi-type fixture spec exercising every type-table row."""
    return {
        "domain": "catalog",
        "entities": {
            "Widget": {
                "table": "widgets",
                "description": "A catalog widget.",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True},
                    "owner_id": {
                        "type": "reference",
                        "reference_table": "users",
                        "required": True,
                    },
                    "display_name": {
                        "type": "text",
                        "max_length": 100,
                        "required": True,
                    },
                    "notes": {"type": "longtext"},
                    "unit_price": {"type": "financial", "required": True},
                    "discount_rate": {"type": "percentage"},
                    "view_count": {"type": "counter", "default": 0},
                    "is_active": {"type": "boolean", "default": True},
                    "released_at": {"type": "datetime"},
                    "thumbnail": {"type": "binary"},
                    "status": {
                        "type": "enum",
                        "enum_name": "WidgetStatus",
                        "default": "ACTIVE",
                    },
                    "metadata": {"type": "json_object"},
                    "tags": {"type": "json_array", "list_type": "str"},
                    "secret_token": {
                        "type": "text",
                        "required": True,
                        "api_field_name": "token",
                        "api_exclude_response": True,
                    },
                },
            }
        },
    }


@pytest.fixture
def enum_defs() -> dict[str, Any]:
    return {
        "WidgetStatus": {
            "description": "Lifecycle state of a widget.",
            "values": [
                {"name": "ACTIVE", "value": "ACTIVE", "description": "In use."},
                {"name": "ARCHIVED", "value": "ARCHIVED"},
            ],
        }
    }


def _render_models(
    model: dict[str, Any], config: dict[str, Any], env: Any, tmp_path: Path
) -> str:
    outputs = generate_flutter_models(model, config, env, tmp_path)
    assert len(outputs) == 1
    return str(outputs[0]["content"])


# --------------------------------------------------------------------------- #
# Stack registration
# --------------------------------------------------------------------------- #


class TestFlutterRegistration:
    def test_flutter_registered(self) -> None:
        assert "flutter" in STACKS
        assert get_stack("flutter") is FLUTTER_STACK

    def test_domain_targets(self) -> None:
        # Phase 1 targets must remain (Phase 2 appends the api-layer targets).
        for target in ("enums", "models", "models-index"):
            assert target in FLUTTER_STACK.domain_targets

    def test_every_domain_target_has_a_generator(self) -> None:
        for target in FLUTTER_STACK.domain_targets:
            assert target in FLUTTER_STACK.generators

    def test_infra_targets_have_no_domain_generator(self) -> None:
        for target in FLUTTER_STACK.infrastructure_targets:
            assert target not in FLUTTER_STACK.generators

    def test_no_python_only_validators(self) -> None:
        assert FLUTTER_STACK.validators == []
        assert FLUTTER_STACK.infra_validators == []
        assert FLUTTER_STACK.extra_deps_fn is None


# --------------------------------------------------------------------------- #
# Type mapping (abstract -> Dart)
# --------------------------------------------------------------------------- #


class TestTypeMapping:
    def test_resolve_fields_dart_types(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {f["name"]: f for f in resolve_fields(entity, flutter_config)}

        assert by_name["id"]["dart_type"] == "String"
        assert by_name["ownerId"]["dart_type"] == "String"
        assert by_name["displayName"]["dart_type"] == "String"
        assert by_name["notes"]["dart_type"] == "String"
        assert by_name["unitPrice"]["dart_type"] == "Decimal"
        assert by_name["discountRate"]["dart_type"] == "Decimal"
        assert by_name["viewCount"]["dart_type"] == "int"
        assert by_name["isActive"]["dart_type"] == "bool"
        assert by_name["releasedAt"]["dart_type"] == "DateTime"
        assert by_name["thumbnail"]["dart_type"] == "Uint8List"
        assert by_name["status"]["dart_type"] == "WidgetStatus"
        assert by_name["metadata"]["dart_type"] == "Map<String, dynamic>"
        assert by_name["tags"]["dart_type"] == "List<String>"

    def test_json_array_defaults_to_dynamic(
        self, flutter_config: dict[str, Any]
    ) -> None:
        entity = {"fields": {"items": {"type": "json_array"}}}
        field = resolve_fields(entity, flutter_config)[0]
        assert field["dart_type"] == "List<dynamic>"

    def test_converters_assigned(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {f["name"]: f for f in resolve_fields(entity, flutter_config)}
        assert by_name["unitPrice"]["from_json"] == "decimalFromJson"
        assert by_name["unitPrice"]["to_json"] == "decimalToJson"
        assert by_name["releasedAt"]["from_json"] == "utcDateTimeFromJson"
        assert by_name["releasedAt"]["to_json"] == "utcDateTimeToJson"
        assert by_name["thumbnail"]["from_json"] == "bytesFromJson"
        assert by_name["thumbnail"]["to_json"] == "bytesToJson"
        # Enum fields get per-enum fromJson/toJson helpers derived from enum_name.
        assert by_name["status"]["from_json"] == "widgetStatusFromJson"
        assert by_name["status"]["to_json"] == "widgetStatusToJson"
        # Plain types carry no fromJson/toJson helpers.
        assert by_name["displayName"]["from_json"] is None
        assert by_name["viewCount"]["from_json"] is None


# --------------------------------------------------------------------------- #
# Naming & nullability
# --------------------------------------------------------------------------- #


class TestNamingAndNullability:
    def test_camel_case_members(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        names = {f["name"] for f in resolve_fields(entity, flutter_config)}
        assert "ownerId" in names
        assert "displayName" in names
        assert "releasedAt" in names
        # No snake_case leaks into Dart members.
        assert not any("_" in n for n in names)

    def test_json_key_preserves_snake_case(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {f["name"]: f for f in resolve_fields(entity, flutter_config)}
        assert by_name["ownerId"]["json_key"] == "owner_id"
        assert by_name["ownerId"]["needs_json_key"] is True
        # Single-segment names need no JsonKey rename.
        assert by_name["notes"]["needs_json_key"] is False

    def test_api_field_name_overrides_json_key(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {f["name"]: f for f in resolve_fields(entity, flutter_config)}
        assert by_name["secretToken"]["json_key"] == "token"

    def test_nullability(
        self, model: dict[str, Any], flutter_config: dict[str, Any]
    ) -> None:
        entity = model["entities"]["Widget"]
        by_name = {f["name"]: f for f in resolve_fields(entity, flutter_config)}
        # required && in-response -> non-null
        assert by_name["displayName"]["nullable"] is False
        assert by_name["unitPrice"]["nullable"] is False
        # not required -> nullable
        assert by_name["notes"]["nullable"] is True
        assert by_name["releasedAt"]["nullable"] is True
        # required but excluded from response -> nullable (mirrors X | None)
        assert by_name["secretToken"]["nullable"] is True


# --------------------------------------------------------------------------- #
# Rendered model template
# --------------------------------------------------------------------------- #


class TestModelTemplate:
    def test_freezed_class_emitted(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _render_models(model, flutter_config, env, tmp_path)
        assert "@freezed" in content
        assert "abstract class Widget with _$Widget {" in content
        assert "const factory Widget({" in content
        assert "factory Widget.fromJson(Map<String, dynamic> json) =>" in content

    def test_jsonkey_and_converters_rendered(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _render_models(model, flutter_config, env, tmp_path)
        assert "@JsonKey(name: 'owner_id')" in content
        assert "@JsonKey(name: 'token')" in content
        # Decimal fields: combined @JsonKey with name + fromJson/toJson helpers.
        assert "fromJson: decimalFromJson, toJson: decimalToJson" in content
        # DateTime fields: combined @JsonKey with fromJson/toJson helpers.
        assert "fromJson: utcDateTimeFromJson, toJson: utcDateTimeToJson" in content
        # Binary field has no name mismatch; only fromJson/toJson is needed.
        assert "@JsonKey(fromJson: bytesFromJson, toJson: bytesToJson)" in content
        # Enum fields: @JsonKey routes through per-enum fromJson/toJson helpers.
        assert "fromJson: widgetStatusFromJson, toJson: widgetStatusToJson" in content

    def test_required_and_nullable_rendered(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _render_models(model, flutter_config, env, tmp_path)
        assert "required String displayName," in content
        assert "required Decimal unitPrice," in content
        assert "DateTime? releasedAt," in content
        assert "String? notes," in content

    def test_part_directives_use_entity_stem(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        content = _render_models(model, flutter_config, env, tmp_path)
        assert "part 'widget.freezed.dart';" in content
        assert "part 'widget.g.dart';" in content

    def test_output_path_derived_from_config(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_flutter_models(model, flutter_config, env, tmp_path)
        path = outputs[0]["path"]
        assert path == tmp_path / "lib" / "models" / "widget.dart"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #


class TestEnumTemplate:
    def test_enum_members_upper_with_jsonvalue(
        self,
        flutter_config: dict[str, Any],
        env: Any,
        enum_defs: dict[str, Any],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "model_generator.generators.flutter.generators.load_shared_enums",
            lambda _: enum_defs,
        )
        result = generate_flutter_enums(
            {}, flutter_config, env, tmp_path, tmp_path / "x.model.json"
        )
        assert result is not None
        content = str(result["content"])
        assert "enum WidgetStatus {" in content
        # No @JsonEnum / part 'enums.g.dart' — helpers use .byName()/.name so
        # the Dart analyser can fully resolve enums.dart without a generated
        # part file, preventing ProductStatus from appearing as InvalidType.
        assert "@JsonEnum" not in content
        assert "part 'enums.g.dart'" not in content
        assert "@JsonValue('ACTIVE')" in content
        assert "ACTIVE," in content
        assert "@JsonValue('ARCHIVED')" in content
        # Per-enum fromJson/toJson helpers use Dart built-in byName/name.
        assert "widgetStatusFromJson" in content
        assert "WidgetStatus.values.byName(" in content
        assert "widgetStatusToJson" in content
        assert "object?.name" in content

    def test_no_enums_returns_none(
        self,
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "model_generator.generators.flutter.generators.load_shared_enums",
            lambda _: {},
        )
        result = generate_flutter_enums(
            {}, flutter_config, env, tmp_path, tmp_path / "x.model.json"
        )
        assert result is None


# --------------------------------------------------------------------------- #
# Models barrel
# --------------------------------------------------------------------------- #


class TestModelsIndex:
    def test_barrel_exports_entities_and_enums(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_flutter_models_index(model, flutter_config, env, tmp_path)
        assert result is not None
        content = str(result["content"])
        assert "export 'enums.dart';" in content
        assert "export 'widget.dart';" in content

    def test_barrel_omits_enums_when_none(
        self,
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        # A spec with no enum fields must NOT export enums.dart — that file is
        # never generated, so exporting it is a hard Dart compile error.
        model = {
            "entities": {
                "Gadget": {"fields": {"name": {"type": "text", "required": True}}}
            }
        }
        result = generate_flutter_models_index(model, flutter_config, env, tmp_path)
        assert result is not None
        content = str(result["content"])
        assert "enums.dart" not in content
        assert "export 'gadget.dart';" in content

    def test_first_run_barrel_exports_requests_dtos(
        self,
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        # First run: the models dir does not exist yet, so the directory glob
        # finds no files and the barrel is built purely from the entity loop.
        # Entities with create/update endpoints emit a ``<entity>_requests.dart``
        # DTO into the models dir, so the barrel must export it too — otherwise
        # the api client's `import '<entity>_requests.dart'` fails to compile on
        # the very first build.
        models_dir = tmp_path / resolve_path(flutter_config, "models")
        assert not models_dir.exists()  # truly first-run

        model = {
            "entities": {
                # Full CRUD (default endpoints) -> emits a requests DTO.
                "Gadget": {
                    "table": "gadgets",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "name": {"type": "text", "required": True},
                    },
                },
                # list/get only -> NO requests DTO, must NOT be exported.
                "Note": {
                    "table": "notes",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "api": {"endpoints": ["list", "get"]},
                },
            }
        }
        result = generate_flutter_models_index(model, flutter_config, env, tmp_path)
        assert result is not None
        content = str(result["content"])
        assert "export 'gadget.dart';" in content
        assert "export 'gadget_requests.dart';" in content
        assert "export 'note.dart';" in content
        assert "export 'note_requests.dart';" not in content
        # No enum fields declared -> enums export still correctly suppressed.
        assert "enums.dart" not in content


# --------------------------------------------------------------------------- #
# Infrastructure: converters & pubspec
# --------------------------------------------------------------------------- #


class TestConverters:
    def test_converters_define_all_three(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        result = generate_converters(flutter_config, env, tmp_path)
        content = str(result["content"])
        assert "class DecimalConverter implements JsonConverter<Decimal, String>" in (
            content
        )
        assert "class BytesConverter implements JsonConverter<Uint8List, String>" in (
            content
        )
        assert (
            "class UtcDateTimeConverter implements JsonConverter<DateTime, String>"
            in content
        )
        # Money carried as a string; datetime appends 'Z'.
        assert "Decimal.parse(json)" in content
        assert "base64Decode(json)" in content

    def test_path_uses_api_core(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        result = generate_converters(flutter_config, env, tmp_path)
        assert result["path"] == tmp_path / "lib" / "core" / "converters.dart"


class TestPubspec:
    def test_pubspec_lists_runtime_and_dev_deps(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        result = generate_pubspec(flutter_config, env, tmp_path, {})
        assert result is not None
        content = str(result["content"])
        assert "freezed_annotation:" in content
        assert "dio:" in content
        assert "decimal:" in content
        assert "build_runner:" in content
        assert "flutter_lints:" in content

    def test_pubspec_skips_if_exists(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        (tmp_path / "pubspec.yaml").write_text("name: existing\n")
        result = generate_pubspec(flutter_config, env, tmp_path, {})
        assert result is None

    def test_pubspec_includes_auth_dep_when_strategy_set(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        project_config = {"auth": {"strategy": "bcrypt-session"}}
        result = generate_pubspec(flutter_config, env, tmp_path, project_config)
        assert result is not None
        assert "flutter_secure_storage:" in str(result["content"])

    def test_pubspec_ignores_python_spec_deps(
        self, flutter_config: dict[str, Any], env: Any, tmp_path: Path
    ) -> None:
        # A backend (pip) dependency must never leak into the Dart pubspec.
        result = generate_pubspec(flutter_config, env, tmp_path, {})
        assert result is not None
        assert "bcrypt>=" not in str(result["content"])


# --------------------------------------------------------------------------- #
# Project-agnostic guarantees (the cardinal rule)
# --------------------------------------------------------------------------- #

_TEMPLATE_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "model_generator"
    / "stacks"
    / "flutter"
    / "templates"
)


class TestProjectAgnostic:
    def test_templates_have_no_hardcoded_entity_names(self) -> None:
        # Fixture/example entity names must never appear as literals in templates.
        banned = ["Widget", "User", "Portfolio", "ApiKey", "Transaction"]
        for template in _TEMPLATE_DIR.rglob("*.j2"):
            text = template.read_text(encoding="utf-8")
            for name in banned:
                assert name not in text, f"{name} hardcoded in {template.name}"

    def test_templates_have_no_hardcoded_paths(self) -> None:
        banned = ["backend/src", "lib/app_api", "lib/probe_api", "package:app_api"]
        for template in _TEMPLATE_DIR.rglob("*.j2"):
            text = template.read_text(encoding="utf-8")
            for frag in banned:
                assert frag not in text, f"{frag} hardcoded in {template.name}"

    def test_rendered_model_imports_are_config_derived(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        # The package import prefix in rendered output must come from
        # flutter.package_name, not a literal — change it and the output tracks.
        cfg = dict(flutter_config)
        cfg["flutter"] = {"package_name": "custom_pkg"}
        outputs = generate_flutter_models(model, cfg, env, tmp_path)
        content = str(outputs[0]["content"])
        assert "package:custom_pkg/core/converters.dart" in content
        assert "package:custom_pkg/models/enums.dart" in content

    def test_resolve_path_substitutes_package_name(self) -> None:
        # resolve_path still supports {pkg} in user-overridden path values.
        cfg = {
            "flutter": {"package_name": "my_client"},
            "paths": {"models": "lib/{pkg}/models", "api_core": "lib/{pkg}/core"},
        }
        assert resolve_path(cfg, "models") == "lib/my_client/models"
        assert resolve_path(cfg, "api_core") == "lib/my_client/core"
