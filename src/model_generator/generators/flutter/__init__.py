"""Flutter (Dart) stack — generators + :class:`StackSpec` registration.

Importing this package registers the ``flutter`` stack into the shared
``STACKS`` registry, so ``generate.py`` can drive it with ``--stack flutter``.
Phase 1 ships freezed models, the enums file, a models barrel, and the project
scaffold (converters, pubspec, analysis_options, build.yaml, README, .gitignore).

Phase 2 will import the domain generators here (and ``resolve_fields`` /
``package_uri`` helpers) to add the retrofit API client and request DTOs, and
register its sibling generators onto :data:`FLUTTER_STACK`.
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
    "generate_converters",
    "generate_flutter_enums",
    "generate_flutter_models",
    "generate_flutter_models_index",
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
}


def _flutter_derived_cleanup_files(
    project_root: Path, paths: dict[str, Any]
) -> list[Path]:
    """Extra explicit files the Flutter ``--clean`` removes.

    The core converters file is named explicitly so selective cleanup is
    complete (the enums file already lives under the ``models`` source dir swept
    by the ``*.dart`` glob). The ``{pkg}`` placeholder is resolved the same way
    as during generation.
    """
    files: list[Path] = []
    core = resolve_path({"paths": paths}, "api_core")
    if core:
        files.append(project_root / core / "converters.dart")
    return files


_FLUTTER_CLEANUP = CleanupSpec(
    source_path_keys=("models", "api_client", "repositories", "api_core"),
    test_path_key="models",
    migrations_path_key=None,
    file_glob="*.dart",
    derived_files=_flutter_derived_cleanup_files,
    full_cleanup_dirs=(".dart_tool", "build"),
    full_cleanup_files=(),
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
        "readme",
        "gitignore",
    ],
    domain_targets=[
        "enums",
        "models",
        "models-index",
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
