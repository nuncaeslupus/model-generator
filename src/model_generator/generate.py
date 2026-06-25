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
from pathlib import Path
from typing import Any

from . import __version__

# Importing the flutter package registers its StackSpec into STACKS at import
# time (mirrors the inline python-fastapi registration below). Kept for the
# registration side effect.
from .generators import flutter as _flutter  # noqa: F401
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
from .generators.registry import (
    CleanupSpec,
    GenContext,
    StackSpec,
    TargetGenerator,
    get_stack,
    register_stack,
)
from .utils import (
    get_layout,
    get_template_env,
    load_config,
    load_shared_constraints,
    load_shared_enums,
    run_quality_tools,
)
from .utils import load_model as load_model  # explicit re-export for mypy strict
from .utils.conftest_generator import generate_conftest_content
from .utils.output import write_outputs
from .utils.quality import run_ruff_quality
from .utils.templates import path_to_import, snake_case


def cleanup_generated(
    project_root: Path,
    scope: str = "selective",
    dry_run: bool = False,
    cleanup_spec: CleanupSpec | None = None,
) -> None:
    """
    Delete generated code files.

    Args:
        project_root: Project root directory
        scope: "selective" (generated files only) or "full" (entire directories)
        dry_run: Show what would be deleted without deleting
        cleanup_spec: stack cleanup descriptor; defaults to python-fastapi.
    """
    config = load_config()
    spec = cleanup_spec or PYTHON_FASTAPI_STACK.cleanup_spec
    # Expand stack-specific path placeholders (e.g. flutter's {pkg}) so the
    # cleanup globs and derived_files target real directories; python-fastapi
    # has no resolver and uses config["paths"] verbatim.
    paths = (
        spec.path_resolver(config)
        if spec.path_resolver is not None
        else config.get("paths", {})
    )

    if scope == "full":
        _cleanup_full(project_root, paths, dry_run, spec)
    else:
        _cleanup_selective(project_root, paths, dry_run, spec)


