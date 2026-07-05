"""Field-type resolution for the Flutter stack.

Translates abstract ``*.model.json`` field definitions into the Dart-shaped
descriptors the freezed templates render. The abstract→Dart type table lives in
``stacks/flutter/config.yaml`` under ``types``; this module reads it (never
hardcoding a mapping) and layers on the naming, nullability and converter rules
from the Flutter stack plan.

Keeping the translation in Python — rather than in Jinja — lets the templates
stay purely presentational and lets the unit tests assert the mapping directly.
"""

from __future__ import annotations

from typing import Any

from ...utils.templates import camel_case

# Field flags that mark a field as server-managed / not part of the wire payload
# the client constructs. ``id`` and primary keys are still read from responses,
# so only ``api_exclude_response`` drives nullability here.


def _dart_type(field: dict[str, Any], type_map: dict[str, Any]) -> str:
    """Resolve a field's concrete Dart type from the config ``types`` table.

    Substitutes the ``{enum_name}`` and ``{list_type}`` placeholders the table
    carries for the enum / json_array rows. Falls back to ``dynamic`` for an
    unknown abstract type so generation never crashes on a new field type the
    Flutter stack hasn't mapped yet.
    """
    abstract = field.get("type", "")
    spec = type_map.get(abstract)
    if not spec or "dart" not in spec:
        return "dynamic"

    dart = str(spec["dart"])
    if "{enum_name}" in dart:
        dart = dart.replace("{enum_name}", str(field.get("enum_name", "dynamic")))
    if "{list_type}" in dart:
        list_type = field.get("list_type") or "dynamic"
        dart = dart.replace("{list_type}", _dart_list_type(str(list_type)))
    return dart


def _dart_list_type(list_type: str) -> str:
    """Map a spec ``list_type`` token onto a Dart element type.

    The spec uses Python-flavored tokens (``str``/``int``/``bool``...); translate
    the common ones to their Dart equivalents and pass anything else through
    (already-Dart tokens like ``String`` or a custom class name survive).
    """
    mapping = {
        "str": "String",
        "string": "String",
        "int": "int",
        "integer": "int",
        "float": "double",
        "number": "num",
        "bool": "bool",
        "boolean": "bool",
        "dict": "Map<String, dynamic>",
        "any": "dynamic",
    }
    return mapping.get(list_type, list_type)


def _is_nullable(field: dict[str, Any]) -> bool:
    """Decide a field's Dart nullability.

    Mirrors the Python stack's ``X | None`` rule: a field is non-null only when
    it is ``required`` *and* present in responses (``api_exclude_response`` not
    set). Everything else — optional fields, response-excluded write-only fields
    like a password — is nullable.
    """
    required = bool(field.get("required", False))
    excluded_from_response = bool(field.get("api_exclude_response", False))
    return not (required and not excluded_from_response)


def _converter_names(
    abstract: str, field: dict[str, Any], spec: dict[str, Any]
) -> tuple[str | None, str | None]:
    """Resolve a field's ``from_json``/``to_json`` converter function names.

    Comes from the type-map spec by default; an ``enum`` field overrides both
    with the shared-enum converter names derived from ``enum_name`` (e.g.
    ``Status`` → ``statusFromJson``/``statusToJson``), matching how the enums
    barrel names its generated converters.
    """
    from_json = spec.get("from_json")
    to_json = spec.get("to_json")
    if abstract == "enum":
        enum_name = str(field.get("enum_name") or "")
        if enum_name:
            fn = enum_name[0].lower() + enum_name[1:]
            from_json = f"{fn}FromJson"
            to_json = f"{fn}ToJson"
    return from_json, to_json


def _json_key(field_name: str, field: dict[str, Any]) -> str:
    """Resolve the wire JSON key for a field.

    Defaults to the spec field name (snake_case wire form). ``api_field_name``
    overrides it — e.g. the auth ``password_hash`` field that is sent as
    ``password`` — matching the Python stack's request alias.
    """
    return str(field.get("api_field_name") or field_name)


