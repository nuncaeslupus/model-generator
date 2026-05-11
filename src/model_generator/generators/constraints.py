"""
Constraint generation utilities.
"""

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment

from ..utils.loaders import load_shared_constraints


def get_existing_constraints(constraints_file: Path) -> set[str]:
    """Parse existing constraints.py to find defined constant names."""
    if not constraints_file.exists():
        return set()

    content = constraints_file.read_text()
    pattern = r"^([A-Z][A-Z0-9_]*)\s*="
    return set(re.findall(pattern, content, re.MULTILINE))


def extract_constraint_refs(
    model: dict[str, Any], shared_constraints: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract all constraint references from model field definitions."""
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()

    for entity in model.get("entities", {}).values():
        for field_name, field in entity.get("fields", {}).items():
            for constraint in field.get("constraints", []):
                _extract_ref(
                    constraint,
                    "min_ref",
                    shared_constraints,
                    field_name,
                    refs,
                    seen,
                    is_min=True,
                )
                _extract_ref(
                    constraint,
                    "max_ref",
                    shared_constraints,
                    field_name,
                    refs,
                    seen,
                    is_min=False,
                )
                _extract_regex_ref(
                    constraint, shared_constraints, field_name, refs, seen
                )

    return refs


def _extract_ref(
    constraint: dict[str, Any],
    ref_key: str,
    shared_constraints: dict[str, Any],
    field_name: str,
    refs: list[dict[str, Any]],
    seen: set[str],
    is_min: bool,
) -> None:
    """Extract min_ref or max_ref from constraint."""
    if ref_key not in constraint or constraint[ref_key] in seen:
        return

    ref_name = constraint[ref_key]
    ref_def = shared_constraints.get(ref_name, {})
    refs.append(
        {
            "name": ref_name,
            "type": ref_def.get("type", constraint.get("type", "decimal")),
            "field": field_name,
            "is_min": is_min,
            "value": ref_def.get("value"),
            "description": ref_def.get("description"),
        }
    )
    seen.add(ref_name)


def _extract_regex_ref(
    constraint: dict[str, Any],
    shared_constraints: dict[str, Any],
    field_name: str,
    refs: list[dict[str, Any]],
    seen: set[str],
) -> None:
    """Extract regex_ref from constraint."""
    if "regex_ref" not in constraint or constraint["regex_ref"] in seen:
        return

    ref_name = constraint["regex_ref"]
    ref_def = shared_constraints.get(ref_name, {})
    refs.append(
        {
            "name": ref_name,
            "type": "pattern",
            "field": field_name,
            "value": ref_def.get("value"),
            "description": ref_def.get("description"),
        }
    )
    seen.add(ref_name)


def generate_constraints(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    model_path: Path | None = None,
) -> dict[str, Any] | None:
    """
    Generate constraint constants from _shared/constraints.json.

    Creates file if missing, appends new constraints if file exists.
    """
    shared_constraints = load_shared_constraints(
        model_path if model_path is not None else project_root
    )
    all_refs = extract_constraint_refs(model, shared_constraints)

    if not all_refs:
        return None

    output_dir = project_root / config["paths"]["database_models"]
    constraints_file = output_dir / "constraints.py"
    file_exists = constraints_file.exists()

    if file_exists:
        existing = get_existing_constraints(constraints_file)
        new_refs = [ref for ref in all_refs if ref["name"] not in existing]

        if not new_refs:
            print(f"  ℹ️  All constraint constants already exist in {constraints_file}")
            return None

        template = env.get_template("database/constraints.py.j2")
        content = template.render(
            mode="append",
            section_header="CONSTRAINTS",
            constraints=new_refs,
            include_helpers=False,
            config=config,
        )

        return {
            "path": constraints_file,
            "content": "\n" + content,
            "mode": "append",
            "new_count": len(new_refs),
            "skipped": len(all_refs) - len(new_refs),
        }
    else:
        template = env.get_template("database/constraints.py.j2")
        content = template.render(
            mode="create",
            section_header="CONSTRAINTS",
            constraints=all_refs,
            include_helpers=True,
            config=config,
        )

        return {
            "path": constraints_file,
            "content": content,
            "mode": "write",
            "new_count": len(all_refs),
            "skipped": 0,
        }
