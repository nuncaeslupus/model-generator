#!/usr/bin/env python3
"""
Model Code Generator.

Generates code files from multi-entity model JSON definitions using Jinja2 templates.

Usage:
    python generate.py <model.json> [--target TARGET] [--diff] [--dry-run]
    python generate.py <model-directory> [--target TARGET]
    python generate.py models/users.model.json --target database
    python generate.py models/ --target all

TDD Generation Order (when --target all):
    1. database     - SQLAlchemy models (source of truth)
    2. api-models   - Pydantic request/response models
    3. api-tests    - Contract tests (RED phase)
    4. api-routes   - FastAPI routes (GREEN phase)
"""

import argparse
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .generators import (
    generate_api_init,
    generate_api_models,
    generate_api_pagination,
    generate_api_routes,
    generate_api_tests,
    generate_constraints,
    generate_database_model,
    generate_enums,
    generate_factories,
    generate_infrastructure,
    generate_init,
    generate_migration_autogen,
    generate_migration_init,
)
from .utils import (
    get_layout,
    get_template_env,
    load_config,
    load_shared_constraints,
    load_shared_enums,
    run_quality_tools,
)
from .utils import load_model as load_model
from .utils.conftest_generator import generate_conftest_content
from .utils.templates import path_to_import, snake_case

# TDD-ordered generation targets
INFRASTRUCTURE_TARGETS = [
    "base",
    "engine",
    "main",
    "test-conftest-root",
]

DOMAIN_TARGETS = [
    "enums",
    "constraints",
    "init",
    "database",
    "factories",
    "api-models",
    "api-init",
    "api-pagination",
    "api-tests",
    "api-tests-config",
    "api-routes",
    "migration-init",
    "migration-autogen",
]

TARGETS = INFRASTRUCTURE_TARGETS + DOMAIN_TARGETS + ["infrastructure", "all"]


# Generator dispatch table
_GeneratorFn = Callable[
    [dict[str, Any], dict[str, Any], Any, Path, Path],
    dict[str, Any] | list[dict[str, Any]] | None,
]

GENERATORS: dict[str, _GeneratorFn] = {
    "enums": lambda m, c, e, p, mp: generate_enums(m, c, e, p, mp),
    "constraints": lambda m, c, e, p, mp: generate_constraints(m, c, e, p, mp),
    "init": lambda m, c, e, p, mp: generate_init(m, c, e, p),
    "database": lambda m, c, e, p, mp: generate_database_model(m, c, e, p),
    "factories": lambda m, c, e, p, mp: generate_factories(m, c, e, p, mp),
    "api-models": lambda m, c, e, p, mp: generate_api_models(m, c, e, p, mp),
    "api-init": lambda m, c, e, p, mp: generate_api_init(m, c, e, p),
    "api-pagination": lambda m, c, e, p, mp: generate_api_pagination(m, c, e, p),
}


def cleanup_generated(
    project_root: Path, scope: str = "selective", dry_run: bool = False
) -> None:
    """
    Delete generated code files.

    Args:
        project_root: Project root directory
        scope: "selective" (generated files only) or "full" (entire directories)
        dry_run: Show what would be deleted without deleting
    """
    config = load_config()
    paths = config.get("paths", {})

    if scope == "full":
        _cleanup_full(project_root, paths, dry_run)
    else:
        _cleanup_selective(project_root, paths, dry_run)


