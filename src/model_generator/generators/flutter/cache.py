"""Flutter (Dart) Phase 4 — Drift/SQLite offline cache generators.

Emits three file types per API-enabled entity (when ``local_cache: true`` is
set in the project ``.model-generator.yaml``):

* ``lib/local/<entity>_table.dart``         — Drift ``Table`` class.
* ``lib/core/local_database.dart``           — ``AppDatabase`` (aggregated).
* ``lib/repositories/<entity>_cached_repository.dart`` — cache-first repo.

All three generators return ``[]`` / ``None`` when ``local_cache`` is absent
or ``false``, so projects that don't need offline support generate nothing extra.

The generated hierarchy:

    EntityRepositoryCustom  (skip-if-exists, Phase 2 adopter seam)
      ↑ extends (manual step documented in README)
    EntityCachedRepository  (Phase 4, overwrite — this module)
      ↑ extends
    EntityRepository        (Phase 2, overwrite — thin retrofit wrapper)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment

from ...utils.templates import camel_case
from .api import _api_enabled, _build_ops, _entity_filename, _filters, _has_requests
from .fields import _dart_type, _is_nullable, primary_key_field
from .paths import package_uri, resolve_path

# ---------------------------------------------------------------------------
# Config / entity helpers
# ---------------------------------------------------------------------------


def _cache_enabled(config: dict[str, Any]) -> bool:
    """Return True when ``local_cache: true`` is set in the merged config."""
    return bool(config.get("local_cache"))


# ---------------------------------------------------------------------------
# Class-name helpers
# ---------------------------------------------------------------------------


def table_class(entity_name: str) -> str:
    """Drift Table class name: ``Category`` → ``CategoryTable``."""
    return f"{entity_name}Table"


def cached_class(entity_name: str) -> str:
    """Cache-first repository class: ``Category`` → ``CategoryCachedRepository``."""
    return f"{entity_name}CachedRepository"


def table_db_accessor(entity_name: str) -> str:
    """AppDatabase getter for the entity's table: ``Category`` → ``categoryTable``.

    Drift generates the getter by lower-casing the first letter of the Table
    class name (``CategoryTable`` → ``categoryTable``).
    """
    return entity_name[0].lower() + entity_name[1:] + "Table"


def table_data_type(entity_name: str) -> str:
    """Drift-generated row data class: ``Category`` → ``CategoryTableData``."""
    return f"{entity_name}TableData"


def table_companion_type(entity_name: str) -> str:
    """Drift-generated companion class: ``Category`` → ``CategoryTableCompanion``."""
    return f"{entity_name}TableCompanion"


# ---------------------------------------------------------------------------
# Drift column mapping
# ---------------------------------------------------------------------------

# Maps abstract type → Drift column builder method name.
_DRIFT_COL_BUILDER: dict[str, str] = {
    "uuid": "text",
    "reference": "text",
    "text": "text",
    "longtext": "text",
    "financial": "text",  # Decimal stored as string (preserves precision)
    "percentage": "text",  # Decimal stored as string
    "counter": "integer",
    "integer": "integer",
    "boolean": "boolean",
    "datetime": "dateTime",
    "binary": "blob",
    "enum": "text",  # enum member name stored as string
    "json_object": "text",  # JSON-encoded string
    "json_array": "text",  # JSON-encoded string
}

# Dart type-alias for the column return type annotation in the Table class.
_DRIFT_COL_DART_TYPE: dict[str, str] = {
    "text": "TextColumn",
    "integer": "IntColumn",
    "boolean": "BoolColumn",
    "dateTime": "DateTimeColumn",
    "blob": "BlobColumn",
}


def _drift_col_builder(field: dict[str, Any]) -> str:
    return _DRIFT_COL_BUILDER.get(field.get("type", ""), "text")


def _drift_col_dart_type(field: dict[str, Any]) -> str:
    builder = _drift_col_builder(field)
    return _DRIFT_COL_DART_TYPE.get(builder, "TextColumn")


# ---------------------------------------------------------------------------
# fromRow / toCompanion expression builders
# ---------------------------------------------------------------------------


def _json_array_elem_type(field: dict[str, Any], type_map: dict[str, Any]) -> str:
    """Extract the element Dart type from a json_array field descriptor.

    ``_dart_type`` returns e.g. ``List<String>``; strip the ``List<…>`` wrapper
    to get the element type (``String``, ``int``, ``dynamic``, …).
    """
    dart = str(_dart_type(field, type_map))
    if dart.startswith("List<") and dart.endswith(">"):
        return dart[5:-1]
    return "dynamic"


def _from_row_expr(
    field_name: str, field: dict[str, Any], type_map: dict[str, Any]
) -> str:
    """Dart expression: Drift ``TableData`` row field → freezed model field value.

    Handles the type mismatches between Drift storage types (e.g. ``String`` for
    Decimal, ``String`` for enum names, ``String`` for JSON blobs) and the
    corresponding Dart field types in the freezed model.
    """
    abstract = field.get("type", "")
    nullable = _is_nullable(field)
    dart_name = camel_case(field_name)
    row = f"row.{dart_name}"

    if abstract in ("financial", "percentage"):
        if nullable:
            return f"{row} != null ? Decimal.parse({row}!) : null"
        return f"Decimal.parse({row})"

    if abstract == "enum":
        enum_name = str(field.get("enum_name") or "Object")
        if nullable:
            return f"{row} != null ? {enum_name}.values.byName({row}!) : null"
        return f"{enum_name}.values.byName({row})"

    if abstract == "json_object":
        if nullable:
            return f"{row} != null ? jsonDecode({row}!) as Map<String, dynamic> : null"
        return f"jsonDecode({row}) as Map<String, dynamic>"

    if abstract == "json_array":
        elem = _json_array_elem_type(field, type_map)
        if elem == "dynamic":
            if nullable:
                return f"{row} != null ? jsonDecode({row}!) as List<dynamic> : null"
            return f"jsonDecode({row}) as List<dynamic>"
        if nullable:
            return (
                f"{row} != null"
                f" ? (jsonDecode({row}!) as List<dynamic>).cast<{elem}>()"
                f" : null"
            )
        return f"(jsonDecode({row}) as List<dynamic>).cast<{elem}>()"

    # String, int, bool, DateTime, Uint8List — Drift stores them natively.
    return row


def _to_companion_expr(
    field_name: str,
    field: dict[str, Any],
    type_map: dict[str, Any],
    column_nullable: bool | None = None,
) -> str:
    """Dart expression: ``Value<T>(…)`` for the Drift companion constructor.

    Wraps each model field value in a Drift ``Value`` (so Drift can distinguish
    "not provided" from ``null``). Type conversions are the inverse of
    :func:`_from_row_expr`.

    ``column_nullable`` overrides the field's own nullability for cases where
    the Drift column is forced non-nullable (e.g. primary keys) even though the
    freezed model field may be nullable (no ``required: true``).  When the
    column is non-nullable but the model field is nullable, a null-assertion
    ``!`` is emitted to satisfy Dart's type checker — the value is always
    present in an API response so the assertion is safe.
    """
    abstract = field.get("type", "")
    model_nullable = _is_nullable(field)
    # column_nullable=False with model_nullable=True → need a null assertion (!).
    nullable = model_nullable if column_nullable is None else column_nullable
    needs_assert = (not nullable) and model_nullable
    dart_name = camel_case(field_name)
    e = f"e.{dart_name}"

    if abstract in ("financial", "percentage"):
        if nullable:
            return f"Value({e}?.toString())"
        suffix = "!" if needs_assert else ""
        return f"Value({e}{suffix}.toString())"

    if abstract == "enum":
        if nullable:
            return f"Value({e}?.name)"
        suffix = "!" if needs_assert else ""
        return f"Value({e}{suffix}.name)"

    if abstract in ("json_object", "json_array"):
        if nullable:
            return f"Value({e} != null ? jsonEncode({e}!) : null)"
        inner = f"{e}!" if needs_assert else e
        return f"Value(jsonEncode({inner}))"

    # String, int, bool, DateTime, Uint8List — direct.
    if needs_assert:
        return f"Value({e}!)"
    return f"Value({e})"


# ---------------------------------------------------------------------------
# Field descriptor
# ---------------------------------------------------------------------------


def _resolve_cache_fields(
    entity: dict[str, Any], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build per-field cache descriptors for the Drift table + cached repo.

    Each descriptor carries everything the two Phase-4 templates need:
    the Drift column builder/type, the ``fromRow`` read expression and the
    ``toCompanion`` write expression — pre-computed in Python so the templates
    stay purely presentational.
    """
    type_map = config.get("types", {}) or {}
    result: list[dict[str, Any]] = []

    for field_name, field in (entity.get("fields") or {}).items():
        if not isinstance(field, dict):
            continue
        abstract = field.get("type", "")
        # Primary keys are always present in API responses — force non-nullable
        # so the Drift column type matches the WHERE-clause parameter type and
        # the getSingleOrNull lookup never needs a null-assertion.
        nullable = False if field.get("primary_key") else _is_nullable(field)
        result.append(
            {
                "name": camel_case(field_name),
                "drift_col_type": _drift_col_dart_type(field),
                "drift_builder": _drift_col_builder(field),
                "nullable": nullable,
                "from_row": _from_row_expr(field_name, field, type_map),
                "to_companion": _to_companion_expr(
                    field_name, field, type_map, column_nullable=nullable
                ),
                "needs_decimal": abstract in ("financial", "percentage"),
                "needs_json": abstract in ("json_object", "json_array"),
                "needs_enum": abstract == "enum",
            }
        )

    return result


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def generate_drift_tables(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate one Drift ``Table`` class per API-enabled entity.

    Each file lands at ``lib/local/<entity>_table.dart`` and defines the SQLite
    schema the :class:`AppDatabase` and cache-first repositories use.  Columns
    mirror the spec fields with type-appropriate Drift builders (``text()``,
    ``integer()``, ``boolean()``, ``dateTime()``, ``blob()``).

    Returns ``[]`` when ``local_cache`` is not enabled.
    """
    if not _cache_enabled(config):
        return []

    template = env.get_template("local/table.dart.j2")
    local_dir = project_root / resolve_path(config, "local")

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue

        stem = _entity_filename(entity_name)
        cache_fields = _resolve_cache_fields(entity, config)
        pk = primary_key_field(entity, config)
        # Prefix the SQL table name with ``local_`` so it never collides with
        # the backend's table names if the SQLite DB is ever shared.
        sql_table_name = f"local_{entity.get('table') or stem + 's'}"

        content = template.render(
            entity_name=entity_name,
            table_class=table_class(entity_name),
            table_name=sql_table_name,
            pk_field=pk["name"] if pk else "id",
            fields=cache_fields,
        )
        outputs.append(
            {
                "path": local_dir / f"{stem}_table.dart",
                "content": content,
                "mode": "write",
            }
        )

    return outputs


def generate_drift_database(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate (or update) ``lib/core/local_database.dart`` — the Drift AppDatabase.

    Follows the same scan-then-merge pattern as ``generate_flutter_api_index``
    and ``generate_flutter_models_index``: scans ``lib/local/`` for all existing
    ``*_table.dart`` files (from previous model-gen runs) and adds the current
    model's entities, so the database stays complete across multi-file specs.

    Returns ``None`` when ``local_cache`` is not enabled.
    """
    if not _cache_enabled(config):
        return None

    template = env.get_template("infrastructure/local_database.dart.j2")
    core_dir = project_root / resolve_path(config, "api_core")
    local_path = resolve_path(config, "local")
    local_dir = project_root / local_path

    # Collect (table_class_name, import_uri) pairs — deduped by class name.
    seen: set[str] = set()
    table_entries: list[dict[str, str]] = []

    def _add(cls: str, file_stem: str) -> None:
        if cls not in seen:
            seen.add(cls)
            table_entries.append(
                {
                    "class_name": cls,
                    "import_uri": package_uri(config, f"{local_path}/{file_stem}.dart"),
                }
            )

    # Scan previously generated table files in lib/local/.
    if local_dir.is_dir():
        for dart_file in sorted(local_dir.glob("*_table.dart")):
            stem = dart_file.stem  # e.g. "category_table"
            # Read the exact class name from the file rather than reconstructing
            # from the filename — capitalize() is lossy for names like APIKeyTable.
            entity_part = stem[: -len("_table")]
            fallback = "".join(p.capitalize() for p in entity_part.split("_")) + "Table"
            try:
                content = dart_file.read_text(encoding="utf-8")
                m = re.search(r"class\s+(\w+Table)\s+extends\s+Table", content)
                cls = m.group(1) if m else fallback
            except OSError:
                cls = fallback
            _add(cls, stem)

    # Add the current model's API-enabled entities (in case lib/local/ is new).
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue
        stem = _entity_filename(entity_name) + "_table"
        _add(table_class(entity_name), stem)

    # Sort for deterministic output.
    table_entries.sort(key=lambda t: t["class_name"])

    content = template.render(tables=table_entries)
    return {
        "path": core_dir / "local_database.dart",
        "content": content,
        "mode": "write",
    }


def generate_cached_repositories(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate one cache-first repository per API-enabled entity.

    Each ``<entity>_cached_repository.dart`` extends the Phase-2
    ``<entity>_repository.dart`` base and wraps every operation with a
    Drift/SQLite cache layer:

    * ``list()`` — cache-first for non-paginated/non-filtered lists; paginated
      or filtered lists delegate to the network (per-page/per-filter keying
      is out of scope for this layer).
    * ``getById()`` — cache-first; falls back to network and populates cache.
    * ``create()`` / ``update()`` — write-through (network first, then upsert).
    * ``delete()`` — write-through (network first, then remove from cache).

    Returns ``[]`` when ``local_cache`` is not enabled.
    """
    if not _cache_enabled(config):
        return []

    template = env.get_template("repositories/cached_repository.dart.j2")
    repo_dir = project_root / resolve_path(config, "repositories")
    api_core_path = resolve_path(config, "api_core")
    models_path = resolve_path(config, "models")
    repo_path = resolve_path(config, "repositories")
    enums_path = resolve_path(config, "enums")

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue

        stem = _entity_filename(entity_name)
        ops = _build_ops(entity, entity_name, config)
        filters = _filters(entity, config)
        cache_fields = _resolve_cache_fields(entity, config)
        has_requests = _has_requests(entity)
        pk = primary_key_field(entity, config)

        needs_decimal = any(f["needs_decimal"] for f in cache_fields)
        needs_json = any(f["needs_json"] for f in cache_fields)
        needs_enums = any(f["needs_enum"] for f in cache_fields)
        needs_pagination = any(
            str(op.get("return_type", "")).startswith("Paginated") for op in ops
        )

        content = template.render(
            entity_name=entity_name,
            base_class=f"{entity_name}Repository",
            cached_class=cached_class(entity_name),
            custom_class=f"{entity_name}RepositoryCustom",
            table_db_accessor=table_db_accessor(entity_name),
            table_data_type=table_data_type(entity_name),
            table_companion_type=table_companion_type(entity_name),
            ops=ops,
            filters=filters,
            cache_fields=cache_fields,
            pk_field=pk["name"],
            has_requests=has_requests,
            needs_decimal=needs_decimal,
            needs_json=needs_json,
            needs_enums=needs_enums,
            needs_pagination=needs_pagination,
            model_uri=package_uri(config, f"{models_path}/{stem}.dart"),
            repository_uri=package_uri(config, f"{repo_path}/{stem}_repository.dart"),
            local_database_uri=package_uri(
                config, f"{api_core_path}/local_database.dart"
            ),
            requests_uri=package_uri(config, f"{models_path}/{stem}_requests.dart"),
            enums_uri=package_uri(config, enums_path),
            pagination_uri=package_uri(config, f"{api_core_path}/pagination.dart"),
        )
        outputs.append(
            {
                "path": repo_dir / f"{stem}_cached_repository.dart",
                "content": content,
                "mode": "write",
            }
        )

    return outputs
