#!/usr/bin/env python3
"""Synchronize model-generator's own version strings across the project.

Source of truth: pyproject.toml [project].version.

NOTE: model-generator is itself a code generator, so the string "0.1.0" also
appears in template defaults, loader fallbacks, wizard prompts, and docs
examples. Those describe the *downstream generated project's* version and are
deliberately NOT touched here. Only the two places that hold model-generator's
OWN version are synced:
  - src/model_generator/__init__.py (__version__)
  - README.md footer ("... | vX.Y.Z")
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


def get_version() -> str:
    # Parse the TOML properly (matching check_version_sync.py) rather than
    # regex-matching a `version =` line that could also live in a [tool.*] table.
    with Path("pyproject.toml").open("rb") as f:
        data = tomllib.load(f)
    try:
        return str(data["project"]["version"])
    except KeyError as exc:
        raise ValueError("Could not find project.version in pyproject.toml") from exc


def update_init(version: str) -> None:
    path = Path("src/model_generator/__init__.py")
    content = path.read_text(encoding="utf-8")
    pattern = r'^__version__\s*=\s*"[^"]+"'
    replacement = f'__version__ = "{version}"'
    content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
    if count == 0:
        raise ValueError(f"Could not find __version__ in {path}")
    path.write_text(content, encoding="utf-8")
    print(f"Updated {path}")


def update_readme(version: str) -> None:
    path = Path("README.md")
    content = path.read_text(encoding="utf-8")
    # Footer line: "**Model Generator** | Bootstrap Tool for API Backends | vX.Y.Z"
    pattern = r"(\*\*Model Generator\*\* \| Bootstrap Tool for API Backends \| v)\S+"
    replacement = rf"\g<1>{version}"
    content, count = re.subn(pattern, replacement, content)
    if count == 0:
        raise ValueError(f"Could not find the version footer in {path}")
    path.write_text(content, encoding="utf-8")
    print(f"Updated {path}")


def main() -> None:
    try:
        version = get_version()
        print(f"Syncing version: {version}")
        update_init(version)
        update_readme(version)
        print("Done!")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
