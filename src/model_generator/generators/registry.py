"""
Stack registry — descriptors that let ``generate.py`` drive any stack generically.

A :class:`StackSpec` bundles everything the orchestrator needs to generate a
stack: its target lists, its generator dispatch table, the infrastructure
orchestrator, the quality runner, the ``--clean`` cleanup spec, and the
validators that must pass before generation. ``generate.py`` resolves
``STACKS[stack_name]`` and reads these fields instead of hardcoding the
python-fastapi generator set.

Phase 0 ships exactly one registered stack — ``python-fastapi`` — wrapping the
existing generators with **no behavior change**. Later phases (e.g. Flutter)
register additional ``StackSpec`` instances into :data:`STACKS` without touching
shared orchestration code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jinja2 import Environment

from ..utils.quality import QualityRunner

# A per-model validator: ``(model, config) -> None``. Raises ``SystemExit`` on a
# fatal misconfiguration (the existing validators already do this).
ModelValidator = Callable[[dict[str, Any], dict[str, Any]], None]

# A cross-model infrastructure validator run once over all loaded models:
# ``(loaded_models, config) -> None``.
InfraValidator = Callable[[list[dict[str, Any]], dict[str, Any]], None]

# Computes stack-specific extra runtime dependencies from config (e.g. the auth
# scaffolding's bcrypt/itsdangerous deps). ``(config) -> list[str]``.
ExtraDepsFn = Callable[[dict[str, Any]], list[str]]


@dataclass(frozen=True)
class GenContext:
    """Everything a single-target generator may need.

    A uniform context keeps the ``StackSpec.generators`` dispatch table simple:
    every entry has the same signature, ``(GenContext) -> dict | list | None``,
    regardless of which inputs an individual generator actually reads.
    """

    model: dict[str, Any]
    config: dict[str, Any]
    env: Environment
    project_root: Path
    model_path: Path
    enums: dict[str, Any]
    constraints: dict[str, Any]
    no_root_files: bool = False
    dry_run: bool = False


# A single-target generator: consumes a context, returns output dict(s) or None.
TargetGenerator = Callable[[GenContext], "dict[str, Any] | list[dict[str, Any]] | None"]


@dataclass(frozen=True)
class CleanupSpec:
    """Declarative inputs to the ``--clean`` path computation for a stack.

    The cleanup logic in ``generate.py`` reads these instead of hardcoding the
    python source/test layout, so a non-Python stack can declare its own set of
    generated path keys and glob patterns.

    Attributes:
        source_path_keys: ``config["paths"]`` keys whose directories hold
            generated source files (used for both full and selective cleanup).
        test_path_key: ``config["paths"]`` key for the generated test root.
        migrations_path_key: ``config["paths"]`` key for migrations (None when
            the stack has no migration concept).
        file_glob: glob suffix appended to each source/test directory in
            selective cleanup (e.g. ``"*.py"`` or ``"*.dart"``).
        derived_files: callable returning extra explicit files to delete given
            ``(project_root, paths)`` — e.g. python's ``utils.py``/``types.py``
            siblings and ``alembic.ini``.
        full_cleanup_dirs: extra top-level directory names removed in full
            cleanup (caches, build output).
        full_cleanup_files: extra top-level file names removed in full cleanup.
        path_resolver: callable mapping the loaded ``config`` to a concrete
            ``paths`` dict, applied before cleanup runs. Lets a stack expand
            placeholders in its path templates (e.g. flutter's ``{pkg}``) so the
            cleanup globs and ``derived_files`` see real directories. Defaults to
            ``config["paths"]`` verbatim when ``None`` (python-fastapi).
    """

    source_path_keys: tuple[str, ...]
    test_path_key: str
    migrations_path_key: str | None
    file_glob: str
    derived_files: Callable[[Path, dict[str, Any]], list[Path]] | None = None
    full_cleanup_dirs: tuple[str, ...] = ()
    full_cleanup_files: tuple[str, ...] = ()
    path_resolver: Callable[[dict[str, Any]], dict[str, Any]] | None = None


@dataclass(frozen=True)
class StackSpec:
    """Descriptor for a code-generation stack.

    ``generate.py`` resolves ``STACKS[stack_name]`` and drives generation from
    these fields, removing stack-specific assumptions from shared code.

    Attributes:
        name: stack identifier (matches the ``stacks/<name>/`` directory).
        infrastructure_targets: skip-if-exists infra targets (TDD order).
        domain_targets: per-model overwrite targets (TDD order).
        generators: target name -> single-target generator (``GenContext`` ->
            output). Covers domain targets; infra targets are emitted by
            ``infra_orchestrator``.
        infra_orchestrator: replaces the hardcoded ``generate_infrastructure``;
            ``(**kwargs) -> list[Path]`` of emitted infra files.
        quality_runner: the stack's quality runner (ruff / dart / ...).
        cleanup_spec: declarative inputs for ``--clean``.
        validators: per-model validators run before generation (python:
            auth/base/layout/composite-FK; other stacks: empty).
        infra_validators: cross-model validators run once over all loaded
            models during infra preparation (python: auth strategy/scope).
        extra_deps_fn: computes stack-specific extra runtime deps from config
            (python: auth scaffolding deps); ``None`` when the stack has none.
    """

    name: str
    infrastructure_targets: list[str]
    domain_targets: list[str]
    generators: dict[str, TargetGenerator]
    infra_orchestrator: Callable[..., list[Path]]
    quality_runner: QualityRunner
    cleanup_spec: CleanupSpec
    validators: list[ModelValidator] = field(default_factory=list)
    infra_validators: list[InfraValidator] = field(default_factory=list)
    extra_deps_fn: ExtraDepsFn | None = None

    @property
    def all_targets(self) -> list[str]:
        """Every selectable ``--target`` value for this stack.

        Mirrors the old module-level ``TARGETS`` constant: infrastructure +
        domain targets, plus the ``infrastructure`` and ``all`` aggregates.
        """
        return [
            *self.infrastructure_targets,
            *self.domain_targets,
            "infrastructure",
            "all",
        ]

    @property
    def generation_targets(self) -> list[str]:
        """Targets generated when ``--target all`` is selected (no aggregates)."""
        return [*self.infrastructure_targets, *self.domain_targets]


# Populated by stack modules at import time (see ``_register_python_fastapi``).
STACKS: dict[str, StackSpec] = {}


def register_stack(spec: StackSpec) -> None:
    """Register a stack descriptor under its name."""
    STACKS[spec.name] = spec


def get_stack(name: str) -> StackSpec:
    """Resolve a registered stack by name, or raise a clear error."""
    try:
        return STACKS[name]
    except KeyError:
        known = ", ".join(sorted(STACKS)) or "(none registered)"
        raise SystemExit(
            f'Error: unknown stack "{name}". Registered stacks: {known}.'
        ) from None