def _cleanup_full(project_root: Path, paths: dict[str, Any], dry_run: bool) -> None:
    """Delete entire source directories and generated files."""
    dirs_to_delete = set()
    files_to_delete = set()

    # Generated source directories
    for key in ["database_models", "factories", "api_models", "api_routes"]:
        if key in paths:
            path_parts = paths[key].split("/")
            if path_parts:
                dirs_to_delete.add(project_root / path_parts[0])

    # Test directory
    api_tests = paths.get("api_tests", "tests/contract/api")
    test_root = api_tests.split("/")[0]
    dirs_to_delete.add(project_root / test_root)

    # Migrations directory
    dirs_to_delete.add(project_root / paths.get("migrations", "alembic"))

    # Cache directories
    cache_dirs = [
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        ".venv",
        "venv",
    ]
    for cache_dir in cache_dirs:
        cache_path = project_root / cache_dir
        if cache_path.exists():
            dirs_to_delete.add(cache_path)

    # Find all __pycache__ recursively in project source/tests
    for src_dir in [
        project_root / "backend",
        project_root / "tests",
        project_root / "src",
    ]:
        if src_dir.exists():
            for pycache in src_dir.rglob("__pycache__"):
                dirs_to_delete.add(pycache)

    # Generated files
    alembic_ini = project_root / "alembic.ini"
    if alembic_ini.exists():
        files_to_delete.add(alembic_ini)

    print("🗑️  Full cleanup mode:")

    # Delete files first
    for file_path in sorted(files_to_delete):
        print(f"  {'Would delete' if dry_run else 'Deleting'}: {file_path}")
        if not dry_run:
            file_path.unlink()

    # Delete directories
    for dir_path in sorted(dirs_to_delete):
        if dir_path.exists():
            print(f"  {'Would delete' if dry_run else 'Deleting'}: {dir_path}")
            if not dry_run:
                shutil.rmtree(dir_path)

    if not dry_run:
        print("✅ Cleanup complete")


def _cleanup_selective(
    project_root: Path, paths: dict[str, Any], dry_run: bool
) -> None:
    """Delete only generated files, not entire directories."""
    files_to_delete: list[Path] = []
    dirs_to_delete: list[Path] = []

    patterns = []
    for key in ["database_models", "factories", "api_models", "api_routes"]:
        if key in paths:
            patterns.append(f"{paths[key]}/*.py")
            # Also include __init__.py in these directories
            patterns.append(f"{paths[key]}/__init__.py")

    api_tests = paths.get("api_tests", "tests/contract/api")
    patterns.append(f"{api_tests}/*.py")
    patterns.append(f"{api_tests}/__init__.py")

    # Add parent __init__.py for tests
    test_dir = api_tests
    while "/" in test_dir:
        test_dir = str(Path(test_dir).parent)
        patterns.append(f"{test_dir}/__init__.py")

    migrations = paths.get("migrations", "alembic")
    patterns.append(f"{migrations}/versions/*.py")
    # Alembic infra files
    patterns.append(f"{migrations}/env.py")
    patterns.append(f"{migrations}/script.py.mako")
    patterns.append(f"{migrations}/README.md")
    patterns.append(f"{migrations}/versions/.gitkeep")

    # All explicit file paths in config
    for path in paths.values():
        if isinstance(path, str) and (path.endswith(".py") or path.endswith(".ini")):
            files_to_delete.append(project_root / path)

    # Derived infrastructure files
    if "api_models" in paths:
        api_dir = Path(paths["api_models"]).parent
        files_to_delete.append(project_root / api_dir / "utils.py")
        files_to_delete.append(project_root / api_dir / "__init__.py")

    if "database_models" in paths:
        db_dir = Path(paths["database_models"]).parent
        files_to_delete.append(project_root / db_dir / "types.py")
        files_to_delete.append(project_root / db_dir / "__init__.py")

    if "main" in paths:
        src_dir = Path(paths["main"]).parent
        files_to_delete.append(project_root / src_dir / "__init__.py")

    # Also include alembic.ini
    alembic_ini = project_root / "alembic.ini"
    if alembic_ini.exists():
        files_to_delete.append(alembic_ini)

    for pattern in patterns:
        files_to_delete.extend(project_root.glob(pattern))

    # Find __pycache__ in generated directories (recursive) and their parents
    # (non-recursive — parents may contain user-written code whose __pycache__
    # must not be touched).
    generated_dirs: set[Path] = set()
    parent_dirs: set[Path] = set()
    for key in [
        "database_models",
        "factories",
        "api_models",
        "api_routes",
        "api_tests",
        "migrations",
    ]:
        if key in paths:
            path = project_root / paths[key]
            if path.exists():
                generated_dirs.add(path)
                if key != "migrations":
                    parent_dirs.add(path.parent)

    for d in generated_dirs:
        if d.is_dir():
            for pycache in d.rglob("__pycache__"):
                dirs_to_delete.append(pycache)

    for d in parent_dirs:
        if d.is_dir():
            for pycache in d.glob("__pycache__"):
                dirs_to_delete.append(pycache)

    print("🗑️  Selective cleanup mode:")
    deleted_count = 0
    # Use set to avoid duplicates, but filter for existence
    for file_path in sorted({f for f in files_to_delete if f.exists()}):
        print(f"  {'Would delete' if dry_run else 'Deleting'}: {file_path}")
        if not dry_run and file_path.is_file():
            file_path.unlink()
            deleted_count += 1

    for dir_path in sorted(set(dirs_to_delete)):
        if dir_path.exists() and dir_path.is_dir():
            print(f"  {'Would delete' if dry_run else 'Deleting'}: {dir_path}")
            if not dry_run:
                shutil.rmtree(dir_path)

    if not dry_run:
        print(f"✅ Cleanup complete ({deleted_count} files)")


