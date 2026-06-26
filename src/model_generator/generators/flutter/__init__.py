"""Flutter (Dart) stack — generators + :class:`StackSpec` registration.

Importing this package registers the ``flutter`` stack into the shared
``STACKS`` registry, so ``generate.py`` can drive it with ``--stack flutter``.
Phase 1 ships freezed models, the enums file, a models barrel, and the project
scaffold (converters, pubspec, analysis_options, build.yaml, README, .gitignore).

Phase 2 adds the retrofit API client, request DTOs, repository wrappers and the
API barrel (domain), plus the ``Paginated<T>`` envelope, dio setup and the
conditional auth interceptor (infrastructure). Its generators live in
:mod:`.api` and are registered onto :data:`FLUTTER_STACK` below.

Phase 4 (``local_cache: true`` in ``.model-generator.yaml``) adds a
Drift/SQLite offline cache layer: Drift ``Table`` classes (``local-tables``),
the ``AppDatabase`` aggregator (``local-database``), and cache-first repository
subclasses (``cached-repositories``). Its generators live in :mod:`.cache`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...utils.quality import run_config_quality
from ..registry import (
    CleanupSpec,
    GenContext,
    StackSpec,
    TargetGenerator,
    register_stack,
)
from .api import (
    generate_auth_interceptor,
    generate_dio_setup,
    generate_flutter_api_client,
    generate_flutter_api_index,
    generate_flutter_pagination,
    generate_flutter_repositories,
    generate_flutter_request_dtos,
)
from .cache import (
    generate_cached_repositories,
    generate_drift_database,
    generate_drift_tables,
)
from .generators import (
    flutter_infra_orchestrator,
    generate_converters,
    generate_flutter_enums,
    generate_flutter_models,
    generate_flutter_models_index,
    generate_pubspec,
)
from .paths import package_name, resolve_path

__all__ = [
    "FLUTTER_STACK",
    "flutter_infra_orchestrator",
    "generate_auth_interceptor",
    "generate_cached_repositories",
    "generate_converters",
    "generate_dio_setup",
    "generate_drift_database",
    "generate_drift_tables",
    "generate_flutter_api_client",
    "generate_flutter_api_index",
    "generate_flutter_enums",
    "generate_flutter_models",
    "generate_flutter_models_index",
    "generate_flutter_pagination",
    "generate_flutter_repositories",
    "generate_flutter_request_dtos",
    "generate_pubspec",
    "package_name",
    "resolve_path",
]


# Domain-target generators wrapped into the uniform GenContext signature, each
# threading only the inputs the underlying generator reads.
_FLUTTER_GENERATORS: dict[str, TargetGenerator] = {
    "models": lambda c: generate_flutter_models(
        c.model, c.config, c.env, c.project_root
    ),
    "enums": lambda c: generate_flutter_enums(
        c.model, c.config, c.env, c.project_root, c.model_path
    ),
    "models-index": lambda c: generate_flutter_models_index(
        c.model, c.config, c.env, c.project_root
    ),
    # Phase 2 — request DTOs land in the models dir, so they generate before the
    # api client / repositories that import them (TDD/domain order below).
    "requests": lambda c: generate_flutter_request_dtos(
        c.model, c.config, c.env, c.project_root
    ),
    "api-client": lambda c: generate_flutter_api_client(
        c.model, c.config, c.env, c.project_root
    ),
    "api-index": lambda c: generate_flutter_api_index(
        c.model, c.config, c.env, c.project_root
    ),
    "repositories": lambda c: generate_flutter_repositories(
        c.model, c.config, c.env, c.project_root
    ),
    # Phase 4 — offline cache (local_cache: true required; no-ops otherwise).
    # Table files before the database (database scans the local dir for tables).
    "local-tables": lambda c: generate_drift_tables(
        c.model, c.config, c.env, c.project_root
    ),
    "local-database": lambda c: generate_drift_database(
        c.model, c.config, c.env, c.project_root
    ),
    "cached-repositories": lambda c: generate_cached_repositories(
        c.model, c.config, c.env, c.project_root
    ),
}


def _flutter_resolve_cleanup_paths(config: dict[str, Any]) -> dict[str, Any]:
    """Expand every ``{pkg}`` placeholder in the flutter ``paths`` for cleanup.

    Cleanup runs against the on-disk tree, so the path templates
    (``lib/{pkg}/models``) must be resolved to the configured package name
    (honoring a custom ``flutter.package_name``) before the globs are built.
    """
    keys = (config.get("paths") or {}).keys()
    return {key: resolve_path(config, key) for key in keys}


def _flutter_derived_cleanup_files(
    project_root: Path, paths: dict[str, Any]
) -> list[Path]:
    """Extra explicit files the Flutter ``--clean`` removes.

    The core converters file is named explicitly so selective cleanup is
    complete (the enums file already lives under the ``models`` source dir swept
    by the ``*.dart`` glob). ``paths`` is already ``{pkg}``-resolved by
    :func:`_flutter_resolve_cleanup_paths`.
    """
    files: list[Path] = []
    core = paths.get("api_core")
    if core:
        files.append(project_root / core / "converters.dart")
    return files


_FLUTTER_CLEANUP = CleanupSpec(
    source_path_keys=("models", "api_client", "repositories", "api_core", "local"),
    test_path_key="models",
    migrations_path_key=None,
    file_glob="*.dart",
    derived_files=_flutter_derived_cleanup_files,
    full_cleanup_dirs=(".dart_tool", "build"),
    full_cleanup_files=(),
    path_resolver=_flutter_resolve_cleanup_paths,
)


FLUTTER_STACK = StackSpec(
    name="flutter",
    # Infrastructure targets are emitted by flutter_infra_orchestrator; they are
    # labels for --target selection, not domain-dispatch entries.
    infrastructure_targets=[
        "pubspec",
        "analysis-options",
        "build-yaml",
        "converters",
        "pagination",
        "dio-setup",
        "auth-interceptor",
        "readme",
        "gitignore",
    ],
    domain_targets=[
        "enums",
        "models",
        "models-index",
        # Phase 2: DTOs first (api client + repositories import them), then the
        # client, its barrel, and the repository wrappers.
        "requests",
        "api-client",
        "api-index",
        "repositories",
        # Phase 4: table files before the database (database scans the local
        # dir for existing tables); cached repos last (depend on both).
        "local-tables",
        "local-database",
        "cached-repositories",
    ],
    generators=_FLUTTER_GENERATORS,
    infra_orchestrator=flutter_infra_orchestrator,
    quality_runner=run_config_quality,
    cleanup_spec=_FLUTTER_CLEANUP,
    # No project-agnostic validators for Flutter in Phase 1 (the python-only
    # auth/base/composite-FK checks don't apply to a generated client).
    validators=[],
    infra_validators=[],
    extra_deps_fn=None,
)


register_stack(FLUTTER_STACK)


# Re-export GenContext for symmetry with the python stack's import surface.
_ = GenContext
