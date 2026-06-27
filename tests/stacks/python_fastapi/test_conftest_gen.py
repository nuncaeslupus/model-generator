"""Tests for conftest/fixture generators."""

import json
from pathlib import Path
from typing import Any


class TestConftestGeneratorDatetimeFixture:
    """TPL-12: datetime create-data fixtures use a far-future literal.

    A hardcoded past date (the old ``2025-01-01``) is a time-bomb: a session
    ``expires_at`` seeded in the past is already expired, and it ages further
    out of range as real time advances. The far-future ``2099`` literal also
    matches the convention the contract update payloads use.
    """

    @staticmethod
    def test_datetime_fixture_is_future() -> None:
        from model_generator.utils.conftest_generator import (
            generate_minimal_create_data,
        )

        entity_data = {
            "fields": {
                "expires_at": {"type": "datetime", "required": True},
            },
        }
        lines = generate_minimal_create_data(
            "UserSession", entity_data, dependencies={}, enums={}
        )
        joined = "\n".join(lines)
        assert '"expires_at": "2099-01-01T00:00:00Z"' in joined
        # The old past-date time-bomb must be gone.
        assert "2025-01-01" not in joined


class TestConftestGeneratorRateLimitReset:
    """Test the autouse rate-limiter reset fixture emission (§12.6)."""

    @staticmethod
    def _models_dir(tmp_path: Path) -> Path:
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "items.model.json").write_text(
            json.dumps(
                {
                    "domain": "items",
                    "entities": {
                        "Item": {
                            "table": "items",
                            "fields": {
                                "id": {
                                    "type": "uuid",
                                    "primary_key": True,
                                    "auto_generate": True,
                                },
                                "name": {
                                    "type": "text",
                                    "max_length": 100,
                                    "required": True,
                                },
                            },
                            "api": {"enabled": True},
                        }
                    },
                }
            )
        )
        return models_dir

    def test_no_reset_fixture_when_rate_limiter_import_none(
        self, tmp_path: Path
    ) -> None:
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(self._models_dir(tmp_path))
        assert "rate_limit" not in content
        assert "_reset_rate_limiter" not in content
        assert "limiter.reset()" not in content

    def test_emits_reset_fixture_when_rate_limiter_import_set(
        self, tmp_path: Path
    ) -> None:
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(
            self._models_dir(tmp_path),
            rate_limiter_import="backend.src.auth.rate_limit",
        )
        assert "from backend.src.auth.rate_limit import limiter" in content
        assert "@pytest.fixture(autouse=True)" in content
        assert "def _reset_rate_limiter() -> None:" in content
        assert "limiter.reset()" in content


