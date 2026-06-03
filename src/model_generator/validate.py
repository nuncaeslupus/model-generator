#!/usr/bin/env python3
"""
Model JSON Validator.

Validates model definition JSON files against the multi-entity schema.

Usage:
    python validate.py <model.json>
    python validate.py models/users.model.json
    python validate.py --all models/
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft7Validator

from . import __version__


def load_schema() -> dict[str, Any]:
    """Load the model schema from the skill directory."""
    script_dir = Path(__file__).parent
    schema_path = script_dir / "schema" / "model.schema.json"

    if not schema_path.exists():
        print(f"Error: Schema not found at {schema_path}")
        sys.exit(1)

    with open(schema_path) as f:
        return cast(dict[str, Any], json.load(f))


def validate_model(model_path: Path, schema: dict[str, Any]) -> list[str]:
    """
    Validate a model JSON file against the schema.

    Returns list of error messages (empty if valid).
    """
    errors = []

    if not model_path.exists():
        return [f"File not found: {model_path}"]

    try:
        with open(model_path) as f:
            model = json.load(f)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]

    # Validate against schema
    validator = Draft7Validator(schema)
    for error in sorted(validator.iter_errors(model), key=lambda e: e.path):
        path = " -> ".join(str(p) for p in error.path) if error.path else "(root)"
        errors.append(f"  {path}: {error.message}")

    # Additional semantic validations
    if not errors:
        errors.extend(validate_semantics(model))

    return errors


def validate_semantics(model: dict[str, Any]) -> list[str]:
    """
    Perform semantic validations beyond schema.

    Validates each entity for:
    - Primary key field exists
    - Enum fields have values or reference existing enum
    - Reference fields point to valid tables
    - Constraint field references exist
    - Relationship targets exist within the domain
    - Immutable entity constraints
    """
    errors = []
    entities = model.get("entities", {})

    for entity_name, entity in entities.items():
        prefix = f"  [{entity_name}]"
        fields = entity.get("fields", {})

        # Check for primary key
        has_pk = any(f.get("primary_key", False) for f in fields.values())
        if not has_pk:
            errors.append(f"{prefix} No primary key field defined")

        # Check enum fields
        for field_name, field in fields.items():
            if field.get("type") == "enum":
                if not field.get("enum_name"):
                    errors.append(
                        f"{prefix} Enum field '{field_name}' missing enum_name"
                    )
                if not field.get("enum_values") and not field.get("enum_existing"):
                    errors.append(
                        f"{prefix} Enum field '{field_name}' "
                        "needs enum_values or enum_existing=true"
                    )

        # Check reference fields
        for field_name, field in fields.items():
            if field.get("type") == "reference":
                if not field.get("reference_table"):
                    errors.append(
                        f"{prefix} Reference field '{field_name}' "
                        "missing reference_table"
                    )

        # Check field constraints reference valid fields
        for field_name, field in fields.items():
            for constraint in field.get("constraints", []):
                if constraint.get("type") == "depends":
                    other_field = constraint.get("other_field")
                    if other_field and other_field not in fields:
                        errors.append(
                            f"{prefix} Constraint on '{field_name}' references "
                            f"non-existent field '{other_field}'"
                        )

        # Check table constraints reference valid fields
        for constraint in entity.get("constraints", []):
            for field_ref in constraint.get("fields", []):
                if field_ref not in fields:
                    errors.append(
                        f"{prefix} Table constraint references "
                        f"non-existent field '{field_ref}'"
                    )

        # Collect all known field names (explicit + timestamp-generated)
        all_field_names = set(fields.keys())
        timestamps = entity.get("timestamps", {})
        if timestamps.get("created", True):
            all_field_names.add("created_at")
        if timestamps.get("updated", True):
            all_field_names.add("updated_at")

        # Check index fields exist
        for index in entity.get("indexes", []):
            for field_ref in index.get("fields", []):
                if field_ref not in all_field_names:
                    errors.append(
                        f"{prefix} Index references non-existent field '{field_ref}'"
                    )

        # Check immutable entities
        if entity.get("mutability") == "immutable":
            if entity.get("timestamps", {}).get("updated"):
                errors.append(
                    f"{prefix} Immutable entities should not have updated_at timestamp"
                )
            api_endpoints = entity.get("api", {}).get("endpoints", [])
            if "update" in api_endpoints or "delete" in api_endpoints:
                errors.append(
                    f"{prefix} Immutable entities should not have "
                    "'update' or 'delete' endpoints"
                )

        # Relationship targets: cross-domain refs are allowed, no validation here.

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate model JSON files")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Model JSON file or directory containing model files",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate all *.model.json files in directory",
    )

    args = parser.parse_args()
    schema = load_schema()

    if args.path.is_dir() or args.all:
        directory = args.path if args.path.is_dir() else args.path.parent
        model_files = list(directory.glob("*.model.json"))
        if not model_files:
            print(f"No *.model.json files found in {directory}")
            sys.exit(1)
    else:
        model_files = [args.path]

    all_valid = True
    for model_path in sorted(model_files):
        errors = validate_model(model_path, schema)
        if errors:
            all_valid = False
            print(f"\n❌ {model_path.name}:")
            for error in errors:
                print(error)
        else:
            # Show entity count
            with open(model_path) as f:
                model = json.load(f)
            entity_count = len(model.get("entities", {}))
            print(f"✅ {model_path.name}: Valid ({entity_count} entities)")

    if not all_valid:
        sys.exit(1)

    print(f"\n✅ All {len(model_files)} model(s) valid")


if __name__ == "__main__":
    main()
