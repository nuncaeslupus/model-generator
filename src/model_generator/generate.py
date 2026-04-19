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
    get_template_env,
    load_config,
    load_model,
    load_shared_constraints,
    load_shared_enums,
    run_quality_tools,
)
from .utils.conftest_generator import generate_conftest_content

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
GENERATORS = {
    "enums": lambda m, c, e, p, mp: generate_enums(m, c, e, p, mp),
    "constraints": lambda m, c, e, p, mp: generate_constraints(m, c, e, p, mp),
    "init": lambda m, c, e, p, mp: generate_init(m, c, e, p),
    "database": lambda m, c, e, p, mp: generate_database_model(m, c, e, p),
    "factories": lambda m, c, e, p, mp: generate_factories(m, c, e, p),
    "api-models": lambda m, c, e, p, mp: generate_api_models(m, c, e, p),
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


def _cleanup_full(project_root: Path, paths: dict, dry_run: bool) -> None:
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


def _cleanup_selective(project_root: Path, paths: dict, dry_run: bool) -> None:
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
    for key, path in paths.items():
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

    # Find __pycache__ in generated directories
    search_dirs = set()
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
                search_dirs.add(path)
                if key != "migrations": # search parent for src/api, src/database
                    search_dirs.add(path.parent)

    for d in search_dirs:
        if d.is_dir():
            for pycache in d.rglob("__pycache__"):
                dirs_to_delete.append(pycache)

    print("🗑️  Selective cleanup mode:")
    deleted_count = 0
    # Use set to avoid duplicates, but filter for existence
    for file_path in sorted(set(f for f in files_to_delete if f.exists())):
        print(f"  {'Would delete' if dry_run else 'Deleting'}: {file_path}")
        if not dry_run:
            if file_path.is_file():
                file_path.unlink()
                deleted_count += 1

    for dir_path in sorted(set(dirs_to_delete)):
        if dir_path.exists() and dir_path.is_dir():
            print(f"  {'Would delete' if dry_run else 'Deleting'}: {dir_path}")
            if not dry_run:
                import shutil
                shutil.rmtree(dir_path)

    if not dry_run:
        print(f"✅ Cleanup complete ({deleted_count} files)")


def generate_conftest(
    model: dict, config: dict, env: Any, project_root: Path, model_path: Path
) -> dict | None:
    """Generate conftest.py with fixtures for all domains."""
    if model_path.is_file():
        models_dir = model_path.parent
    else:
        models_dir = model_path

    content, count = generate_conftest_content(models_dir)
    output_dir = project_root / config["paths"]["api_tests"]
    output_file = output_dir / "conftest.py"

    return {"path": output_file, "content": content, "mode": "write"}


def generate(
    model_path: Path,
    target: str = "all",
    diff: bool = False,
    dry_run: bool = False,
    stack: str = "python-fastapi",
) -> None:
    """Generate code from model definition."""
    project_root = _find_project_root(model_path)
    _validate_project_root(project_root)

    model = load_model(model_path)
    config = load_config(stack)
    env = get_template_env(stack)

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
            t, model, config, env, project_root, model_path, enums, constraints
        )
        if result is None:
            continue
        if isinstance(result, list):
            outputs.extend(result)
        elif isinstance(result, dict) and "instructions" in result:
            print(result["instructions"])
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


def _generate_target(
    target: str,
    model: dict,
    config: dict,
    env: Any,
    project_root: Path,
    model_path: Path,
    enums: dict,
    constraints: dict,
) -> dict | list | None:
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
        return generate_migration_init(model, config, env, project_root)
    elif target == "migration-autogen":
        return generate_migration_autogen(model, config, env, project_root)

    return None


def _process_outputs(outputs: list[dict], diff: bool, dry_run: bool) -> list[Path]:
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
            with open(path, "a") as f:
                f.write(content)
            new_count = output.get("new_count", 0)
            skipped = output.get("skipped", 0)
            print(f"  ✅ Appended {new_count} item(s) to: {path}")
            if skipped > 0:
                print(f"     (skipped {skipped} already existing)")
        else:
            with open(path, "w") as f:
                f.write(content)
            print(f"  ✅ Generated: {path}")

        generated_files.append(path)

    return generated_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate code from model definitions")
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
    env = get_template_env(args.stack)

    # Extract domains from all model files (only those with api-enabled entities)
    domains = []
    extra_deps: list[str] = []
    for model_file in model_files:
        model = load_model(model_file)
        domain = model.get("domain", "unknown")
        has_api = any(
            e.get("api", {}).get("enabled", True)
            for e in model.get("entities", {}).values()
        )
        if domain not in domains and has_api:
            domains.append(domain)
        extra_deps.extend(model.get("dependencies", []))
    extra_deps = sorted(set(extra_deps))

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
            project_config=config,
            extra_deps=extra_deps,
            diff=args.diff,
            dry_run=args.dry_run,
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
        )


if __name__ == "__main__":
    main()
