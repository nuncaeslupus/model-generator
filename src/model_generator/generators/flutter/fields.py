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
        converter   JsonConverter annotation name, or None
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

        descriptors.append(
            {
                "name": dart_member,
                "json_key": json_key,
                "dart_type": _dart_type(field, type_map),
                "nullable": _is_nullable(field),
                "converter": spec.get("converter"),
                # The JsonKey annotation is only needed when the wire key and the
                # Dart member name diverge — which is whenever the source field
                # name is snake_case (multi-segment) or renamed via api_field_name.
                "needs_json_key": json_key != dart_member,
                "doc": _doc_comment(field),
            }
        )

    return descriptors


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
        abstract = field.get("type", "")
        spec = type_map.get(abstract, {}) or {}
        for imp in spec.get("imports", []) or []:
            raw_imports.add(str(imp))
        if spec.get("converter"):
            has_converter = True
        if abstract == "enum":
            has_enum = True

    return {
        "dart_imports": sorted(raw_imports),
        "has_converter": has_converter,
        "has_enum": has_enum,
    }