def _cleanup_full(
    project_root: Path,
    paths: dict[str, Any],
    dry_run: bool,
    spec: CleanupSpec,
) -> None:
    """Delete entire source directories and generated files."""
    dirs_to_delete = set()
    files_to_delete = set()

    # Generated source directories
    for key in spec.source_path_keys:
        if key in paths:
            path_parts = paths[key].split("/")
            if path_parts:
                dirs_to_delete.add(project_root / path_parts[0])

    # Test directory
    api_tests = paths.get(spec.test_path_key, "tests/contract/api")
    test_root = api_tests.split("/")[0]
    dirs_to_delete.add(project_root / test_root)

    # Migrations directory
    if spec.migrations_path_key is not None:
        dirs_to_delete.add(
            project_root / paths.get(spec.migrations_path_key, "alembic")
        )

    # Cache / build directories (stack-specific)
    for cache_dir in spec.full_cleanup_dirs:
        cache_path = project_root / cache_dir
        if cache_path.exists():
            dirs_to_delete.add(cache_path)

    # Find all __pycache__ recursively in project source/tests (python only)
    if spec.file_glob == "*.py":
        for src_dir in [
            project_root / "backend",
            project_root / "tests",
            project_root / "src",
        ]:
            if src_dir.exists():
                for pycache in src_dir.rglob("__pycache__"):
                    dirs_to_delete.add(pycache)

    # Generated top-level files (stack-specific)
    for file_name in spec.full_cleanup_files:
        file_path = project_root / file_name
        if file_path.exists():
            files_to_delete.add(file_path)

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
    project_root: Path,
    paths: dict[str, Any],
    dry_run: bool,
    spec: CleanupSpec,
) -> None:
    """Delete only generated files, not entire directories."""
    files_to_delete: list[Path] = []
    dirs_to_delete: list[Path] = []

    glob = spec.file_glob
    init_name = "__init__.py" if glob == "*.py" else None

    patterns = []
    for key in spec.source_path_keys:
        if key in paths:
            patterns.append(f"{paths[key]}/{glob}")
            # Also include __init__.py in these directories (python packages)
            if init_name:
                patterns.append(f"{paths[key]}/{init_name}")

    api_tests = paths.get(spec.test_path_key, "tests/contract/api")
    patterns.append(f"{api_tests}/{glob}")
    if init_name:
        patterns.append(f"{api_tests}/{init_name}")

        # Add parent __init__.py for tests (python packages)
        test_dir = api_tests
        while "/" in test_dir:
            test_dir = str(Path(test_dir).parent)
            patterns.append(f"{test_dir}/{init_name}")

    if spec.migrations_path_key is not None:
        migrations = paths.get(spec.migrations_path_key, "alembic")
        # Generated migration revisions (stack-agnostic — uses the stack's glob).
        # Stack-specific migration scaffold files (alembic's env.py/script.py.mako/
        # README.md/.gitkeep) are contributed by the stack's ``derived_files``.
        patterns.append(f"{migrations}/versions/{glob}")

    # All explicit file paths in config
    for path in paths.values():
        if isinstance(path, str) and (path.endswith(".py") or path.endswith(".ini")):
            files_to_delete.append(project_root / path)

    # Stack-derived infrastructure files (e.g. python's utils.py/types.py siblings,
    # __init__.py packages, alembic.ini).
    if spec.derived_files is not None:
        files_to_delete.extend(spec.derived_files(project_root, paths))

    for pattern in patterns:
        files_to_delete.extend(project_root.glob(pattern))

    # Find __pycache__ in generated directories (recursive) and their parents
    # (non-recursive — parents may contain user-written code whose __pycache__
    # must not be touched). Python only.
    if glob == "*.py":
        generated_dirs: set[Path] = set()
        parent_dirs: set[Path] = set()
        pycache_keys = [*spec.source_path_keys, spec.test_path_key]
        if spec.migrations_path_key is not None:
            pycache_keys.append(spec.migrations_path_key)
        for key in pycache_keys:
            if key in paths:
                path = project_root / paths[key]
                if path.exists():
                    generated_dirs.add(path)
                    if key != spec.migrations_path_key:
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
    # For the api-key strategy the contract suite overrides require_api_key with
    # a no-op (CRUD tests don't carry the header); it needs the dotted path the
    # loader inferred onto auth.dependency_path.
    api_key_dependency = (
        (config.get("auth") or {}).get("dependency_path")
        if auth_strategy == "api-key"
        else None
    )
    content, _count = generate_conftest_content(
        models_dir,
        auth_strategy=auth_strategy,
        rate_limiter_import=rate_limiter_import,
        auth_router_import=_compute_auth_router_import(config),
        main_import=_compute_main_import(config),
        api_key_dependency=api_key_dependency,
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
    # Rate limiting is session-strategy infrastructure only; the api-key strategy
    # ships no rate_limit module, so the conftest must not try to import one.
    if auth.get("strategy") != "bcrypt-session":
        return None
    rate_limit = auth.get("rate_limit") or {}
    if rate_limit.get("enabled") is False:
        return None
    auth_path = auth.get("path", "backend/src/auth/router.py")
    rate_limit_module_path = str(Path(auth_path).parent / "rate_limit")
    python_root = config.get("python_root", "")
    return path_to_import(rate_limit_module_path, python_root=python_root)


def _compute_auth_router_import(config: dict[str, Any]) -> str | None:
    """Return the import path to the auth router module, or None.

    The default-auth contract fixture imports ``get_current_user`` from here to
    override the owner identity. Mirrors the route template's
    ``from <auth.path> import get_current_user``. Session strategy only — the
    api-key strategy emits no router.
    """
    auth = config.get("auth") or {}
    if auth.get("strategy") != "bcrypt-session":
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
    # .model-generator.yaml `stack:` overrides the argument default so callers
    # don't need to pass --stack when the project config already declares it.
    # Note: in the stack's own config.yaml, `stack:` is a metadata dict
    # ({name, description, version}), not a stack name; only a plain string
    # from the project yaml represents an actual override.
    _stack_field = config.get("stack")
    actual_stack = _stack_field if isinstance(_stack_field, str) else stack
    if actual_stack != stack:
        config = load_config(actual_stack)
    spec = get_stack(actual_stack)
    for validator in spec.validators:
        validator(model, config)
    env = get_template_env(actual_stack, config)

    domain = model.get("domain", "unknown")
    entity_count = len(model.get("entities", {}))

    print(f"\n🔧 Generating code for domain: {domain} ({entity_count} entities)")
    print(f"   Target: {target}")
    print(f"   Stack: {actual_stack}")

    outputs = []
    # When "all", iterate every concrete target plus the "infrastructure"
    # aggregate (a no-op in per-model dispatch, kept for byte-identical order).
    targets_to_generate = (
        [*spec.generation_targets, "infrastructure"] if target == "all" else [target]
    )

    # Pre-load shared data to avoid duplicate loading
    enums = load_shared_enums(model_path)
    constraints = load_shared_constraints(model_path)

    for t in targets_to_generate:
        ctx = GenContext(
            model=model,
            config=config,
            env=env,
            project_root=project_root,
            model_path=model_path,
            enums=enums,
            constraints=constraints,
            no_root_files=no_root_files,
            dry_run=dry_run,
            diff=diff,
        )
        result = _generate_target(t, spec, ctx)
        if result is None:
            continue
        if isinstance(result, list):
            outputs.extend(result)
        else:
            outputs.append(result)

    generated_files = _process_outputs(outputs, diff, dry_run)

    if generated_files and not dry_run and not diff:
        run_quality_tools(config, project_root, generated_files, spec.quality_runner)

    if not diff and not dry_run:
        print(f"\n✅ Generated {len(generated_files)} file(s)")


def _find_project_root(model_path: Path) -> Path:
    """Find project root by looking for .model-generator.yaml.

    Resolution order:
    1. CWD has .model-generator.yaml → use CWD (standard invocation).
    2. CWD's parent has .model-generator.yaml → use parent (monorepo: run
       from a sub-directory).
    3. Fall back to the model file's location: if the model lives in a
       ``models/`` directory, the project root is its parent; otherwise the
       model file's own directory is the root.
    """
    project_root = Path.cwd()
    if not (project_root / ".model-generator.yaml").exists():
        parent = project_root.parent
        if (parent / ".model-generator.yaml").exists():
            project_root = parent
        elif model_path.parent.name == "models":
            project_root = model_path.parent.parent
        else:
            project_root = model_path.parent
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
    paths = config.get("paths") or {}
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

    valid_strategies = {"bcrypt-session", "api-key"}
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

    # The api-key strategy is self-contained: a single shared secret read from
    # an env var (key_env, default API_KEY). It needs no User entity, no pepper,
    # and works in any layout — so the session-strategy prerequisites below
    # don't apply.
    if strategy == "api-key":
        key_env = auth.get("key_env", "API_KEY")
        if not isinstance(key_env, str) or not key_env.strip():
            print(
                'Error: auth.strategy "api-key" requires auth.key_env to name a '
                "non-empty environment variable (defaults to API_KEY).\n\n"
                "Set in .model-generator.yaml:\n\n"
                "  auth:\n"
                '    strategy: "api-key"\n'
                '    key_env: "API_KEY"'
            )
            sys.exit(1)
        return

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
    """Warn if auth.strategy is set but no API-enabled entity opts into auth.

    CRUD routes are unauthenticated by default; the auth scaffold is only
    wired in per-entity — via ``api.scope`` (bcrypt-session, owner filtering)
    or ``api.require_auth`` (api-key, gate on a shared key). An auth-on project
    with zero protected entities ships a fully-open API, which is almost always
    unintentional.
    """
    auth = config.get("auth") or {}
    strategy = auth.get("strategy")
    if not strategy:
        return

    # The opt-in key (and the remediation example) depends on the strategy.
    api_key_strategy = strategy == "api-key"
    opt_in_key = "require_auth" if api_key_strategy else "scope"

    protected: list[str] = []
    api_enabled: list[str] = []
    for model in models:
        for entity_name, entity in (model.get("entities") or {}).items():
            api_cfg = entity.get("api") or {}
            if not api_cfg.get("enabled", True):
                continue
            api_enabled.append(entity_name)
            if api_cfg.get(opt_in_key):
                protected.append(entity_name)

    if api_enabled and not protected:
        if api_key_strategy:
            example = '  "api": {\n    "require_auth": true\n  }\n\n'
        else:
            example = '  "api": {\n    "scope": {"owner_field": "user_id"}\n  }\n\n'
        print(
            "Warning: auth.strategy is set but no API-enabled entity declares\n"
            f"api.{opt_in_key}. All generated CRUD endpoints will be "
            "unauthenticated.\n\n"
            "Add it to the entities you want protected, for example:\n\n"
            + example
            + f"API-enabled entities found: {', '.join(sorted(set(api_enabled)))}\n"
            "See docs/user/usage-guide.md for details."
        )


def _generate_target(
    target: str,
    spec: StackSpec,
    ctx: GenContext,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Generate a single target via the stack's generator dispatch table.

    Targets not registered as domain generators (infrastructure targets and the
    ``infrastructure`` aggregate) are no-ops here — infrastructure is emitted by
    ``spec.infra_orchestrator`` in ``main()``.
    """
    generator = spec.generators.get(target)
    if generator is None:
        return None
    return generator(ctx)


def _process_outputs(
    outputs: list[dict[str, Any]], diff: bool, dry_run: bool
) -> list[Path]:
    return write_outputs(outputs, diff, dry_run)


def _prepare_infra_modules(
    model_files: list[Path],
    config: dict[str, Any],
    spec: StackSpec | None = None,
) -> tuple[list[str], list[str], list[str], list[str], list[dict[str, Any]]]:
    """Collect module lists and extra deps for infrastructure generation.

    Shared by main() and the interactive wizard so both paths produce an
    identical pyproject.toml and validate auth prerequisites. ``spec`` supplies
    the stack's cross-model infra validators and extra-deps computation;
    defaults to python-fastapi.
    """
    spec = spec or PYTHON_FASTAPI_STACK
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

    for infra_validator in spec.infra_validators:
        infra_validator(loaded_models, config)

    if spec.extra_deps_fn is not None:
        stack_extra = spec.extra_deps_fn(config)
        if stack_extra:
            extra_deps = sorted(set(extra_deps + stack_extra))

    if layout != "per-entity":
        route_modules = list(domains)
        factory_modules = list(domains)

    return domains, route_modules, factory_modules, extra_deps, loaded_models


# ===================================================================
# python-fastapi stack registration
# ===================================================================
#
# Wraps the existing generator set into a StackSpec. This is a mechanical
# refactor of the former module-level GENERATORS/TARGET lists/validators —
# behavior is byte-identical to the pre-registry orchestration.


def _python_derived_cleanup_files(
    project_root: Path, paths: dict[str, Any]
) -> list[Path]:
    """Extra explicit files python-fastapi cleanup must remove.

    Reproduces the former inline derivation in ``_cleanup_selective``: the
    ``utils.py``/``types.py`` infrastructure siblings, the package ``__init__.py``
    files next to the api/db/main modules, ``alembic.ini``, and the alembic
    migration scaffold (``env.py``/``script.py.mako``/``README.md``/``.gitkeep``)
    — all Python/Alembic-specific, so the shared selective-cleanup stays generic.
    """
    files: list[Path] = []

    if "api_models" in paths:
        api_dir = Path(paths["api_models"]).parent
        files.append(project_root / api_dir / "utils.py")
        files.append(project_root / api_dir / "__init__.py")

    if "database_models" in paths:
        db_dir = Path(paths["database_models"]).parent
        files.append(project_root / db_dir / "types.py")
        files.append(project_root / db_dir / "__init__.py")

    if "main" in paths:
        src_dir = Path(paths["main"]).parent
        files.append(project_root / src_dir / "__init__.py")

    alembic_ini = project_root / "alembic.ini"
    if alembic_ini.exists():
        files.append(alembic_ini)

    migrations_dir = project_root / paths.get("migrations", "alembic")
    files.extend(
        [
            migrations_dir / "env.py",
            migrations_dir / "script.py.mako",
            migrations_dir / "README.md",
            migrations_dir / "versions" / ".gitkeep",
        ]
    )

    return files


_PYTHON_FASTAPI_CLEANUP = CleanupSpec(
    source_path_keys=("database_models", "factories", "api_models", "api_routes"),
    test_path_key="api_tests",
    migrations_path_key="migrations",
    file_glob="*.py",
    derived_files=_python_derived_cleanup_files,
    full_cleanup_dirs=(
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        ".venv",
        "venv",
    ),
    full_cleanup_files=("alembic.ini",),
)


# Domain-target generators wrapped into the uniform GenContext signature. The
# wrappers thread only the arguments each underlying generator actually reads,
# matching the former GENERATORS dispatch table + special cases exactly.
_PYTHON_FASTAPI_GENERATORS: dict[str, TargetGenerator] = {
    "enums": lambda c: generate_enums(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "constraints": lambda c: generate_constraints(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "init": lambda c: generate_init(c.model, c.config, c.env, c.project_root),
    "database": lambda c: generate_database_model(
        c.model, c.config, c.env, c.project_root
    ),
    "factories": lambda c: generate_factories(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "api-models": lambda c: generate_api_models(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "api-init": lambda c: generate_api_init(c.model, c.config, c.env, c.project_root),
    "api-pagination": lambda c: generate_api_pagination(
        c.model, c.config, c.env, c.project_root
    ),
    "api-tests": lambda c: generate_api_tests(
        c.model, c.config, c.env, c.project_root, c.enums, c.constraints
    ),
    "api-tests-config": lambda c: generate_conftest(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "api-routes": lambda c: generate_api_routes(
        c.model, c.config, c.env, c.project_root, c.enums, c.constraints
    ),
    "migration-init": lambda c: generate_migration_init(
        c.model,
        c.config,
        c.env,
        c.project_root,
        no_root_files=c.no_root_files,
        dry_run=c.dry_run,
        diff=c.diff,
    ),
    "migration-autogen": lambda c: _run_migration_autogen(c),
}


def _run_migration_autogen(
    ctx: GenContext,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Instruction-only target: prints guidance, emits no file."""
    generate_migration_autogen(ctx.model, ctx.config, ctx.env, ctx.project_root)
    return None


# The StackSpec wires its orchestrator / validators / deps through thin wrappers
# that resolve the underlying module-level functions *at call time* rather than
# capturing references at construction. This keeps the historical
# patch-the-module-attribute test seams working (e.g. patching
# ``generate.generate_infrastructure`` or ``generate._validate_auth_strategy``)
# and stays byte-identical to the pre-registry call sites.


def _infra_orchestrator(**kwargs: Any) -> list[Path]:
    return generate_infrastructure(**kwargs)


def _validate_generation_config_v(
    model: dict[str, Any], config: dict[str, Any]
) -> None:
    _validate_generation_config(config)


def _validate_paths_base_v(model: dict[str, Any], config: dict[str, Any]) -> None:
    _validate_paths_base(config)


def _validate_composite_foreign_keys_v(
    model: dict[str, Any], config: dict[str, Any]
) -> None:
    _validate_composite_foreign_keys(model)


def _validate_auth_config_v(model: dict[str, Any], config: dict[str, Any]) -> None:
    _validate_auth_config(model, config)


def _validate_auth_strategy_v(
    models: list[dict[str, Any]], config: dict[str, Any]
) -> None:
    _validate_auth_strategy(models, config)


def _validate_auth_scope_coverage_v(
    models: list[dict[str, Any]], config: dict[str, Any]
) -> None:
    _validate_auth_scope_coverage(models, config)


def _compute_auth_extra_v(config: dict[str, Any]) -> list[str]:
    return _compute_auth_extra(config)


PYTHON_FASTAPI_STACK = StackSpec(
    name="python-fastapi",
    infrastructure_targets=[
        "base",
        "engine",
        "main",
        "test-conftest-root",
    ],
    domain_targets=[
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
    ],
    generators=_PYTHON_FASTAPI_GENERATORS,
    infra_orchestrator=_infra_orchestrator,
    quality_runner=run_ruff_quality,
    cleanup_spec=_PYTHON_FASTAPI_CLEANUP,
    # Normalized to the (model, config) ModelValidator signature. Several
    # underlying validators read only one of the two; the wrappers adapt them
    # without changing their behavior or call order.
    validators=[
        _validate_auth_config_v,
        _validate_generation_config_v,
        _validate_paths_base_v,
        _validate_composite_foreign_keys_v,
    ],
    infra_validators=[
        _validate_auth_strategy_v,
        _validate_auth_scope_coverage_v,
    ],
    extra_deps_fn=_compute_auth_extra_v,
)

register_stack(PYTHON_FASTAPI_STACK)


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
        default="all",
        help=(
            "Generation target (default: all). Valid targets depend on the "
            "resolved --stack; validated after the stack is known."
        ),
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
        default=None,
        help=(
            "Stack configuration to use (default: from .model-generator.yaml "
            "or python-fastapi)"
        ),
    )

    args = parser.parse_args()

    # Handle --interactive: launch wizard and exit
    if args.interactive:
        from .wizard import run_wizard

        run_wizard()
        return

    # Resolve stack: explicit --stack > .model-generator.yaml `stack:` > default.
    # load_config() already reads the project yaml to pick the right stack
    # config.yaml; extract the resolved name from the merged config so the rest
    # of main() (get_stack, get_template_env, generate()) uses the right spec.
    # Note: in the stack's own config.yaml, `stack:` is a metadata dict
    # ({name, description, version}); only a plain string from the project
    # .model-generator.yaml represents an actual stack name override.
    if args.stack is None:
        _probe_config = load_config("python-fastapi")
        _stack_val = _probe_config.get("stack")
        args.stack = _stack_val if isinstance(_stack_val, str) else "python-fastapi"

    # Resolve the stack registry entry. Done here (not in argparse) so --target
    # is validated against the stack's registered targets, not a static
    # python-only list.
    spec = get_stack(args.stack)

    # Handle --clear-only: just cleanup and exit (doesn't require model argument)
    if args.clear_only:
        project_root = Path.cwd()
        if not (project_root / ".model-generator.yaml").exists():
            parent = project_root.parent
            if (parent / ".model-generator.yaml").exists():
                project_root = parent
        _validate_project_root(project_root)
        cleanup_generated(
            project_root,
            scope=args.scope,
            dry_run=args.dry_run,
            cleanup_spec=spec.cleanup_spec,
        )
        return

    # Validate --target against the resolved stack's registered targets.
    if args.target not in spec.all_targets:
        valid = ", ".join(spec.all_targets)
        print(
            f'Error: unknown --target "{args.target}" for stack '
            f'"{spec.name}".\nValid targets: {valid}.'
        )
        sys.exit(1)

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
        cleanup_generated(
            project_root,
            scope=args.scope,
            dry_run=args.dry_run,
            cleanup_spec=spec.cleanup_spec,
        )
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
    ) = _prepare_infra_modules(model_files, config, spec)

    has_encrypted_binary = _has_encrypted_binary_field(loaded_models)

    # Generate infrastructure
    if (
        args.target in ("all", "infrastructure")
        or args.target in spec.infrastructure_targets
    ):
        infra_files = spec.infra_orchestrator(
            config=config,
            env=env,
            project_root=project_root,
            domains=domains,
            route_modules=route_modules,
            factory_modules=factory_modules,
            extra_deps=extra_deps,
            diff=args.diff,
            dry_run=args.dry_run,
            has_encrypted_binary=has_encrypted_binary,
            no_root_files=args.no_root_files,
        )
        if infra_files and not args.dry_run and not args.diff:
            run_quality_tools(config, project_root, infra_files, spec.quality_runner)

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
