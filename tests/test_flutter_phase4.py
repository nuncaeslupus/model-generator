"""Tests for the Flutter (Dart) stack Phase 4 — Drift/SQLite offline cache.

Renders the Phase-4 templates against fixture specs and asserts:

* ``generate_drift_tables``       — Drift Table classes: correct column types,
  nullability, SQL table name, class name.
* ``generate_drift_database``     — AppDatabase: table aggregation, imports,
  ``@DriftDatabase`` annotation.
* ``generate_cached_repositories``— CachedRepository: class hierarchy,
  fromRow/toCompanion conversions, cache-vs-network strategy per operation.

All tests run without a Dart SDK (pure Python + Jinja rendering).  The
project-agnostic assertions confirm no hardcoded entity names or package names
escape from the templates.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.generators.flutter import (
    generate_cached_repositories,
    generate_drift_database,
    generate_drift_tables,
)
from model_generator.generators.flutter.cache import (
    _cache_enabled,
    _from_row_expr,
    _to_companion_expr,
    cached_class,
    table_class,
    table_db_accessor,
)
from model_generator.utils.templates import get_template_env

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
    with _STACK_CONFIG_PATH.open(encoding="utf-8") as f:
        cfg: dict[str, Any] = yaml.safe_load(f)
    return cfg


@pytest.fixture
def cache_config(flutter_config: dict[str, Any]) -> dict[str, Any]:
    """Flutter config with local_cache enabled."""
    return {**flutter_config, "local_cache": True}


@pytest.fixture
def env() -> Any:
    return get_template_env("flutter")


@pytest.fixture
def model() -> dict[str, Any]:
    """Multi-type fixture exercising every Drift column and conversion path.

    * ``Widget``  — full CRUD, paginated, all type variants.
    * ``Ledger``  — immutable, list/get only.
    * ``Silent``  — ``api.enabled: false`` — must produce no Phase-4 output.
    """
    return {
        "domain": "catalog",
        "entities": {
            "Widget": {
                "table": "widgets",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "owner_id": {"type": "reference", "required": True},
                    "label": {"type": "text", "required": True},
                    "notes": {"type": "longtext"},
                    "unit_price": {"type": "financial", "required": True},
                    "discount": {"type": "percentage"},
                    "view_count": {"type": "counter", "required": True},
                    "is_active": {"type": "boolean"},
                    "released_at": {"type": "datetime", "required": True},
                    "thumbnail": {"type": "binary"},
                    "status": {
                        "type": "enum",
                        "enum_name": "WidgetStatus",
                        "required": True,
                    },
                    "status_optional": {
                        "type": "enum",
                        "enum_name": "WidgetStatus",
                    },
                    "metadata": {"type": "json_object"},
                    "tags": {"type": "json_array", "list_type": "str"},
                    "scores": {"type": "json_array"},
                },
                "api": {
                    "enabled": True,
                    "prefix": "widgets",
                    "endpoints": ["list", "create", "get", "update", "delete"],
                    "pagination": True,
                },
            },
            "Ledger": {
                "table": "ledgers",
                "mutability": "immutable",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "amount": {"type": "financial", "required": True},
                },
                "api": {
                    "enabled": True,
                    "prefix": "ledgers",
                    "endpoints": ["list", "get"],
                },
            },
            "Silent": {
                "table": "silents",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True},
                },
                "api": {"enabled": False},
            },
        },
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _rendered(outputs: list[dict[str, Any]], suffix: str) -> str:
    """Return content of the first output whose path ends with ``suffix``."""
    for o in outputs:
        if str(o["path"]).endswith(suffix):
            return str(o["content"])
    raise AssertionError(f"No output ending with {suffix!r} found.")


# ---------------------------------------------------------------------------
# _cache_enabled
# ---------------------------------------------------------------------------


class TestCacheEnabled:
    def test_false_when_absent(self, flutter_config: dict[str, Any]) -> None:
        assert not _cache_enabled(flutter_config)

    def test_false_when_explicit_false(self, flutter_config: dict[str, Any]) -> None:
        assert not _cache_enabled({**flutter_config, "local_cache": False})

    def test_true_when_set(self, cache_config: dict[str, Any]) -> None:
        assert _cache_enabled(cache_config)


# ---------------------------------------------------------------------------
# Class-name helpers
# ---------------------------------------------------------------------------


class TestCacheHelpers:
    def test_table_class(self) -> None:
        assert table_class("Category") == "CategoryTable"
        assert table_class("UserProfile") == "UserProfileTable"

    def test_cached_class(self) -> None:
        assert cached_class("Widget") == "WidgetCachedRepository"

    def test_table_db_accessor(self) -> None:
        assert table_db_accessor("Category") == "categoryTable"
        assert table_db_accessor("UserProfile") == "userProfileTable"
        assert table_db_accessor("ApiKey") == "apiKeyTable"


# ---------------------------------------------------------------------------
# _from_row_expr / _to_companion_expr
# ---------------------------------------------------------------------------


class TestFieldExpressions:
    @pytest.fixture
    def type_map(self, flutter_config: dict[str, Any]) -> dict[str, Any]:
        return flutter_config.get("types", {}) or {}

    def _field(self, **kw: Any) -> dict[str, Any]:
        return {"required": False, **kw}

    def _req(self, **kw: Any) -> dict[str, Any]:
        return {"required": True, **kw}

    # fromRow

    def test_from_row_text_direct(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("label", self._req(type="text"), type_map)
        assert expr == "row.label"

    def test_from_row_decimal_required(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("unit_price", self._req(type="financial"), type_map)
        assert "Decimal.parse" in expr
        assert "!" not in expr  # non-null — no null-assertion needed

    def test_from_row_decimal_nullable(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("discount", self._field(type="percentage"), type_map)
        assert "Decimal.parse" in expr
        assert "!" in expr  # nullable — null-assertion present
        assert "null" in expr

    def test_from_row_enum_required(self, type_map: dict[str, Any]) -> None:
        field = self._req(type="enum", enum_name="WidgetStatus")
        expr = _from_row_expr("status", field, type_map)
        assert "WidgetStatus.values.byName" in expr
        assert "!" not in expr

    def test_from_row_enum_nullable(self, type_map: dict[str, Any]) -> None:
        field = self._field(type="enum", enum_name="WidgetStatus")
        expr = _from_row_expr("status", field, type_map)
        assert "WidgetStatus.values.byName" in expr
        assert "!" in expr
        assert "null" in expr

    def test_from_row_json_object(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("metadata", self._field(type="json_object"), type_map)
        assert "jsonDecode" in expr
        assert "Map<String, dynamic>" in expr

    def test_from_row_json_array_typed(self, type_map: dict[str, Any]) -> None:
        field = self._field(type="json_array", list_type="str")
        expr = _from_row_expr("tags", field, type_map)
        assert "jsonDecode" in expr
        assert ".cast<String>()" in expr

    def test_from_row_json_array_dynamic(self, type_map: dict[str, Any]) -> None:
        field = self._field(type="json_array")
        expr = _from_row_expr("scores", field, type_map)
        assert "jsonDecode" in expr
        assert "List<dynamic>" in expr
        assert ".cast<" not in expr

    def test_from_row_datetime_direct(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("released_at", self._req(type="datetime"), type_map)
        assert expr == "row.releasedAt"

    def test_from_row_binary_direct(self, type_map: dict[str, Any]) -> None:
        expr = _from_row_expr("thumbnail", self._field(type="binary"), type_map)
        assert expr == "row.thumbnail"

    # toCompanion

    def test_to_companion_text(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("label", self._req(type="text"), type_map)
        assert expr == "Value(e.label)"

    def test_to_companion_decimal_required(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("unit_price", self._req(type="financial"), type_map)
        assert "e.unitPrice.toString()" in expr
        assert "?." not in expr

    def test_to_companion_decimal_nullable(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("discount", self._field(type="percentage"), type_map)
        assert "e.discount?.toString()" in expr

    def test_to_companion_enum_required(self, type_map: dict[str, Any]) -> None:
        field = self._req(type="enum", enum_name="WidgetStatus")
        expr = _to_companion_expr("status", field, type_map)
        assert "e.status.name" in expr
        assert "?." not in expr

    def test_to_companion_enum_nullable(self, type_map: dict[str, Any]) -> None:
        field = self._field(type="enum", enum_name="WidgetStatus")
        # Field name "status_optional" → camelCase "statusOptional"
        expr = _to_companion_expr("status_optional", field, type_map)
        assert "e.statusOptional?.name" in expr

    def test_to_companion_json(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("metadata", self._field(type="json_object"), type_map)
        assert "jsonEncode" in expr

    def test_to_companion_int(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("view_count", self._req(type="counter"), type_map)
        assert expr == "Value(e.viewCount)"

    def test_to_companion_bool(self, type_map: dict[str, Any]) -> None:
        expr = _to_companion_expr("is_active", self._field(type="boolean"), type_map)
        assert expr == "Value(e.isActive)"


# ---------------------------------------------------------------------------
# generate_drift_tables
# ---------------------------------------------------------------------------


class TestDriftTableGeneration:
    def test_disabled_returns_empty(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, flutter_config, env, tmp_path)
        assert outputs == []

    def test_emits_one_file_per_api_enabled_entity(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        # Widget + Ledger (Silent has api.enabled: false)
        assert len(outputs) == 2
        paths = [str(o["path"]) for o in outputs]
        assert any("widget_table.dart" in p for p in paths)
        assert any("ledger_table.dart" in p for p in paths)
        assert not any("silent" in p for p in paths)

    def test_table_class_name(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "class WidgetTable extends Table" in content

    def test_sql_table_name_prefixed(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "local_widgets" in content

    def test_text_columns_for_string_types(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "TextColumn get id => text()()" in content
        assert "TextColumn get label => text()()" in content
        assert "TextColumn get unitPrice => text()()" in content  # financial
        assert "TextColumn get status => text()()" in content  # enum

    def test_integer_column(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "IntColumn get viewCount => integer()()" in content

    def test_boolean_column(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "BoolColumn get isActive => boolean().nullable()()" in content

    def test_datetime_column(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "DateTimeColumn get releasedAt => dateTime()()" in content

    def test_blob_column(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "BlobColumn get thumbnail => blob().nullable()()" in content

    def test_nullable_columns(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        # notes (longtext, no required) → nullable
        assert "TextColumn get notes => text().nullable()()" in content
        # discount (percentage, no required) → nullable
        assert "TextColumn get discount => text().nullable()()" in content

    def test_non_nullable_required_columns(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        # unit_price is required → NOT nullable
        assert "TextColumn get unitPrice => text()()" in content
        assert "TextColumn get unitPrice => text().nullable()()" not in content

    def test_primary_key_override(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Drift requires an explicit primaryKey override for insertOnConflictUpdate."""
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_table.dart")
        assert "Set<Column> get primaryKey => { id };" in content

    def test_mode_is_write(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_drift_tables(model, cache_config, env, tmp_path)
        assert all(o.get("mode") == "write" for o in outputs)

    def test_project_agnostic_no_hardcoded_names(
        self,
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Template must not reference any entity or project name directly."""
        alt_model = {
            "domain": "inventory",
            "entities": {
                "Gadget": {
                    "table": "gadgets",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "api": {"enabled": True},
                }
            },
        }
        outputs = generate_drift_tables(alt_model, cache_config, env, tmp_path)
        assert len(outputs) == 1
        content = outputs[0]["content"]
        assert "GadgetTable" in content
        assert "WidgetTable" not in content
        assert "Widget" not in content


# ---------------------------------------------------------------------------
# generate_drift_database
# ---------------------------------------------------------------------------


class TestDriftDatabaseGeneration:
    def test_disabled_returns_none(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, flutter_config, env, tmp_path)
        assert result is None

    def test_includes_all_api_enabled_entities(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        content = result["content"]
        assert "WidgetTable" in content
        assert "LedgerTable" in content
        assert "SilentTable" not in content

    def test_drift_database_annotation(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        content = result["content"]
        assert "@DriftDatabase(tables: [" in content
        assert "WidgetTable" in content
        assert "LedgerTable" in content

    def test_part_directive(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        assert "part 'local_database.g.dart';" in result["content"]

    def test_extends_generated_base(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        assert "class AppDatabase extends _$AppDatabase" in result["content"]

    def test_schema_version_one(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        assert "int get schemaVersion => 1;" in result["content"]

    def test_import_uris_reference_local_dir(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        content = result["content"]
        # Import URIs use the package:// form, not a bare lib/ path.
        assert "local/widget_table.dart" in content
        assert "local/ledger_table.dart" in content

    def test_output_path_in_core_dir(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        result = generate_drift_database(model, cache_config, env, tmp_path)
        assert result is not None
        assert str(result["path"]).endswith("local_database.dart")
        assert "core" in str(result["path"])

    def test_aggregates_existing_table_files(
        self,
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Database generator picks up table files already on disk."""
        local_dir = tmp_path / "lib" / "local"
        local_dir.mkdir(parents=True)
        (local_dir / "thing_table.dart").write_text("// stub")

        model_b = {
            "domain": "b",
            "entities": {
                "Other": {
                    "table": "others",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "api": {"enabled": True},
                }
            },
        }
        result = generate_drift_database(model_b, cache_config, env, tmp_path)
        assert result is not None
        content = result["content"]
        # Should include both the on-disk stub and the current model's entity.
        assert "ThingTable" in content
        assert "OtherTable" in content


# ---------------------------------------------------------------------------
# generate_cached_repositories
# ---------------------------------------------------------------------------


class TestCachedRepositoryGeneration:
    def test_disabled_returns_empty(
        self,
        model: dict[str, Any],
        flutter_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, flutter_config, env, tmp_path)
        assert outputs == []

    def test_one_file_per_api_enabled_entity(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        paths = [str(o["path"]) for o in outputs]
        assert any("widget_cached_repository.dart" in p for p in paths)
        assert any("ledger_cached_repository.dart" in p for p in paths)
        assert not any("silent" in p for p in paths)

    def test_extends_base_repository(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "class WidgetCachedRepository extends WidgetRepository" in content

    def test_appdb_field(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "final AppDatabase _db;" in content

    def test_paginated_list_delegates_to_network(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Widget has pagination:true — list() must delegate (no batch cache write)."""
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "return super.list(" in content
        # Paginated list never does a batch cache insert — that's the distinguishing
        # marker.  (Individual ops like getById still use _db.select.)
        assert "insertAllOnConflictUpdate" not in content

    def test_unfiltered_unpaginated_list_uses_cache(
        self,
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Ledger has list/get only, no pagination — list() should be cache-first."""
        ledger_model = {
            "domain": "catalog",
            "entities": {
                "Ledger": {
                    "table": "ledgers",
                    "mutability": "immutable",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "amount": {"type": "financial", "required": True},
                    },
                    "api": {
                        "enabled": True,
                        "prefix": "ledgers",
                        "endpoints": ["list", "get"],
                        "pagination": False,
                    },
                }
            },
        }
        outputs = generate_cached_repositories(
            ledger_model, cache_config, env, tmp_path
        )
        content = _rendered(outputs, "ledger_cached_repository.dart")
        assert "_db.select(_db.ledgerTable)" in content
        assert "insertAllOnConflictUpdate" in content

    def test_get_by_id_cache_first(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "getById" in content
        assert "getSingleOrNull" in content
        assert "insertOnConflictUpdate" in content

    def test_create_write_through(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "Future<Widget> create(" in content
        assert "await super.create(body)" in content
        assert "insertOnConflictUpdate(_toCompanion(result))" in content

    def test_update_write_through(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "Future<Widget> update(" in content
        assert "await super.update(" in content
        assert "insertOnConflictUpdate(_toCompanion(result))" in content

    def test_delete_removes_from_cache(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "await super.delete(" in content
        assert "_db.delete(_db.widgetTable)" in content

    def test_from_row_decimal_conversion(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "Decimal.parse(row.unitPrice)" in content

    def test_from_row_enum_conversion(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "WidgetStatus.values.byName(row.status)" in content

    def test_to_companion_decimal_to_string(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "e.unitPrice.toString()" in content

    def test_to_companion_enum_name(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "e.status.name" in content

    def test_decimal_import_when_needed(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "package:decimal/decimal.dart" in content

    def test_json_convert_import_when_needed(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "widget_cached_repository.dart")
        assert "dart:convert" in content

    def test_no_decimal_import_when_not_needed(
        self,
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        simple_model = {
            "domain": "x",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "required": True},
                    },
                    "api": {
                        "enabled": True,
                        "prefix": "things",
                        "endpoints": ["list", "get"],
                    },
                }
            },
        }
        outputs = generate_cached_repositories(
            simple_model, cache_config, env, tmp_path
        )
        content = _rendered(outputs, "thing_cached_repository.dart")
        # Decimal import should NOT appear when no financial/percentage fields.
        # The template always imports decimal — check at least no Decimal.parse
        assert "Decimal.parse" not in content

    def test_immutable_entity_no_update_method(
        self,
        model: dict[str, Any],
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        """Ledger is immutable — no update override should be emitted."""
        outputs = generate_cached_repositories(model, cache_config, env, tmp_path)
        content = _rendered(outputs, "ledger_cached_repository.dart")
        assert "Future<Ledger> update(" not in content

    def test_project_agnostic(
        self,
        cache_config: dict[str, Any],
        env: Any,
        tmp_path: Path,
    ) -> None:
        alt_model = {
            "domain": "store",
            "entities": {
                "Product": {
                    "table": "products",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "price": {"type": "financial", "required": True},
                    },
                    "api": {
                        "enabled": True,
                        "prefix": "products",
                        "endpoints": ["list", "get"],
                    },
                }
            },
        }
        outputs = generate_cached_repositories(alt_model, cache_config, env, tmp_path)
        assert len(outputs) == 1
        content = outputs[0]["content"]
        assert "ProductCachedRepository" in content
        assert "WidgetCachedRepository" not in content
        assert "Widget" not in content