def generate_conftest(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Any,
    project_root: Path,
    model_path: Path,
) -> dict[str, Any] | None:
    """Generate conftest.py with fixtures for all domains."""
    models_dir = model_path.parent if model_path.is_file() else model_path

    auth_strategy = config.get("auth", {}).get("strategy")
    rate_limiter_import = _compute_rate_limiter_import(config)
    content, _count = generate_conftest_content(
        models_dir,
        auth_strategy=auth_strategy,
        rate_limiter_import=rate_limiter_import,
        auth_router_import=_compute_auth_router_import(config),
        main_import=_compute_main_import(config),
    )
    output_dir = project_root / config["paths"]["api_tests"]
    output_file = output_dir / "conftest.py"

    return {"path": output_file, "content": content, "mode": "write"}


def _compute_rate_limiter_import(config: dict[str, Any]) -> str | None:
    """Return the import path to the auth rate_limit module, or None.

    Mirrors the import-path logic in ``generators/infrastructure.py``: emits
    a value only when ``auth.strategy`` is set and rate limiting is enabled
    (the slowapi default-on behavior).
    """
    auth = config.get("auth") or {}
    if not auth.get("strategy"):
        return None
    rate_limit = auth.get("rate_limit") or {}
    if rate_limit.get("enabled") is False:
        return None
    auth_path = auth.get("path", "backend/src/auth/router.py")
    rate_limit_module_path = str(Path(auth_path).parent / "rate_limit")
    python_root = config.get("python_root", "")
    return path_to_import(rate_limit_module_path, python_root=python_root)


def _compute_auth_router_import(config: dict[str, Any]) -> str | None:
    """Return the import path to the auth router module, or None when auth is off.

    The default-auth contract fixture imports ``get_current_user`` from here to
    override the owner identity. Mirrors the route template's
    ``from <auth.path> import get_current_user``.
    """
    auth = config.get("auth") or {}
    if not auth.get("strategy"):
        return None
    auth_path = auth.get("path", "backend/src/auth/router.py")
    module = str(Path(auth_path).with_suffix(""))
    return path_to_import(module, python_root=config.get("python_root", ""))


def _compute_main_import(config: dict[str, Any]) -> str | None:
    """Return the import path to the FastAPI app module, or None when auth is off.

    The default-auth contract fixture imports ``app`` from here to register a
    dependency override. Only needed alongside the auth router import.
    """
    auth = config.get("auth") or {}
    if not auth.get("strategy"):
        return None
    main_path = config.get("paths", {}).get("main", "backend/src/main.py")
    module = str(Path(main_path).with_suffix(""))
    return path_to_import(module, python_root=config.get("python_root", ""))


def _compute_auth_extra(config: dict[str, Any]) -> list[str]:
    """Runtime deps the auth scaffolding pulls in. Empty when auth is off.

    The auth router uses bcrypt for password hashing and itsdangerous for
    cookie/token signing. email-validator backs Pydantic's EmailStr. slowapi
    is added when rate limiting is enabled (default-on); redis is added when
    its storage backend is selected.
    """
    auth = config.get("auth") or {}
    if not auth.get("strategy"):
        return []
    extra = ["bcrypt>=4.0.0", "itsdangerous>=2.0", "email-validator>=2.0"]
    rate_limit = auth.get("rate_limit") or {}
    if rate_limit.get("enabled") is not False:
        extra.append("slowapi>=0.1.9")
        if rate_limit.get("backend") == "redis":
            extra.append("redis>=4.0")
    return extra