class TestConftestGeneratorDefaultAuth:
    """Autouse default-authenticated-user fixture for owner-scoped entities.

    When auth is on and any API-enabled entity declares ``api.scope``, the
    generated API conftest must authenticate every test as a persisted owner
    user (overriding ``get_current_user``); otherwise scoped CRUD returns 401
    and the whole contract suite cascades.
    """

    @staticmethod
    def _models_dir(tmp_path: Path, *, scoped: bool) -> Path:
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        portfolio_api: dict[str, Any] = {"enabled": True, "prefix": "portfolios"}
        if scoped:
            portfolio_api["scope"] = {"owner_field": "user_id"}
        (models_dir / "users.model.json").write_text(
            json.dumps(
                {
                    "domain": "users",
                    "entities": {
                        "User": {
                            "table": "users",
                            "fields": {
                                "id": {
                                    "type": "uuid",
                                    "primary_key": True,
                                    "auto_generate": True,
                                },
                                "username": {
                                    "type": "text",
                                    "max_length": 50,
                                    "required": True,
                                    "unique": True,
                                },
                                "email": {
                                    "type": "text",
                                    "max_length": 255,
                                    "required": True,
                                    "unique": True,
                                },
                                "password_hash": {
                                    "type": "text",
                                    "max_length": 255,
                                    "required": True,
                                    "api_field_name": "password",
                                    "api_exclude_response": True,
                                },
                            },
                            "api": {"enabled": True, "endpoints": ["list", "get"]},
                        },
                        "Portfolio": {
                            "table": "portfolios",
                            "fields": {
                                "id": {
                                    "type": "uuid",
                                    "primary_key": True,
                                    "auto_generate": True,
                                },
                                "user_id": {
                                    "type": "reference",
                                    "reference_table": "users",
                                    "required": True,
                                },
                                "name": {
                                    "type": "text",
                                    "max_length": 100,
                                    "required": True,
                                },
                            },
                            "api": portfolio_api,
                        },
                    },
                }
            )
        )
        return models_dir

    def test_no_default_auth_fixture_when_no_scoped_entity(
        self, tmp_path: Path
    ) -> None:
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(
            self._models_dir(tmp_path, scoped=False),
            auth_strategy="bcrypt-session",
            auth_router_import="backend.src.auth.router",
            main_import="backend.src.main",
        )
        assert "_default_authenticated_user" not in content
        assert "dependency_overrides" not in content

    def test_no_default_auth_fixture_when_auth_off(self, tmp_path: Path) -> None:
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(
            self._models_dir(tmp_path, scoped=True),
            auth_strategy=None,
            auth_router_import="backend.src.auth.router",
            main_import="backend.src.main",
        )
        assert "_default_authenticated_user" not in content

    def test_emits_default_auth_fixture_when_scoped(self, tmp_path: Path) -> None:
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(
            self._models_dir(tmp_path, scoped=True),
            auth_strategy="bcrypt-session",
            auth_router_import="backend.src.auth.router",
            main_import="backend.src.main",
        )
        assert "@pytest.fixture(autouse=True)" in content
        assert "def _default_authenticated_user(user_id: str)" in content
        assert "from backend.src.auth.router import get_current_user" in content
        assert "from backend.src.main import app" in content
        assert "app.dependency_overrides[get_current_user]" in content
        assert "app.dependency_overrides.pop(get_current_user, None)" in content
        assert "from collections.abc import Iterator" in content
        # A non-UUID PK (int -> AttributeError, None -> TypeError, bad str ->
        # ValueError) must fall back to the raw id rather than crash at startup.
        assert "except (ValueError, TypeError, AttributeError):" in content

    @staticmethod
    def _api_key_models_dir(tmp_path: Path) -> Path:
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "widgets.model.json").write_text(
            json.dumps(
                {
                    "domain": "widgets",
                    "entities": {
                        "Widget": {
                            "table": "widgets",
                            "fields": {
                                "id": {
                                    "type": "uuid",
                                    "primary_key": True,
                                    "auto_generate": True,
                                },
                                "name": {
                                    "type": "text",
                                    "max_length": 100,
                                    "required": True,
                                },
                            },
                            "api": {"enabled": True, "require_auth": True},
                        }
                    },
                }
            )
        )
        return models_dir

    def test_emits_api_key_bypass_fixture(self, tmp_path: Path) -> None:
        """api-key + require_auth → autouse fixture overrides require_api_key."""
        from model_generator.utils.conftest_generator import generate_conftest_content

        content, _ = generate_conftest_content(
            self._api_key_models_dir(tmp_path),
            auth_strategy="api-key",
            main_import="backend.src.main",
            api_key_dependency="backend.src.auth.api_key.require_api_key",
        )
        assert "def _bypass_api_key()" in content
        assert "from backend.src.auth.api_key import require_api_key" in content
        assert "app.dependency_overrides[require_api_key] = lambda: None" in content
        assert "app.dependency_overrides.pop(require_api_key, None)" in content

    def test_no_bypass_fixture_without_require_auth(self, tmp_path: Path) -> None:
        from model_generator.utils.conftest_generator import generate_conftest_content

        # Same model but require_auth off — no bypass fixture.
        models_dir = self._api_key_models_dir(tmp_path)
        spec_path = models_dir / "widgets.model.json"
        spec_path.write_text(
            spec_path.read_text().replace(
                '"require_auth": true', '"require_auth": false'
            )
        )
        content, _ = generate_conftest_content(
            models_dir,
            auth_strategy="api-key",
            main_import="backend.src.main",
            api_key_dependency="backend.src.auth.api_key.require_api_key",
        )
        assert "_bypass_api_key" not in content


class TestConftestLoadAllModelsComments:
    """GEN-2: conftest model loading accepts the // -comment JSON dialect."""

    def test_load_all_models_strips_comments(self, tmp_path: Path) -> None:
        from model_generator.utils.conftest_generator import load_all_models

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "items.model.json").write_text(
            "{\n"
            "  // a leading comment the rest of the pipeline tolerates\n"
            '  "domain": "items",\n'
            '  "entities": {\n'
            '    "Item": {\n'
            '      "table": "items",  // inline comment\n'
            '      "fields": {"id": {"type": "uuid", "primary_key": true}}\n'
            "    }\n"
            "  }\n"
            "}\n"
        )

        # Raw json.load would raise on the // comments; the shared parser must not.
        models = load_all_models(models_dir)
        assert "items" in models
        assert models["items"]["entities"]["Item"]["table"] == "items"

    def test_load_all_models_normalizes_integer_alias(self, tmp_path: Path) -> None:
        from model_generator.utils.conftest_generator import load_all_models

        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "items.model.json").write_text(
            json.dumps(
                {
                    "domain": "items",
                    "entities": {
                        "Item": {
                            "table": "items",
                            "fields": {
                                "id": {"type": "uuid", "primary_key": True},
                                "qty": {"type": "integer", "default": 0},
                            },
                        }
                    },
                }
            )
        )

        models = load_all_models(models_dir)
        qty = models["items"]["entities"]["Item"]["fields"]["qty"]
        assert qty["type"] == "counter"  # integer alias normalized


