"""
Code quality tools runner.

The runner is stack-aware: each stack registers a ``quality_runner`` callable in
its :class:`~model_generator.generators.registry.StackSpec`. ``run_quality_tools``
dispatches to that callable, defaulting to the python-fastapi ruff runner when no
runner is supplied (preserving the historical behavior for direct callers that
pass an empty config).

Two distinct runners ship:

* :func:`run_ruff_quality` — the original ruff ``format`` + ``check --fix`` flow.
* :func:`run_config_quality` — a generic, ``config["quality"]``-driven runner that
  can target either the per-file path list (formatters like ``ruff format`` /
  ``dart format``) or the package root (analyzers like ``dart analyze`` that need
  ``pubspec.yaml`` / ``analysis_options.yaml`` context). It no-ops with a warning
  when the underlying tool/SDK is absent, so generation always succeeds.
"""

import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

# Type of a stack's quality runner: (config, project_root, files) -> None.
QualityRunner = Callable[[dict[str, Any], Path, list[Path]], None]

# Cap files per tool invocation so a large project can't exceed the OS
# command-line length limit (Windows ~8 KiB).
_MAX_FILES_PER_CALL = 100


def _chunked(items: list[str], size: int) -> Iterator[list[str]]:
    """Yield successive ``size``-length slices of ``items``."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _find_ruff(project_root: Path) -> str:
    """Find ruff binary, preferring the project's venv."""
    for venv_dir in [".venv", "venv"]:
        ruff_path = project_root / venv_dir / "bin" / "ruff"
        if ruff_path.exists():
            return str(ruff_path)
    return "ruff"


def _find_dart(project_root: Path) -> str:
    """Find the dart executable, preferring a project-local Dart/Flutter SDK.

    Mirrors :func:`_find_ruff`: looks for a vendored SDK under the project before
    falling back to a ``dart`` on PATH. Common local-SDK layouts are checked so a
    project that pins its own Dart toolchain is honored. On Windows the SDK
    executable may carry an ``.exe`` / ``.bat`` / ``.cmd`` extension, so those are
    probed too.
    """
    extensions = [".exe", ".bat", ".cmd", ""] if sys.platform == "win32" else [""]
    base_candidates = [
        project_root / ".dart_tool" / "bin" / "dart",
        project_root / "flutter" / "bin" / "dart",
        project_root / "bin" / "dart",
    ]
    for base in base_candidates:
        for ext in extensions:
            dart_path = base.with_suffix(ext) if ext else base
            if dart_path.exists():
                return str(dart_path)
    return "dart"


def run_ruff_quality(
    config: dict[str, Any], project_root: Path, files: list[Path]
) -> None:
    """Run ruff ``format`` then ``check --fix`` on the generated files.

    This is the python-fastapi stack's quality runner. Behavior is unchanged
    from the original ``run_quality_tools``: it no-ops with a warning when ruff
    is absent so generation still succeeds.
    """
    if not files:
        return

    ruff = _find_ruff(project_root)
    if shutil.which(ruff) is None:
        print(
            "  ⚠️  ruff not found; skipping formatting/linting. "
            "Install ruff or add it to the project's venv."
        )
        return

    file_args = [str(f) for f in files]

    # Pass argv lists (shell=False) so paths with spaces/special chars are safe,
    # and chunk them so a large project can't exceed the OS command-line length
    # limit (~8 KiB on Windows → OSError "Argument list too long").
    print("\n  Running ruff format...")
    for batch in _chunked(file_args, _MAX_FILES_PER_CALL):
        _run_tool([ruff, "format", *batch], project_root, warn_on_failure=True)

    # `ruff check --fix` exits non-zero when residual unfixable lints remain,
    # which is expected for freshly generated code — not treated as a failure.
    print("  Running ruff check --fix...")
    for batch in _chunked(file_args, _MAX_FILES_PER_CALL):
        _run_tool([ruff, "check", "--fix", *batch], project_root, warn_on_failure=False)


def _run_tool(cmd: list[str], project_root: Path, *, warn_on_failure: bool) -> None:
    """Run an arbitrary tool (argv list, no shell), surfacing real failures."""
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if warn_on_failure and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"  ⚠️  '{' '.join(cmd)}' failed (exit {result.returncode}).")
        if detail:
            print(f"     {detail.splitlines()[-1]}")


def _resolve_tool(token: str, project_root: Path) -> str:
    """Resolve a command's leading executable token to a concrete path.

    Known tools (``ruff``, ``dart``) are resolved via their project-aware
    finders so a vendored toolchain is honored; anything else is returned as-is.
    """
    if token == "ruff":
        return _find_ruff(project_root)
    if token == "dart":
        return _find_dart(project_root)
    return token


def run_config_quality(
    config: dict[str, Any], project_root: Path, files: list[Path]
) -> None:
    """Run the stack's ``config["quality"]`` commands over the generated files.

    Each command value is either a shell-style string (e.g. ``"dart format ."``)
    or a mapping ``{command: "...", target: "package-root"}``. Tokens are split
    with :func:`shlex.split` (honoring quotes/escapes); a trailing ``"."``
    placeholder is replaced by the explicit
    file path list for per-file tools (formatters), or dropped for package-root
    tools.

    ``target: package-root`` runs the command once from the package root (the
    directory holding ``pubspec.yaml`` / ``analysis_options.yaml``) with no file
    arguments — needed by analyzers like ``dart analyze`` that resolve imports
    from project context rather than from a file list.

    No-ops with a warning when the underlying executable is absent, so
    generation succeeds even without the stack's SDK installed.
    """
    if not files:
        return

    quality = config.get("quality") or {}
    if not isinstance(quality, dict):
        return

    file_args = [str(f) for f in files]
    missing_tools: set[str] = set()

    # Stable, predictable order: formatters first, then linters/analyzers.
    ordered_keys = sorted(
        quality.keys(),
        key=lambda k: (0 if "format" in k else 1, k),
    )

    for key in ordered_keys:
        spec = quality[key]
        if isinstance(spec, dict):
            command = spec.get("command")
            package_root = spec.get("target") == "package-root"
        else:
            command = spec
            package_root = False

        if not isinstance(command, str) or not command.strip():
            continue

        tokens = shlex.split(command)
        if not tokens:
            continue
        executable = _resolve_tool(tokens[0], project_root)

        if shutil.which(executable) is None:
            missing_tools.add(tokens[0])
            continue

        # Drop a trailing "." placeholder; per-file tools get the explicit list,
        # package-root tools run from the package directory with no file args.
        base = [executable, *tokens[1:]]
        if base and base[-1] == ".":
            base = base[:-1]

        print(f"\n  Running {command}...")
        if package_root:
            _run_tool(base, project_root, warn_on_failure=True)
        else:
            for batch in _chunked(file_args, _MAX_FILES_PER_CALL):
                _run_tool([*base, *batch], project_root, warn_on_failure=True)

    for tool in sorted(missing_tools):
        print(
            f"  ⚠️  {tool} not found; skipping the steps that use it. "
            f"Install {tool} to format/lint the generated files."
        )


def run_quality_tools(
    config: dict[str, Any],
    project_root: Path,
    files: list[Path],
    quality_runner: QualityRunner | None = None,
) -> None:
    """Run linter/formatter on generated files via the stack's quality runner.

    ``quality_runner`` is the stack's registered runner (see ``StackSpec``).
    When omitted, defaults to the python-fastapi ruff runner so direct callers
    (and the historical contract) keep working unchanged.
    """
    runner = quality_runner or run_ruff_quality
    runner(config, project_root, files)