def _has_encrypted_binary_field(models: list[dict[str, Any]]) -> bool:
    """True when any loaded model has a ``binary`` field with an ``encrypt`` block.

    Mirrors the ``ns.has_encrypted_binary`` template flag in ``model.py.j2``
    and gates the project-wide emission of ``encrypted_bytes.py``.
    """
    return any(
        field.get("type") == "binary" and "encrypt" in field
        for model in models
        for entity in model.get("entities", {}).values()
        for field in entity.get("fields", {}).values()
    )


def generate(
    model_path: Path,
    target: str = "all",
    diff: bool = False,
    dry_run: bool = False,
    stack: str = "python-fastapi",
    no_root_files: bool = False,
) -> None:
    """Generate code from model definition."""
    project_root = _find_project_root(model_path)
    _validate_project_root(project_root)

    model = load_model(model_path)
    config = load_config(stack)
    _validate_auth_config(model, config)
    _validate_generation_config(config)
    _validate_paths_base(config)
    _validate_composite_foreign_keys(model)
    env = get_template_env(stack, config)

    domain = model.get("domain", "unknown")
    entity_count = len(model.get("entities", {}))

    print(f"\n🔧 Generating code for domain: {domain} ({entity_count} entities)")
    print(f"   Target: {target}")
    print(f"   Stack: {stack}")

    outputs = []
    targets_to_generate = TARGETS[:-1] if target == "all" else [target]

    # Pre-load shared data to avoid duplicate loading
    enums = load_shared_enums(model_path)
    constraints = load_shared_constraints(model_path)

    for t in targets_to_generate:
        result = _generate_target(
            t,
            model,
            config,
            env,
            project_root,
            model_path,
            enums,
            constraints,
            no_root_files=no_root_files,
        )
        if result is None:
            continue
        if isinstance(result, list):
            outputs.extend(result)
        else:
            outputs.append(result)

    generated_files = _process_outputs(outputs, diff, dry_run)

    if generated_files and not dry_run and not diff:
        run_quality_tools(config, project_root, generated_files)

    if not diff and not dry_run:
        print(f"\n✅ Generated {len(generated_files)} file(s)")


def _find_project_root(model_path: Path) -> Path:
    """Find project root by looking for .model-generator.yaml."""
    project_root = Path.cwd()
    if not (project_root / ".model-generator.yaml").exists():
        parent = project_root.parent
        if (parent / ".model-generator.yaml").exists():
            project_root = parent
        else:
            project_root = model_path.parent.parent
            if model_path.parent.name == "models":
                project_root = model_path.parent.parent
    return project_root


# The directory that contains model-generator's own source code.
# Used to guard against accidentally generating into the tool itself.
_GENERATOR_OWN_DIR = Path(__file__).parent.parent.parent.resolve()


def _validate_project_root(project_root: Path) -> None:
    """
    Abort if project_root is unsafe to generate into.

    Raises SystemExit when:
    - No .model-generator.yaml exists in project_root (not a generated project)
    - project_root is model-generator's own source directory
    """
    resolved = project_root.resolve()

    if resolved == _GENERATOR_OWN_DIR:
        print(
            f"Error: Refusing to generate into model-generator's own directory "
            f"({resolved}).\n"
            "Run model-gen from inside your target project, or pass the models "
            "directory as a path relative to that project."
        )
        sys.exit(1)

    if not (project_root / ".model-generator.yaml").exists():
        print(
            f"Error: No .model-generator.yaml found in {project_root}.\n"
            "Create a .model-generator.yaml in your project root, or run model-gen "
            "from inside the project directory."
        )
        sys.exit(1)


def _validate_auth_config(model: dict[str, Any], config: dict[str, Any]) -> None:
    """Abort if any entity declares api.scope without auth.dependency_path in config."""
    scoped = [
        name
        for name, entity in model.get("entities", {}).items()
        if entity.get("api", {}).get("scope")
    ]
    if not scoped:
        return

    auth_dep = config.get("auth", {}).get("dependency_path")
    if not auth_dep:
        names = ", ".join(scoped)
        print(
            f"Error: Entities ({names}) declare api.scope but "
            "auth.dependency_path is not set in .model-generator.yaml.\n\n"
            "Add this to your .model-generator.yaml:\n\n"
            "  auth:\n"
            '    dependency_path: "path.to.your.get_current_user"\n\n'
            "The generator will import this function and inject it via "
            "FastAPI's Depends() in scoped endpoints."
        )
        sys.exit(1)

    if "." not in auth_dep:
        print(
            f'Error: auth.dependency_path "{auth_dep}" must be a dotted path '
            'like "module.submodule.get_current_user".\n'
            "The segment before the last dot is the import module; the segment "
            "after is the callable."
        )
        sys.exit(1)