class TestFieldInUniqueIndex:
    """_field_in_unique_index must return True when field IS in a unique index."""

    def test_field_in_unique_index_returns_true(self) -> None:
        from model_generator.utils.conftest_generator import _field_in_unique_index

        entity_data = {
            "fields": {},
            "indexes": [{"unique": True, "fields": ["email", "tenant_id"]}],
        }
        assert _field_in_unique_index("email", entity_data) is True

    def test_field_not_in_unique_index_returns_false(self) -> None:
        from model_generator.utils.conftest_generator import _field_in_unique_index

        entity_data = {
            "fields": {},
            "indexes": [{"unique": True, "fields": ["email"]}],
        }
        assert _field_in_unique_index("username", entity_data) is False

    def test_field_in_unique_constraint_returns_true(self) -> None:
        from model_generator.utils.conftest_generator import _field_in_unique_index

        entity_data = {
            "fields": {},
            "indexes": [],
            "constraints": [{"type": "unique", "fields": ["slug"]}],
        }
        assert _field_in_unique_index("slug", entity_data) is True

    def test_non_unique_index_ignored(self) -> None:
        from model_generator.utils.conftest_generator import _field_in_unique_index

        entity_data = {
            "fields": {},
            "indexes": [{"unique": False, "fields": ["name"]}],
        }
        assert _field_in_unique_index("name", entity_data) is False


class TestTopologicalSort:
    """topological_sort must place dependencies before dependents."""

    def test_dependency_comes_before_dependent(self) -> None:
        from model_generator.utils.conftest_generator import topological_sort

        deps = {"Post": {"Author"}, "Author": set(), "Comment": {"Post"}}
        result = topological_sort(set(deps.keys()), deps)
        assert result.index("Author") < result.index("Post")
        assert result.index("Post") < result.index("Comment")

    def test_no_dependencies_returns_all(self) -> None:
        from model_generator.utils.conftest_generator import topological_sort

        result = topological_sort({"A", "B", "C"}, {"A": set(), "B": set(), "C": set()})
        assert set(result) == {"A", "B", "C"}

    def test_independent_entities_all_present(self) -> None:
        from model_generator.utils.conftest_generator import topological_sort

        result = topological_sort({"X", "Y"}, {})
        assert set(result) == {"X", "Y"}


class TestFindForeignKeyDependencies:
    """find_foreign_key_dependencies must detect reference-type required fields."""

    def test_required_reference_creates_dependency(self) -> None:
        from model_generator.utils.conftest_generator import (
            find_foreign_key_dependencies,
        )

        entities = {
            "Author": {
                "table": "authors",
                "fields": {"id": {"type": "uuid", "primary_key": True}},
            },
            "Post": {
                "table": "posts",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True},
                    "author_id": {
                        "type": "reference",
                        "reference_table": "authors",
                        "required": True,
                    },
                },
            },
        }
        deps = find_foreign_key_dependencies(entities)
        assert "Author" in deps["Post"]

    def test_optional_reference_does_not_create_dependency(self) -> None:
        from model_generator.utils.conftest_generator import (
            find_foreign_key_dependencies,
        )

        entities = {
            "Tag": {
                "table": "tags",
                "fields": {"id": {"type": "uuid", "primary_key": True}},
            },
            "Post": {
                "table": "posts",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True},
                    "tag_id": {
                        "type": "reference",
                        "reference_table": "tags",
                        # required omitted — optional FK
                    },
                },
            },
        }
        deps = find_foreign_key_dependencies(entities)
        assert "Tag" not in deps["Post"]


class TestGenerateFixtureWithDeps:
    """generate_fixture must wire dep entity params when reference fields exist."""

    def _author_entities(self) -> dict[str, Any]:
        return {
            "Author": {
                "table": "authors",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True}
                },
                "api_prefix": "authors",
            },
            "Post": {
                "table": "posts",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "author_id": {
                        "type": "reference",
                        "reference_table": "authors",
                        "required": True,
                    },
                    "title": {"type": "text", "required": True},
                },
                "api_prefix": "posts",
            },
        }

    def test_fixture_includes_dep_param(self) -> None:
        from model_generator.utils.conftest_generator import generate_fixture

        entities = self._author_entities()
        lines = generate_fixture(
            "Post",
            entities["Post"],
            "post_id",
            required_deps={"Author"},
            all_entities=entities,
            enums={},
        )
        combined = "\n".join(lines)
        assert "author_id" in combined

    def test_fixture_dep_not_in_all_entities_is_skipped(self) -> None:
        from model_generator.utils.conftest_generator import generate_fixture

        entities = self._author_entities()
        # Remove Author from all_entities — dep should be silently skipped
        all_without_author = {k: v for k, v in entities.items() if k != "Author"}
        lines = generate_fixture(
            "Post",
            entities["Post"],
            "post_id",
            required_deps={"Author"},
            all_entities=all_without_author,
            enums={},
        )
        combined = "\n".join(lines)
        # Fixture still emits — just without the missing dep parameter
        assert "def post_id(" in combined
