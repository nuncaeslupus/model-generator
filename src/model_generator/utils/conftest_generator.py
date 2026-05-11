#!/usr/bin/env python3
"""
Generate conftest.py for API tests from model JSON files.

Analyzes all model JSON files to identify entities and their dependencies,
then generates pytest fixtures in the correct order.
"""

import json
from pathlib import Path
from typing import Any, cast

from .constants import GENERATED_MARKER
from .loaders import load_shared_constraints


def load_all_models(models_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all model JSON files."""
    models = {}
    for json_file in sorted(models_dir.glob("*.model.json")):
        with open(json_file) as f:
            data = json.load(f)
            domain = data["domain"]
            models[domain] = data
    return models


def load_enums(models_dir: Path) -> dict[str, str]:
    """Load enum definitions from _shared/enums.json."""
    enums_file = models_dir / "_shared" / "enums.json"
    if not enums_file.exists():
        return {}

    with open(enums_file) as f:
        data = json.load(f)
        enums: dict[str, str] = {}
        for enum_name, enum_def in data.get("enums", {}).items():
            values = enum_def.get("values", [])
            # Extract first value (handle both string and object format)
            if values:
                first_val = values[0]
                if isinstance(first_val, str):
                    enums[enum_name] = first_val
                elif isinstance(first_val, dict):
                    enums[enum_name] = first_val.get("value", "")
        return enums


def extract_entities(models: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Extract all entities across all domains.

    Returns: {EntityName: {domain, table, fields, relationships, api_prefix}}
    """
    entities = {}
    for domain, model_data in models.items():
        for entity_name, entity in model_data.get("entities", {}).items():
            # Get API prefix from API config
            api_config = entity.get("api", {})
            if not api_config.get("enabled", True):
                continue

            api_prefix = api_config.get("prefix", entity["table"]).replace("_", "-")

            entities[entity_name] = {
                "domain": domain,
                "table": entity["table"],
                "fields": entity["fields"],
                "relationships": entity.get("relationships", {}),
                "api_prefix": api_prefix,
                "timestamps": entity.get("timestamps", {}),
            }
    return entities


def find_foreign_key_dependencies(
    entities: dict[str, dict[str, Any]],
) -> dict[str, set[str]]:
    """
    Find which entities depend on which others via foreign keys.

    Returns: {EntityName: {RequiredEntity1, RequiredEntity2, ...}}
    """
    dependencies = {}

    for entity_name, entity_data in entities.items():
        deps = set()

        # Check fields for references
        for field_name, field in entity_data["fields"].items():
            if field.get("type") == "reference":
                # Convert reference_table to entity name
                ref_table = field.get("reference_table")
                # Find entity with this table name
                for other_name, other_data in entities.items():
                    if other_data["table"] == ref_table and field.get(
                        "required", False
                    ):
                        deps.add(other_name)
                        break

        dependencies[entity_name] = deps

    return dependencies


def topological_sort(
    entities: set[str], dependencies: dict[str, set[str]]
) -> list[str]:
    """
    Sort entities by dependency order (dependencies first).
    """
    # Build a copy of dependencies
    deps = {e: set(dependencies.get(e, [])) for e in entities}

    sorted_entities = []
    while deps:
        # Find entities with no dependencies
        ready = [e for e, d in deps.items() if not d]

        if not ready:
            # Circular dependency or missing entity
            # Just take remaining entities in arbitrary order
            ready = list(deps.keys())

        # Add them to result
        sorted_entities.extend(sorted(ready))

        # Remove them from graph
        for e in ready:
            deps.pop(e)
            for d in deps.values():
                d.discard(e)

    return sorted_entities


def get_fixture_name(entity_name: str, entity_data: dict[str, Any]) -> str:
    """
    Generate fixture name for entity.
    For most entities: {entity_name.lower()}_id
    For entities with non-id primary key: {entity_name.lower()}_{pk_field}
    """
    # Find primary key field
    for field_name, field in entity_data["fields"].items():
        if field.get("primary_key"):
            if field_name == "id":
                return f"{entity_name.lower()}_id"
            else:
                return f"{entity_name.lower()}_{field_name}"

    # Default to _id if no PK found
    return f"{entity_name.lower()}_id"


def get_primary_key_field(entity_data: dict[str, Any]) -> str:
    """Get the primary key field name."""
    for field_name, field in entity_data["fields"].items():
        if field.get("primary_key"):
            return cast(str, field_name)
    return "id"


def generate_minimal_create_data(
    entity_name: str,
    entity_data: dict[str, Any],
    dependencies: dict[str, str],
    enums: dict[str, str],
    constraints: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """
    Generate minimal create data for an entity.
    Returns list of lines for the JSON payload.

    dependencies: {field_name: fixture_name} for required foreign keys
    enums: {EnumName: first_value} mapping from enums.json
    constraints: {ConstraintName: {type, value, description}} from shared constraints
    """
    lines = []

    for field_name, field in entity_data["fields"].items():
        # Skip fields excluded from request
        if field.get("api_exclude_request", False):
            continue

        # Include required fields OR user-provided primary keys
        is_required = field.get("required", False)
        is_user_pk = field.get("primary_key", False) and not field.get(
            "auto_generate", True
        )

        if not (is_required or is_user_pk):
            continue

        # Skip auto-generated primary keys
        if field.get("primary_key", False) and field.get("auto_generate", True):
            continue

        api_field_name = field.get("api_field_name", field_name)
        field_type = field["type"]

        # Handle foreign keys
        if field_type == "reference":
            if field_name in dependencies:
                lines.append(
                    f'            "{api_field_name}": {dependencies[field_name]},'
                )
            continue

        # Handle other types
        if field_type == "text":
            # Check for email FIRST (before unique check)
            if "email" in field_name.lower():
                email_val = 'f"test.{unique_suffix}@example.com"'
                lines.append(f'            "{api_field_name}": {email_val},')
            elif field.get("unique", False) or is_user_pk:
                # For unique fields or user-provided PKs, use unique suffix
                entity_lower = entity_name.lower()
                field_prefix = field_name if is_user_pk else entity_lower
                unique_val = f'f"test_{field_prefix}_{{unique_suffix}}"'
                lines.append(f'            "{api_field_name}": {unique_val},')
            else:
                # Respect max_length for non-unique text fields
                max_length = field.get("max_length")
                if max_length and max_length <= 3:
                    lines.append(f'            "{api_field_name}": "tst",')
                elif max_length and max_length <= 10:
                    lines.append(f'            "{api_field_name}": "test",')
                else:
                    lines.append(f'            "{api_field_name}": "test_value",')
        elif field_type in ["financial", "percentage"]:
            # Check for range constraints that limit the value
            default_val = "100.00" if field_type == "financial" else "0.1500"
            field_constraints = field.get("constraints", [])
            for c in field_constraints:
                if c.get("type") in ("range", "range_or_null"):
                    # Resolve max from ref or inline value
                    max_val = None
                    max_ref = c.get("max_ref")
                    if max_ref and constraints and max_ref in constraints:
                        max_val = float(constraints[max_ref]["value"])
                    elif c.get("max") is not None:
                        max_val = float(c["max"])
                    if max_val is not None:
                        if max_val <= 0.05:
                            default_val = f"{max_val / 2:.4f}"
                        elif max_val <= 1.0:
                            default_val = "0.5000"
                        elif max_val < 100.0:
                            default_val = f"{max_val / 2:.2f}"
            lines.append(f'            "{api_field_name}": "{default_val}",')
        elif field_type == "counter":
            lines.append(f'            "{api_field_name}": 10,')
        elif field_type == "boolean":
            default_val = str(field.get("default", True))
            lines.append(f'            "{api_field_name}": {default_val},')
        elif field_type == "enum":
            # Use actual enum value from enums.json
            enum_name = field.get("enum_name")
            if enum_name and enum_name in enums:
                enum_val = enums[enum_name].upper()
            else:
                # Fallback to default or "active"
                enum_val = field.get("default", "active").upper()
            lines.append(f'            "{api_field_name}": "{enum_val}",')
        elif field_type == "datetime":
            lines.append(f'            "{api_field_name}": "2025-01-01T00:00:00Z",')
        elif field_type == "json_array":
            lines.append(f'            "{api_field_name}": ["item1", "item2"],')
        elif field_type == "json_object":
            lines.append(f'            "{api_field_name}": {{}},')

    return lines


def needs_unique_suffix(
    entity_data: dict[str, Any], dep_mapping: dict[str, str]
) -> bool:
    """Check if entity needs unique_suffix variable."""
    for field_name, field in entity_data["fields"].items():
        # Skip excluded and auto-generated fields
        if field.get("api_exclude_request", False):
            continue
        if field.get("primary_key", False) and field.get("auto_generate", True):
            continue

        # Check if field is required or user-provided PK
        is_required = field.get("required", False)
        is_user_pk = field.get("primary_key", False) and not field.get(
            "auto_generate", True
        )

        if not (is_required or is_user_pk):
            continue

        field_type = field["type"]

        # Skip foreign keys (they use fixture params)
        if field_type == "reference":
            continue

        # Text fields with email or unique constraint need unique_suffix
        if field_type == "text":
            if "email" in field_name.lower():
                return True
            if field.get("unique", False) or is_user_pk:
                return True

    return False


def generate_fixture(
    entity_name: str,
    entity_data: dict[str, Any],
    fixture_name: str,
    required_deps: set[str],
    all_entities: dict[str, dict[str, Any]],
    enums: dict[str, str],
    constraints: dict[str, dict[str, Any]] | None = None,
    auth_strategy: str | None = None,
) -> list[str]:
    """Generate fixture code for an entity.

    When ``auth_strategy`` is set, the User fixture POSTs to
    ``/api/v1/auth/register`` instead of ``/api/v1/users`` — the latter
    drops its create endpoint when auth is on (the auth router owns
    user creation).
    """
    lines = []

    # Build fixture parameters
    params = ["client: TestClient"]
    dep_mapping = {}  # {field_name: fixture_param_name}

    # Add dependencies as parameters
    for dep_entity in sorted(required_deps):
        if dep_entity in all_entities:
            dep_fixture = get_fixture_name(dep_entity, all_entities[dep_entity])
            params.append(f"{dep_fixture}: str")

            # Find which field uses this dependency
            for field_name, field in entity_data["fields"].items():
                if field.get("type") == "reference":
                    ref_table = field.get("reference_table")
                    if all_entities[dep_entity]["table"] == ref_table:
                        dep_mapping[field_name] = dep_fixture

    # Fixture signature
    lines.append("@pytest.fixture")
    lines.append(f"def {fixture_name}({', '.join(params)}) -> str:")

    # Docstring
    pk_field = get_primary_key_field(entity_data)
    return_desc = f"its {pk_field}" if pk_field != "id" else "its ID"
    use_register = bool(auth_strategy) and entity_name == "User"
    if use_register:
        lines.append(
            f'    """Create a test {entity_name.lower()} via /auth/register '
            f'and return {return_desc}."""'
        )
    else:
        lines.append(
            f'    """Create a test {entity_name.lower()} and return {return_desc}."""'
        )

    # Only generate unique_suffix if needed
    if needs_unique_suffix(entity_data, dep_mapping):
        lines.append("    unique_suffix = str(uuid.uuid4())[:8]")
    lines.append("")

    # Build create request
    lines.append("    response = client.post(")
    if use_register:
        lines.append('        "/api/v1/auth/register",')
    else:
        api_prefix = entity_data["api_prefix"]
        lines.append(f'        "/api/v1/{api_prefix}",')
    lines.append("        json={")

    # Generate minimal create data
    create_lines = generate_minimal_create_data(
        entity_name, entity_data, dep_mapping, enums, constraints
    )
    lines.extend(create_lines)

    lines.append("        },")
    lines.append("    )")
    lines.append("")
    lines.append("    assert response.status_code == 201")

    # Return the primary key
    pk_field = get_primary_key_field(entity_data)
    lines.append(f'    return cast(str, response.json()["{pk_field}"])')
    lines.append("")

    return lines


def find_alt_fixtures_needed(entities: dict[str, dict[str, Any]]) -> set[str]:
    """
    Find which fixture names need _alt variants.

    Scans all entities for dual FK references to the same table+column.
    Returns a set of base fixture names that need _alt variants.
    """
    needed = set()

    for entity_data in entities.values():
        ref_counter: dict[str, int] = {}  # "table::column" -> count
        for field in entity_data["fields"].values():
            if field.get("type") == "reference":
                ref_table = field.get("reference_table", "")
                ref_column = field.get("reference_column", "id")
                ref_key = f"{ref_table}::{ref_column}"
                ref_counter[ref_key] = ref_counter.get(ref_key, 0) + 1

        # Any ref_key with count > 1 means we need an _alt fixture
        for ref_key, count in ref_counter.items():
            if count > 1:
                ref_table = ref_key.split("::")[0]
                # Find the entity for this table
                for ent_name, ent_data in entities.items():
                    if ent_data["table"] == ref_table:
                        base_fixture = get_fixture_name(ent_name, ent_data)
                        needed.add(base_fixture)
                        break

    return needed


def generate_alt_fixture(
    base_fixture_name: str,
    entity_name: str,
    entity_data: dict[str, Any],
    enums: dict[str, str],
    constraints: dict[str, dict[str, Any]] | None = None,
    auth_strategy: str | None = None,
) -> list[str]:
    """Generate an _alt fixture that creates a second instance of the same entity."""
    alt_fixture_name = f"{base_fixture_name}_alt"
    lines = []

    # Build simple fixture with no deps (alt fixtures are for independent entities)
    params = ["client: TestClient"]
    dep_mapping: dict[str, str] = {}

    lines.append("@pytest.fixture")
    lines.append(f"def {alt_fixture_name}({', '.join(params)}) -> str:")

    pk_field = get_primary_key_field(entity_data)
    return_desc = f"its {pk_field}" if pk_field != "id" else "its ID"
    use_register = bool(auth_strategy) and entity_name == "User"
    if use_register:
        lines.append(
            f'    """Create an alternate test {entity_name.lower()} '
            f'via /auth/register and return {return_desc}."""'
        )
    else:
        lines.append(
            f'    """Create an alternate test {entity_name.lower()} '
            f'and return {return_desc}."""'
        )

    if needs_unique_suffix(entity_data, dep_mapping):
        lines.append("    unique_suffix = str(uuid.uuid4())[:8]")
    lines.append("")

    lines.append("    response = client.post(")
    if use_register:
        lines.append('        "/api/v1/auth/register",')
    else:
        api_prefix = entity_data["api_prefix"]
        lines.append(f'        "/api/v1/{api_prefix}",')
    lines.append("        json={")

    create_lines = generate_minimal_create_data(
        entity_name, entity_data, dep_mapping, enums
    )
    lines.extend(create_lines)

    lines.append("        },")
    lines.append("    )")
    lines.append("")
    lines.append("    assert response.status_code == 201")
    lines.append(f'    return cast(str, response.json()["{pk_field}"])')
    lines.append("")

    return lines


def generate_conftest(
    entities: dict[str, dict[str, Any]],
    dependencies: dict[str, set[str]],
    enums: dict[str, str],
    constraints: dict[str, dict[str, Any]] | None = None,
    auth_strategy: str | None = None,
    rate_limiter_import: str | None = None,
) -> str:
    """Generate complete conftest.py content."""
    lines = []

    # Header
    lines.append(GENERATED_MARKER)
    lines.append('"""')
    lines.append("Shared fixtures for contract tests.")
    lines.append("")
    lines.append(
        "Provides common entity fixtures to avoid duplication across test files."
    )
    lines.append("")
    lines.append("Fixtures are organized by dependency chain - entities are created in")
    lines.append("dependency order (independent first, then dependent entities).")
    lines.append('"""')
    lines.append("")
    lines.append("import uuid")
    lines.append("from typing import cast")
    lines.append("")
    lines.append("import pytest")
    lines.append("from fastapi.testclient import TestClient")
    if rate_limiter_import:
        lines.append("")
        lines.append(f"from {rate_limiter_import} import limiter")
    lines.append("")

    if rate_limiter_import:
        lines.append("")
        lines.append("@pytest.fixture(autouse=True)")
        lines.append("def _reset_rate_limiter() -> None:")
        lines.append(
            '    """Reset slowapi rate-limit counters before each test '
            '(test isolation)."""'
        )
        lines.append("    limiter.reset()")
        lines.append("")

    # Sort entities by dependency
    entity_names = set(entities.keys())
    sorted_entities = topological_sort(entity_names, dependencies)

    # Group entities by dependency level for comments
    level_groups: dict[int, list[str]] = {}
    for entity_name in sorted_entities:
        deps = dependencies.get(entity_name, set())
        level = len(deps)
        if level not in level_groups:
            level_groups[level] = []
        level_groups[level].append(entity_name)

    # Generate fixtures grouped by dependency level
    for level in sorted(level_groups.keys()):
        level_entities = level_groups[level]

        # Add section comment
        if level == 0:
            lines.append("# " + "=" * 70)
            lines.append("# INDEPENDENT ENTITIES (no dependencies)")
            lines.append("# " + "=" * 70)
        else:
            dep_word = "DEPENDENCY" if level == 1 else "DEPENDENCIES"
            lines.append("")
            lines.append("# " + "=" * 70)
            lines.append(f"# ENTITIES WITH {level} {dep_word}")
            lines.append("# " + "=" * 70)
        lines.append("")

        # Generate fixtures for this level
        for entity_name in sorted(level_entities):
            entity_data = entities[entity_name]
            fixture_name = get_fixture_name(entity_name, entity_data)
            required_deps = dependencies.get(entity_name, set())

            fixture_lines = generate_fixture(
                entity_name,
                entity_data,
                fixture_name,
                required_deps,
                entities,
                enums,
                constraints,
                auth_strategy=auth_strategy,
            )
            lines.extend(fixture_lines)

    # Generate _alt fixtures for entities referenced multiple times
    alt_needed = find_alt_fixtures_needed(entities)
    if alt_needed:
        lines.append("")
        lines.append("# " + "=" * 70)
        lines.append("# ALTERNATE FIXTURES (for entities referenced multiple times)")
        lines.append("# " + "=" * 70)
        lines.append("")

        for entity_name in sorted(entities.keys()):
            entity_data = entities[entity_name]
            fixture_name = get_fixture_name(entity_name, entity_data)
            if fixture_name in alt_needed:
                alt_lines = generate_alt_fixture(
                    fixture_name,
                    entity_name,
                    entity_data,
                    enums,
                    constraints,
                    auth_strategy=auth_strategy,
                )
                lines.extend(alt_lines)

    return "\n".join(lines)


def generate_conftest_content(
    models_dir: Path,
    auth_strategy: str | None = None,
    rate_limiter_import: str | None = None,
) -> tuple[str, int]:
    """
    Generate content for conftest.py based on all models in the directory.

    Returns:
        tuple[str, int]: (content, fixture_count)
    """
    # Load enums
    enums = load_enums(models_dir)

    # Load constraints
    constraints = load_shared_constraints(models_dir)

    # Load all models
    models = load_all_models(models_dir)

    # Extract entities
    entities = extract_entities(models)

    # Find dependencies
    dependencies = find_foreign_key_dependencies(entities)

    # Generate content
    content = generate_conftest(
        entities,
        dependencies,
        enums,
        constraints,
        auth_strategy=auth_strategy,
        rate_limiter_import=rate_limiter_import,
    )

    return content, len(entities)
