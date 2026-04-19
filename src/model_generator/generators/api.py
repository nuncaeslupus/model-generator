"""
API generation utilities (models, routes, tests).
"""

from pathlib import Path

from jinja2 import Environment

from ..utils.loaders import load_shared_constraints, load_shared_enums
from ..utils.parser import scan_api_model_files


def _filter_api_entities(model: dict) -> dict | None:
    """Return model copy with only API-enabled entities, or None if none."""
    entities = {
        name: entity
        for name, entity in model.get("entities", {}).items()
        if entity.get("api", {}).get("enabled", True)
    }
    if not entities:
        return None
    return {**model, "entities": entities}


def _filter_test_entities(model: dict) -> dict | None:
    """Return model copy with only test-enabled entities, or None if none."""
    entities = {
        name: entity
        for name, entity in model.get("entities", {}).items()
        if entity.get("tests", {}).get("enabled", True)
    }
    if not entities:
        return None
    return {**model, "entities": entities}


def generate_api_models(
    model: dict,
    config: dict,
    env: Environment,
    project_root: Path,
    model_path: Path | None = None,
) -> list[dict] | None:
    """Generate Pydantic response and request models."""
    filtered = _filter_api_entities(model)
    if filtered is None:
        return None

    enums = load_shared_enums(model_path or project_root)

    outputs = []
    domain = filtered.get("domain", "models")
    output_dir = project_root / config["paths"]["api_models"]

    # Response models
    template = env.get_template("api/response.py.j2")
    content = template.render(model=filtered, config=config, enums=enums)
    outputs.append({"path": output_dir / f"{domain}_response.py", "content": content})

    # Request models
    template = env.get_template("api/request.py.j2")
    content = template.render(model=filtered, config=config, enums=enums)
    outputs.append({"path": output_dir / f"{domain}_requests.py", "content": content})

    return outputs


def generate_api_init(
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate __init__.py with exports for all API model files."""
    output_dir = project_root / config["paths"]["api_models"]
    domains = scan_api_model_files(output_dir)

    # Include current model even if its files haven't been written yet
    filtered = _filter_api_entities(model)
    current_domain = model.get("domain", "unknown")
    domain_names = {d["name"] for d in domains}
    if filtered is not None and current_domain not in domain_names:
        entities = list(filtered.get("entities", {}).keys())
        domains.append(
            {
                "name": current_domain,
                "section": current_domain.upper().replace("_", " ") + " MODELS",
                "response_models": [f"{e}Response" for e in entities],
                "request_models": [f"Create{e}Request" for e in entities]
                + [
                    f"Update{e}Request"
                    for e in entities
                    if filtered["entities"][e].get("mutability", "mutable")
                    != "immutable"
                ],
            }
        )

    if not domains:
        print(f"  ℹ️  No API model files found in {output_dir}")
        return None

    total_responses = sum(len(d["response_models"]) for d in domains)
    total_requests = sum(len(d["request_models"]) for d in domains)

    template = env.get_template("api/init.py.j2")
    content = template.render(domains=domains, config=config)

    return {
        "path": output_dir / "__init__.py",
        "content": content,
        "mode": "write",
        "domain_count": len(domains),
        "response_count": total_responses,
        "request_count": total_requests,
    }


def generate_api_pagination(
    model: dict, config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate pagination.py with reusable pagination models."""
    output_dir = project_root / config["paths"]["api_models"]
    pagination_file = output_dir / "pagination.py"

    if pagination_file.exists():
        print(f"  ℹ️  Pagination file already exists at {pagination_file}")
        print("     To regenerate, delete the file first")
        return None

    template = env.get_template("api/pagination.py.j2")
    content = template.render(config=config)

    return {"path": pagination_file, "content": content, "mode": "write"}


def generate_api_routes(
    model: dict,
    config: dict,
    env: Environment,
    project_root: Path,
    enums: dict | None = None,
    constraints: dict | None = None,
    model_path: Path | None = None,
) -> dict | None:
    """Generate FastAPI routes."""
    filtered = _filter_api_entities(model)
    if filtered is None:
        return None

    if enums is None:
        enums = load_shared_enums(model_path or project_root)
    if constraints is None:
        constraints = load_shared_constraints(model_path or project_root)

    template = env.get_template("api/route.py.j2")
    content = template.render(
        model=filtered, config=config, enums=enums, constraints=constraints
    )

    output_dir = project_root / config["paths"]["api_routes"]
    domain = filtered.get("domain", "models")
    output_file = output_dir / f"{domain}.py"

    return {"path": output_file, "content": content}


def generate_api_tests(
    model: dict,
    config: dict,
    env: Environment,
    project_root: Path,
    enums: dict | None = None,
    constraints: dict | None = None,
    model_path: Path | None = None,
) -> dict | None:
    """Generate API contract tests."""
    # Both API and tests must be enabled
    filtered = _filter_api_entities(model)
    if filtered is None:
        return None
    filtered = _filter_test_entities(filtered)
    if filtered is None:
        return None

    if enums is None:
        enums = load_shared_enums(model_path or project_root)
    if constraints is None:
        constraints = load_shared_constraints(model_path or project_root)

    template = env.get_template("tests/contract.py.j2")
    content = template.render(
        model=filtered, config=config, enums=enums, constraints=constraints
    )

    output_dir = project_root / config["paths"]["api_tests"]
    domain = filtered.get("domain", "models")
    output_file = output_dir / f"test_{domain}_api.py"

    return {"path": output_file, "content": content}
