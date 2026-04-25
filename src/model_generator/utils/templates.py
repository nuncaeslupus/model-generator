"""
Jinja2 template utilities.
"""

import textwrap
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def path_to_import(file_path: str, module_name: str = "", python_root: str = "") -> str:
    """
    Convert a file path to a Python import path.

    Examples:
        backend/src/database/models → backend.src.database.models
        src/api/validators → src.api.validators

    When ``python_root`` is set, strip it as a prefix before conversion so
    adopters using a ``src``-layout get ``models.database`` instead of
    ``src.models.database``:

        path_to_import("src/api/validators", python_root="src")
        → "api.validators"
    """
    stripped = file_path
    if python_root:
        pr = python_root.rstrip("/")
        if stripped == pr or stripped.startswith(pr + "/"):
            stripped = stripped[len(pr) :].lstrip("/")
    import_base = stripped.replace("/", ".").replace("\\", ".")
    if module_name:
        return f"{import_base}.{module_name}" if import_base else module_name
    return import_base


def wrap_text(text: str, width: int = 88, indent: int = 0, prefix: str = "") -> str:
    """Wrap text to fit within a given line width.

    Args:
        text: The text to wrap.
        width: Maximum line width (default 88, matching ruff).
        indent: Number of spaces for continuation lines.
        prefix: The first-line prefix already in the template (e.g.,
            "        field_name: "). Used to calculate first-line available
            width but NOT included in output.
    """
    if not text:
        return text
    wrapper = textwrap.TextWrapper(
        width=width,
        initial_indent=prefix,
        subsequent_indent=" " * indent,
    )
    result = wrapper.fill(text)
    # Strip the prefix since the template already renders it
    if prefix:
        return result[len(prefix) :]
    return result


def _normalize_decimal(value: float | int | str) -> str:
    """Normalize a numeric value to its minimal string representation.

    Matches the behavior of normalize_decimal() in generated utils.py:
    strips trailing zeros, uses fixed-point for scientific notation.
    """
    d = Decimal(str(value)).normalize()
    if "E" in str(d):
        return f"{d:f}"
    return str(d)


def snake_case(name: str) -> str:
    """Convert CamelCase to snake_case.

    Mirrors the ``to_snake_case`` Jinja macro in
    ``stacks/python-fastapi/templates/_shared/_entity.j2`` so generators
    deriving filenames in Python and templates emitting the same names
    in Jinja agree byte-for-byte.

    Examples:
        User           → user
        UserSession    → user_session
        ApiKey         → api_key
    """
    parts: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            parts.append("_")
        parts.append(ch.lower())
    return "".join(parts)


def get_template_env(
    stack: str = "python-fastapi", config: dict | None = None
) -> Environment:
    """Create Jinja2 environment for templates.

    If ``config`` contains a ``python_root`` key, the ``path_to_import``
    filter closes over it so templates can emit import paths stripped of
    the project's Python source root.
    """
    script_dir = Path(__file__).parent.parent
    template_dir = script_dir / "stacks" / stack / "templates"

    env = Environment(
        loader=FileSystemLoader(template_dir),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    python_root = (config or {}).get("python_root", "")

    def _path_to_import_filter(file_path: str, module_name: str = "") -> str:
        return path_to_import(file_path, module_name, python_root)

    # Add custom filters
    env.filters["dict2items"] = lambda d: [{"key": k, "value": v} for k, v in d.items()]
    env.filters["path_to_import"] = _path_to_import_filter
    env.filters["wrap"] = wrap_text
    env.filters["normalize_decimal"] = _normalize_decimal
    env.filters["snake_case"] = snake_case

    return env
