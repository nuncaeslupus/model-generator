"""Flutter (Dart) code generators — Phase 1.

Emits freezed models, the enums file, a models barrel, and the project scaffold
(converters, pubspec, analysis_options, build.yaml, README, .gitignore) from a
``*.model.json`` spec. Each function returns the uniform ``{"path", "content",
"mode"}`` output dict(s) the orchestrator writes, matching the python-fastapi
generator contract.

Domain generators receive a :class:`~model_generator.generators.registry.GenContext`
via thin wrappers registered in the stack's ``StackSpec``. Infrastructure
generators are driven by :func:`flutter_infra_orchestrator`, which mirrors the
python ``generate_infrastructure`` signature so ``generate.main`` can call it
unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment

from ...utils.loaders import load_shared_enums
from ...utils.templates import snake_case
from .fields import collect_model_imports, resolve_fields
from .paths import package_name, package_uri, resolve_path


def _entity_filename(entity_name: str) -> str:
    """Dart file stem for an entity (snake_case; ``UserProfile`` → ``user_profile``)."""
    return snake_case(entity_name)


# ---------------------------------------------------------------------------
# Domain generators
# ---------------------------------------------------------------------------


def generate_flutter_models(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate one ``@freezed`` Dart model file per entity.

    Each file lands at ``lib/<pkg>/models/<entity>.dart`` and declares a freezed
    data class with the entity's fields mapped to Dart types, JsonKey-renamed to
    the snake_case wire form, and annotated with the appropriate JsonConverters.
    """
    template = env.get_template("models/model.dart.j2")
    models_dir = project_root / resolve_path(config, "models")
    pkg = package_name(config)

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None:
            continue
        descriptors = resolve_fields(entity, config)
        imports = collect_model_imports(entity, config)
        file_stem = _entity_filename(entity_name)
        converters_uri = package_uri(
            config, f"{resolve_path(config, 'api_core')}/converters.dart"
        )
        enums_uri = package_uri(config, resolve_path(config, "enums"))

        content = template.render(
            entity_name=entity_name,
            file_stem=file_stem,
            fields=descriptors,
            dart_imports=imports["dart_imports"],
            needs_converters=imports["has_converter"],
            needs_enums=imports["has_enum"],
            converters_uri=converters_uri,
            enums_uri=enums_uri,
            package_name=pkg,
            description=entity.get("description"),
        )
        outputs.append({"path": models_dir / f"{file_stem}.dart", "content": content})

    return outputs


def generate_flutter_enums(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    model_path: Path,
) -> dict[str, Any] | None:
    """Generate ``lib/<pkg>/models/enums.dart`` from ``_shared/enums.json``.

    Emits one Dart ``enum`` per shared enum with UPPER_CASE members, each carrying
    a ``@JsonValue('UPPER_CASE')`` so (de)serialization is byte-compatible with
    the FastAPI wire format. Overwrites the file (single source of truth).
    """
    enum_defs = load_shared_enums(model_path)
    if not enum_defs:
        print("  ℹ️  No enums found in models/_shared/enums.json")
        return None

    template = env.get_template("models/enums.dart.j2")
    enums_path = project_root / resolve_path(config, "enums")
    content = template.render(enums=enum_defs)

    return {"path": enums_path, "content": content, "mode": "write"}


