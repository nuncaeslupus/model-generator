"""
Database model generation utilities.
"""

from pathlib import Path
from typing import cast

from jinja2 import Environment

from ..utils.parser import scan_model_files
from ..utils.templates import snake_case


def _layout(config: dict) -> str:
    """Return the configured generation layout (defaulting to per-entity)."""
    return cast(str, config.get("generation", {}).get("layout", "per-entity"))


def generate_database_model(
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | list[dict]:
    """Generate SQLAlchemy database model(s).

    In per-entity layout (the default) returns one dict per entity, each
    pointing at ``{entity_snake}.py``. In per-domain layout returns a single
    dict pointing at ``{domain}.py`` with all entities in one file.
    """
    template = env.get_template("database/model.py.j2")
    output_dir = project_root / config["paths"]["database_models"]
    sibling_entities = list(model.get("entities", {}).keys())

    if _layout(config) == "per-entity":
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
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate __init__.py with exports for all model files."""
    output_dir = project_root / config["paths"]["database_models"]
    domains = scan_model_files(output_dir)

    if _layout(config) == "per-entity":
        existing_files = {d["file"] for d in domains}
        for name in model.get("entities", {}).keys():
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
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | list[dict]:
    """Generate FactoryBoy factories for test data generation.

    Per-entity layout returns one factory file per entity; per-domain returns
    a single combined file. ``sibling_entities`` (the full domain entity
    list) is threaded into the template so cross-entity ``create_related``
    blocks survive the per-entity slicing of ``model.entities``.
    """
    template = env.get_template("database/factory.py.j2")
    factories_dir = project_root / config["paths"]["database_models"] / "factories"
    sibling_entities = list(model.get("entities", {}).keys())

    if _layout(config) == "per-entity":
        return [
            {
                "path": factories_dir / f"{snake_case(name)}.py",
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
    return {"path": factories_dir / f"{domain}.py", "content": content}
