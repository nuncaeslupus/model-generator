"""
Enum generation utilities.
"""

import re
from pathlib import Path
from typing import Any

from jinja2 import Environment

from ..utils.loaders import load_shared_enums


def get_existing_enums(enums_file: Path) -> set[str]:
    """Parse existing enums.py to find defined enum names."""
    if not enums_file.exists():
        return set()

    content = enums_file.read_text(encoding="utf-8")
    pattern = r"class\s+(\w+)\s*\(\s*(?:str\s*,\s*Enum|StrEnum)\s*\)"
    return set(re.findall(pattern, content))


def generate_enums(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    model_path: Path,
) -> dict[str, Any] | None:
    """
    Generate enum definitions from _shared/enums.json.

    Creates file if missing, appends new enums if file exists.
    """
    enum_defs = load_shared_enums(model_path)

    if not enum_defs:
        print("  ℹ️  No enums found in models/_shared/enums.json")
        return None

    output_dir = project_root / config["paths"]["database_models"]
    enums_file = output_dir / "enums.py"
    file_exists = enums_file.exists()

    if file_exists:
        existing_enums = get_existing_enums(enums_file)
        enums = {
            name: definition
            for name, definition in enum_defs.items()
            if name not in existing_enums
        }

        if not enums:
            print(f"  ℹ️  All enums already exist in {enums_file}")
            return None

        mode = "append"
    else:
        enums = enum_defs
        mode = "create"

    template = env.get_template("database/enums.py.j2")
    content = template.render(
        mode=mode,
        section_header="ENUMS",
        enums=enums,
        config=config,
    )

    return {
        "path": enums_file,
        "content": ("\n" + content) if file_exists else content,
        "mode": "append" if file_exists else "write",
        "new_count": len(enums),
        "skipped": len(enum_defs) - len(enums),
    }