def _validate_generation_config(config: dict[str, Any]) -> None:
    """Abort if generation.layout has an unknown value."""
    valid = {"per-entity", "per-domain"}
    layout = get_layout(config)
    if layout not in valid:
        choices = ", ".join(repr(v) for v in sorted(valid))
        print(
            f"Error: generation.layout must be one of [{choices}], "
            f'got "{layout}".\n\n'
            "Set in .model-generator.yaml:\n\n"
            "  generation:\n"
            '    layout: "per-entity"  # default; one file per entity\n'
            "  # or\n"
            "  generation:\n"
            '    layout: "per-domain"  # legacy; one file per domain'
        )
        sys.exit(1)


def _validate_paths_base(config: dict[str, Any]) -> None:
    """Abort if paths.base is not inside paths.database_models (or misnamed).

    Generated database model files emit ``from .base import Base`` (relative),
    so the base module must live inside paths.database_models AND be named
    ``base.py``. A mismatch is silent at generation time but raises
    ``ModuleNotFoundError`` at import or test-collection time.
    """
    paths = config.get("paths", {})
    db_models_str = paths.get("database_models", "backend/src/database/models")
    base_str = paths.get("base", f"{db_models_str}/base.py")

    base_path = Path(base_str)
    if base_path.name != "base.py":
        print(
            f'Error: paths.base filename must be "base.py" '
            f'(got "{base_path.name}" from "{base_str}").\n\n'
            "Generated model files import the base module with a hardcoded "
            "relative 'from .base import Base' statement, so the filename "
            "is fixed.\n\n"
            "Fix in .model-generator.yaml:\n\n"
            "  paths:\n"
            f"    base: {base_path.parent}/base.py"
        )
        sys.exit(1)

    if base_path.parent != Path(db_models_str):
        print(
            f'Error: paths.base ("{base_str}") must live inside '
            f'paths.database_models ("{db_models_str}"), '
            f'but its parent is "{base_path.parent}".\n\n'
            "Generated model files import the base module with a relative "
            "'from .base import Base' statement, so paths.base must be a "
            "child of paths.database_models on disk.\n\n"
            "Fix in .model-generator.yaml:\n\n"
            "  paths:\n"
            f"    database_models: {db_models_str}\n"
            f"    base: {db_models_str}/base.py"
        )
        sys.exit(1)


def _validate_composite_foreign_keys(model: dict[str, Any]) -> None:
    """Abort if any entity declares a composite foreign_key with invalid structure.

    Per composite FK, checks:
    - len(fk.fields) == len(fk.references_columns)
    - All names in fk.fields exist in entity.fields
    - No fk.fields member is typed "reference" (mutex with single-column FK)
    - fk.references_table matches an entity table in this model

    Cross-model composite FKs (target entity in another model file) are
    rejected for v1; the underlying template emission works mechanically,
    but cross-model validation is deferred.
    """
    entities = model.get("entities", {}) or {}
    known_tables = {entity.get("table") for entity in entities.values()}

    errors: list[str] = []
    for entity_name, entity in entities.items():
        entity_fields = entity.get("fields", {}) or {}
        for fk_idx, fk in enumerate(entity.get("foreign_keys", []) or []):
            label = f"{entity_name}.foreign_keys[{fk_idx}]"
            fields = fk.get("fields") or []
            ref_cols = fk.get("references_columns") or []
            ref_table = fk.get("references_table")

            if len(fields) != len(ref_cols):
                errors.append(
                    f"  - {label}: fields has {len(fields)} entries but "
                    f"references_columns has {len(ref_cols)} (must match)"
                )

            for f in fields:
                if f not in entity_fields:
                    errors.append(
                        f'  - {label}: field "{f}" not declared in {entity_name}.fields'
                    )
                elif entity_fields[f].get("type") == "reference":
                    errors.append(
                        f'  - {label}: field "{f}" has type "reference" '
                        "(mutex with composite FK — declare as the underlying "
                        'type like "uuid" instead)'
                    )

            if ref_table not in known_tables:
                known = ", ".join(sorted(t for t in known_tables if t))
                errors.append(
                    f'  - {label}: references_table "{ref_table}" not found '
                    f"in this model (known tables: {known})"
                )

    if errors:
        joined = "\n".join(errors)
        print(
            "Error: Invalid composite foreign_keys declarations:\n\n"
            f"{joined}\n\n"
            "Composite FKs require:\n"
            "  - All listed fields declared in entity.fields\n"
            '  - Fields typed as their underlying type (not "reference")\n'
            "  - references_columns count equal to fields count\n"
            "  - references_table matching an entity table in this model"
        )
        sys.exit(1)


