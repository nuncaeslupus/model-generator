"""
Enum generation utilities.
"""

import re
from pathlib import Path

from jinja2 import Environment

from ..utils.loaders import load_shared_enums


def get_existing_enums(enums_file: Path) -> set[str]:
    """Parse existing enums.py to find defined enum names."""
    if not enums_file.exists():
        return set()

    content = enums_file.read_text()
    pattern = r"class\s+(\w+)\s*\(\s*(?:str\s*,\s*Enum|StrEnum)\s*\)"
    return set(re.findall(pattern, content))


def generate_enums(
    model: dict, config: dict, env: Environment, project_root: Path, model_path: Path
) -> dict | None:
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
        new_enums = {
            name: definition
            for name, definition in enum_defs.items()
            if name not in existing_enums
        }

        if not new_enums:
            print(f"  ℹ️  All enums already exist in {enums_file}")
            return None

        template = env.get_template("database/enums.py.j2")
        content = template.render(
            mode="append",
            section_header="ENUMS",
            enums=new_enums,
            config=config,
        )

        return {
            "path": enums_file,
            "content": "\n" + content,
            "mode": "append",
            "new_count": len(new_enums),
            "skipped": len(enum_defs) - len(new_enums),
        }
    else:
        template = env.get_template("database/enums.py.j2")
        content = template.render(
            mode="create",
            section_header="ENUMS",
            enums=enum_defs,
            config=config,
        )

        return {
            "path": enums_file,
            "content": content,
            "mode": "write",
            "new_count": len(enum_defs),
            "skipped": 0,
        }