def generate_flutter_models_index(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the ``models_index.dart`` barrel exporting every model + enums.

    Scans the models directory for generated ``*.dart`` files (plus this run's
    entities, in case the directory does not exist yet) so the barrel stays
    complete across multi-file specs.
    """
    template = env.get_template("models/index.dart.j2")
    models_dir = project_root / resolve_path(config, "models")
    enums_path = Path(resolve_path(config, "enums"))

    exports: set[str] = set()
    if models_dir.is_dir():
        for dart_file in models_dir.glob("*.dart"):
            if dart_file.name in {"models_index.dart", enums_path.name}:
                continue
            exports.add(dart_file.name)

    for entity_name in model.get("entities") or {}:
        exports.add(f"{_entity_filename(entity_name)}.dart")

    content = template.render(
        exports=sorted(exports),
        enums_file=enums_path.name,
    )
    return {
        "path": models_dir / "models_index.dart",
        "content": content,
        "mode": "write",
    }


# ---------------------------------------------------------------------------
# Infrastructure generators
# ---------------------------------------------------------------------------


def generate_converters(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any]:
    """Generate ``lib/<pkg>/core/converters.dart`` (overwrite).

    Provides the ``DecimalConverter`` / ``BytesConverter`` / ``UtcDateTimeConverter``
    JsonConverters the freezed models reference, encoding money as a JSON string,
    binary as base64, and datetimes as ISO8601 + ``Z`` — matching the FastAPI
    wire format exactly.
    """
    template = env.get_template("infrastructure/converters.dart.j2")
    core_dir = project_root / resolve_path(config, "api_core")
    content = template.render()
    return {"path": core_dir / "converters.dart", "content": content}


def generate_pubspec(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    project_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate ``pubspec.yaml`` (skip-if-exists — the pyproject analogue).

    Bootstrap-only: emitted once, then maintained by hand (matching the Python
    stack's ``pyproject.toml`` behavior). Runtime/dev dependency lists come from
    the stack ``dependencies`` config; the conditional ``auth`` block is included
    only when the project enables an auth strategy.

    The spec's own ``dependencies`` array is deliberately ignored here: those are
    backend (pip) requirements and have no place in a Dart pubspec.
    """
    pubspec_path = project_root / "pubspec.yaml"
    if pubspec_path.exists():
        return None

    template = env.get_template("infrastructure/pubspec.yaml.j2")
    deps = config.get("dependencies", {}) or {}
    runtime = list(deps.get("runtime", []) or [])
    dev = list(deps.get("dev", []) or [])

    auth = (project_config.get("auth") or {}) if project_config else {}
    if auth.get("strategy"):
        conditional = (deps.get("conditional") or {}).get("auth", []) or []
        runtime.extend(c for c in conditional if c not in runtime)

    project = (project_config or {}).get("project", {}) if project_config else {}
    content = template.render(
        package_name=package_name(config),
        project_name=project.get("name"),
        project_description=project.get("description"),
        runtime_deps=runtime,
        dev_deps=dev,
    )
    return {"path": pubspec_path, "content": content}


def generate_analysis_options(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any]:
    """Generate ``analysis_options.yaml`` (overwrite).

    Pulls in ``flutter_lints`` and suppresses ``constant_identifier_names`` so the
    UPPER_CASE enum members generated from the spec don't trip the analyzer.
    """
    template = env.get_template("infrastructure/analysis_options.yaml.j2")
    content = template.render()
    return {"path": project_root / "analysis_options.yaml", "content": content}


def generate_build_yaml(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any]:
    """Generate ``build.yaml`` (overwrite) configuring the build_runner codegen."""
    template = env.get_template("infrastructure/build.yaml.j2")
    content = template.render()
    return {"path": project_root / "build.yaml", "content": content}


def generate_flutter_readme(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    project_config: dict[str, Any],
) -> dict[str, Any] | None:
    """Generate ``README.md`` (skip-if-exists).

    Documents the required post-generation step — ``dart run build_runner build``
    — which produces the ``*.freezed.dart`` / ``*.g.dart`` companion files the
    hand-authored annotated source depends on.
    """
    readme_path = project_root / "README.md"
    if readme_path.exists():
        return None

    template = env.get_template("infrastructure/README.md.j2")
    project = (project_config or {}).get("project", {}) if project_config else {}
    content = template.render(
        package_name=package_name(config),
        project_name=project.get("name"),
        project_description=project.get("description"),
        models_dir=resolve_path(config, "models"),
    )
    return {"path": readme_path, "content": content}


def generate_flutter_gitignore(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    no_root_files: bool = False,
) -> dict[str, Any] | None:
    """Generate ``.gitignore`` (skip-if-exists) ignoring Dart build artifacts."""
    if no_root_files:
        return None
    gitignore_path = project_root / ".gitignore"
    if gitignore_path.exists():
        return None
    template = env.get_template("infrastructure/gitignore.j2")
    content = template.render()
    return {"path": gitignore_path, "content": content}


def flutter_infra_orchestrator(
    *,
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    project_config: dict[str, Any],
    diff: bool = False,
    dry_run: bool = False,
    no_root_files: bool = False,
    **_ignored: Any,
) -> list[Path]:
    """Emit the Flutter infrastructure files; return the written paths.

    Signature-compatible with the python ``generate_infrastructure`` orchestrator
    so ``generate.main`` calls it with the same kwargs. Python-specific kwargs
    (``domains``, ``route_modules``, ``factory_modules``, ``has_encrypted_binary``,
    ``extra_deps`` — pip requirements that have no place in a Dart pubspec) are
    accepted and ignored via ``**_ignored``.
    """
    print("\n🏗️  Generating Flutter infrastructure files...")

    candidates = [
        generate_pubspec(config, env, project_root, project_config),
        generate_analysis_options(config, env, project_root),
        generate_build_yaml(config, env, project_root),
        generate_converters(config, env, project_root),
        generate_flutter_readme(config, env, project_root, project_config),
        generate_flutter_gitignore(
            config, env, project_root, no_root_files=no_root_files
        ),
    ]
    outputs = [c for c in candidates if c]

    generated_files: list[Path] = []
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
        with path.open("w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✅ Generated: {path}")
        generated_files.append(path)

    return generated_files
