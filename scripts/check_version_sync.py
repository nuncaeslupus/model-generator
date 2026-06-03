#!/usr/bin/env python3
"""Fail with a non-zero exit code if model-generator's own version strings in
src/model_generator/__init__.py and README.md have drifted from pyproject.toml.

Wired into CI as `make check-version-sync`. Unlike `sync_version.py`, this
script makes no changes — it just compares values.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


def _pyproject_version() -> str:
    # tomllib (stdlib 3.11+) parses the TOML properly, avoiding false positives
    # from regex-matching a `version =` line inside a [tool.*] table.
    with Path("pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    try:
        return str(data["project"]["version"])
    except KeyError as exc:
        raise SystemExit(f"No project.version in pyproject.toml: {exc}") from exc


def _init_version() -> str:
    content = Path("src/model_generator/__init__.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not m:
        raise SystemExit("No __version__ in src/model_generator/__init__.py")
    return m.group(1)


def _readme_version() -> str:
    content = Path("README.md").read_text(encoding="utf-8")
    # \S+ covers pre-release/build suffixes (e.g. "1.2.0-rc1", "1.2.0+build.5").
    m = re.search(
        r"\*\*Model Generator\*\* \| Bootstrap Tool for API Backends \| v(\S+)",
        content,
    )
    if not m:
        raise SystemExit("Could not find the version footer in README.md")
    return m.group(1)


def main() -> None:
    canonical = _pyproject_version()
    checks = {
        "src/model_generator/__init__.py (__version__)": _init_version(),
        "README.md (footer)": _readme_version(),
    }
    drift = {k: v for k, v in checks.items() if v != canonical}
    if drift:
        print(f"Version drift detected (pyproject.toml: {canonical}):", file=sys.stderr)
        for where, found in drift.items():
            print(f"  - {where} = {found}", file=sys.stderr)
        print("\nRun `make version-sync` and commit the result.", file=sys.stderr)
        sys.exit(1)
    print(f"Version in sync: {canonical}")


if __name__ == "__main__":
    main()
