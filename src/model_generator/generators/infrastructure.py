"""
Infrastructure file generation (base, engine, main, errors, validators, etc.).
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment

from ..utils.constants import GENERATED_MARKER
from ..utils.output import write_outputs
from ..utils.templates import path_to_import

# Generous default request-body cap (10 MiB) — large enough that normal JSON /
# base64 payloads are never affected, small enough to blunt large-body soft-DoS.
DEFAULT_MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


def _app_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return the ``app`` config section as a dict.

    Falls back to an empty dict when the key is absent or misconfigured as a
    non-mapping value (e.g. ``app: true``), so callers can ``.get()`` without
    risking an ``AttributeError``.
    """
    app_config = config.get("app")
    return app_config if isinstance(app_config, dict) else {}


def _max_request_body_bytes(config: dict[str, Any]) -> int:
    """Resolve the configured request-body cap in bytes.

    Reads ``app.max_request_body_bytes`` (falling back to the generous
    default). A non-positive value disables the limit: the middleware is not
    emitted and ``main.py`` does not wire it.
    """
    value = _app_config(config).get(
        "max_request_body_bytes", DEFAULT_MAX_REQUEST_BODY_BYTES
    )
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_REQUEST_BODY_BYTES


def generate_base(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate SQLAlchemy Base class."""
    db_models = config["paths"].get("database_models", "backend/src/database/models")
    base_path = config["paths"].get("base", f"{db_models}/base.py")
    output_path = project_root / base_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/base.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_engine(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate database engine and session management."""
    engine_path = config["paths"].get("engine", "backend/src/database/engine.py")
    output_path = project_root / engine_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/engine.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_types(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate custom SQLAlchemy types (SqliteNumeric for financial/percentage)."""
    db_models = config["paths"].get("database_models", "backend/src/database/models")
    db_dir = str(Path(db_models).parent)
    output_path = project_root / db_dir / "types.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/types.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_database_init(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate database package __init__.py with get_session export."""
    db_models = config["paths"].get("database_models", "backend/src/database/models")
    db_dir = str(Path(db_models).parent)
    output_path = project_root / db_dir / "__init__.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/database_init.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_errors(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate API error formatting utilities."""
    errors_path = config["paths"].get("errors", "backend/src/api/errors.py")
    output_path = project_root / errors_path

    if output_path.exists():
        return None

    expose_integrity_error_fields = bool(
        _app_config(config).get("expose_integrity_error_fields", False)
    )

    template = env.get_template("infrastructure/errors.py.j2")
    content = template.render(
        expose_integrity_error_fields=expose_integrity_error_fields
    )

    return {"path": output_path, "content": content}


def generate_validators(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate API validation utilities.

    Bootstrap-only: returns None when the file already exists so adopters
    who add domain-specific validators are not overwritten on regeneration.
    """
    validators_path = config["paths"].get("validators", "backend/src/api/validators.py")
    output_path = project_root / validators_path

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/validators.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_utils(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate API utility functions (normalize_decimal).

    Bootstrap-only: returns None when the file already exists so adopters
    who add domain-specific utilities are not overwritten on regeneration.
    """
    api_models_path = config["paths"].get("api_models", "backend/src/api/models")
    api_dir = str(Path(api_models_path).parent)
    output_path = project_root / api_dir / "utils.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/utils.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_request_limit(
    config: dict[str, Any], env: Environment, project_root: Path
) -> dict[str, Any] | None:
    """Generate the request-body size-limit ASGI middleware.

    Bootstrap-only. Emitted by default (when ``app.max_request_body_bytes``
    is a positive integer); setting it to 0 disables the limit and skips
    emission. Lives next to the other API-layer infrastructure files.
    """
    if _max_request_body_bytes(config) <= 0:
        return None

    api_models_path = config["paths"].get("api_models", "backend/src/api/models")
    api_dir = str(Path(api_models_path).parent)
    output_path = project_root / api_dir / "request_limit.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/request_limit.py.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_gitignore(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    no_root_files: bool = False,
) -> dict[str, Any] | None:
    """Generate .gitignore for new projects (only if none exists).

    Returns None when ``no_root_files`` is set, so adopters using
    --no-root-files for scratch-and-migrate workflows keep their own
    repository's .gitignore unchanged.
    """
    if no_root_files:
        return None

    output_path = project_root / ".gitignore"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/gitignore.j2")
    content = template.render()

    return {"path": output_path, "content": content}


def generate_env_example(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    has_encrypted_binary: bool = False,
    no_root_files: bool = False,
) -> dict[str, Any] | None:
    """Generate a ``.env.example`` manifest of the project's environment vars.

    The generated app reads ~5-9 env vars (DATABASE_URL, APP_ENV, CORS_ORIGINS,
    plus auth / rate-limit / encryption vars when those features are on); a
    manifest makes the required set discoverable. Root-file and bootstrap-only:
    returns None under ``no_root_files`` and skips when a ``.env.example``
    already exists.
    """
    if no_root_files:
        return None

    output_path = project_root / ".env.example"

    if output_path.exists():
        return None

    auth = config.get("auth") or {}
    strategy = auth.get("strategy")
    session_auth = strategy == "bcrypt-session"
    api_key_auth = strategy == "api-key"
    auth_enabled = bool(strategy)
    pepper_env = auth.get("pepper_env", "APP_PASSWORD_PEPPER")
    key_env = auth.get("key_env", "API_KEY")

    rate_limit_redis = False
    if session_auth:
        rate_limit = auth.get("rate_limit") or {}
        if rate_limit.get("enabled") is not False:
            rate_limit_redis = rate_limit.get("backend") == "redis"

    template = env.get_template("infrastructure/env.example.j2")
    content = template.render(
        project=config.get("project", {}),
        auth_enabled=auth_enabled,
        session_auth=session_auth,
        api_key_auth=api_key_auth,
        pepper_env=pepper_env,
        key_env=key_env,
        rate_limit_redis=rate_limit_redis,
        has_encrypted_binary=has_encrypted_binary,
    )

    return {"path": output_path, "content": content}


def generate_pyproject(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    extra_deps: list[str] | None = None,
    no_root_files: bool = False,
) -> dict[str, Any] | None:
    """Generate pyproject.toml for new projects (only if none exists).

    Returns None when ``no_root_files`` is set, so adopters using
    --no-root-files for scratch-and-migrate workflows keep their own
    repository's pyproject.toml unchanged.
    """
    if no_root_files:
        return None

    output_path = project_root / "pyproject.toml"

    if output_path.exists():
        return None

    project = config.get("project", {})
    raw_name = project.get("name", "my-project")
    project_slug = raw_name.lower().replace(" ", "-")

    deps = config.get("dependencies", {})
    runtime_deps = deps.get("runtime", [])
    dev_deps = deps.get("dev", [])

    # Merge domain-level extra dependencies
    if extra_deps:
        runtime_deps = sorted(set(runtime_deps + extra_deps))

    paths = config.get("paths", {})
    validators_path = paths.get("validators", "backend/src/api/validators.py")

    api_models_path = paths.get("api_models", "backend/src/api/models")
    utils_path = str(Path(api_models_path).parent / "utils.py")

    constraints_path = paths.get(
        "constraints", "backend/src/database/models/constraints.py"
    )

    migrations_path = paths.get("migrations", "alembic")

    # Top-level source directory for mutmut also_copy
    also_copy_dir = Path(validators_path).parts[0] + "/"

    # Package root for setuptools discovery (e.g., "backend/src")
    main_path = paths.get("main", "backend/src/main.py")
    package_root = str(Path(main_path).parent)

    raw_style = config.get("style") or {}
    style = {
        "python_version": raw_style.get("python_version") or "3.12",
        "line_length": raw_style.get("line_length"),
        "quote_style": raw_style.get("quote_style"),
        "indent_style": raw_style.get("indent_style"),
    }

    template = env.get_template("infrastructure/pyproject.toml.j2")
    content = template.render(
        project=project,
        project_slug=project_slug,
        runtime_deps=runtime_deps,
        dev_deps=dev_deps,
        validators_path=validators_path,
        utils_path=utils_path,
        constraints_path=constraints_path,
        migrations_path=migrations_path,
        also_copy_dir=also_copy_dir,
        package_root=package_root,
        style=style,
    )

    return {"path": output_path, "content": content}


def generate_main(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    domains: list[str],
    route_modules: list[str] | None = None,
) -> dict[str, Any] | None:
    """Generate FastAPI main application.

    ``domains`` is kept for backward compatibility. ``route_modules`` is the
    layout-aware list of route module stems imported by main.py — entity
    snake_case names in per-entity mode, domain names in per-domain mode.
    Defaults to ``domains`` when not provided.

    Bootstrap-only: returns None when the file already exists so adopters
    who wire up additional routers / middleware are not overwritten on
    regeneration. New domains/routes added later must be wired manually.
    """
    main_path = config["paths"].get("main", "backend/src/main.py")
    output_path = project_root / main_path

    if output_path.exists():
        return None

    python_root = config.get("python_root", "")

    api_routes_path = config["paths"].get("api_routes", "backend/src/api/routes")
    api_routes_import = path_to_import(api_routes_path, python_root=python_root)

    db_models_path = config["paths"].get(
        "database_models", "backend/src/database/models"
    )
    db_import = path_to_import(
        str(Path(db_models_path).parent), python_root=python_root
    )

    main_dir = str(Path(main_path).parent)
    main_module = path_to_import(main_dir, "main", python_root=python_root)

    errors_path = config["paths"].get("errors", "backend/src/api/errors.py")
    errors_module = errors_path[:-3] if errors_path.endswith(".py") else errors_path
    errors_import = path_to_import(errors_module, python_root=python_root)

    max_request_body_bytes = _max_request_body_bytes(config)
    request_limit_module_import = None
    if max_request_body_bytes > 0:
        api_models_path = config["paths"].get("api_models", "backend/src/api/models")
        api_dir = str(Path(api_models_path).parent)
        request_limit_module_import = path_to_import(
            str(Path(api_dir) / "request_limit"), python_root=python_root
        )

    # Session-strategy infrastructure (router / CSRF / rate-limit) is mounted in
    # main only for bcrypt-session. The api-key strategy ships no router — its
    # require_api_key dependency is imported by the routes, not the app.
    auth_router_import = None
    auth = config.get("auth") or {}
    if auth.get("strategy") == "bcrypt-session":
        auth_path = auth.get("path", "backend/src/auth/router.py")
        auth_module_path = auth_path[:-3] if auth_path.endswith(".py") else auth_path
        auth_router_import = path_to_import(auth_module_path, python_root=python_root)

    csrf_module_import = None
    if auth.get("strategy") == "bcrypt-session":
        auth_path = auth.get("path", "backend/src/auth/router.py")
        csrf_module_path = str(Path(auth_path).parent / "csrf")
        csrf_module_import = path_to_import(csrf_module_path, python_root=python_root)

    rate_limit_module_import = None
    if auth.get("strategy") == "bcrypt-session":
        rate_limit = auth.get("rate_limit") or {}
        if rate_limit.get("enabled") is not False:
            auth_path = auth.get("path", "backend/src/auth/router.py")
            rate_limit_module_path = str(Path(auth_path).parent / "rate_limit")
            rate_limit_module_import = path_to_import(
                rate_limit_module_path, python_root=python_root
            )

    template = env.get_template("infrastructure/main.py.j2")
    content = template.render(
        domains=route_modules if route_modules is not None else domains,
        api_routes_import=api_routes_import,
        db_import=db_import,
        main_module=main_module,
        project=config.get("project", {}),
        auth_router_import=auth_router_import,
        csrf_module_import=csrf_module_import,
        rate_limit_module_import=rate_limit_module_import,
        errors_import=errors_import,
        request_limit_module_import=request_limit_module_import,
        max_request_body_bytes=max_request_body_bytes,
    )

    return {"path": output_path, "content": content}


def generate_auth_router(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the auth router (register / login / logout / etc.).

    Emitted only when ``config.auth.strategy`` is set. Bootstrap-only:
    returns None when the file already exists at the configured
    ``auth.path`` so adopters who customize the router are not overwritten
    on regeneration.
    """
    if config.get("auth", {}).get("strategy") != "bcrypt-session":
        return None

    auth_path = config.get("auth", {}).get("path", "backend/src/auth/router.py")
    output_path = project_root / auth_path

    if output_path.exists():
        return None

    python_root = config.get("python_root", "")

    db_models_path = config["paths"].get(
        "database_models", "backend/src/database/models"
    )
    db_models_import = path_to_import(db_models_path, python_root=python_root)
    db_import = path_to_import(
        str(Path(db_models_path).parent), python_root=python_root
    )

    template = env.get_template("infrastructure/auth_router.py.j2")
    content = template.render(
        config=config,
        db_models_import=db_models_import,
        db_import=db_import,
        project=config.get("project", {}),
        rate_limit_enabled=(config.get("auth", {}).get("rate_limit") or {}).get(
            "enabled"
        )
        is not False,
    )

    return {"path": output_path, "content": content}


def generate_csrf(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the CSRF middleware (double-submit cookie pattern).

    Emitted only when ``config.auth.strategy`` is set. The file lives next
    to the auth router (sibling in the same package) so the router can
    import it via ``from .csrf import set_csrf_cookie``. Bootstrap-only:
    returns None when the file already exists.
    """
    if config.get("auth", {}).get("strategy") != "bcrypt-session":
        return None

    auth_path = config.get("auth", {}).get("path", "backend/src/auth/router.py")
    csrf_path = str(Path(auth_path).parent / "csrf.py")
    output_path = project_root / csrf_path

    if output_path.exists():
        return None

    cookie_name = config.get("auth", {}).get("cookie_name", "session_id")

    template = env.get_template("infrastructure/csrf.py.j2")
    content = template.render(cookie_name=cookie_name)

    return {"path": output_path, "content": content}


def generate_encrypted_bytes(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    has_encrypted_binary: bool = False,
) -> dict[str, Any] | None:
    """Generate the EncryptedBytes TypeDecorator next to the model files.

    Emitted only when at least one entity in the project has a ``binary``
    field with an ``encrypt`` block — mirrors the ``ns.has_encrypted_binary``
    gate that ``model.py.j2`` uses to conditionally emit
    ``from .encrypted_bytes import EncryptedBytes``. Bootstrap-only:
    returns None when the file already exists at the target path.
    """
    if not has_encrypted_binary:
        return None

    db_models = config["paths"].get("database_models", "backend/src/database/models")
    output_path = project_root / db_models / "encrypted_bytes.py"

    if output_path.exists():
        return None

    template = env.get_template("infrastructure/encrypted_bytes.py.j2")
    content = template.render(config=config)

    return {"path": output_path, "content": content}


def generate_rate_limit(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the rate-limit module (shared slowapi Limiter instance).

    Emitted only when ``config.auth.strategy`` is set AND
    ``config.auth.rate_limit.enabled`` is not False (rate limiting is on
    by default for auth-enabled projects). The file lives next to the
    auth router so the router can import it via
    ``from .rate_limit import limiter``. Bootstrap-only: returns None
    when the file already exists.
    """
    auth = config.get("auth") or {}
    if auth.get("strategy") != "bcrypt-session":
        return None

    rate_limit = auth.get("rate_limit") or {}
    if rate_limit.get("enabled") is False:
        return None

    auth_path = auth.get("path", "backend/src/auth/router.py")
    rate_limit_path = str(Path(auth_path).parent / "rate_limit.py")
    output_path = project_root / rate_limit_path

    if output_path.exists():
        return None

    backend = rate_limit.get("backend", "memory")
    default_storage_uri = (
        "redis://localhost:6379/0" if backend == "redis" else "memory://"
    )

    template = env.get_template("infrastructure/rate_limit.py.j2")
    content = template.render(
        login_limit=rate_limit.get("login", "5/minute"),
        register_limit=rate_limit.get("register", "3/hour"),
        forgot_limit=rate_limit.get("forgot", "3/hour"),
        default_storage_uri=default_storage_uri,
    )

    return {"path": output_path, "content": content}


def api_key_dependency_module(auth: dict[str, Any]) -> str:
    """Return the file path (relative to project root) of the api-key module.

    The ``require_api_key`` dependency lives in the auth package, a sibling of
    where the session strategy's router would live, so the module path tracks
    ``auth.path``'s directory (default ``backend/src/auth/``).
    """
    auth_path = auth.get("path", "backend/src/auth/router.py")
    return str(Path(auth_path).parent / "api_key.py")


def generate_api_key_auth(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | None:
    """Generate the static API-key auth dependency (``require_api_key``).

    Emitted only when ``config.auth.strategy`` is ``"api-key"``. The module
    lives in the auth package so routes import it via the inferred
    ``auth.dependency_path``. Bootstrap-only: returns None when the file
    already exists so adopter edits survive regeneration.
    """
    auth = config.get("auth") or {}
    if auth.get("strategy") != "api-key":
        return None

    output_path = project_root / api_key_dependency_module(auth)
    if output_path.exists():
        return None

    header_name = auth.get("header_name", "X-API-Key")
    key_env = auth.get("key_env", "API_KEY")
    # Python identifier for the FastAPI Header parameter. The alias carries the
    # real header name, so this only needs to be a valid, stable identifier —
    # sanitize any non-alphanumeric char (space, dot, symbol) to an underscore
    # so a custom header_name can't produce a SyntaxError in the generated code.
    sanitized = "".join(c if c.isalnum() else "_" for c in header_name.lower())
    header_param = sanitized if sanitized.strip("_") else "api_key"
    if header_param[0].isdigit():
        header_param = "_" + header_param

    template = env.get_template("infrastructure/api_key_auth.py.j2")
    content = template.render(
        key_env=key_env,
        header_name=header_name,
        header_param=header_param,
        project=config.get("project", {}),
    )

    return {"path": output_path, "content": content}


def generate_test_conftest_root(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    domains: list[str],
    factory_modules: list[str] | None = None,
) -> dict[str, Any] | None:
    """Generate root test conftest with database and client fixtures.

    ``domains`` is kept for backward compatibility. ``factory_modules`` is the
    layout-aware list of factory module stems imported by conftest.py — entity
    snake_case names in per-entity mode, domain names in per-domain mode.
    Defaults to ``domains`` when not provided.

    Bootstrap-only: returns None when the file already exists so adopters
    who add fixture overrides are not overwritten on regeneration. New
    factory modules added later must be wired manually.
    """
    conftest_path = config["paths"].get("test_conftest_root", "tests/conftest.py")
    output_path = project_root / conftest_path

    if output_path.exists():
        return None

    python_root = config.get("python_root", "")

    database_models_path = config["paths"].get(
        "database_models", "backend/src/database/models"
    )
    database_models_import = path_to_import(
        database_models_path, python_root=python_root
    )

    main_path = config["paths"].get("main", "backend/src/main.py")
    main_dir = str(Path(main_path).parent)
    main_import = path_to_import(main_dir, "main", python_root=python_root)

    engine_path = config["paths"].get("engine", "backend/src/database/engine.py")
    engine_dir = str(Path(engine_path).parent)
    engine_import = path_to_import(engine_dir, "engine", python_root=python_root)

    factories_path = config["paths"].get("factories", "backend/tests/factories")
    factories_import = path_to_import(factories_path, python_root=python_root)

    # Auth scaffolding requires a password pepper (and signs cookies); default
    # both in the generated conftest so the contract suite is green without a
    # manual export. Only emitted when an auth strategy is configured.
    auth_cfg = config.get("auth")
    auth_dict = auth_cfg if isinstance(auth_cfg, dict) else {}
    auth_strategy = auth_dict.get("strategy")
    pepper_env = auth_dict.get("pepper_env", "APP_PASSWORD_PEPPER")

    template = env.get_template("tests/conftest_root.py.j2")
    content = template.render(
        domains=factory_modules if factory_modules is not None else domains,
        database_models_import=database_models_import,
        main_import=main_import,
        engine_import=engine_import,
        factories_import=factories_import,
        auth_strategy=auth_strategy,
        pepper_env=pepper_env,
    )

    return {"path": output_path, "content": content}


def generate_package_init_files(
    config: dict[str, Any], project_root: Path
) -> list[dict[str, Any]]:
    """
    Generate __init__.py files for all package directories.

    Creates empty __init__.py files in all necessary directories
    to make them proper Python packages.
    """
    outputs = []
    paths_config = config.get("paths", {})

    # Collect all directories that need __init__.py
    paths_to_init = []

    # Main source directory
    main_path = paths_config.get("main", "backend/src/main.py")
    src_dir = str(Path(main_path).parent)
    paths_to_init.append(src_dir)

    # Database paths
    db_models = paths_config.get("database_models", "backend/src/database/models")
    paths_to_init.append(db_models)

    # Factories
    factories = paths_config.get("factories", "backend/tests/factories")
    paths_to_init.append(factories)

    # API paths
    api_models = paths_config.get("api_models", "backend/src/api/models")
    paths_to_init.append(api_models)
    api_dir = str(Path(api_models).parent)
    paths_to_init.append(api_dir)

    api_routes = paths_config.get("api_routes", "backend/src/api/routes")
    paths_to_init.append(api_routes)

    # Auth package (when auth.strategy is set, the auth router and CSRF
    # middleware live in the same package and use relative imports).
    if config.get("auth", {}).get("strategy"):
        auth_path = config.get("auth", {}).get("path", "backend/src/auth/router.py")
        paths_to_init.append(str(Path(auth_path).parent))

    # Test paths (including parent directories)
    api_tests = paths_config.get("api_tests", "tests/contract/api")
    paths_to_init.append(api_tests)
    test_dir = api_tests
    while "/" in test_dir:
        test_dir = str(Path(test_dir).parent)
        paths_to_init.append(test_dir)

    # Generate __init__.py for each unique path
    init_content = f"{GENERATED_MARKER}\n"
    for path in sorted(set(paths_to_init)):
        init_path = project_root / path / "__init__.py"
        if not init_path.exists():
            outputs.append({"path": init_path, "content": init_content})

    return outputs


def generate_infrastructure(
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
    domains: list[str],
    extra_deps: list[str] | None = None,
    diff: bool = False,
    dry_run: bool = False,
    route_modules: list[str] | None = None,
    factory_modules: list[str] | None = None,
    has_encrypted_binary: bool = False,
    no_root_files: bool = False,
) -> list[Path]:
    """
    Generate all infrastructure files.

    Returns list of generated file paths.
    """
    print("\n🏗️  Generating infrastructure files...")

    outputs = []

    # Collect all infrastructure outputs
    generators = [
        generate_gitignore(config, env, project_root, no_root_files=no_root_files),
        generate_pyproject(
            config,
            env,
            project_root,
            extra_deps,
            no_root_files=no_root_files,
        ),
        generate_env_example(
            config,
            env,
            project_root,
            has_encrypted_binary=has_encrypted_binary,
            no_root_files=no_root_files,
        ),
        generate_base(config, env, project_root),
        generate_engine(config, env, project_root),
        generate_types(config, env, project_root),
        generate_database_init(config, env, project_root),
        generate_errors(config, env, project_root),
        generate_validators(config, env, project_root),
        generate_utils(config, env, project_root),
        generate_request_limit(config, env, project_root),
        generate_main(
            config,
            env,
            project_root,
            domains,
            route_modules=route_modules,
        ),
        generate_auth_router(config, env, project_root),
        generate_api_key_auth(config, env, project_root),
        generate_csrf(config, env, project_root),
        generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=has_encrypted_binary
        ),
        generate_rate_limit(config, env, project_root),
        generate_test_conftest_root(
            config, env, project_root, domains, factory_modules=factory_modules
        ),
    ]

    for result in generators:
        if result:
            outputs.append(result)

    # Add package init files
    outputs.extend(generate_package_init_files(config, project_root))

    return write_outputs(outputs, diff, dry_run)
