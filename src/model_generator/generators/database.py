"""
Database model generation utilities.
"""

from pathlib import Path

from jinja2 import Environment

from ..utils.parser import scan_model_files


def generate_database_model(
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict:
    """Generate SQLAlchemy database model with all entities."""
    template = env.get_template("database/model.py.j2")
    content = template.render(model=model, config=config)

    output_dir = project_root / config["paths"]["database_models"]
    domain = model.get("domain", "models")
    output_file = output_dir / f"{domain}.py"

    return {"path": output_file, "content": content}


def generate_init(
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate __init__.py with exports for all model files."""
    output_dir = project_root / config["paths"]["database_models"]
    domains = scan_model_files(output_dir)

    # Include current model even if its file hasn't been written yet
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
) -> dict | None:
    """Generate FactoryBoy factories for test data generation."""
    template = env.get_template("database/factory.py.j2")
    content = template.render(model=model, config=config)

    db_models_dir = project_root / config["paths"]["database_models"]
    factories_dir = db_models_dir / "factories"

    domain = model.get("domain", "models")
    output_file = factories_dir / f"{domain}.py"

    return {"path": output_file, "content": content}