def _doc_comment(field: dict[str, Any]) -> list[str]:
    """Build the Dart doc-comment lines for a field.

    Surfaces the field ``description`` plus any min/max/pattern constraints as
    human-readable bounds (Phase 1 renders constraints as documentation only —
    no runtime validation yet). Returns a list of comment *bodies* (no leading
    ``///``); the template adds the prefix and indentation.
    """
    lines: list[str] = []
    description = field.get("description")
    if description:
        lines.append(str(description))

    for constraint in field.get("constraints", []) or []:
        if not isinstance(constraint, dict):
            continue
        ctype = constraint.get("type")
        if ctype == "range":
            lo = constraint.get("min")
            hi = constraint.get("max")
            if lo is not None and hi is not None:
                lines.append(f"Constraint: {lo} <= value <= {hi}.")
            elif lo is not None:
                lines.append(f"Constraint: value >= {lo}.")
            elif hi is not None:
                lines.append(f"Constraint: value <= {hi}.")
        elif ctype == "length":
            lo = constraint.get("min")
            hi = constraint.get("max")
            if lo is not None and hi is not None:
                lines.append(f"Length: {lo}–{hi} chars.")
            elif lo is not None:
                lines.append(f"Length: at least {lo} chars.")
            elif hi is not None:
                lines.append(f"Length: at most {hi} chars.")
        elif ctype == "pattern":
            regex = constraint.get("regex")
            if regex:
                lines.append(f"Must match pattern: {regex}")
        elif ctype == "non_negative":
            lines.append("Constraint: value >= 0.")
        elif ctype == "positive":
            lines.append("Constraint: value > 0.")

    min_length = field.get("min_length")
    max_length = field.get("max_length")
    if min_length is not None and max_length is not None:
        lines.append(f"Length: {min_length}–{max_length} chars.")
    elif min_length is not None:
        lines.append(f"Length: at least {min_length} chars.")
    elif max_length is not None:
        lines.append(f"Length: at most {max_length} chars.")

    return lines


