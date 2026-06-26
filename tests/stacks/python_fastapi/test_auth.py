"""Tests for auth router, API-key, CSRF, rate limit, and auth validation."""

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.utils import load_config


class TestValidateAuthConfig:
    """Test the _validate_auth_config helper."""

    def test_no_scope_passes_without_auth_config(self) -> None:
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Item": {"api": {"enabled": True}}}}
        _validate_auth_config(model, config={})  # Should not exit

    def test_scope_with_auth_config_passes(self) -> None:
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        config = {"auth": {"dependency_path": "x.y.z"}}
        _validate_auth_config(model, config)  # Should not exit

    def test_scope_without_auth_config_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_config(model, config={})
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "Widget" in out
        assert "auth.dependency_path" in out
        assert "api.scope" in out

    def test_scope_with_dotless_auth_path_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """auth.dependency_path must include a module separator."""
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        config = {"auth": {"dependency_path": "no_dots_here"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_config(model, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "no_dots_here" in out
        assert "dotted path" in out


class TestValidateAuthStrategy:
    """Test the _validate_auth_strategy helper."""

    def _user_model(self) -> dict[str, Any]:
        return {
            "entities": {
                "User": {
                    "fields": {
                        "password_hash": {"type": "text"},
                        "username": {"type": "text"},
                        "email": {"type": "text"},
                        "last_login_at": {"type": "datetime"},
                    }
                }
            }
        }

    def test_no_strategy_passes(self) -> None:
        from model_generator.generate import _validate_auth_strategy

        _validate_auth_strategy([self._user_model()], config={})

    def test_bcrypt_session_with_user_and_pepper_passes(self) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        _validate_auth_strategy([self._user_model()], config)

    def test_api_key_strategy_needs_no_user_or_pepper(self) -> None:
        """api-key is self-contained: no User entity, no pepper required."""
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "api-key"}}
        # No User entity in the models — must still pass.
        _validate_auth_strategy([{"entities": {"Item": {"fields": {}}}}], config)

    def test_api_key_strategy_listed_as_valid(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "magic-jwt"}}
        with pytest.raises(SystemExit):
            _validate_auth_strategy([self._user_model()], config)
        out = capsys.readouterr().out
        assert "api-key" in out

    def test_api_key_blank_key_env_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "api-key", "key_env": "   "}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        assert "key_env" in capsys.readouterr().out

    def test_unknown_strategy_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "magic-jwt", "pepper_env": "X"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "magic-jwt" in out
        assert "bcrypt-session" in out

    def test_missing_pepper_env_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "pepper_env" in out

    def test_missing_user_entity_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        models: list[dict[str, Any]] = [{"entities": {"Item": {"fields": {}}}}]
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy(models, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "User" in out

    def test_user_without_password_hash_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        models = [{"entities": {"User": {"fields": {"username": {"type": "text"}}}}}]
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy(models, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "password_hash" in out

    def test_per_domain_layout_with_strategy_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_strategy

        config = {
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
            "generation": {"layout": "per-domain"},
        }
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "per-entity" in out
        assert "per-domain" in out

    @pytest.mark.parametrize("missing", ["username", "email", "last_login_at"])
    def test_user_missing_router_field_exits(
        self, capsys: pytest.CaptureFixture[str], missing: Any
    ) -> None:
        """Router uses username/email/last_login_at; validator must require each."""
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        model = self._user_model()
        del model["entities"]["User"]["fields"][missing]
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([model], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert missing in out


class TestValidateAuthScopeCoverage:
    """Tests for _validate_auth_scope_coverage."""

    def test_no_auth_strategy_passes(self) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [{"entities": {"Widget": {"api": {"enabled": True}}}}]
        _validate_auth_scope_coverage(models, config={})  # must not print/exit

    def test_auth_with_scoped_entity_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [
            {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        ]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "bcrypt-session"}})
        assert capsys.readouterr().out == ""

    def test_auth_no_scoped_entities_warns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [{"entities": {"Widget": {"api": {"enabled": True}}}}]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "bcrypt-session"}})
        out = capsys.readouterr().out
        assert "Warning" in out
        assert "api.scope" in out
        assert "Widget" in out

    def test_no_api_enabled_entities_no_warning(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [{"entities": {"Widget": {"api": {"enabled": False}}}}]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "bcrypt-session"}})
        assert capsys.readouterr().out == ""

    def test_mixed_scoped_unscoped_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [
            {
                "entities": {
                    "Widget": {"api": {"scope": {"owner_field": "user_id"}}},
                    "Tag": {"api": {"enabled": True}},
                }
            }
        ]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "bcrypt-session"}})
        assert capsys.readouterr().out == ""

    def test_api_key_with_require_auth_passes(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_auth_scope_coverage

        models = [{"entities": {"Widget": {"api": {"require_auth": True}}}}]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "api-key"}})
        assert capsys.readouterr().out == ""

    def test_api_key_no_protected_entities_warns(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Under api-key the warning checks require_auth, not scope."""
        from model_generator.generate import _validate_auth_scope_coverage

        models = [{"entities": {"Widget": {"api": {"enabled": True}}}}]
        _validate_auth_scope_coverage(models, {"auth": {"strategy": "api-key"}})
        out = capsys.readouterr().out
        assert "Warning" in out
        assert "require_auth" in out
        assert "Widget" in out


class TestLoadConfigAuthDependency:
    """load_config auto-wires auth.dependency_path per strategy."""

    def _write_and_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, auth: dict[str, Any]
    ) -> dict[str, Any]:
        (tmp_path / ".model-generator.yaml").write_text(
            yaml.dump({"stack": "python-fastapi", "auth": auth})
        )
        monkeypatch.chdir(tmp_path)
        return load_config("python-fastapi")

    def test_api_key_infers_require_api_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded = self._write_and_load(tmp_path, monkeypatch, {"strategy": "api-key"})
        assert loaded["auth"]["dependency_path"].endswith(".api_key.require_api_key")

    def test_session_infers_get_current_user(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded = self._write_and_load(
            tmp_path, monkeypatch, {"strategy": "bcrypt-session", "pepper_env": "X"}
        )
        assert loaded["auth"]["dependency_path"].endswith(".router.get_current_user")

    def test_explicit_dependency_path_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded = self._write_and_load(
            tmp_path,
            monkeypatch,
            {"strategy": "api-key", "dependency_path": "my.custom.dep"},
        )
        assert loaded["auth"]["dependency_path"] == "my.custom.dep"


class TestAuthRouterGenerator:
    """Smoke-test the §12 auth_router emission helper."""

    def _project_config(self) -> dict[str, Any]:
        return {"project": {"name": "Test"}}

    def test_returns_none_when_strategy_unset(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        result = generate_auth_router(config, env, project_root)
        assert result is None

    def test_emits_router_when_strategy_set(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }

        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "backend/src/auth/router.py"
        content = result["content"]
        # All six endpoints emitted
        assert '@router.post(\n    "/register"' in content
        assert '@router.post("/login"' in content
        assert '@router.post("/logout"' in content
        assert '@router.post("/forgot-password"' in content
        assert '@router.post("/reset-password"' in content
        assert '@router.post("/change-password"' in content
        # Bcrypt + HMAC pepper present
        assert "import bcrypt" in content
        assert "bcrypt.hashpw(" in content
        assert "hmac.new(pepper.encode(), password.encode(), hashlib.sha256)" in content
        # Pepper env name baked in from config
        assert '_PEPPER_ENV = "PEPPER"' in content
        # The template must produce syntactically valid Python (ast.parse catches
        # malformed Jinja output such as unclosed brackets or bad indentation that
        # string-match assertions cannot detect).

        ast.parse(content)

    def test_emits_per_entity_imports(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "from src.database.models.user import User" in content
        assert "from src.database.models.user_session import UserSession" in content
        assert "from src.database.engine import get_session" in content

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        # Adopter has customized the router; bootstrap helper must skip.
        auth_file = project_root / "backend/src/auth/router.py"
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text("# adopter has customized this\n")

        result = generate_auth_router(config, env, project_root)
        assert result is None

    def test_honors_custom_auth_path(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "path": "src/auth/api.py",
            },
        }

        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        assert result is not None
        assert result["path"] == project_root / "src/auth/api.py"

    def test_wires_csrf_cookies_in_login_logout(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Relative import keeps router and csrf in the same package
        assert "from .csrf import clear_csrf_cookie, set_csrf_cookie" in content
        # Login mints the CSRF cookie alongside the session cookie
        assert "set_csrf_cookie(response)" in content
        # Logout clears it alongside the session cookie
        assert "clear_csrf_cookie(response)" in content

    def test_emits_rate_limit_decorators_by_default(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Sibling import for the limiter and limit constants
        assert (
            "from .rate_limit import FORGOT_LIMIT, LOGIN_LIMIT, REGISTER_LIMIT, limiter"
            in content
        )
        # Decorators wrap the three abusable endpoints
        assert "@limiter.limit(REGISTER_LIMIT)" in content
        assert "@limiter.limit(LOGIN_LIMIT)" in content
        assert "@limiter.limit(FORGOT_LIMIT)" in content
        # change-password is authenticated → not rate-limited
        change_block = content.split('@router.post("/change-password"')[1]
        assert "@limiter.limit" not in change_block
        # register and forgot pick up the request: Request param the
        # decorator needs to extract the IP for the keyfunc.
        register_block = content.split("async def register(")[1].split(") ->")[0]
        assert "request: Request" in register_block
        forgot_block = content.split("async def forgot_password(")[1].split(") ->")[0]
        assert "request: Request" in forgot_block

    def test_no_rate_limit_when_disabled(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {"enabled": False},
            },
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "@limiter.limit" not in content
        assert "from .rate_limit" not in content
        # register and forgot drop the unused request: Request param
        register_block = content.split("async def register(")[1].split(") ->")[0]
        assert "request: Request" not in register_block
        forgot_block = content.split("async def forgot_password(")[1].split(") ->")[0]
        assert "request: Request" not in forgot_block

    def test_resolves_session_secret_via_helper(
        self, project_env_per_entity: Any
    ) -> None:
        """Production must fail-closed when SESSION_SECRET_KEY is missing."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "def _resolve_session_secret() -> str:" in content
        assert 'os.environ.get("APP_ENV") == "production"' in content
        assert "SESSION_SECRET_KEY environment variable must be set" in content
        # The dev fallback string still exists for non-production use.
        assert '"DEV-ONLY-CHANGE-ME-IN-PRODUCTION"' in content
        # Serializers are initialized via the helper, not the inline get-with-default.
        assert (
            "URLSafeTimedSerializer(\n    _resolve_session_secret(), salt=" in content
        )

    def test_password_reset_email_is_async(self, project_env_per_entity: Any) -> None:
        """Email send must be async to avoid blocking the event loop."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "async def _send_password_reset_email(" in content
        # forgot_password must await it
        assert "await _send_password_reset_email(user.email, token)" in content

    def test_reset_and_change_revoke_sessions(
        self, project_env_per_entity: Any
    ) -> None:
        """SEC-2: rotating a password must deactivate the user's sessions."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "from sqlalchemy import select, update" in content
        # reset-password AND change-password each deactivate the user's sessions
        # (logout uses an attribute set, not a bulk update, so isn't counted).
        assert content.count("update(UserSession)") == 2
        assert content.count(".values(is_active=False)") == 2

    def test_reset_token_is_single_use(self, project_env_per_entity: Any) -> None:
        """SEC-3: reset token is bound to the current password-hash fingerprint."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "def _token_fingerprint(password_hash: str) -> str:" in content
        # forgot-password binds the fingerprint into the signed token...
        assert '"pw": _token_fingerprint(user.password_hash)' in content
        # ...and reset-password rejects a token whose fingerprint no longer matches.
        assert 'fingerprint = data.get("pw")' in content

    def test_session_and_reset_tokens_use_separate_salts(
        self, project_env_per_entity: Any
    ) -> None:
        """SEC-4: cookie and reset-token serializers are salt-separated."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Two distinct serializers with distinct salts.
        assert "_session_serializer = URLSafeTimedSerializer(" in content
        assert "_reset_serializer = URLSafeTimedSerializer(" in content
        assert 'salt="session-cookie"' in content
        assert 'salt="password-reset"' in content
        # Session paths use the session serializer; the bare `_serializer` is gone.
        assert "_session_serializer.dumps(session_token)" in content
        assert "\n_serializer = " not in content
        assert "= _serializer." not in content
        # Reset paths use the reset serializer for both mint and verify.
        assert "_reset_serializer.dumps(" in content
        assert "_reset_serializer.loads(" in content

    def test_forgot_password_has_no_enumeration_oracle(
        self, project_env_per_entity: Any
    ) -> None:
        """SEC-5: forgot-password returns uniformly; missing hook is logged, not 501."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # Module logger is wired.
        assert "import logging" in content
        assert "logger = logging.getLogger(__name__)" in content
        # The forgot-password body raises no status that leaks account existence.
        forgot_block = content.split("async def forgot_password(")[1].split(
            "@router.post"
        )[0]
        assert "501" not in forgot_block
        assert "HTTP_501_NOT_IMPLEMENTED" not in forgot_block
        # The missing-config gap is surfaced via a log warning instead.
        assert "except NotImplementedError:" in forgot_block
        assert "logger.warning(" in forgot_block
        # ANY send failure (SMTP/network/etc.) is swallowed too — a 500 would
        # only fire when the user exists, reintroducing the enumeration oracle.
        assert "except Exception:" in forgot_block
        assert "logger.exception(" in forgot_block

    def test_auth_router_is_syntactically_valid_with_custom_path(
        self, project_env_per_entity: Any
    ) -> None:
        """TST-3: auth_router with a non-default auth path must parse cleanly.

        Exercises the import-path derivation code path that differs from the
        default backend/src layout, so a template regression in that branch
        would be caught here rather than only in the smoke-example CI job.
        """

        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "MY_PEPPER",
                "path": "src/api/auth.py",
                "cookie_name": "sid",
            },
        }
        result = generate_auth_router(config, env, project_root)
        assert isinstance(result, dict)
        ast.parse(result["content"])


class TestApiKeyAuthGenerator:
    """The static-API-key auth strategy (auth.strategy: api-key)."""

    def _project_config(self) -> dict[str, Any]:
        return {"project": {"name": "Test"}}

    def test_returns_none_when_strategy_unset(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        assert generate_api_key_auth(config, env, project_root) is None

    def test_returns_none_for_session_strategy(
        self, project_env_per_entity: Any
    ) -> None:
        """api-key generator must not fire for the session strategy."""
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        assert generate_api_key_auth(config, env, project_root) is None

    def test_emits_dependency_when_strategy_api_key(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "api-key"}}
        result = generate_api_key_auth(config, env, project_root)
        assert isinstance(result, dict)
        assert result["path"] == project_root / "backend/src/auth/api_key.py"
        content = result["content"]
        assert "async def require_api_key(" in content
        # Default env var name + header, constant-time compare, prod guard.
        assert '_KEY_ENV = "API_KEY"' in content
        assert 'alias="X-API-Key"' in content
        assert "secrets.compare_digest(" in content
        assert 'os.environ.get("APP_ENV") == "production"' in content
        # Env value is stripped: stray deploy whitespace can't cause silent auth
        # failures, and a whitespace-only value is treated as unset.
        assert 'os.environ.get(_KEY_ENV, "").strip()' in content
        # No session machinery leaks in.
        assert "bcrypt" not in content
        assert "URLSafeTimedSerializer" not in content

    def test_honors_custom_key_env_and_header(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "api-key",
                "key_env": "SERVICE_TOKEN",
                "header_name": "X-Service-Token",
            },
        }
        result = generate_api_key_auth(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert '_KEY_ENV = "SERVICE_TOKEN"' in content
        assert 'alias="X-Service-Token"' in content
        # Header param identifier is the snake_cased header name.
        assert "x_service_token: str | None = Header(" in content

    def test_pathological_header_name_yields_valid_identifier(
        self, project_env_per_entity: Any
    ) -> None:
        """A header with spaces/dots/symbols must not break the generated code."""

        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "api-key", "header_name": "1 Weird.Header!"},
        }
        result = generate_api_key_auth(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        # The real header name is preserved in the alias...
        assert 'alias="1 Weird.Header!"' in content
        # ...and the param is a valid identifier, so the module parses cleanly.
        ast.parse(content)
        assert "_1_weird_header_: str | None = Header(" in content

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "api-key"}}
        dep_file = project_root / "backend/src/auth/api_key.py"
        dep_file.parent.mkdir(parents=True, exist_ok=True)
        dep_file.write_text("# adopter customized\n")
        assert generate_api_key_auth(config, env, project_root) is None

    def test_session_generators_skip_api_key_strategy(
        self, project_env_per_entity: Any
    ) -> None:
        """Router / CSRF / rate-limit are session-only — silent under api-key."""
        from model_generator.generators.infrastructure import (
            generate_auth_router,
            generate_csrf,
            generate_rate_limit,
        )

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "api-key"}}
        assert generate_auth_router(config, env, project_root) is None
        assert generate_csrf(config, env, project_root) is None
        assert generate_rate_limit(config, env, project_root) is None


class TestCsrfGenerator:
    """Smoke-test the §12.4 CSRF middleware emission helper."""

    def test_returns_none_when_strategy_unset(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        assert generate_csrf(config, env, project_root) is None

    def test_emits_csrf_when_strategy_set(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_csrf(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "backend/src/auth/csrf.py"
        content = result["content"]
        # Core API surface
        assert "class CsrfMiddleware(BaseHTTPMiddleware)" in content
        assert "def set_csrf_cookie(" in content
        assert "def clear_csrf_cookie(" in content
        assert 'CSRF_COOKIE_NAME = "csrf_token"' in content
        assert 'CSRF_HEADER_NAME = "X-CSRF-Token"' in content
        # Session-cookie gating: middleware skips CSRF when no session cookie
        # is present (standard double-submit-cookie semantics — there is
        # nothing to forge for unauthenticated requests).
        assert 'SESSION_COOKIE_NAME = "session_id"' in content
        assert "SESSION_COOKIE_NAME in request.cookies" in content
        # Mutating-method gating + constant-time compare
        assert '"POST", "PUT", "PATCH", "DELETE"' in content
        assert "secrets.compare_digest" in content
        # Exempt paths cover unauthenticated mutating endpoints + token-auth reset
        assert "/api/v1/auth/register" in content
        assert "/api/v1/auth/login" in content
        assert "/api/v1/auth/forgot-password" in content
        assert "/api/v1/auth/reset-password" in content
        # TST-3: CSRF is the other highest-stakes output; parse it too.

        ast.parse(content)

    def test_session_cookie_name_follows_auth_cookie_name(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "cookie_name": "sid",
            },
        }

        result = generate_csrf(config, env, project_root)
        assert isinstance(result, dict)
        assert result is not None
        # Custom cookie_name flows from config into SESSION_COOKIE_NAME so the
        # gating check matches what the auth router actually sets.
        assert 'SESSION_COOKIE_NAME = "sid"' in result["content"]

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        # Adopter has customized csrf.py; bootstrap helper must skip.
        csrf_file = project_root / "backend/src/auth/csrf.py"
        csrf_file.parent.mkdir(parents=True, exist_ok=True)
        csrf_file.write_text("# adopter has customized this\n")

        assert generate_csrf(config, env, project_root) is None

    def test_csrf_path_follows_custom_auth_path(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "path": "src/api/auth.py",
            },
        }

        result = generate_csrf(config, env, project_root)
        assert isinstance(result, dict)
        # csrf.py is sibling of auth.path
        assert result["path"] == project_root / "src/api/csrf.py"

    def test_csrf_is_syntactically_valid_with_custom_cookie_name(
        self, project_env_per_entity: Any
    ) -> None:
        """TST-3: CSRF with a non-default cookie_name must parse cleanly.

        A custom cookie name is baked into SESSION_COOKIE_NAME and the exempt-
        path prefix; verifying this code path parses ensures the interpolation
        did not break the surrounding Python syntax.
        """

        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "cookie_name": "my_session",
                "path": "src/api/auth.py",
            },
        }
        result = generate_csrf(config, env, project_root)
        assert isinstance(result, dict)
        ast.parse(result["content"])


class TestRateLimitGenerator:
    """Smoke-test the §12.5 rate-limit module emission helper."""

    def test_returns_none_when_strategy_unset(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        assert generate_rate_limit(config, env, project_root) is None

    def test_returns_none_when_explicitly_disabled(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {"enabled": False},
            },
        }
        assert generate_rate_limit(config, env, project_root) is None

    def test_emits_module_with_default_limits(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_rate_limit(config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "backend/src/auth/rate_limit.py"
        content = result["content"]
        # Default limits from the §12 plan
        assert 'LOGIN_LIMIT = "5/minute"' in content
        assert 'REGISTER_LIMIT = "3/hour"' in content
        assert 'FORGOT_LIMIT = "3/hour"' in content
        # Memory backend by default
        assert '"memory://"' in content
        # IP-based key, env override hook
        assert "from slowapi import Limiter" in content
        assert "from slowapi.util import get_remote_address" in content
        assert "limiter = Limiter(key_func=get_remote_address" in content
        assert 'os.environ.get("RATELIMIT_STORAGE_URI"' in content

    def test_uses_configured_limits(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {
                    "login": "10/minute",
                    "register": "5/hour",
                    "forgot": "2/hour",
                },
            },
        }
        result = generate_rate_limit(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert 'LOGIN_LIMIT = "10/minute"' in content
        assert 'REGISTER_LIMIT = "5/hour"' in content
        assert 'FORGOT_LIMIT = "2/hour"' in content

    def test_uses_redis_default_uri_when_backend_redis(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {"backend": "redis"},
            },
        }
        result = generate_rate_limit(config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert (
            'os.environ.get("RATELIMIT_STORAGE_URI", "redis://localhost:6379/0")'
            in content
        )
        # Memory default is replaced, not just appended.
        assert 'os.environ.get("RATELIMIT_STORAGE_URI", "memory://")' not in content

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        rl_file = project_root / "backend/src/auth/rate_limit.py"
        rl_file.parent.mkdir(parents=True, exist_ok=True)
        rl_file.write_text("# adopter customized\n")

        assert generate_rate_limit(config, env, project_root) is None

    def test_module_path_follows_custom_auth_path(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "path": "src/api/auth.py",
            },
        }
        result = generate_rate_limit(config, env, project_root)
        assert isinstance(result, dict)
        # rate_limit.py is sibling of auth.path
        assert result["path"] == project_root / "src/api/rate_limit.py"

    def test_documents_reverse_proxy_ip_caveat(
        self, project_env_per_entity: Any
    ) -> None:
        """SEC-7: the socket-peer-IP-behind-a-proxy footgun is documented."""
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_rate_limit(config, env, project_root)
        assert isinstance(result, dict)
        lowered = result["content"].lower()
        assert "x-forwarded-for" in lowered
        assert "proxy" in lowered


class TestComputeAuthExtra:
    """Test the _compute_auth_extra helper (§12 review #2)."""

    def test_no_strategy_returns_empty(self) -> None:
        from model_generator.generate import _compute_auth_extra

        assert _compute_auth_extra({}) == []
        assert _compute_auth_extra({"auth": {}}) == []

    def test_strategy_set_includes_bcrypt_itsdangerous_email_validator(self) -> None:
        from model_generator.generate import _compute_auth_extra

        extra = _compute_auth_extra(
            {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        )
        # bcrypt is required — the auth router imports bcrypt directly.
        assert "bcrypt>=4.0.0" in extra
        assert "itsdangerous>=2.0" in extra
        assert "email-validator>=2.0" in extra
        # slowapi is default-on
        assert "slowapi>=0.1.9" in extra
        # redis is opt-in
        assert not any(dep.startswith("redis") for dep in extra)

    def test_rate_limit_disabled_omits_slowapi(self) -> None:
        from model_generator.generate import _compute_auth_extra

        extra = _compute_auth_extra(
            {
                "auth": {
                    "strategy": "bcrypt-session",
                    "rate_limit": {"enabled": False},
                }
            }
        )
        assert "bcrypt>=4.0.0" in extra
        assert not any(dep.startswith("slowapi") for dep in extra)
        assert not any(dep.startswith("redis") for dep in extra)

    def test_redis_backend_adds_redis_dep(self) -> None:
        from model_generator.generate import _compute_auth_extra

        extra = _compute_auth_extra(
            {
                "auth": {
                    "strategy": "bcrypt-session",
                    "rate_limit": {"backend": "redis"},
                }
            }
        )
        assert "slowapi>=0.1.9" in extra
        assert "redis>=4.0" in extra