def _validate_auth_strategy(
    models: list[dict[str, Any]], config: dict[str, Any]
) -> None:
    """Abort if auth.strategy is set but its prerequisites are missing.

    Cross-model validation: takes the full list of loaded models so it can
    check that *some* spec contains a User entity with a password_hash field.
    Called once from main() after the aggregation loop, not per-model.
    """
    auth = config.get("auth") or {}
    strategy = auth.get("strategy")
    if not strategy:
        return

    valid_strategies = {"bcrypt-session"}
    if strategy not in valid_strategies:
        choices = ", ".join(repr(v) for v in sorted(valid_strategies))
        print(
            f'Error: auth.strategy "{strategy}" is not supported.\n'
            f"Allowed strategies: [{choices}].\n\n"
            "Set in .model-generator.yaml:\n\n"
            "  auth:\n"
            '    strategy: "bcrypt-session"\n'
            '    pepper_env: "APP_PASSWORD_PEPPER"'
        )
        sys.exit(1)

    pepper_env = auth.get("pepper_env")
    if not isinstance(pepper_env, str) or not pepper_env.strip():
        print(
            f'Error: auth.strategy "{strategy}" requires auth.pepper_env to '
            "name a non-empty environment variable.\n\n"
            "Set in .model-generator.yaml:\n\n"
            "  auth:\n"
            f'    strategy: "{strategy}"\n'
            '    pepper_env: "APP_PASSWORD_PEPPER"'
        )
        sys.exit(1)

    layout = get_layout(config)
    if layout != "per-entity":
        print(
            f'Error: auth.strategy "{strategy}" currently requires '
            f'generation.layout: per-entity (got "{layout}").\n\n'
            "Set in .model-generator.yaml:\n\n"
            "  generation:\n"
            '    layout: "per-entity"\n\n'
            "Per-domain auth scaffolding may be added in a future version."
        )
        sys.exit(1)

    user_entity = None
    for model in models:
        entities = model.get("entities", {}) or {}
        if "User" in entities:
            user_entity = entities["User"]
            break

    if user_entity is None:
        print(
            f'Error: auth.strategy "{strategy}" requires a "User" entity in '
            "your model specifications, but none was found.\n\n"
            'Define a User entity with a "password_hash" field in one of your '
            "*.model.json files."
        )
        sys.exit(1)

    fields = user_entity.get("fields", {}) or {}
    if "password_hash" not in fields:
        print(
            f'Error: auth.strategy "{strategy}" requires the "User" entity to '
            'have a "password_hash" field, but none was found.\n\n'
            "Add to your User entity:\n\n"
            '  "password_hash": {\n'
            '    "type": "text",\n'
            '    "max_length": 255,\n'
            '    "required": true,\n'
            '    "api_field_name": "password",\n'
            '    "api_exclude_response": true,\n'
            '    "api_exclude_update": true\n'
            "  }"
        )
        sys.exit(1)

    for required_field in ("username", "email", "last_login_at"):
        if required_field not in fields:
            print(
                f'Error: auth.strategy "{strategy}" requires the "User" entity '
                f'to have a "{required_field}" field, but none was found.\n\n'
                "The generated auth router uses this field to register, "
                "authenticate, or track user sessions."
            )
            sys.exit(1)


