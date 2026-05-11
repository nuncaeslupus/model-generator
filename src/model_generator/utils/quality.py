"""
Code quality tools runner.
"""

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


def run_quality_tools(
    config: dict[str, Any], project_root: Path, files: list[Path]
) -> None:
    """Run linter and formatter on generated files."""
    if not files:
        return

    ruff = _find_ruff(project_root)
    file_paths = " ".join(str(f) for f in files)

    print("\n  Running ruff format...")
    subprocess.run(
        f"{ruff} format {file_paths}",
        shell=True,
        cwd=project_root,
        capture_output=True,
    )

    print("  Running ruff check --fix...")
    subprocess.run(
        f"{ruff} check --fix {file_paths}",
        shell=True,
        cwd=project_root,
        capture_output=True,
    )
