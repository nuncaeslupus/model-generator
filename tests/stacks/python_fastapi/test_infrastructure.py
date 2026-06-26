"""Tests for infrastructure generators (base, engine, main, pyproject, etc.)."""

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml

from model_generator.generators import (
    generate_api_models,
    generate_database_model,
)
from model_generator.generators.infrastructure import (
    generate_base,
    generate_engine,
    generate_env_example,
    generate_errors,
    generate_gitignore,
    generate_infrastructure,
    generate_main,
    generate_pyproject,
    generate_request_limit,
    generate_test_conftest_root,
    generate_types,
    generate_utils,
    generate_validators,
)
from model_generator.utils import get_template_env, load_config
from model_generator.utils.loaders import load_model
from model_generator.validate import load_schema, validate_model


class TestInfrastructureGenerators:
    """Test infrastructure file generators."""

    def test_generate_pyproject(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "pyproject.toml"
        assert "[project]" in result["content"]
        assert "test-project" in result["content"]
        assert "[tool.mutmut]" in result["content"]
        assert "[tool.ruff.lint]" in result["content"]
        assert "[tool.ruff.format]" in result["content"]
        assert "[tool.mypy]" in result["content"]

    def test_generate_pyproject_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        (project_root / "pyproject.toml").write_text("[project]\nname = 'existing'\n")

        result = generate_pyproject(config, env, project_root)
        assert result is None

    def test_generate_pyproject_with_no_root_files_returns_none(
        self, project_env: Any
    ) -> None:
        """--no-root-files suppresses pyproject.toml even in a fresh project."""
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, no_root_files=True)
        assert result is None
        assert not (project_root / "pyproject.toml").exists()

    def test_generate_gitignore_skips_when_exists(self, project_env: Any) -> None:
        """Pre-existing .gitignore must not be overwritten on regeneration."""
        project_root, config, env = project_env
        (project_root / ".gitignore").write_text(".venv/\n")

        result = generate_gitignore(config, env, project_root)
        assert result is None

    def test_generate_gitignore_with_no_root_files_returns_none(
        self, project_env: Any
    ) -> None:
        """--no-root-files suppresses .gitignore even in a fresh project."""
        project_root, config, env = project_env
        result = generate_gitignore(config, env, project_root, no_root_files=True)
        assert result is None
        assert not (project_root / ".gitignore").exists()

    def test_generate_pyproject_contains_runtime_deps(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        for dep in config.get("dependencies", {}).get("runtime", []):
            assert dep in result["content"]

    def test_generate_pyproject_mutmut_targets_logic_files(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "validators.py" in result["content"]
        assert "utils.py" in result["content"]
        assert "constraints.py" in result["content"]

    def test_generate_pyproject_has_package_discovery(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "[tool.setuptools.packages.find]" in result["content"]
        # Derived from main path's parent directory
        main_path = config["paths"].get("main", "backend/src/main.py")
        expected_root = str(Path(main_path).parent)
        assert f'where = ["{expected_root}"]' in result["content"]

    def test_generate_pyproject_no_readme_file_reference(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert 'readme = "README.md"' not in result["content"]
        assert "readme = {text" in result["content"]

    def test_generate_pyproject_merges_extra_deps(self, project_env: Any) -> None:
        project_root, config, env = project_env
        extra = ["bcrypt>=4.0.0", "passlib>=1.7.0"]
        result = generate_pyproject(config, env, project_root, extra_deps=extra)
        assert isinstance(result, dict)

        assert result is not None
        assert "bcrypt>=4.0.0" in result["content"]
        assert "passlib>=1.7.0" in result["content"]
        # Base runtime deps still present
        assert "fastapi" in result["content"]

    def test_generate_pyproject_extra_deps_deduplicated(self, project_env: Any) -> None:
        project_root, config, env = project_env
        base_dep = config["dependencies"]["runtime"][0]
        extra = [base_dep, "bcrypt>=4.0.0"]
        result = generate_pyproject(config, env, project_root, extra_deps=extra)
        assert isinstance(result, dict)

        assert result is not None
        assert result["content"].count(base_dep) == 1

    def test_generate_pyproject_style_defaults_omit_ruff_hardcodes(
        self, project_env: Any
    ) -> None:
        """With no overrides, ruff-default keys are absent; ruff uses its own."""
        project_root, config, env = project_env
        config.pop("style", None)
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        content = result["content"]
        # Keys that match ruff defaults must NOT be emitted (ruff uses its own).
        assert "line-length = " not in content
        assert "target-version = " not in content
        assert "quote-style = " not in content
        assert "indent-style = " not in content
        # The [tool.ruff] section itself is absent when no ruff-level overrides exist.
        for line in content.splitlines():
            assert line.strip() != "[tool.ruff]"
        # Python-version pins are always emitted (not tool defaults — mypy defaults
        # to the runtime Python, and requires-python must be declared).
        assert 'requires-python = ">=3.12"' in content
        assert 'python_version = "3.12"' in content

    def test_generate_pyproject_style_overrides_emitted(self, project_env: Any) -> None:
        """All four style overrides appear verbatim in the generated pyproject.toml."""
        project_root, config, env = project_env
        config["style"] = {
            "line_length": 100,
            "python_version": "3.12",
            "quote_style": "single",
            "indent_style": "tab",
        }
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        content = result["content"]
        assert "[tool.ruff]" in content
        assert "line-length = 100" in content
        assert 'quote-style = "single"' in content
        assert 'indent-style = "tab"' in content
        assert 'requires-python = ">=3.12"' in content
        assert 'python_version = "3.12"' in content
        # target-version is auto-inferred by ruff from requires-python; not emitted.
        assert "target-version = " not in content

    def test_generate_pyproject_python_version_drives_both_pins(
        self, project_env: Any
    ) -> None:
        """Setting only python_version updates requires-python AND mypy python_version,
        without emitting any ruff-level keys."""
        project_root, config, env = project_env
        config["style"] = {"python_version": "3.12"}
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        content = result["content"]
        assert 'requires-python = ">=3.12"' in content
        assert 'python_version = "3.12"' in content
        assert "line-length = " not in content
        assert "target-version = " not in content
        assert "quote-style = " not in content
        assert "indent-style = " not in content

    def test_generate_pyproject_handles_null_style(self, project_env: Any) -> None:
        """`style: null` in YAML parses as None — must not crash the generator."""
        project_root, config, env = project_env
        config["style"] = None
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        # Default python_version still applied, no ruff-level overrides emitted.
        assert 'requires-python = ">=3.12"' in result["content"]
        assert 'python_version = "3.12"' in result["content"]
        assert "line-length = " not in result["content"]

    def test_generate_base(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_base(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "base.py" in str(result["path"])
        assert "Base" in result["content"]

    def test_generate_base_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        output_path = project_root / config["paths"]["base"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_base(config, env, project_root)
        assert result is None

    def test_generate_engine(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_engine(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "engine.py" in str(result["path"])

    def test_generate_engine_production_database_url_guard(
        self, project_env: Any
    ) -> None:
        """TPL-4: engine refuses the SQLite dev fallback under APP_ENV=production."""
        project_root, config, env = project_env
        result = generate_engine(config, env, project_root)
        assert isinstance(result, dict)

        content = result["content"]
        # Guard helper present; raises in production, dev fallback otherwise.
        assert "def _resolve_database_url() -> str:" in content
        assert 'if os.getenv("APP_ENV") == "production":' in content
        assert "DATABASE_URL environment variable must be set in production." in content
        assert 'return "sqlite+aiosqlite:///./app.db"' in content
        assert "DATABASE_URL = _resolve_database_url()" in content

    def test_generate_pyproject_alembic_env_per_file_ignore(
        self, project_env: Any
    ) -> None:
        """TPL-3: emitted pyproject ignores E402 for the alembic env module."""
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)

        content = result["content"]
        assert "[tool.ruff.lint.per-file-ignores]" in content
        # Derived from the configured migrations path (default "alembic").
        migrations_path = config["paths"].get("migrations", "alembic")
        assert f'"{migrations_path}/env.py" = ["E402"]' in content

    def test_generate_env_example(self, project_env: Any) -> None:
        """TPL-9: .env.example manifests the always-present env vars."""
        project_root, config, env = project_env
        result = generate_env_example(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / ".env.example"
        content = result["content"]
        assert "APP_ENV=development" in content
        # DATABASE_URL ships commented so it stays unset by default — keeps the
        # production guard armed while the dev SQLite fallback still works.
        assert "# DATABASE_URL=sqlite+aiosqlite:///./app.db" in content
        assert "\nDATABASE_URL=" not in content
        assert "ALEMBIC_DATABASE_URL" in content
        assert "CORS_ORIGINS" in content
        # No auth section without an auth strategy.
        assert "SESSION_SECRET_KEY" not in content
        assert "FERNET_KEY" not in content

    def test_generate_env_example_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        (project_root / ".env.example").write_text("APP_ENV=keep\n")

        result = generate_env_example(config, env, project_root)
        assert result is None

    def test_generate_env_example_with_no_root_files_returns_none(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_env_example(config, env, project_root, no_root_files=True)
        assert result is None
        assert not (project_root / ".env.example").exists()

    def test_generate_env_example_auth_vars(self, project_env: Any) -> None:
        """Auth + redis rate-limit + encryption add their env vars to the manifest."""
        project_root, config, env = project_env
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "MY_PEPPER",
                "rate_limit": {"backend": "redis"},
            },
        }

        result = generate_env_example(
            config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)

        content = result["content"]
        assert "SESSION_SECRET_KEY=" in content
        assert "MY_PEPPER=" in content
        assert "RATELIMIT_STORAGE_URI" in content
        assert "FERNET_KEY=" in content

    def test_generate_env_example_api_key_vars(self, project_env: Any) -> None:
        """api-key strategy lists API_KEY, not the session secrets."""
        project_root, config, env = project_env
        config = {**config, "auth": {"strategy": "api-key", "key_env": "SVC_TOKEN"}}

        result = generate_env_example(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "SVC_TOKEN=" in content
        assert "api-key" in content
        # Session-only vars must not appear under the api-key strategy.
        assert "SESSION_SECRET_KEY" not in content
        assert "PASSWORD_PEPPER" not in content

    def test_generate_types(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_types(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "types.py" in str(result["path"])
        assert "SqliteNumeric" in result["content"]

    def test_generate_errors(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "errors.py" in str(result["path"])

    def test_generate_validators(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_validators(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "validators.py" in str(result["path"])

    def test_generate_validators_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        output_path = project_root / config["paths"]["validators"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_validators(config, env, project_root)
        assert result is None

    def test_generate_utils(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_utils(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "utils.py" in str(result["path"])

    def test_generate_utils_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        api_dir = Path(config["paths"]["api_models"]).parent
        output_path = project_root / api_dir / "utils.py"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_utils(config, env, project_root)
        assert result is None

    def test_generate_utils_isoformat_utc(self, project_env: Any) -> None:
        """TPL-1: isoformat_utc emits one 'Z' for naive AND tz-aware input."""
        from datetime import datetime

        project_root, config, env = project_env
        result = generate_utils(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "def isoformat_utc(" in content

        ns: dict[str, Any] = {}
        exec(content, ns)  # exercising generated code
        iso = ns["isoformat_utc"]
        aware = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
        naive = datetime(2025, 1, 2, 3, 4, 5)
        # Both must produce a single trailing 'Z' and never the malformed
        # '...+00:00Z' that the old `isoformat() + "Z"` emitted on Postgres.
        assert iso(aware) == "2025-01-02T03:04:05Z"
        assert iso(naive) == "2025-01-02T03:04:05Z"
        assert iso(None) is None

    def test_generate_main(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)

        assert result is not None
        assert "main.py" in str(result["path"])
        assert "FastAPI" in result["content"]
        assert "users" in result["content"]

    def test_generate_main_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        output_path = project_root / config["paths"]["main"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_main(config, env, project_root, domains=["users"])
        assert result is None

    def test_generate_main_no_auth_router_when_strategy_unset(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        # No auth.strategy → no auth-router import or include.
        assert "auth_router" not in result["content"]
        assert "/api/v1/auth" not in result["content"]

    def test_generate_main_with_auth_router(self, project_env_per_entity: Any) -> None:
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        # Default auth.path resolves to backend.src.auth.router.
        assert (
            "from backend.src.auth.router import router as auth_router"
            in result["content"]
        )
        assert (
            'app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])'
            in result["content"]
        )

    def test_generate_main_honors_custom_auth_path(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "path": "src/api/auth.py",
            },
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        assert "from src.api.auth import router as auth_router" in result["content"]

    def test_generate_main_includes_csrf_when_auth_set(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        # CSRF middleware imported from sibling of auth.path
        assert "from backend.src.auth.csrf import CsrfMiddleware" in result["content"]
        # Registered before CORS so CORS stays outermost
        assert "app.add_middleware(CsrfMiddleware)" in result["content"]
        csrf_idx = result["content"].index("app.add_middleware(CsrfMiddleware)")
        cors_idx = result["content"].index("app.add_middleware(\n    CORSMiddleware")
        assert csrf_idx < cors_idx, "CSRF must be added before CORS"

    def test_generate_main_no_csrf_when_strategy_unset(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        assert "CsrfMiddleware" not in result["content"]

    def test_generate_main_includes_rate_limit_when_set(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        # slowapi pieces imported and limiter pulled from sibling of auth.path
        assert "from slowapi import _rate_limit_exceeded_handler" in content
        assert "from slowapi.errors import RateLimitExceeded" in content
        assert "from backend.src.auth.rate_limit import limiter" in content
        # Wired onto the FastAPI app
        assert "app.state.limiter = limiter" in content
        assert (
            "app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)"
            in content
        )

    def test_generate_main_no_rate_limit_when_strategy_unset(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        assert "RateLimitExceeded" not in content
        assert "app.state.limiter" not in content

    def test_generate_main_no_rate_limit_when_disabled(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {"enabled": False},
            },
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        # Auth + CSRF still wired, rate-limit pieces absent
        assert "auth_router" in content
        assert "RateLimitExceeded" not in content
        assert "app.state.limiter" not in content

    def test_generate_main_cors_no_wildcard_default(self, project_env: Any) -> None:
        """CORS default is a concrete dev origin, never the wildcard."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        # No wildcard default, and credentials are never hardcoded on.
        assert 'os.getenv("CORS_ORIGINS", "*")' not in content
        assert "allow_credentials=True" not in content
        assert 'os.getenv("CORS_ORIGINS", "http://localhost:3000")' in content
        # Credentials are decoupled from a wildcard origin (the actual
        # CVE-class misconfiguration): they switch off when "*" is configured.
        assert 'allow_credentials="*" not in cors_origins' in content

    def test_generate_main_cors_methods_and_headers_narrowed(
        self, project_env: Any
    ) -> None:
        """CORS methods/headers are narrowed from the old ["*"] wildcards."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        assert 'allow_methods=["*"]' not in content
        assert 'allow_headers=["*"]' not in content
        assert (
            'allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"]'
            in content
        )
        assert '"Content-Type",' in content

    def test_generate_main_cors_allows_csrf_header_when_auth_set(
        self, project_env_per_entity: Any
    ) -> None:
        """When CSRF middleware is wired, CORS allows its X-CSRF-Token header."""
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        assert '"X-CSRF-Token",' in result["content"]

    def test_generate_main_cors_omits_csrf_header_when_no_auth(
        self, project_env: Any
    ) -> None:
        """No auth/CSRF → the X-CSRF-Token header is absent from the allowlist."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        assert "X-CSRF-Token" not in result["content"]

    def test_generate_test_conftest_root(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_test_conftest_root(
            config, env, project_root, domains=["users"]
        )
        assert isinstance(result, dict)

        assert result is not None
        assert "conftest.py" in str(result["path"])
        assert "client" in result["content"]

    def test_generate_test_conftest_root_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        output_path = project_root / config["paths"]["test_conftest_root"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_test_conftest_root(
            config, env, project_root, domains=["users"]
        )
        assert result is None

    def test_conftest_root_no_auth_env_without_strategy(self, project_env: Any) -> None:
        """TST-2: no env defaults emitted when auth is not configured."""
        project_root, config, env = project_env
        result = generate_test_conftest_root(
            config, env, project_root, domains=["users"]
        )
        assert isinstance(result, dict)
        assert "os.environ.setdefault" not in result["content"]

    def test_conftest_root_defaults_auth_env_when_strategy_set(
        self, project_env: Any
    ) -> None:
        """TST-2: auth env vars default so the suite runs without a manual export."""
        project_root, config, env = project_env
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "APP_PASSWORD_PEPPER"},
        }
        result = generate_test_conftest_root(
            config, env, project_root, domains=["users"]
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert 'os.environ.setdefault("APP_PASSWORD_PEPPER"' in content
        assert 'os.environ.setdefault("SESSION_SECRET_KEY"' in content

    def test_generate_errors_generic_duplicate_message_by_default(
        self, project_env: Any
    ) -> None:
        """P2: the 409 duplicate message omits the parsed DB column name."""
        project_root, config, env = project_env
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Generic message; no column-name extraction.
        assert "with these values already exists" in content
        assert "with this {field} already exists" not in content
        assert 'split("UNIQUE constraint failed:")' not in content
        # Structured shape preserved.
        assert '"error": "duplicate_value"' in content

    def test_generate_errors_exposes_field_when_opted_in(
        self, project_env: Any
    ) -> None:
        """P2: app.expose_integrity_error_fields restores the field-named 409."""
        project_root, config, env = project_env
        config = {
            **config,
            "app": {**config.get("app", {}), "expose_integrity_error_fields": True},
        }
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "with this {field} already exists" in content
        assert 'split("UNIQUE constraint failed:")' in content

    def test_generate_errors_validation_handler_trims_raw_errors(
        self, project_env: Any
    ) -> None:
        """P4: a validation handler summarizes errors to field + message."""
        project_root, config, env = project_env
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "async def validation_exception_handler(" in content
        assert "RequestValidationError" in content
        assert "JSONResponse" in content
        # Trimmed to a field + message summary, structured shape.
        assert '"error": "validation_error"' in content
        assert '"field":' in content
        assert '"message":' in content
        # Never returns the raw exc.errors() list verbatim.
        assert "content=exc.errors()" not in content

    def test_generate_errors_strips_only_leading_locator(
        self, project_env: Any
    ) -> None:
        """Review follow-up: only the leading loc source marker is stripped.

        Filtering every occurrence would mangle a field legitimately named
        'body'/'query'/etc.; only loc[0] is the source marker.
        """
        project_root, config, env = project_env
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "loc[0] in (" in content
        assert "loc[1:]" in content

    def test_generate_errors_handles_non_dict_app_config(
        self, project_env: Any
    ) -> None:
        """Review follow-up: a non-dict app: value doesn't raise AttributeError."""
        project_root, config, env = project_env
        config = {**config, "app": True}
        result = generate_errors(config, env, project_root)
        assert isinstance(result, dict)
        assert "with these values already exists" in result["content"]

    def test_generate_main_registers_validation_handler(self, project_env: Any) -> None:
        """P4: main imports and registers the trimmed validation handler."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        assert "from fastapi.exceptions import RequestValidationError" in content
        assert "import validation_exception_handler" in content
        assert (
            "app.add_exception_handler("
            "RequestValidationError, validation_exception_handler)" in content
        )

    def test_generate_main_wires_request_body_limit(self, project_env: Any) -> None:
        """P3: main imports and installs the body-size middleware by default."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        assert "import RequestBodySizeLimitMiddleware" in content
        assert "RequestBodySizeLimitMiddleware, max_body_bytes=" in content
        # Default generous cap (10 MiB) is emitted.
        assert "max_body_bytes=10485760" in content

    def test_generate_main_no_body_limit_when_disabled(self, project_env: Any) -> None:
        """P3: setting the cap to 0 omits the middleware and its import."""
        project_root, config, env = project_env
        config = {
            **config,
            "app": {**config.get("app", {}), "max_request_body_bytes": 0},
        }
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        assert "RequestBodySizeLimitMiddleware" not in result["content"]

    def test_generate_main_body_limit_before_cors(self, project_env: Any) -> None:
        """P3: body limit is added before CORS so CORS stays outermost."""
        project_root, config, env = project_env
        result = generate_main(config, env, project_root, domains=["users"])
        assert isinstance(result, dict)
        content = result["content"]
        body_idx = content.index(
            "app.add_middleware(\n    RequestBodySizeLimitMiddleware"
        )
        cors_idx = content.index("app.add_middleware(\n    CORSMiddleware")
        assert body_idx < cors_idx, "body-limit must be added before CORS"

    def test_generate_infrastructure_creates_all(self, project_env: Any) -> None:
        project_root, config, env = project_env
        files = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
        )

        assert isinstance(files, list)
        assert len(files) > 0
        file_names = [f.name for f in files]
        assert "base.py" in file_names
        assert "main.py" in file_names
        assert "pyproject.toml" in file_names
        assert ".env.example" in file_names
        assert "request_limit.py" in file_names

    def test_infrastructure_skips_existing(self, project_env: Any) -> None:
        """Infrastructure: some files skip if existing, others always regenerate."""
        project_root, config, env = project_env

        # First run
        files1 = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
        )

        # Second run — should skip some files
        files2 = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
        )

        assert len(files1) > 0
        # All single-file infra generators are bootstrap-only: skipped on the
        # second run so adopter customizations (main router wiring, conftest
        # fixture overrides, domain validators/utils) survive regeneration.
        skipped_infra = {
            "base.py",
            "engine.py",
            "types.py",
            "errors.py",
            "main.py",
            "conftest.py",
            "validators.py",
            "utils.py",
            "request_limit.py",
            ".env.example",
        }
        new_infra = [f for f in files2 if f.name in skipped_infra]
        assert len(new_infra) == 0


class TestRequestLimitGenerator:
    """P3: request-body size-limit ASGI middleware generation."""

    def test_emits_middleware_module_by_default(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_request_limit(config, env, project_root)
        assert isinstance(result, dict)
        assert "request_limit.py" in str(result["path"])
        content = result["content"]
        assert "class RequestBodySizeLimitMiddleware" in content
        assert '"status": 413' in content
        compile(content, "<request_limit>", "exec")

    def test_skips_when_disabled(self, project_env: Any) -> None:
        project_root, config, env = project_env
        config = {
            **config,
            "app": {**config.get("app", {}), "max_request_body_bytes": 0},
        }
        assert generate_request_limit(config, env, project_root) is None

    def test_skips_existing(self, project_env: Any) -> None:
        project_root, config, env = project_env
        api_dir = Path(config["paths"]["api_models"]).parent
        output_path = project_root / api_dir / "request_limit.py"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")
        assert generate_request_limit(config, env, project_root) is None

    def test_uses_deque_for_o1_replay(self, project_env: Any) -> None:
        """Review follow-up: replay buffer is a deque (O(1) popleft), not a list."""
        project_root, config, env = project_env
        result = generate_request_limit(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "from collections import deque" in content
        assert "deque[Message] = deque()" in content
        assert "buffered.popleft()" in content
        assert "buffered.pop(0)" not in content

    def test_returns_on_client_disconnect(self, project_env: Any) -> None:
        """Review follow-up: disconnect mid-body returns without invoking the app."""
        project_root, config, env = project_env
        result = generate_request_limit(config, env, project_root)
        assert isinstance(result, dict)
        assert 'elif message["type"] == "http.disconnect":' in result["content"]

    def test_handles_non_dict_app_config(self, project_env: Any) -> None:
        """Review follow-up: a non-dict app: value falls back, no AttributeError."""
        project_root, config, env = project_env
        config = {**config, "app": "not-a-dict"}
        # Default cap (>0) still applies -> middleware still emitted, no crash.
        assert isinstance(generate_request_limit(config, env, project_root), dict)

    def test_negative_content_length_treated_as_invalid(
        self, project_env: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense-in-depth: a negative Content-Length must not bypass the cap.

        ``int(b"-100")`` used to be returned verbatim, so ``-100 > max`` was
        False and the request streamed through uncounted. Now a negative length
        is invalid (``None``), so the request falls through to the chunked
        byte-counting path and is still rejected on overflow.
        """
        import asyncio
        import types as types_module

        project_root, config, env = project_env
        result = generate_request_limit(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Template-level guard: a negative declared length is invalid.
        assert "if n < 0:" in content

        # Runtime probe: drive the middleware with a lying Content-Length: -100
        # and an oversized body; the cap must still produce a 413. starlette is
        # not a generator dependency, so stub its type-only import (auto-undone
        # by the monkeypatch fixture).
        starlette = types_module.ModuleType("starlette")
        starlette_types = types_module.ModuleType("starlette.types")
        for name in ("ASGIApp", "Message", "Receive", "Scope", "Send"):
            setattr(starlette_types, name, Any)
        starlette.types = starlette_types  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "starlette", starlette)
        monkeypatch.setitem(sys.modules, "starlette.types", starlette_types)

        ns: dict[str, Any] = {}
        exec(content, ns)
        middleware_cls = ns["RequestBodySizeLimitMiddleware"]

        async def app(scope: Any, receive: Any, send: Any) -> None:
            raise AssertionError("oversized body reached the app")

        mw = middleware_cls(app, max_body_bytes=10)
        scope = {"type": "http", "headers": [(b"content-length", b"-100")]}

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"x" * 100, "more_body": False}

        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        asyncio.run(mw(scope, receive, send))

        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 413

    def test_duplicate_content_length_treated_as_invalid(
        self, project_env: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense-in-depth: duplicate Content-Length headers must not bypass the cap.

        Returning the first header's value lets a smuggling pair (small + large)
        slip an oversized body past a guard keyed on the small one if a
        downstream server honors the other. Two Content-Length headers are now
        treated as invalid, forcing the chunked byte-counting path → 413.
        """
        import asyncio
        import types as types_module

        project_root, config, env = project_env
        result = generate_request_limit(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]

        starlette = types_module.ModuleType("starlette")
        starlette_types = types_module.ModuleType("starlette.types")
        for name in ("ASGIApp", "Message", "Receive", "Scope", "Send"):
            setattr(starlette_types, name, Any)
        starlette.types = starlette_types  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "starlette", starlette)
        monkeypatch.setitem(sys.modules, "starlette.types", starlette_types)

        ns: dict[str, Any] = {}
        exec(content, ns)
        middleware_cls = ns["RequestBodySizeLimitMiddleware"]

        async def app(scope: Any, receive: Any, send: Any) -> None:
            raise AssertionError("oversized body reached the app")

        mw = middleware_cls(app, max_body_bytes=10)
        # Smuggling pair: a small declared length the guard would accept, plus a
        # second header. The middleware must distrust both and count bytes.
        scope = {
            "type": "http",
            "headers": [
                (b"content-length", b"5"),
                (b"content-length", b"100"),
            ],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"x" * 100, "more_body": False}

        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        asyncio.run(mw(scope, receive, send))

        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 413


@pytest.fixture
def project_env_with_python_root(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
    """project_env variant with python_root: 'src' and paths under src/.

    Mirrors a standard src-layout where src/ is on sys.path, not a package.
    Used by the python_root integration test to verify the filter threads
    end-to-end from .model-generator.yaml → load_config → get_template_env
    → Jinja filter → generated file contents.
    """
    config_data = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
        "python_root": "src",
        "generation": {"layout": "per-domain"},
        "paths": {
            "database_models": "src/database/models",
            "factories": "src/database/models/factories",
            "api_models": "src/api/models",
            "api_routes": "src/api/routes",
            "api_tests": "tests/api",
            "base": "src/database/models/base.py",
            "engine": "src/database/engine.py",
            "main": "src/main.py",
            "errors": "src/api/errors.py",
            "validators": "src/api/validators.py",
            "test_conftest_root": "tests/conftest.py",
            "enums": "src/database/models/enums.py",
            "constraints": "src/database/models/constraints.py",
            "migrations": "alembic",
        },
    }

    config_path = tmp_path / ".model-generator.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        config = load_config("python-fastapi")
        env = get_template_env("python-fastapi", config=config)
    finally:
        os.chdir(original_cwd)

    return tmp_path, config, env


class TestPythonRootIntegration:
    """End-to-end: python_root in config flows through to generated imports.

    test_template_utils.py covers path_to_import() and the filter closure in
    isolation. This test guards against future regressions where someone
    adds a new absolute-import site in a template without piping the value
    through the path_to_import filter — model.py.j2's `types` import is the
    canonical site to probe in the database-model surface.
    """

    def test_database_model_strips_python_root_from_types_import(
        self,
        minimal_model: dict[str, Any],
        project_env_with_python_root: Any,
    ) -> None:
        project_root, config, env = project_env_with_python_root
        result = generate_database_model(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        content = result["content"]
        # paths.database_models="src/database/models" + python_root="src" →
        # types-module parent="src/database" → import base="database".
        assert "from database.types import" in content
        assert "from src.database.types import" not in content


class TestSchemaInvalidSpecHandling:
    """TST-6: characterize how the pipeline treats schema-invalid-but-plausible
    specs.

    ``load_model`` is deliberately warn-only (it supports partial/WIP specs),
    so an invalid spec flows on to the generators. The ``model-val`` validator
    is the actual gate. These tests pin both halves of that contract so a
    regression — load_model starting to ``sys.exit``, or the validator going
    silent — is caught.
    """

    def _write(self, tmp_path: Path, spec: dict[str, Any]) -> Path:
        path = tmp_path / "bad.model.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    # Plausible spec with a typo'd field type — passes a human eyeball, fails
    # the schema's `type` enum.
    _UNKNOWN_TYPE_SPEC: ClassVar[dict[str, Any]] = {
        "domain": "shop",
        "entities": {
            "Widget": {
                "table": "widgets",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "price": {"type": "frobnicate", "required": True},
                },
            }
        },
    }

    # Plausible spec missing a primary key — a semantic, not schema, violation.
    _NO_PK_SPEC: ClassVar[dict[str, Any]] = {
        "domain": "shop",
        "entities": {
            "Widget": {
                "table": "widgets",
                "fields": {
                    "name": {"type": "text", "max_length": 50, "required": True},
                },
            }
        },
    }

    def test_load_model_is_warn_only_on_unknown_field_type(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        path = self._write(tmp_path, self._UNKNOWN_TYPE_SPEC)
        # Must NOT sys.exit — load_model tolerates partial/WIP specs.
        data = load_model(path)
        out = capsys.readouterr().out
        assert "validation warning" in out
        assert "frobnicate" in out
        # The invalid spec is returned intact (it flows on to the generators).
        assert data["entities"]["Widget"]["fields"]["price"]["type"] == "frobnicate"

    def test_validator_flags_unknown_field_type(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, self._UNKNOWN_TYPE_SPEC)
        errors = validate_model(path, load_schema())
        # The gate catches what load_model only warned about.
        assert errors
        assert any("frobnicate" in e for e in errors)

    def test_validator_flags_missing_primary_key(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, self._NO_PK_SPEC)
        errors = validate_model(path, load_schema())
        assert any("primary key" in e.lower() for e in errors)

    def test_load_model_tolerates_missing_primary_key(self, tmp_path: Path) -> None:
        """A missing PK is a semantic gap the schema doesn't enforce, so
        load_model returns it silently — proving the generators are reachable
        with such a spec (which is exactly why model-val must be run first)."""
        path = self._write(tmp_path, self._NO_PK_SPEC)
        data = load_model(path)
        assert "Widget" in data["entities"]


class TestGeneratedOutputLintClean:
    """TST-7: the emitted source is lint-clean after the generator's own
    quality pass.

    The "exemplary, mypy-strict" claim is otherwise only checked by the
    out-of-tree smoke job. Here we run the SAME ``ruff`` select/ignore set the
    generated ``pyproject.toml`` ships, apply the auto-fix pass the generator
    performs on every write (import sorting / formatting), then assert no
    residual — i.e. no *non-auto-fixable* lint (B007/F841/UP…) slipped into a
    template.
    """

    # Mirrors infrastructure/pyproject.toml.j2's [tool.ruff.lint] config.
    _SELECT = "E,W,F,I,B,C4,UP"
    _IGNORE = "E501,B008,B904,W191"

    def _ruff(
        self, args: list[str], files: list[str]
    ) -> "subprocess.CompletedProcess[str]":
        return subprocess.run(
            [
                "ruff",
                *args,
                "--no-cache",
                "--select",
                self._SELECT,
                "--ignore",
                self._IGNORE,
                *files,
            ],
            capture_output=True,
            text=True,
        )

    @pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
    def test_generated_models_are_lint_clean_after_fix(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        written: list[str] = []
        for generator in (generate_database_model, generate_api_models):
            generated = generator(multi_entity_model, config, env, project_root)
            assert generated is not None
            entries = generated if isinstance(generated, list) else [generated]
            for entry in entries:
                path = entry["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(entry["content"], encoding="utf-8")
                written.append(str(path))

        assert written, "expected the generator to emit at least one file"

        # The generator's own quality pass: ruff --fix then ruff format.
        self._ruff(["check", "--fix"], written)
        fmt = subprocess.run(
            ["ruff", "format", *written], capture_output=True, text=True
        )
        assert fmt.returncode == 0, f"ruff format failed:\n{fmt.stderr}"

        # No residual lint — anything left here is NOT auto-fixable and is a
        # real template defect.
        check = self._ruff(["check"], written)
        assert check.returncode == 0, (
            "generated output is not lint-clean after the standard quality "
            f"pass:\n{check.stdout}"
        )


class TestPyprojectAsyncioMode:
    """TPL-13: asyncio_mode must not be emitted — the generated tests are sync."""

    def test_asyncio_mode_absent_from_pyproject(self, project_env: Any) -> None:
        """asyncio_mode = 'auto' must not appear; it needs pytest-asyncio which
        is not in the generated dev deps, and the contract tests are sync."""
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)
        assert "asyncio_mode" not in result["content"]
