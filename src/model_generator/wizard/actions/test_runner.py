"""
Action: Run tests via pytest.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..prompts import confirm, select
from ._common import find_project_root as _find_project_root


def _find_test_dir(project_root: Path) -> Path | None:
    """Find the test directory."""
    for candidate in ["tests", "test"]:
        test_dir = project_root / candidate
        if test_dir.exists():
            return test_dir
    return None


def run_tests() -> None:
    """Run pytest with selected options."""
    project_root = _find_project_root()
    test_dir = _find_test_dir(project_root)

    if test_dir is None:
        print(f"\nNo tests/ directory found in {project_root}")
        return

    mode = select(
        "Test mode:",
        choices=["all tests", "verbose (-v)", "with coverage"],
        default="all tests",
    )

    cmd = [sys.executable, "-m", "pytest", str(test_dir)]

    if mode == "verbose (-v)":
        cmd.append("-v")
    elif mode == "with coverage":
        cmd.extend(["--cov", "--cov-report=term-missing"])

    print(f"\nRunning: {' '.join(cmd)}")
    if not confirm("Proceed?"):
        return

    subprocess.run(cmd, cwd=str(project_root))