def resolve_fields(
    entity: dict[str, Any], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build the ordered list of Dart field descriptors for an entity.

    Each descriptor carries everything the freezed model template needs:

        name        Dart member name (camelCase)
        json_key    wire JSON key (snake_case, or ``api_field_name`` override)
        dart_type   concrete Dart type (nullability applied separately)
        nullable    whether the member is ``T?``
        from_json   fromJson helper function name for @JsonKey, or None
        to_json     toJson helper function name for @JsonKey, or None
        needs_json_key  True when json_key differs from the Dart member name
        doc         list of doc-comment body lines
    """
    type_map = config.get("types", {}) or {}
    descriptors: list[dict[str, Any]] = []

    for field_name, field in (entity.get("fields") or {}).items():
        if not isinstance(field, dict):
            continue
        dart_member = camel_case(field_name)
        json_key = _json_key(field_name, field)
        abstract = field.get("type", "")
        spec = type_map.get(abstract, {}) or {}
        from_json, to_json = _converter_names(abstract, field, spec)

        descriptors.append(
            {
                "name": dart_member,
                "json_key": json_key,
                "dart_type": _dart_type(field, type_map),
                "nullable": _is_nullable(field),
                "from_json": from_json,
                "to_json": to_json,
                # The JsonKey annotation is only needed when the wire key and the
                # Dart member name diverge — which is whenever the source field
                # name is snake_case (multi-segment) or renamed via api_field_name.
                "needs_json_key": json_key != dart_member,
                "doc": _doc_comment(field),
            }
        )

    return descriptors


def _is_auto_pk(field: dict[str, Any]) -> bool:
    """True for an auto-generated primary key (server-assigned id).

    Mirrors the python request template, which omits a primary key from the
    create payload only when it is auto-generated (``auto_generate`` defaults to
    ``true``). A client-supplied pk (``auto_generate: false``) stays in.
    """
    return bool(field.get("primary_key", False)) and bool(
        field.get("auto_generate", True)
    )


def _scope_owner_field(entity: dict[str, Any]) -> str | None:
    """The owner field the server injects from the session, if any.

    Owner-scoped entities (``api.scope.owner_field``) have this field set by the
    backend from the authenticated user, so the client never sends it on create
    — matching the python request model.
    """
    api = entity.get("api") or {}
    scope = api.get("scope") or {}
    owner = scope.get("owner_field")
    return str(owner) if owner else None


def primary_key_field(entity: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the entity's primary-key descriptor for path params.

    Returns ``{"name": <camelCase member>, "json_key": <snake wire key>,
    "dart_type": <Dart type>}`` for the field flagged ``primary_key``. The Dart
    type is resolved from the config ``types`` table via :func:`_dart_type`, so an
    integer PK yields ``int`` and a uuid/string PK yields ``String`` — keeping the
    ``@Path`` param type aligned with the model field type (a hardcoded ``String``
    would mismatch and fail to compile for an integer PK).

    Defaults to a synthetic ``id``/``String`` when no PK is declared (every spec
    entity has an id, but the fallback keeps generation crash-free).
    """
    type_map = config.get("types", {}) or {}
    for field_name, field in (entity.get("fields") or {}).items():
        if isinstance(field, dict) and field.get("primary_key"):
            return {
                "name": camel_case(field_name),
                "json_key": _json_key(field_name, field),
                "dart_type": _dart_type(field, type_map),
            }
    return {"name": "id", "json_key": "id", "dart_type": "String"}


def resolve_dto_fields(
    entity: dict[str, Any], config: dict[str, Any], kind: str
) -> list[dict[str, Any]]:
    """Build the field descriptors for a Create/Update request DTO.

    ``kind`` is ``"create"`` or ``"update"``. Excludes the same fields the python
    request models exclude:

    * ``api_exclude_<kind>`` / ``api_readonly`` flagged fields,
    * the auto-generated primary key,
    * the owner field injected by an owner-scoped endpoint.

    Update DTO fields are always nullable (PATCH-style partial update); create DTO
    nullability follows the field's ``required`` flag.
    """
    type_map = config.get("types", {}) or {}
    exclude_flag = "api_exclude_create" if kind == "create" else "api_exclude_update"
    owner_field = _scope_owner_field(entity)
    descriptors: list[dict[str, Any]] = []

    for field_name, field in (entity.get("fields") or {}).items():
        if not isinstance(field, dict):
            continue
        if field.get(exclude_flag, False) or field.get("api_readonly", False):
            continue
        if _is_auto_pk(field):
            continue
        if owner_field is not None and field_name == owner_field:
            continue

        abstract_dto = field.get("type", "")
        spec = type_map.get(abstract_dto, {}) or {}
        dart_member = camel_case(field_name)
        json_key = _json_key(field_name, field)
        # Create DTO fields follow the field's ``required`` flag; Update DTO
        # fields are always nullable (PATCH-style partial update).
        nullable = not bool(field.get("required", False)) if kind == "create" else True
        from_json, to_json = _converter_names(abstract_dto, field, spec)

        descriptors.append(
            {
                "name": dart_member,
                "json_key": json_key,
                "dart_type": _dart_type(field, type_map),
                "nullable": nullable,
                "from_json": from_json,
                "to_json": to_json,
                "needs_json_key": json_key != dart_member,
                "doc": _doc_comment(field),
            }
        )

    return descriptors


def _field_import_flags(
    field: dict[str, Any], type_map: dict[str, Any]
) -> tuple[list[str], bool, bool]:
    """Resolve one field's import contribution: (imports, has_converter, has_enum)."""
    abstract = field.get("type", "")
    spec = type_map.get(abstract, {}) or {}
    imports = [str(imp) for imp in spec.get("imports", []) or []]
    has_converter = bool(spec.get("from_json") or spec.get("to_json"))
    has_enum = abstract == "enum"
    return imports, has_converter, has_enum


def collect_dto_imports(
    entity: dict[str, Any], config: dict[str, Any], kinds: tuple[str, ...]
) -> dict[str, Any]:
    """Collect the Dart imports the request-DTO file needs across ``kinds``.

    Same shape as :func:`collect_model_imports` but scoped to the fields that
    actually survive DTO exclusion, so a file whose only ``Decimal`` field is
    create-excluded doesn't drag in the converter import.
    """
    type_map = config.get("types", {}) or {}
    raw_imports: set[str] = set()
    has_converter = False
    has_enum = False

    seen: set[str] = set()
    for kind in kinds:
        for descriptor in resolve_dto_fields(entity, config, kind):
            seen.add(descriptor["name"])

    for field_name, field in (entity.get("fields") or {}).items():
        if not isinstance(field, dict):
            continue
        if camel_case(field_name) not in seen:
            continue
        imports, conv, en = _field_import_flags(field, type_map)
        raw_imports.update(imports)
        has_converter = has_converter or conv
        has_enum = has_enum or en

    return {
        "dart_imports": sorted(raw_imports),
        "has_converter": has_converter,
        "has_enum": has_enum,
    }


def collect_model_imports(
    entity: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Collect the extra Dart imports an entity's model file needs.

    Returns ``{"dart": [...], "converters": bool, "enums": bool}``-ish data:
    a sorted list of bare ``dart:``/``package:`` imports (e.g. ``dart:typed_data``
    for binary fields, ``package:decimal/decimal.dart`` for money), and flags for
    whether the file references any converter (→ import the core converters) or
    any enum (→ import the enums barrel). All paths are derived, never hardcoded
    to a project layout.
    """
    type_map = config.get("types", {}) or {}
    raw_imports: set[str] = set()
    has_converter = False
    has_enum = False

    for field in (entity.get("fields") or {}).values():
        if not isinstance(field, dict):
            continue
        imports, conv, en = _field_import_flags(field, type_map)
        raw_imports.update(imports)
        has_converter = has_converter or conv
        has_enum = has_enum or en

    return {
        "dart_imports": sorted(raw_imports),
        "has_converter": has_converter,
        "has_enum": has_enum,
    }