def _validate_auth_scope_coverage(
    models: list[dict[str, Any]], config: dict[str, Any]
) -> None:
    """Warn if auth.strategy is set but no API-enabled entity declares api.scope.

    CRUD routes are unauthenticated by default; the auth scaffold is only
    wired in when an entity sets api.scope. An auth-on project with zero
    scoped entities ships a fully-open API, which is almost always unintentional.
    """
    auth = config.get("auth") or {}
    if not auth.get("strategy"):
        return

    scoped: list[str] = []
    api_enabled: list[str] = []
    for model in models:
        for entity_name, entity in (model.get("entities") or {}).items():
            api_cfg = entity.get("api") or {}
            if not api_cfg.get("enabled", True):
                continue
            api_enabled.append(entity_name)
            if api_cfg.get("scope"):
                scoped.append(entity_name)

    if api_enabled and not scoped:
        print(
            "Warning: auth.strategy is set but no API-enabled entity declares\n"
            "api.scope. All generated CRUD endpoints will be unauthenticated.\n\n"
            "Add api.scope to owner-bound entities, for example:\n\n"
            '  "api": {\n'
            '    "scope": {"owner_field": "user_id"}\n'
            "  }\n\n"
            f"API-enabled entities found: {', '.join(sorted(set(api_enabled)))}\n"
            "See docs/user/usage-guide.md for details."
        )


