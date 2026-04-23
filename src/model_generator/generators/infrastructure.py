"""
Infrastructure file generation (base, engine, main, errors, validators, etc.).
"""

from pathlib import Path

from jinja2 import Environment

from ..utils.constants import GENERATED_MARKER
from ..utils.templates import path_to_import


def generate_base(config: dict, env: Environment, project_root: Path) -> dict | None:
    """Generate SQLAlchemy Base class."""
    base_path = config["paths"].get("base", "backend/src/database/models/base.py")
    output_path = project_root / base_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/base.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_engine(config: dict, env: Environment, project_root: Path) -> dict | None:
    """Generate database engine and session management."""
    engine_path = config["paths"].get("engine", "backend/src/database/engine.py")
    output_path = project_root / engine_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/engine.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_types(config: dict, env: Environment, project_root: Path) -> dict | None:
    """Generate custom SQLAlchemy types (SqliteNumeric for financial/percentage)."""
    db_models = config["paths"].get("database_models", "backend/src/database/models")
    db_dir = str(Path(db_models).parent)
    output_path = project_root / db_dir / "types.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/types.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_database_init(
    config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate database package __init__.py with get_session export."""
    db_models = config["paths"].get("database_models", "backend/src/database/models")
    db_dir = str(Path(db_models).parent)
    output_path = project_root / db_dir / "__init__.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/database_init.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_errors(config: dict, env: Environment, project_root: Path) -> dict | None:
    """Generate API error formatting utilities."""
    errors_path = config["paths"].get("errors", "backend/src/api/errors.py")
    output_path = project_root / errors_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/errors.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_validators(
    config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate API validation utilities."""
    validators_path = config["paths"].get("validators", "backend/src/api/validators.py")
    output_path = project_root / validators_path

    template = env.get_template("infrastructure/validators.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_utils(config: dict, env: Environment, project_root: Path) -> dict | None:
    """Generate API utility functions (normalize_decimal)."""
    api_models_path = config["paths"].get("api_models", "backend/src/api/models")
    api_dir = str(Path(api_models_path).parent)
    output_path = project_root / api_dir / "utils.py"

    template = env.get_template("infrastructure/utils.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_gitignore(
    config: dict, env: Environment, project_root: Path
) -> dict | None:
    """Generate .gitignore for new projects (only if none exists)."""
    output_path = project_root / ".gitignore"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/gitignore.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_pyproject(
    config: dict,
    env: Environment,
    project_root: Path,
    project_config: dict,
    extra_deps: list[str] | None = None,
) -> dict | None:
    """Generate pyproject.toml for new projects (only if none exists)."""
    output_path = project_root / "pyproject.toml"

    if output_path.exists():
        return None

    project = project_config.get("project", {})
    raw_name = project.get("name", "my-project")
    project_slug = raw_name.lower().replace(" ", "-")

    deps = config.get("dependencies", {})
    runtime_deps = deps.get("runtime", [])
    dev_deps = deps.get("dev", [])

    # Merge domain-level extra dependencies
    if extra_deps:
        runtime_deps = sorted(set(runtime_deps + extra_deps))

    paths = config.get("paths", {})
    validators_path = paths.get("validators", "backend/src/api/validators.py")

    api_models_path = paths.get("api_models", "backend/src/api/models")
    utils_path = str(Path(api_models_path).parent / "utils.py")

    constraints_path = paths.get(
        "constraints", "backend/src/database/models/constraints.py"
    )

    # Top-level source directory for mutmut also_copy
    also_copy_dir = Path(validators_path).parts[0] + "/"

    # Package root for setuptools discovery (e.g., "backend/src")
    main_path = paths.get("main", "backend/src/main.py")
    package_root = str(Path(main_path).parent)

    raw_style = {
        **(config.get("style") or {}),
        **(project_config.get("style") or {}),
    }
    style = {
        "python_version": raw_style.get("python_version") or "3.11",
        "line_length": raw_style.get("line_length"),
        "quote_style": raw_style.get("quote_style"),
        "indent_style": raw_style.get("indent_style"),
    }

    template = env.get_template("infrastructure/pyproject.toml.j2")
    content = template.render(
        project=project,
        project_slug=project_slug,
        runtime_deps=runtime_deps,
        dev_deps=dev_deps,
        validators_path=validators_path,
        utils_path=utils_path,
        constraints_path=constraints_path,
        also_copy_dir=also_copy_dir,
        package_root=package_root,
        style=style,
    )

    return {"path": output_path, "content": content}


def generate_main(
    config: dict,
    env: Environment,
    project_root: Path,
    domains: list[str],
    project_config: dict,
) -> dict | None:
    """Generate FastAPI main application."""
    main_path = config["paths"].get("main", "backend/src/main.py")
    output_path = project_root / main_path

    python_root = config.get("python_root", "")

    api_routes_path = config["paths"].get("api_routes", "backend/src/api/routes")
    api_routes_import = path_to_import(api_routes_path, python_root=python_root)

    db_models_path = config["paths"].get(
        "database_models", "backend/src/database/models"
    )
    db_import = path_to_import(
        str(Path(db_models_path).parent), python_root=python_root
    )

    main_dir = str(Path(main_path).parent)
    main_module = path_to_import(main_dir, "main", python_root=python_root)

    template = env.get_template("infrastructure/main.py.j2")
    content = template.render(
        domains=domains,
        api_routes_import=api_routes_import,
        db_import=db_import,
        main_module=main_module,
        project=project_config.get("project", {}),
    )

    return {"path": output_path, "content": content}


def generate_test_conftest_root(
    config: dict,
    env: Environment,
    project_root: Path,
    domains: list[str],
) -> dict | None:
    """Generate root test conftest with database and client fixtures."""
    conftest_path = config["paths"].get("test_conftest_root", "tests/conftest.py")
    output_path = project_root / conftest_path

    python_root = config.get("python_root", "")

    database_models_path = config["paths"].get(
        "database_models", "backend/src/database/models"
    )
    database_models_import = path_to_import(
        database_models_path, python_root=python_root
    )

    main_path = config["paths"].get("main", "backend/src/main.py")
    main_dir = str(Path(main_path).parent)
    main_import = path_to_import(main_dir, "main", python_root=python_root)

    engine_path = config["paths"].get("engine", "backend/src/database/engine.py")
    engine_dir = str(Path(engine_path).parent)
    engine_import = path_to_import(engine_dir, "engine", python_root=python_root)

    factories_path = config["paths"].get(
        "factories", "backend/src/database/models/factories"
    )
    factories_import = path_to_import(factories_path, python_root=python_root)

    template = env.get_template("tests/conftest_root.py.j2")
    content = template.render(
        domains=domains,
        database_models_import=database_models_import,
        main_import=main_import,
        engine_import=engine_import,
        factories_import=factories_import,
    )

    return {"path": output_path, "content": content}


def generate_package_init_files(config: dict, project_root: Path) -> list[dict]:
    """
    Generate __init__.py files for all package directories.

    Creates empty __init__.py files in all necessary directories
    to make them proper Python packages.
    """
    outputs = []
    paths_config = config.get("paths", {})

    # Collect all directories that need __init__.py
    paths_to_init = []

    # Main source directory
    main_path = paths_config.get("main", "backend/src/main.py")
    src_dir = str(Path(main_path).parent)
    paths_to_init.append(src_dir)

    # Database paths
    db_models = paths_config.get("database_models", "backend/src/database/models")
    paths_to_init.append(db_models)

    # Factories
    factories = paths_config.get("factories", "backend/src/database/models/factories")
    paths_to_init.append(factories)

    # API paths
    api_models = paths_config.get("api_models", "backend/src/api/models")
    paths_to_init.append(api_models)
    api_dir = str(Path(api_models).parent)
    paths_to_init.append(api_dir)

    api_routes = paths_config.get("api_routes", "backend/src/api/routes")
    paths_to_init.append(api_routes)

    # Test paths (including parent directories)
    api_tests = paths_config.get("api_tests", "tests/contract/api")
    paths_to_init.append(api_tests)
    test_dir = api_tests
    while "/" in test_dir:
        test_dir = str(Path(test_dir).parent)
        paths_to_init.append(test_dir)

    # Generate __init__.py for each unique path
    init_content = f"{GENERATED_MARKER}\n"
    for path in sorted(set(paths_to_init)):
        init_path = project_root / path / "__init__.py"
        if not init_path.exists():
            outputs.append({"path": init_path, "content": init_content})

    return outputs


def generate_infrastructure(
    config: dict,
    env: Environment,
    project_root: Path,
    domains: list[str],
    project_config: dict,
    extra_deps: list[str] | None = None,
    diff: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """
    Generate all infrastructure files.

    Returns list of generated file paths.
    """
    print("\n🏗️  Generating infrastructure files...")

    outputs = []

    # Collect all infrastructure outputs
    generators = [
        generate_gitignore(config, env, project_root),
        generate_pyproject(config, env, project_root, project_config, extra_deps),
        generate_base(config, env, project_root),
        generate_engine(config, env, project_root),
        generate_types(config, env, project_root),
        generate_database_init(config, env, project_root),
        generate_errors(config, env, project_root),
        generate_validators(config, env, project_root),
        generate_utils(config, env, project_root),
        generate_main(config, env, project_root, domains, project_config),
        generate_test_conftest_root(config, env, project_root, domains),
    ]

    for result in generators:
        if result:
            outputs.append(result)

    # Add package init files
    outputs.extend(generate_package_init_files(config, project_root))

    # Process outputs
    generated_files = []
    for output in outputs:
        path = output["path"]
        content = output["content"]

        if diff:
            print(f"\n--- {path} ---")
            print(content[:500] + "..." if len(content) > 500 else content)
            continue

        if dry_run:
            print(f"  Would write: {path}")
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        print(f"  ✅ Generated: {path}")
        generated_files.append(path)

    return generated_files
