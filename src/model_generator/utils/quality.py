"""
Code quality tools runner.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any


def _find_ruff(project_root: Path) -> str:
    """Find ruff binary, preferring the project's venv."""
    for venv_dir in [".venv", "venv"]:
        ruff_path = project_root / venv_dir / "bin" / "ruff"
        if ruff_path.exists():
            return str(ruff_path)
    return "ruff"


def _run_ruff(cmd: list[str], project_root: Path, *, warn_on_failure: bool) -> None:
    """Run a ruff subcommand (argv list, no shell), surfacing real failures."""
    result = subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if warn_on_failure and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"  ⚠️  '{' '.join(cmd)}' failed (exit {result.returncode}).")
        if detail:
            print(f"     {detail.splitlines()[-1]}")


def run_quality_tools(
    config: dict[str, Any], project_root: Path, files: list[Path]
) -> None:
    """Run linter and formatter on generated files."""
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

    # Pass argv lists (shell=False) so paths with spaces/special chars are safe.
    print("\n  Running ruff format...")
    _run_ruff([ruff, "format", *file_args], project_root, warn_on_failure=True)

    # `ruff check --fix` exits non-zero when residual unfixable lints remain,
    # which is expected for freshly generated code — not treated as a failure.
    print("  Running ruff check --fix...")
    _run_ruff([ruff, "check", "--fix", *file_args], project_root, warn_on_failure=False)
