"""
Action: Generate code from model specifications.
"""

from __future__ import annotations

from pathlib import Path

from ..prompts import checkbox, confirm, select

INFRASTRUCTURE_TARGETS = {"all", "infrastructure"}


def _find_project_root() -> Path:
    """Find project root by looking for .model-generator.yaml."""
    cwd = Path.cwd()
    if (cwd / ".model-generator.yaml").exists():
        return cwd
    parent = cwd.parent
    if (parent / ".model-generator.yaml").exists():
        return parent
    return cwd


def _find_models_dir(project_root: Path) -> Path | None:
    """Find the models directory."""
    models_dir = project_root / "models"
    if models_dir.exists():
        return models_dir
    return None


def run_generate() -> None:
    """Select domains and targets, then run generation."""
    project_root = _find_project_root()

    if not (project_root / ".model-generator.yaml").exists():
        print("\nNo .model-generator.yaml found.")
        print("Run 'Setup/update project settings' first.")
        return

    models_dir = _find_models_dir(project_root)
    if models_dir is None:
        print(f"\nNo models/ directory found in {project_root}")
        return

    # Scan for model files
    model_files = sorted(models_dir.glob("*.model.json"))
    if not model_files:
        print(f"\nNo *.model.json files found in {models_dir}")
        return

    domain_names = [f.stem.replace(".model", "") for f in model_files]
    print(f"\nFound {len(model_files)} domain(s): {', '.join(domain_names)}")

    # Select domains
    if len(model_files) > 1:
        selected = checkbox(
            "Select domains to generate:",
            choices=["all", *domain_names],
        )
        if "all" in selected:
            selected_files = model_files
        else:
            selected_files = [
                f for f in model_files if f.stem.replace(".model", "") in selected
            ]
    else:
        selected_files = model_files

    if not selected_files:
        print("No domains selected.")
        return

    # Select target
    targets = [
        "all",
        "infrastructure",
        "database",
        "factories",
        "api-models",
        "api-routes",
        "api-tests",
        "enums",
        "constraints",
        "migration-init",
    ]
    target = select("Generation target:", choices=targets, default="all")

    # Root project files (pyproject.toml / alembic.ini / .gitignore) only matter
    # when infrastructure is emitted. Mirror the CLI's --no-root-files so the
    # scratch-and-migrate-into-an-existing-tree workflow has parity here.
    no_root_files = False
    if target in INFRASTRUCTURE_TARGETS:
        no_root_files = not confirm(
            "Generate root project files (pyproject.toml, alembic.ini, .gitignore)?",
            default=True,
        )

    # Confirm
    file_names = [f.name for f in selected_files]
    print(f"\nWill generate '{target}' for: {', '.join(file_names)}")
    if not confirm("Proceed?"):
        return

    # Generate infrastructure if needed (same logic as main())
    if target in INFRASTRUCTURE_TARGETS:
        from ...generate import _has_encrypted_binary_field, _prepare_infra_modules
        from ...generators.infrastructure import generate_infrastructure
        from ...utils import (
            get_template_env,
            load_config,
            run_quality_tools,
        )

        stack = "python-fastapi"
        config = load_config(stack)
        env = get_template_env(stack, config)

        (
            domains,
            route_modules,
            factory_modules,
            extra_deps,
            loaded_models,
        ) = _prepare_infra_modules(selected_files, config)

        infra_files = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=domains,
            route_modules=route_modules,
            factory_modules=factory_modules,
            project_config=config,
            has_encrypted_binary=_has_encrypted_binary_field(loaded_models),
            extra_deps=extra_deps,
            no_root_files=no_root_files,
        )
        if infra_files:
            run_quality_tools(config, project_root, infra_files)

    if target == "infrastructure":
        print("\nInfrastructure generation complete.")
        return

    # Generate per domain using the existing generate() function
    from ...generate import generate

    for model_file in selected_files:
        generate(model_path=model_file, target=target, no_root_files=no_root_files)

    print("\nGeneration complete.")
