"""Path/package helpers for the Flutter stack.

The Flutter ``config.yaml`` carries a ``{pkg}`` placeholder in every ``paths``
entry so the whole ``lib/<package>/…`` tree is configurable from a single
``flutter.package_name`` value. These helpers resolve that placeholder and the
``package:<pkg>/…`` import prefix consistently across generators and templates.
"""

from __future__ import annotations

from typing import Any

DEFAULT_PACKAGE_NAME = "app_api"


def package_name(config: dict[str, Any]) -> str:
    """Return the configured Dart package name (``flutter.package_name``).

    Falls back to :data:`DEFAULT_PACKAGE_NAME` so an ad-hoc config dict that
    omits the ``flutter`` block still resolves a usable layout.
    """
    flutter = config.get("flutter")
    if isinstance(flutter, dict):
        name = flutter.get("package_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return DEFAULT_PACKAGE_NAME


def resolve_path(config: dict[str, Any], key: str, default: str = "") -> str:
    """Resolve a ``paths.<key>`` entry, substituting the ``{pkg}`` placeholder.

    e.g. ``lib/{pkg}/models`` → ``lib/app_api/models``. Project overrides in
    ``.model-generator.yaml`` are honored because they flow through the same
    merged ``config["paths"]`` and are subject to the same substitution.
    """
    raw = (config.get("paths") or {}).get(key, default)
    return str(raw).replace("{pkg}", package_name(config))


def package_uri(config: dict[str, Any], lib_relative: str) -> str:
    """Build a ``package:<pkg>/<path>`` import URI from a lib-relative path.

    ``lib_relative`` is a path under ``lib/`` (e.g. ``lib/models/user.dart``);
    Dart package URIs have the form ``package:<pubspec_name>/<lib-relative>``
    where the package name comes from ``flutter.package_name``. Derived from
    config — never hardcoded to a project name.
    """
    pkg = package_name(config)
    relative = lib_relative
    if relative.startswith("lib/"):
        relative = relative[len("lib/") :]
    return f"package:{pkg}/{relative}"