def _generate_target(
    target: str,
    model: dict[str, Any],
    config: dict[str, Any],
    env: Any,
    project_root: Path,
    model_path: Path,
    enums: dict[str, Any],
    constraints: dict[str, Any],
    no_root_files: bool = False,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Generate a single target, returning output dict(s) or None."""
    # Use dispatch table for simple generators
    if target in GENERATORS:
        return GENERATORS[target](model, config, env, project_root, model_path)

    # Handle special cases
    if target == "api-tests":
        return generate_api_tests(model, config, env, project_root, enums, constraints)
    elif target == "api-tests-config":
        return generate_conftest(model, config, env, project_root, model_path)
    elif target == "api-routes":
        return generate_api_routes(model, config, env, project_root, enums, constraints)
    elif target == "migration-init":
        return generate_migration_init(
            model, config, env, project_root, no_root_files=no_root_files
        )
    elif target == "migration-autogen":
        # Instruction-only target: prints guidance, emits no file.
        generate_migration_autogen(model, config, env, project_root)
        return None

    return None


def _process_outputs(
    outputs: list[dict[str, Any]], diff: bool, dry_run: bool
) -> list[Path]:
    """Write outputs to files, returning list of generated paths."""
    generated_files = []

    for output in outputs:
        path = output["path"]
        content = output["content"]
        mode = output.get("mode", "write")

        if diff:
            print(f"\n--- {path} ---")
            if mode == "append":
                print(f"[Would append - {output.get('new_count', 0)} new items]")
            elif path.exists():
                print("[Would update existing file]")
            else:
                print("[Would create new file]")
            print(content[:500] + "..." if len(content) > 500 else content)
            continue

        if dry_run:
            action = "append to" if mode == "append" else "write"
            print(f"  Would {action}: {path}")
            continue

        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with path.open("a", encoding="utf-8") as f:
                f.write(content)
            new_count = output.get("new_count", 0)
            skipped = output.get("skipped", 0)
            print(f"  ✅ Appended {new_count} item(s) to: {path}")
            if skipped > 0:
                print(f"     (skipped {skipped} already existing)")
        else:
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  ✅ Generated: {path}")

        generated_files.append(path)

    return generated_files


def _prepare_infra_modules(
    model_files: list[Path],
    config: dict[str, Any],
) -> tuple[list[str], list[str], list[str], list[str], list[dict[str, Any]]]:
    """Collect module lists and extra deps for infrastructure generation.

    Shared by main() and the interactive wizard so both paths produce an
    identical pyproject.toml and validate auth prerequisites.
    """
    layout = get_layout(config)
    domains: list[str] = []
    route_modules: list[str] = []
    factory_modules: list[str] = []
    extra_deps: list[str] = []
    loaded_models: list[dict[str, Any]] = []

    for model_file in model_files:
        model = load_model(model_file)
        loaded_models.append(model)
        domain = model.get("domain", "unknown")
        has_api = any(
            e.get("api", {}).get("enabled", True)
            for e in (model.get("entities") or {}).values()
        )
        if domain not in domains and has_api:
            domains.append(domain)

        if layout == "per-entity":
            for name, entity in (model.get("entities") or {}).items():
                stem = snake_case(name)
                if (
                    entity.get("api", {}).get("enabled", True)
                    and stem not in route_modules
                ):
                    route_modules.append(stem)
                if has_api and stem not in factory_modules:
                    factory_modules.append(stem)

        extra_deps.extend(model.get("dependencies", []))

    extra_deps = sorted(set(extra_deps))

    _validate_auth_strategy(loaded_models, config)
    _validate_auth_scope_coverage(loaded_models, config)

    auth_extra = _compute_auth_extra(config)
    if auth_extra:
        extra_deps = sorted(set(extra_deps + auth_extra))

    if layout != "per-entity":
        route_modules = list(domains)
        factory_modules = list(domains)

    return domains, route_modules, factory_modules, extra_deps, loaded_models


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate code from model definitions")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "model",
        type=Path,
        nargs="?",
        default=None,
        help="Model JSON file or directory containing *.model.json files",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch interactive wizard",
    )
    parser.add_argument(
        "--target",
        choices=TARGETS,
        default="all",
        help="Generation target (default: all)",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show what would be generated without writing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show files that would be created without writing",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Delete generated files before generating",
    )
    parser.add_argument(
        "--scope",
        choices=["selective", "full"],
        default="selective",
        help="Cleanup scope (requires --clean)",
    )
    parser.add_argument(
        "--clear-only",
        action="store_true",
        help="Only delete generated files without regenerating",
    )
    parser.add_argument(
        "--no-root-files",
        action="store_true",
        help=(
            "Skip pyproject.toml, alembic.ini, and .gitignore emission "
            "(for the scratch-and-migrate workflow)"
        ),
    )
    parser.add_argument(
        "--stack",
        default="python-fastapi",
        help="Stack configuration to use (default: python-fastapi)",
    )

    args = parser.parse_args()

    # Handle --interactive: launch wizard and exit
    if args.interactive:
        from .wizard import run_wizard

        run_wizard()
        return

    # Handle --clear-only: just cleanup and exit (doesn't require model argument)
    if args.clear_only:
        project_root = Path.cwd()
        if not (project_root / ".model-generator.yaml").exists():
            parent = project_root.parent
            if (parent / ".model-generator.yaml").exists():
                project_root = parent
        _validate_project_root(project_root)
        cleanup_generated(project_root, scope=args.scope, dry_run=args.dry_run)
        return

    # Model is required for all other operations
    if args.model is None:
        print("Error: Model argument is required (unless using --clear-only)")
        sys.exit(1)

    if not args.model.exists():
        print(f"Error: Model file or directory not found: {args.model}")
        sys.exit(1)

    if args.clean and args.dry_run:
        print(f"🗑️  Preview mode: Would clean {args.scope} scope then generate")

    # Handle directory or single file
    model_files = []
    if args.model.is_dir():
        model_files = sorted(args.model.glob("*.model.json"))
        if not model_files:
            print(f"Error: No *.model.json files found in {args.model}")
            sys.exit(1)
    else:
        model_files = [args.model]

    # Find project root; falls back to model_path.parent.parent when no config in cwd
    project_root = _find_project_root(model_files[0])
    _validate_project_root(project_root)

    # Cleanup if requested
    if args.clean:
        cleanup_generated(project_root, scope=args.scope, dry_run=args.dry_run)
        if not args.dry_run:
            print()

    config = load_config(args.stack)
    env = get_template_env(args.stack, config)

    (
        domains,
        route_modules,
        factory_modules,
        extra_deps,
        loaded_models,
    ) = _prepare_infra_modules(model_files, config)

    has_encrypted_binary = _has_encrypted_binary_field(loaded_models)

    # Generate infrastructure
    if (
        args.target in ("all", "infrastructure")
        or args.target in INFRASTRUCTURE_TARGETS
    ):
        infra_files = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=domains,
            route_modules=route_modules,
            factory_modules=factory_modules,
            project_config=config,
            extra_deps=extra_deps,
            diff=args.diff,
            dry_run=args.dry_run,
            has_encrypted_binary=has_encrypted_binary,
            no_root_files=args.no_root_files,
        )
        if infra_files and not args.dry_run and not args.diff:
            run_quality_tools(config, project_root, infra_files)

    if args.target == "infrastructure":
        print("\n✅ Infrastructure generation complete")
        return

    # Generate for each model
    for model_file in model_files:
        print(f"\nGenerating from: {model_file}")
        generate(
            model_path=model_file,
            target=args.target,
            diff=args.diff,
            dry_run=args.dry_run,
            stack=args.stack,
            no_root_files=args.no_root_files,
        )


if __name__ == "__main__":
    main()
