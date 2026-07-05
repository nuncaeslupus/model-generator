"""Flutter (Dart) API-layer generators — Phase 2.

Emits the retrofit API client, the request DTOs (``Create<E>Request`` /
``Update<E>Request`` freezed classes), the thin repository wrappers, and the API
barrel from a ``*.model.json`` spec, plus the shared API infrastructure
(``Paginated<T>`` envelope, dio setup, conditional auth interceptor).

Everything is driven by the spec's ``api`` block — ``enabled``, ``prefix``,
``endpoints``, ``pagination``, ``filters`` — exactly as the python-fastapi stack
drives its routes. Entities with ``api.enabled: false`` get no client (DB-model /
DTO only, mirroring python). All paths/imports are derived via ``paths.py`` —
never hardcoded — so the templates stay project-agnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment

from ...utils.templates import camel_case, snake_case
from .fields import (
    collect_dto_imports,
    primary_key_field,
    resolve_dto_fields,
)
from .paths import package_uri, resolve_path

# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #

# HTTP verb a spec ``update`` endpoint maps to. The backend mounts PUT for
# full-replacement update; PATCH is the partial-update alternative. Kept as a
# single source so the client matches the backend's verb.
_UPDATE_VERB = "PUT"


def _entity_filename(entity_name: str) -> str:
    """Dart file stem for an entity (snake_case; ``UserProfile`` → ``user_profile``)."""
    return snake_case(entity_name)


def _api_enabled(entity: dict[str, Any]) -> bool:
    """Whether an entity exposes an HTTP API (``api.enabled``, default true)."""
    api = entity.get("api") or {}
    return bool(api.get("enabled", True))


def _is_immutable(entity: dict[str, Any]) -> bool:
    """Whether the entity is immutable (no Update DTO / update endpoint)."""
    return bool(entity.get("mutability", "mutable") == "immutable")


def _endpoints(entity: dict[str, Any]) -> list[str]:
    """The entity's endpoint list, defaulting to the full CRUD set."""
    api = entity.get("api") or {}
    endpoints = api.get("endpoints")
    if endpoints is None:
        return ["list", "create", "get", "update", "delete"]
    return [str(e) for e in endpoints]


def _api_prefix(entity: dict[str, Any]) -> str:
    """Resolve the URL path segment for an entity, matching the backend.

    Prefers ``api.prefix`` (the spec's declared, already-kebab path). Falls back
    to the table name kebab-cased (the python route's ``entity_plural_kebab``)
    so the client URL is wire-compatible even when ``prefix`` is omitted.
    """
    api = entity.get("api") or {}
    prefix = api.get("prefix")
    if prefix:
        return str(prefix).strip("/")
    table = entity.get("table")
    if table:
        return str(table).replace("_", "-")
    return ""


