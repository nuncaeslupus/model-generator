"""
Database model generation utilities.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment

from ..utils.loaders import get_layout, load_shared_constraints
from ..utils.parser import scan_model_files
from ..utils.templates import snake_case


def generate_database_model(
    model: dict[str, Any], config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | list[dict[str, Any]]:
    """Generate SQLAlchemy database model(s).

    In per-entity layout (the default) returns one dict per entity, each
    pointing at ``{entity_snake}.py``. In per-domain layout returns a single
    dict pointing at ``{domain}.py`` with all entities in one file.
    """
    template = env.get_template("database/model.py.j2")
    output_dir = project_root / config["paths"]["database_models"]
    sibling_entities = list(model.get("entities", {}).keys())

    if get_layout(config) == "per-entity":
        return [
            {
                "path": output_dir / f"{snake_case(name)}.py",
                "content": template.render(
                    model={**model, "entities": {name: entity}},
                    config=config,
                    sibling_entities=sibling_entities,
                ),
            }
            for name, entity in model.get("entities", {}).items()
        ]

    domain = model.get("domain", "models")
    content = template.render(
        model=model, config=config, sibling_entities=sibling_entities
    )
    return {"path": output_dir / f"{domain}.py", "content": content}


def generate_init(
    model: dict[str, Any], config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate __init__.py with exports for all model files."""
    output_dir = project_root / config["paths"]["database_models"]
    domains = scan_model_files(output_dir)

    if get_layout(config) == "per-entity":
        existing_files = {d["file"] for d in domains}
        for name in model.get("entities", {}):
            stem = snake_case(name)
            if stem not in existing_files:
                domains.append(
                    {
                        "name": stem,
                        "file": stem,
                        "section": None,
                        "entities": [name],
                    }
                )
    else:
        current_domain = model.get("domain", "unknown")
        domain_names = {d["name"] for d in domains}
        if current_domain not in domain_names:
            domains.append(
                {
                    "name": current_domain,
                    "file": current_domain,
                    "section": model.get("section_header"),
                    "entities": list(model.get("entities", {}).keys()),
                }
            )

    if not domains:
        print(f"  ℹ️  No model files found in {output_dir}")
        return None

    total_entities = sum(len(d["entities"]) for d in domains)

    template = env.get_template("database/init.py.j2")
    content = template.render(domains=domains, config=config)

    return {
        "path": output_dir / "__init__.py",
        "content": content,
        "mode": "write",
        "domain_count": len(domains),
        "entity_count": total_entities,
    }


def generate_factories(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    model_path: Path | None = None,
    constraints: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    """Generate FactoryBoy factories for test data generation.

    Per-entity layout returns one factory file per entity; per-domain returns
    a single combined file. ``sibling_entities`` (the full domain entity
    list) is threaded into the template so cross-entity ``create_related``
    blocks survive the per-entity slicing of ``model.entities``.

    ``constraints`` (the flattened shared-constraint dict) is threaded into
    the template so ``min_ref`` / ``max_ref`` bounds on financial/counter
    fields resolve to literal values at generation time — the factory module
    never imports the constraints module, so emitting the bare constant name
    would ``NameError`` at ``create()`` time.
    """
    template = env.get_template("database/factory.py.j2")
    factories_dir = project_root / config["paths"]["factories"]
    sibling_entities = list(model.get("entities", {}).keys())
    if constraints is None:
        constraints = load_shared_constraints(model_path or project_root)

    # Build table-name → entity-name mapping for resolving reference fields.
    all_entities = model.get("entities", {})
    table_to_entity: dict[str, str] = {
        entity.get("table", snake_case(name) + "s"): name
        for name, entity in all_entities.items()
        if entity is not None
    }

    if get_layout(config) == "per-entity":
        return [
            {
                "path": factories_dir / f"{snake_case(name)}.py",
                "content": template.render(
                    model={**model, "entities": {name: entity}},
                    config=config,
                    sibling_entities=sibling_entities,
                    constraints=constraints,
                    table_to_entity=table_to_entity,
                ),
            }
            for name, entity in model.get("entities", {}).items()
        ]

    domain = model.get("domain", "models")
    content = template.render(
        model=model,
        config=config,
        sibling_entities=sibling_entities,
        constraints=constraints,
        table_to_entity=table_to_entity,
    )
    return {"path": factories_dir / f"{domain}.py", "content": content}