def _filters(entity: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the ``@Query`` filter params for the list endpoint.

    Honors the ``api.filters`` whitelist when present (only those fields become
    query params); otherwise no field filters are emitted (the client keeps the
    universal ``page``/``page_size`` paging params, which are added separately).
    Server-managed fields (primary keys, response-excluded) are never filterable,
    matching the backend.
    """
    api = entity.get("api") or {}
    whitelist = api.get("filters")
    if not whitelist:
        return []

    type_map = config.get("types", {}) or {}
    filters: list[dict[str, Any]] = []
    for field_name in whitelist:
        field = (entity.get("fields") or {}).get(field_name)
        if not isinstance(field, dict):
            continue
        if field.get("primary_key") or field.get("api_exclude_response"):
            continue
        spec = type_map.get(field.get("type", ""), {}) or {}
        dart_type = str(spec.get("dart", "String"))
        # Enum filters carry the concrete enum type; others fall back to their
        # plain Dart type (Decimal/DateTime serialize via dio's value encoding).
        if field.get("type") == "enum":
            dart_type = str(field.get("enum_name", "String"))
        filters.append(
            {
                "name": camel_case(field_name),
                "query": str(field.get("api_field_name") or field_name),
                "dart_type": dart_type,
            }
        )
    return filters


def _build_ops(
    entity: dict[str, Any], entity_name: str, config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve the ordered list of client operations for an entity.

    Each op carries everything the retrofit/repository templates render: the
    ``kind`` (list/get/create/update/delete), HTTP path, method name, return and
    body types, and the id path-param name. ``immutable`` entities drop the
    ``update`` op even if listed, mirroring the python stack (no Update DTO ⇒ no
    update route); ``delete`` is *kept* for immutable entities, matching the
    python route template which gates delete only on ``"delete" in endpoints``.
    """
    prefix = _api_prefix(entity)
    base_path = f"/{prefix}" if prefix else "/"
    pk = primary_key_field(entity, config)
    paginated = bool((entity.get("api") or {}).get("pagination", False))
    immutable = _is_immutable(entity)

    single = f"{base_path.rstrip('/')}/{{{pk['json_key']}}}"
    list_return = f"Paginated<{entity_name}>" if paginated else f"List<{entity_name}>"

    ops: list[dict[str, Any]] = []
    for endpoint in _endpoints(entity):
        if endpoint == "list":
            ops.append(
                {
                    "kind": "list",
                    "path": base_path,
                    "method": "list",
                    "return_type": list_return,
                    "paginated": paginated,
                }
            )
        elif endpoint == "get":
            ops.append(
                {
                    "kind": "get",
                    "path": single,
                    "method": "getById",
                    "return_type": entity_name,
                    "id_key": pk["json_key"],
                    "id_param": pk["name"],
                    "id_type": pk["dart_type"],
                }
            )
        elif endpoint == "create":
            ops.append(
                {
                    "kind": "create",
                    "path": base_path,
                    "method": "create",
                    "return_type": entity_name,
                    "body_type": f"Create{entity_name}Request",
                }
            )
        elif endpoint == "update" and not immutable:
            ops.append(
                {
                    "kind": "update",
                    "verb": _UPDATE_VERB,
                    "path": single,
                    "method": "update",
                    "return_type": entity_name,
                    "body_type": f"Update{entity_name}Request",
                    "id_key": pk["json_key"],
                    "id_param": pk["name"],
                    "id_type": pk["dart_type"],
                }
            )
        elif endpoint == "delete":
            ops.append(
                {
                    "kind": "delete",
                    "path": single,
                    "method": "delete",
                    "id_key": pk["json_key"],
                    "id_param": pk["name"],
                    "id_type": pk["dart_type"],
                }
            )
    return ops


def _client_class(entity_name: str) -> str:
    """The retrofit client class name for an entity (``<E>Api``)."""
    return f"{entity_name}Api"


def _has_requests(entity: dict[str, Any]) -> bool:
    """Whether the entity has create/update endpoints needing request DTOs."""
    endpoints = _endpoints(entity)
    if "create" in endpoints:
        return True
    return "update" in endpoints and not _is_immutable(entity)


# --------------------------------------------------------------------------- #
# Domain generators
# --------------------------------------------------------------------------- #


def generate_flutter_api_client(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate one ``@RestApi`` retrofit client per API-enabled entity.

    Each lands at ``lib/<pkg>/api/<entity>_api.dart``. Entities with
    ``api.enabled: false`` are skipped (no client — DB model / DTO only).
    """
    template = env.get_template("api/retrofit_client.dart.j2")
    api_dir = project_root / resolve_path(config, "api_client")
    models_path = resolve_path(config, "models")
    core_path = resolve_path(config, "api_core")

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue
        file_stem = f"{_entity_filename(entity_name)}_api"
        ops = _build_ops(entity, entity_name, config)
        paginated = any(op.get("paginated") for op in ops)
        needs_requests = _has_requests(entity)

        content = template.render(
            entity_name=entity_name,
            class_name=_client_class(entity_name),
            file_stem=file_stem,
            ops=ops,
            filters=_filters(entity, config),
            needs_pagination=paginated,
            needs_requests=needs_requests,
            model_uri=package_uri(
                config, f"{models_path}/{_entity_filename(entity_name)}.dart"
            ),
            pagination_uri=package_uri(config, f"{core_path}/pagination.dart"),
            requests_uri=package_uri(
                config, f"{models_path}/{_entity_filename(entity_name)}_requests.dart"
            ),
        )
        outputs.append({"path": api_dir / f"{file_stem}.dart", "content": content})

    return outputs


def generate_flutter_request_dtos(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate the ``Create<E>Request`` / ``Update<E>Request`` freezed DTOs.

    One ``<entity>_requests.dart`` per API-enabled entity that has create/update
    endpoints, placed in the **models** directory alongside the freezed response
    models (keeping every freezed class — and its build_runner part files — under
    one tree, exported by the models barrel). ``immutable`` entities emit only the
    Create DTO, mirroring ``generate_api_init``.
    """
    template = env.get_template("api/request.dart.j2")
    models_dir = project_root / resolve_path(config, "models")
    core_path = resolve_path(config, "api_core")
    enums_path = resolve_path(config, "enums")

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue
        if not _has_requests(entity):
            continue

        immutable = _is_immutable(entity)
        kinds: tuple[str, ...] = ("create",) if immutable else ("create", "update")
        imports = collect_dto_imports(entity, config, kinds)
        file_stem = f"{_entity_filename(entity_name)}_requests"

        content = template.render(
            file_stem=file_stem,
            create_class=f"Create{entity_name}Request",
            create_fields=resolve_dto_fields(entity, config, "create"),
            update_class=None if immutable else f"Update{entity_name}Request",
            update_fields=(
                [] if immutable else resolve_dto_fields(entity, config, "update")
            ),
            dart_imports=imports["dart_imports"],
            needs_converters=imports["has_converter"],
            needs_enums=imports["has_enum"],
            converters_uri=package_uri(config, f"{core_path}/converters.dart"),
            enums_uri=package_uri(config, enums_path),
        )
        outputs.append({"path": models_dir / f"{file_stem}.dart", "content": content})

    return outputs


def generate_flutter_repositories(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Generate the thin repository wrappers (the Phase-4 offline-cache seam).

    Per API-enabled entity, two files under ``lib/<pkg>/repositories/``:

    * ``<entity>_repository.dart`` (overwrite) — delegates to the retrofit client.
    * ``<entity>_repository_custom.dart`` (skip-if-exists) — the hand-editable
      subclass adopters extend; an offline cache layers in here without touching
      the regenerated base.
    """
    template = env.get_template("api/repository.dart.j2")
    repo_dir = project_root / resolve_path(config, "repositories")
    api_path = resolve_path(config, "api_client")
    models_path = resolve_path(config, "models")
    core_path = resolve_path(config, "api_core")

    outputs: list[dict[str, Any]] = []
    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue
        stem = _entity_filename(entity_name)
        ops = _build_ops(entity, entity_name, config)
        paginated = any(op.get("paginated") for op in ops)
        needs_requests = _has_requests(entity)
        base_class = f"{entity_name}Repository"
        custom_class = f"{entity_name}RepositoryCustom"

        common = {
            "entity_name": entity_name,
            "base_class": base_class,
            "custom_class": custom_class,
            "client_class": _client_class(entity_name),
            "ops": ops,
            "filters": _filters(entity, config),
            "needs_pagination": paginated,
            "needs_requests": needs_requests,
            "api_uri": package_uri(config, f"{api_path}/{stem}_api.dart"),
            "model_uri": package_uri(config, f"{models_path}/{stem}.dart"),
            "pagination_uri": package_uri(config, f"{core_path}/pagination.dart"),
            "requests_uri": package_uri(config, f"{models_path}/{stem}_requests.dart"),
            "repository_uri": package_uri(
                config, f"{resolve_path(config, 'repositories')}/{stem}_repository.dart"
            ),
        }

        outputs.append(
            {
                "path": repo_dir / f"{stem}_repository.dart",
                "content": template.render(which="base", **common),
                "mode": "write",
            }
        )
        outputs.append(
            {
                "path": repo_dir / f"{stem}_repository_custom.dart",
                "content": template.render(which="custom", **common),
                "mode": "skip-if-exists",
            }
        )

    return outputs


def generate_flutter_api_index(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the ``api_index.dart`` barrel exporting every retrofit client.

    Scans the api directory for generated ``*_api.dart`` files (plus this run's
    API-enabled entities) so the barrel stays complete across multi-file specs.
    Returns ``None`` when no entity exposes an API.
    """
    template = env.get_template("api/index.dart.j2")
    api_dir = project_root / resolve_path(config, "api_client")

    exports: set[str] = set()
    if api_dir.is_dir():
        for dart_file in api_dir.glob("*_api.dart"):
            exports.add(dart_file.name)

    for entity_name, entity in (model.get("entities") or {}).items():
        if entity is None or not _api_enabled(entity):
            continue
        exports.add(f"{_entity_filename(entity_name)}_api.dart")

    if not exports:
        return None

    content = template.render(exports=sorted(exports))
    return {
        "path": api_dir / "api_index.dart",
        "content": content,
        "mode": "write",
    }


# --------------------------------------------------------------------------- #
# Infrastructure generators
# --------------------------------------------------------------------------- #


def generate_flutter_pagination(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any]:
    """Generate ``lib/<pkg>/core/pagination.dart`` (overwrite).

    Emits the ``Paginated<T>`` / ``PageInfo`` envelope matching the FastAPI
    stack's ``PaginatedResponse[T]`` wire shape byte-for-byte (``items`` +
    ``page_info``). Project-agnostic — no entity-specific code.
    """
    template = env.get_template("infrastructure/pagination.dart.j2")
    core_dir = project_root / resolve_path(config, "api_core")
    content = template.render()
    return {"path": core_dir / "pagination.dart", "content": content}


def _auth_strategy(config: dict[str, Any]) -> str | None:
    """The configured auth strategy, or None when auth is disabled."""
    auth = (config or {}).get("auth") or {}
    strategy = auth.get("strategy")
    return str(strategy) if strategy else None


def generate_dio_setup(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    project_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate the dio base + the hand-editable custom hook (two files).

    * ``api_client.dart`` (overwrite) — builds a configured ``Dio`` with the API
      base URL and, when an auth strategy is set, the generated auth interceptor.
    * ``api_client_custom.dart`` (skip-if-exists) — the adopter-owned
      ``configureApiClient`` hook.

    The base URL defaults to the FastAPI backend's versioned API root so the
    generated client is wire-compatible out of the box; adopters override per
    environment via ``buildApiClient(baseUrl: ...)``.
    """
    # project_config overlays config for auth/project lookups (orchestrator always
    # passes the same value; tests may pass a separate overlay).
    effective = {**config, **(project_config or {})}
    template = env.get_template("infrastructure/dio_setup.dart.j2")
    core_dir = project_root / resolve_path(config, "api_core")
    strategy = _auth_strategy(effective)
    has_auth = strategy is not None
    auth_interceptor_uri = package_uri(
        config, f"{resolve_path(config, 'api_core')}/auth_interceptor.dart"
    )

    common = {
        "has_auth": has_auth,
        "base_url": "/api/v1",
        "auth_interceptor_uri": auth_interceptor_uri,
    }

    return [
        {
            "path": core_dir / "api_client.dart",
            "content": template.render(which="base", **common),
            "mode": "write",
        },
        {
            "path": core_dir / "api_client_custom.dart",
            "content": template.render(which="custom", **common),
            "mode": "skip-if-exists",
        },
    ]


def generate_auth_interceptor(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    project_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Generate ``lib/<pkg>/core/auth_interceptor.dart`` — conditional on auth.

    Returns ``None`` when no ``auth.strategy`` is set (no interceptor — server
    concern only). Reads auth coarsely:

    * ``api-key`` → attach the configured ``auth.header_name`` (default
      ``X-API-Key``) on every request.
    * ``bcrypt-session`` → cookie passthrough + CSRF double-submit header.
    """
    # project_config overlays config for auth/project lookups (orchestrator always
    # passes the same value; tests may pass a separate overlay).
    effective = {**config, **(project_config or {})}
    strategy = _auth_strategy(effective)
    if strategy is None:
        return None

    auth = effective.get("auth") or {}
    template = env.get_template("infrastructure/auth_interceptor.dart.j2")
    core_dir = project_root / resolve_path(config, "api_core")
    content = template.render(
        strategy=strategy,
        header_name=auth.get("header_name", "X-API-Key"),
        csrf_cookie="csrf_token",
        csrf_header="X-CSRF-Token",
    )
    return {"path": core_dir / "auth_interceptor.dart", "content": content}
