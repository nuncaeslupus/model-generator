"""Tests for API models, routes, and generated contract tests."""

import copy
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from model_generator.generators import (
    generate_api_init,
    generate_api_models,
    generate_api_routes,
    generate_api_tests,
    generate_validators,
)


@pytest.fixture
def scoped_model() -> dict[str, Any]:
    """Model with an owner-scoped entity for testing api.scope generation."""
    return {
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
                    "owner_id": {"type": "uuid", "required": True},
                },
                "timestamps": {"created": True, "updated": True},
                "api": {
                    "enabled": True,
                    "endpoints": ["list", "create", "get", "update", "delete"],
                    "scope": {"owner_field": "owner_id"},
                },
            }
        },
    }


class TestApiRoutesUuidReferenceFilter:
    """TPL-14: reference filters on an id column are typed UUID → 422, not 500."""

    def _model(self, ref_field: dict[str, Any]) -> dict[str, Any]:
        return {
            "domain": "blog",
            "entities": {
                "Post": {
                    "table": "posts",
                    "api": {"endpoints": ["list", "get", "create", "update", "delete"]},
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "title": {
                            "type": "text",
                            "max_length": 100,
                            "required": True,
                        },
                        **ref_field,
                    },
                    "timestamps": {"created": True, "updated": True},
                },
            },
        }

    def test_id_reference_filter_typed_uuid(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = self._model(
            {
                "author_id": {
                    "type": "reference",
                    "reference_table": "authors",
                    "required": True,
                }
            }
        )
        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert "author_id: UUID | None = Query(" in content
        assert "author_id: str | None = Query(" not in content
        assert "from uuid import UUID" in content

    def test_non_id_reference_filter_stays_str(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = self._model(
            {
                "slug_ref": {
                    "type": "reference",
                    "reference_table": "slugs",
                    "reference_column": "slug",
                    "required": True,
                }
            }
        )
        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert "slug_ref: str | None = Query(" in content
        assert "slug_ref: UUID | None = Query(" not in content


class TestApiModelsGeneratorPerEntity:
    """Per-entity api-models emission: two files per entity."""

    def test_returns_one_response_and_one_request_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 4
        names = {r["path"].name for r in result}
        assert names == {
            "author_response.py",
            "author_request.py",
            "post_response.py",
            "post_request.py",
        }

    def test_response_file_contains_only_one_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """author_response.py contains AuthorResponse and not PostResponse."""
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        author_resp = next(
            r["content"] for r in result if r["path"].name == "author_response.py"
        )
        assert "class AuthorResponse(BaseModel):" in author_resp
        assert "class PostResponse" not in author_resp

    def test_request_file_contains_only_one_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """author_request.py contains Create/UpdateAuthorRequest and not Post."""
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        author_req = next(
            r["content"] for r in result if r["path"].name == "author_request.py"
        )
        assert "class CreateAuthorRequest(BaseModel):" in author_req
        assert "class UpdateAuthorRequest(BaseModel):" in author_req
        assert "CreatePostRequest" not in author_req

    def test_password_example_is_not_a_secret(
        self, project_env_per_entity: Any
    ) -> None:
        """The OpenAPI example for a password field must be a non-secret
        placeholder so secret scanners (GitGuardian) don't flag generated repos."""
        project_root, config, env = project_env_per_entity
        model = {
            "domain": "accounts",
            "entities": {
                "User": {
                    "table": "users",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "password": {"type": "text", "required": True},
                    },
                }
            },
        }
        result = generate_api_models(model, config, env, project_root)
        assert isinstance(result, list)
        content = next(
            r["content"] for r in result if r["path"].name == "user_request.py"
        )
        assert "SecureP@ssw0rd!" not in content
        assert '"password": "your-password-here"' in content


@pytest.fixture
def financial_model() -> dict[str, Any]:
    """Single entity exercising signed vs constrained financial fields.

    - unrealized_pnl: no constraint  -> signed -> validate_decimal
    - balance:        non_negative   -> validate_non_negative_decimal
    - deposit:        positive       -> validate_positive_decimal
    """
    return {
        "domain": "ledger",
        "description": "Ledger domain with signed and constrained money",
        "entities": {
            "Account": {
                "table": "accounts",
                "description": "Trading account",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "unrealized_pnl": {
                        "type": "financial",
                        "required": True,
                    },
                    "balance": {
                        "type": "financial",
                        "required": True,
                        "constraints": [{"type": "non_negative"}],
                    },
                    "deposit": {
                        "type": "financial",
                        "required": True,
                        "constraints": [{"type": "positive"}],
                    },
                },
                "timestamps": {"created": True, "updated": True},
            },
        },
    }


class TestFinancialValidatorSelection:
    """Signed financial fields must not be forced non-negative.

    Regression: the response/request templates hardcoded
    validate_non_negative_decimal for every financial field, so any
    legitimately negative value (PnL, returns) failed validation.
    """

    def _content(self, model: dict[str, Any], env_fixture: Any, suffix: str) -> str:
        project_root, config, env = env_fixture
        result = generate_api_models(model, config, env, project_root)
        assert isinstance(result, list)
        content = next(r["content"] for r in result if r["path"].name.endswith(suffix))
        assert isinstance(content, str)
        return content

    def test_response_signed_financial_uses_validate_decimal(
        self, financial_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._content(
            financial_model, project_env_per_entity, "account_response.py"
        )
        # Unconstrained financial -> signed validator
        assert (
            '_validate_unrealized_pnl = field_validator("unrealized_pnl")'
            "(validate_decimal)" in content
        )
        # Constrained financial -> stays non-negative / positive
        assert (
            '_validate_balance = field_validator("balance")'
            "(validate_non_negative_decimal)" in content
        )
        assert (
            '_validate_deposit = field_validator("deposit")'
            "(validate_positive_decimal)" in content
        )

    def test_response_imports_match_validators_used(
        self, financial_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._content(
            financial_model, project_env_per_entity, "account_response.py"
        )
        import_line = next(
            line
            for line in content.splitlines()
            if line.startswith("from") and "validators import" in line
        )
        assert "validate_decimal" in import_line
        assert "validate_non_negative_decimal" in import_line
        assert "validate_positive_decimal" in import_line

    def test_request_signed_financial_uses_validate_decimal(
        self, financial_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._content(
            financial_model, project_env_per_entity, "account_request.py"
        )
        assert (
            '_validate_unrealized_pnl = field_validator("unrealized_pnl")'
            "(validate_decimal)" in content
        )
        assert (
            '_validate_balance = field_validator("balance")'
            "(validate_non_negative_decimal)" in content
        )
        assert (
            '_validate_deposit = field_validator("deposit")'
            "(validate_positive_decimal)" in content
        )

    def test_request_imports_match_validators_used(
        self, financial_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._content(
            financial_model, project_env_per_entity, "account_request.py"
        )
        import_line = next(
            line
            for line in content.splitlines()
            if line.startswith("from") and "validators import" in line
        )
        assert "validate_decimal" in import_line
        assert "validate_non_negative_decimal" in import_line
        assert "validate_positive_decimal" in import_line

    def test_validators_module_defines_validate_decimal(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_validators(config, env, project_root)
        assert result is not None
        assert "def validate_decimal(value: Any) -> str | None:" in result["content"]

    def test_validate_decimal_rejects_non_finite(
        self, project_env_per_entity: Any
    ) -> None:
        """The emitted validate_decimal must reject NaN/Infinity, not just
        malformed strings (financial fields cannot store non-finite values)."""
        project_root, config, env = project_env_per_entity
        result = generate_validators(config, env, project_root)
        assert result is not None
        ns: dict[str, Any] = {}
        exec(result["content"], ns)
        validate_decimal = ns["validate_decimal"]
        # Signed finite values pass.
        assert validate_decimal("-12.5") == "-12.5"
        assert validate_decimal(None) is None
        # Non-finite values are rejected.
        for bad in ("NaN", "Infinity", "-Infinity", "sNaN"):
            with pytest.raises(ValueError):
                validate_decimal(bad)
        with pytest.raises(ValueError):
            validate_decimal("not-a-number")

    def test_empty_constraints_fall_back_to_signed(
        self, project_env_per_entity: Any
    ) -> None:
        """A financial field with an empty (falsy) `constraints` list falls
        back to the signed default rather than crashing on the `map` filter."""
        model = {
            "domain": "ledger",
            "entities": {
                "Account": {
                    "table": "accounts",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "pnl": {
                            "type": "financial",
                            "required": True,
                            "constraints": [],
                        },
                    },
                }
            },
        }
        for suffix in ("account_response.py", "account_request.py"):
            content = self._content(model, project_env_per_entity, suffix)
            assert '_validate_pnl = field_validator("pnl")(validate_decimal)' in content


class TestRequestFieldValidatorSectionHeader:
    """TPL-17: Field Validators section header must appear on its own line.

    Regression: the {#- comment in request.py.j2 stripped the newline after
    `}` (model_config closing brace), gluing the section header inline.
    """

    def test_field_validator_header_not_inline_with_brace(
        self, project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        model = {
            "domain": "ledger",
            "entities": {
                "Account": {
                    "table": "accounts",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "balance": {
                            "type": "financial",
                            "required": True,
                        },
                    },
                }
            },
        }
        result = generate_api_models(model, config, env, project_root)
        assert isinstance(result, list)
        content = next(
            r["content"] for r in result if r["path"].name == "account_request.py"
        )
        assert "}  # " not in content, (
            "Section header must not appear inline with closing brace"
        )
        assert "}  #" not in content


class TestGenerateApiInitPerEntity:
    """Per-entity api __init__.py emission."""

    def test_emits_one_import_block_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.api.scan_api_model_files", return_value=[]
        ):
            result = generate_api_init(multi_entity_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert "from .author_response import" in result["content"]
        assert "from .author_request import" in result["content"]
        assert "from .post_response import" in result["content"]
        assert "from .post_request import" in result["content"]
        assert result["domain_count"] == 2

    def test_no_none_banner_emitted(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """section=None must suppress the banner, not render '# None'."""
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.api.scan_api_model_files", return_value=[]
        ):
            result = generate_api_init(multi_entity_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert "# None" not in result["content"]

    def test_existing_per_entity_files_not_redeclared(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """If scan finds 'author', model contributes only Post."""
        project_root, config, env = project_env_per_entity
        existing = [
            {
                "name": "author",
                "section": None,
                "response_models": ["AuthorResponse"],
                "request_models": ["CreateAuthorRequest", "UpdateAuthorRequest"],
            }
        ]
        with patch(
            "model_generator.generators.api.scan_api_model_files",
            return_value=existing,
        ):
            result = generate_api_init(multi_entity_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert result["domain_count"] == 2  # author (existing) + post (added)
        assert "from .author_response import" in result["content"]
        assert "from .post_response import" in result["content"]


class TestApiRoutesGeneratorPerEntity:
    """Per-entity api routes emission."""

    def test_returns_list_with_one_route_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"author.py", "post.py"}

    def test_db_model_imports_use_per_entity_paths(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """DB model is imported from {db_models}.{entity_snake}, not {domain}."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "from src.database.models.author import Author" in by_name["author.py"]
        assert "from src.database.models.post import Post" in by_name["post.py"]
        # Per-domain import shape must NOT appear.
        assert "from src.database.models.blog import" not in by_name["author.py"]
        assert "from src.database.models.blog import" not in by_name["post.py"]

    def test_api_model_imports_use_per_entity_paths(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """API models are imported from per-entity files, not per-domain combined."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert (
            "from src.api.models.author_request import CreateAuthorRequest"
            in by_name["author.py"]
        )
        assert (
            "from src.api.models.author_response import AuthorResponse"
            in by_name["author.py"]
        )
        # Per-domain combined imports must NOT appear.
        assert "from src.api.models.blog_request" not in by_name["author.py"]
        assert "from src.api.models.blog_response" not in by_name["author.py"]

    def test_content_isolated_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """author.py only has Author handlers; post.py only has Post handlers."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "async def create_author" in by_name["author.py"]
        assert "async def create_post" not in by_name["author.py"]
        assert "async def create_post" in by_name["post.py"]
        assert "async def create_author" not in by_name["post.py"]


class TestApiTestsGeneratorPerEntity:
    """Per-entity api contract test emission."""

    def test_returns_list_with_one_test_file_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_api_tests(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"test_author_api.py", "test_post_api.py"}

    def test_content_isolated_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """test_author_api.py only references Author response/request models."""
        project_root, config, env = project_env_per_entity
        result = generate_api_tests(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "AuthorResponse" in by_name["test_author_api.py"]
        assert "PostResponse" not in by_name["test_author_api.py"]
        assert "PostResponse" in by_name["test_post_api.py"]
        assert "AuthorResponse" not in by_name["test_post_api.py"]

    def test_read_only_factory_import_is_layout_aware(
        self, project_env_per_entity: Any
    ) -> None:
        """Read-only get-by-id seeds via the per-entity factory module.

        The factory import must target ``{factories}/{entity_snake}.py`` in
        per-entity layout (not ``{factories}/{domain}.py``, which only exists in
        per-domain layout).
        """
        project_root, config, env = project_env_per_entity
        model = {
            "domain": "geo",
            "entities": {
                "Country": {
                    "table": "countries",
                    # Read-only, no required FK, no one_to_many → factory-seeded.
                    "api": {"enabled": True, "endpoints": ["list", "get"]},
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
                            "unique": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }
        result = generate_api_tests(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        content = result[0]["content"]
        # Import targets the entity snake module, not the domain.
        assert "factories.country import CountryFactory" in content
        assert "factories.geo import" not in content
        # Factory-seeded get-by-id test is emitted.
        assert "def test_get_country_by_id_success" in content
        assert "CountryFactory.create()" in content

    """Test API models (request/response) generation."""

    def test_generates_two_files(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)

        assert isinstance(results, list)
        assert len(results) == 2
        filenames = [str(r["path"].name) for r in results]
        assert "items_response.py" in filenames
        assert "items_request.py" in filenames

    def test_response_model_content(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)
        assert isinstance(results, list)
        response = next(r for r in results if "response" in r["path"].name)

        assert "class ItemResponse(BaseModel):" in response["content"]

    def test_request_model_content(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)
        assert isinstance(results, list)
        request = next(r for r in results if "request" in r["path"].name)

        assert "class CreateItemRequest(BaseModel):" in request["content"]
        assert "class UpdateItemRequest(BaseModel):" in request["content"]

    def test_field_description_not_truncated(self, project_env: Any) -> None:
        """Verify field descriptions are no longer truncated in request models."""
        project_root, config, env = project_env
        long_desc = "A" * 100  # Longer than the old 65-char limit
        model = {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "label": {
                            "type": "text",
                            "max_length": 200,
                            "required": True,
                            "description": long_desc,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        request = next(r for r in results if "request" in r["path"].name)
        assert long_desc in request["content"]


class TestApiModelsGeneratorScope:
    """Test API request model generation when entities declare api.scope."""

    def _request_content(self, model: Any, project_env: Any) -> str:
        project_root, config, env = project_env
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        content = next(r for r in results if "request" in r["path"].name)["content"]
        assert isinstance(content, str)
        return content

    def test_owner_field_excluded_from_create_request(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """owner_field is set by the handler, not by the API caller."""
        content = self._request_content(scoped_model, project_env)
        create_start = content.index("class CreateWidgetRequest")
        update_start = content.index("class UpdateWidgetRequest")
        create_block = content[create_start:update_start]
        assert "owner_id" not in create_block

    def test_owner_field_excluded_from_update_request(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """owner_field is immutable from the API; update payloads cannot reassign it."""
        content = self._request_content(scoped_model, project_env)
        update_start = content.index("class UpdateWidgetRequest")
        update_block = content[update_start:]
        assert "owner_id" not in update_block


class TestApiRoutesGenerator:
    """Test API routes generation."""

    def test_generates_route_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "src/api/routes/items.py"
        assert "@router.post" in result["content"]
        assert "@router.get" in result["content"]
        assert "@router.put" in result["content"]
        assert "@router.delete" in result["content"]

    def test_crud_endpoints(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)

        assert "async def create_item" in result["content"]
        assert "async def list_items" in result["content"]
        assert "async def get_item" in result["content"]
        assert "async def update_item" in result["content"]
        assert "async def delete_item" in result["content"]


class TestApiRoutesGeneratorScope:
    """Test API route generation when entities declare api.scope."""

    AUTH_PATH = "backend.src.auth.get_current_user"

    def _config_with_auth(self, config: Any) -> dict[str, Any]:
        return {**config, "auth": {"dependency_path": self.AUTH_PATH}}

    def test_imports_auth_dependency(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert "from backend.src.auth import get_current_user" in result["content"]

    def test_all_handlers_receive_current_user(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """All 5 CRUD handlers inject current_user when scope is set."""
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert (
            result["content"].count("current_user: Any = Depends(get_current_user)")
            == 5
        )

    def test_create_handler_auto_sets_owner_field(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """Create handler force-assigns owner_field from current_user.id."""
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert "widget.owner_id = current_user.id" in result["content"]

    def test_list_query_filters_by_owner(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert (
            "stmt = stmt.where(Widget.owner_id == current_user.id)" in result["content"]
        )
        assert (
            "count_stmt = count_stmt.where(Widget.owner_id == current_user.id)"
            in result["content"]
        )

    def test_default_miss_status_uses_not_found(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """404 falls through to format_not_found_error; HTTPException not imported."""
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert "if widget.owner_id != current_user.id:" in result["content"]
        assert "from fastapi import HTTPException" not in result["content"]

    def test_custom_miss_status_uses_http_exception(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """Non-404 miss_status emits HTTPException with the custom code."""
        project_root, config, env = project_env
        scoped_model["entities"]["Widget"]["api"]["scope"]["miss_status"] = 403
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert "from fastapi import HTTPException" in result["content"]
        assert "status_code=403" in result["content"]


@pytest.fixture
def filter_model() -> dict[str, Any]:
    """Model exercising every numeric/date list-filter param type."""
    return {
        "domain": "metrics",
        "entities": {
            "Metric": {
                "table": "metrics",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "threshold_usd": {
                        "type": "financial",
                        "precision": 18,
                        "scale": 8,
                    },
                    "ratio": {"type": "percentage"},
                    "observed_at": {"type": "datetime"},
                    "retries": {"type": "counter"},
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }


class TestApiRoutesGeneratorRequireAuth:
    """Routes for entities with api.require_auth (the api-key gate)."""

    DEP_PATH = "backend.src.auth.api_key.require_api_key"

    def _gated_model(self) -> dict[str, Any]:
        return {
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
                        "name": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                    "api": {"enabled": True, "require_auth": True},
                }
            },
        }

    def test_gates_every_route_with_dependency(self, project_env: Any) -> None:
        project_root, config, env = project_env
        cfg = {**config, "auth": {"dependency_path": self.DEP_PATH}}
        result = generate_api_routes(
            self._gated_model(), cfg, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # Imports the gate dependency...
        assert "from backend.src.auth.api_key import require_api_key" in content
        # ...and attaches it to all 5 route decorators (no owner injection).
        assert content.count("dependencies=[Depends(require_api_key)]") == 5
        assert "current_user" not in content

    def test_no_gate_without_require_auth(self, project_env: Any) -> None:
        """An unprotected entity gets neither the import nor the dependency."""
        project_root, config, env = project_env
        model = self._gated_model()
        model["entities"]["Widget"]["api"]["require_auth"] = False
        cfg = {**config, "auth": {"dependency_path": self.DEP_PATH}}
        result = generate_api_routes(
            model, cfg, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        assert "require_api_key" not in result["content"]
        assert "dependencies=[Depends(" not in result["content"]


class TestApiRoutesFilterCoercion:
    """P1: numeric/date list filters are typed so FastAPI validates them.

    Previously these params were ``str | None`` and coerced inside the handler
    (``Decimal(...)`` / ``datetime.fromisoformat(...)``), so a malformed value
    raised an unhandled 500. Emitting the real types moves validation to the
    framework boundary (422) and drops the manual coercion entirely.
    """

    def _render(self, model: dict[str, Any], project_env: Any) -> str:
        project_root, config, env = project_env
        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        return str(result["content"])

    def test_financial_and_percentage_filters_typed_as_decimal(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        assert "threshold_usd_min: Decimal | None = Query(None" in content
        assert "threshold_usd_max: Decimal | None = Query(None" in content
        assert "ratio_min: Decimal | None = Query(None" in content
        assert "ratio_max: Decimal | None = Query(None" in content
        # No str-typed numeric filter params remain.
        assert "threshold_usd_min: str | None" not in content
        assert "ratio_min: str | None" not in content

    def test_datetime_filters_typed_as_datetime(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        assert "observed_at_after: datetime | None = Query(None" in content
        assert "observed_at_before: datetime | None = Query(None" in content
        assert "observed_at_after: str | None" not in content

    def test_no_manual_coercion_in_handler_body(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        # The unguarded coercions that produced 500s are gone.
        assert "Decimal(threshold_usd_min)" not in content
        assert "Decimal(ratio_min)" not in content
        assert "datetime.fromisoformat(" not in content
        # Filters compare against the validated param directly.
        assert "Metric.threshold_usd >= threshold_usd_min" in content
        assert "Metric.observed_at >= observed_at_after" in content

    def test_counter_filters_stay_int_typed(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        # Counters were already int-typed (FastAPI validates them); unchanged.
        assert "retries_min: int | None = Query(None" in content
        assert "retries_max: int | None = Query(None" in content

    def test_generated_route_compiles_with_required_imports(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        compile(content, "<metric_route>", "exec")
        # Decimal / datetime imports remain — now used in the signatures.
        assert "from decimal import Decimal" in content
        assert "from datetime import datetime" in content


class TestApiRoutesDatetimeFilterTzAware:
    """Naive datetime filter values are localized to UTC before comparison.

    A ``datetime | None`` filter parses input without a tz offset (e.g.
    ``2026-06-11T12:00:00``) as a naive datetime; compared against a tz-aware
    ``DateTime(timezone=True)`` column it raises ``TypeError``/``DataError`` on
    strict drivers (asyncpg/psycopg2). The handler localizes a naive value to
    UTC first. Latent (SQLite suites don't enforce tz-awareness), not a
    regression — fixed uniformly for both ``_after`` and ``_before``.
    """

    def _render(self, model: dict[str, Any], project_env: Any) -> str:
        project_root, config, env = project_env
        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        return str(result["content"])

    def test_imports_timezone(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        assert "from datetime import datetime, timezone" in content

    def test_naive_after_localized_to_utc(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        assert "if observed_at_after.tzinfo is None:" in content
        assert (
            "observed_at_after = observed_at_after.replace(tzinfo=timezone.utc)"
            in content
        )

    def test_naive_before_localized_to_utc(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        assert "if observed_at_before.tzinfo is None:" in content
        assert (
            "observed_at_before = observed_at_before.replace(tzinfo=timezone.utc)"
            in content
        )

    def test_route_still_compiles(
        self, filter_model: dict[str, Any], project_env: Any
    ) -> None:
        content = self._render(filter_model, project_env)
        compile(content, "<metric_route>", "exec")


class TestApiRoutesExplicitFilters:
    """EX-2: api.filters whitelist restricts the auto-generated list filter params."""

    def _model_with_many_filterable_fields(
        self, api_filters: list[str] | None = None
    ) -> dict[str, Any]:
        """Entity with enum + boolean + financial fields — all filterable by default."""
        api_config: dict[str, Any] = {"enabled": True}
        if api_filters is not None:
            api_config["filters"] = api_filters
        return {
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
                        "status": {
                            "type": "enum",
                            "enum_name": "ItemStatus",
                            "enum_values": ["ACTIVE", "INACTIVE"],
                            "required": True,
                        },
                        "is_featured": {"type": "boolean", "default": False},
                        "price": {"type": "financial"},
                    },
                    "timestamps": {"created": True, "updated": True},
                    "api": api_config,
                }
            },
        }

    def _render(self, model: dict[str, Any], project_env: Any) -> str:
        project_root, config, env = project_env
        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        return str(result["content"])

    def test_all_filterable_fields_emitted_when_no_whitelist(
        self, project_env: Any
    ) -> None:
        """Without api.filters, every filterable type gets a filter param."""
        content = self._render(self._model_with_many_filterable_fields(), project_env)
        assert "status: ItemStatus | None = Query(None" in content
        assert "is_featured: bool | None = Query(None" in content
        assert "price_min: Decimal | None = Query(None" in content
        assert "price_max: Decimal | None = Query(None" in content

    def test_whitelist_restricts_to_listed_fields(self, project_env: Any) -> None:
        """api.filters: ['status'] → only status filter param is emitted."""
        content = self._render(
            self._model_with_many_filterable_fields(api_filters=["status"]), project_env
        )
        assert "status: ItemStatus | None = Query(None" in content
        # Non-listed filterable fields must be absent.
        assert "is_featured: bool | None = Query(None" not in content
        assert "price_min: Decimal | None = Query(None" not in content
        assert "price_max: Decimal | None = Query(None" not in content

    def test_whitelist_applies_to_filter_logic_body(self, project_env: Any) -> None:
        """Restricted fields must also be absent from the 'Apply filters' body."""
        content = self._render(
            self._model_with_many_filterable_fields(api_filters=["status"]), project_env
        )
        # Only status filter is wired in the handler body.
        assert "Item.status == status" in content
        assert "Item.is_featured == is_featured" not in content
        assert "Item.price >= price_min" not in content

    def test_empty_whitelist_suppresses_all_filters(self, project_env: Any) -> None:
        """api.filters: [] → no field filter params at all."""
        content = self._render(
            self._model_with_many_filterable_fields(api_filters=[]), project_env
        )
        assert "status: ItemStatus | None" not in content
        assert "is_featured: bool | None" not in content
        assert "price_min: Decimal | None" not in content

    def test_whitelist_with_multi_param_field(self, project_env: Any) -> None:
        """When price (financial → _min/_max) is listed, both params are emitted."""
        content = self._render(
            self._model_with_many_filterable_fields(api_filters=["price"]), project_env
        )
        assert "price_min: Decimal | None = Query(None" in content
        assert "price_max: Decimal | None = Query(None" in content
        assert "status: ItemStatus | None" not in content


class TestApiTestsGenerator:
    """Test contract test generation."""

    def test_generates_test_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_tests(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "tests/api/test_items_api.py"

    def test_test_content(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_tests(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)

        assert "class TestItemsAPI:" in result["content"]
        assert "def test_get_items_list_success" in result["content"]
        assert "def test_post_item_success" in result["content"]
        assert "def test_get_item_by_id_success" in result["content"]
        assert "def test_delete_item_success" in result["content"]

    def test_skips_put_tests_when_update_endpoint_excluded(
        self, project_env: Any
    ) -> None:
        """If api.endpoints omits 'update', no test_put_* tests should be emitted."""
        project_root, config, env = project_env
        model = {
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
                        "name": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                    "api": {
                        "enabled": True,
                        "endpoints": ["list", "create", "get", "delete"],
                    },
                }
            },
        }
        result = generate_api_tests(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        assert "def test_put_item" not in result["content"]
        assert "def test_item_immutable_fields" not in result["content"]
        # Sections that ARE in endpoints should still emit
        assert "def test_delete_item" in result["content"]
        assert "def test_post_item" in result["content"]

    def test_skips_delete_tests_when_delete_endpoint_excluded(
        self, project_env: Any
    ) -> None:
        """If api.endpoints omits 'delete', no test_delete_* tests should be emitted."""
        project_root, config, env = project_env
        model = {
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
                        "name": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                    "api": {
                        "enabled": True,
                        "endpoints": ["list", "create", "get"],
                    },
                }
            },
        }
        result = generate_api_tests(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        assert "def test_delete_item" not in result["content"]
        assert "def test_put_item" not in result["content"]
        # READ + CREATE still emitted
        assert "def test_post_item" in result["content"]
        assert "def test_get_item_by_id_success" in result["content"]


class TestApiTestsGeneratorScope:
    """Test contract test generation when entities declare api.scope."""

    AUTH_PATH = "backend.src.auth.get_current_user"

    def test_main_import_module_derived_from_paths(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """Import path follows config.paths.main filename, not a hard-coded `main`."""
        project_root, config, env = project_env
        config_with_auth = {
            **config,
            "paths": {**config["paths"], "main": "src/app.py"},
            "auth": {"dependency_path": self.AUTH_PATH},
        }
        result = generate_api_tests(
            scoped_model,
            config_with_auth,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        assert "from src.app import app" in result["content"]
        assert "from src.main import app" not in result["content"]

    def test_missing_required_skips_owner_field(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """The owner field is injected/excluded under scope, so the missing-

        required-fields test must not omit it and expect 422 (it would now 201).
        """
        project_root, config, env = project_env
        config_with_auth = {
            **config,
            "auth": {"dependency_path": self.AUTH_PATH},
        }
        result = generate_api_tests(
            scoped_model,
            config_with_auth,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        content = result["content"]
        # The required non-owner field still gets a missing-field sub-case...
        assert "# Missing name" in content
        # ...but the owner field does not (it's injected from current_user).
        assert "# Missing owner_id" not in content

    def test_scope_access_denied_gated_on_create(
        self, scoped_model: dict[str, Any], project_env: Any
    ) -> None:
        """The cross-owner denial test POSTs to seed, so it requires `create`.

        A scoped entity without a `create` endpoint can't be seeded via POST
        (the POST would 405), so the test must be suppressed rather than emit a
        guaranteed failure — mirrors how the other POST-seeding tests are gated.
        """
        project_root, config, env = project_env
        config_with_auth = {**config, "auth": {"dependency_path": self.AUTH_PATH}}

        # With `create` present the denial test is emitted.
        with_create = generate_api_tests(
            scoped_model, config_with_auth, env, project_root, enums={}, constraints={}
        )
        assert isinstance(with_create, dict)
        assert "def test_widget_scope_access_denied(" in with_create["content"]

        # Drop `create`: the denial test must no longer be emitted.
        no_create = copy.deepcopy(scoped_model)
        no_create["entities"]["Widget"]["api"]["endpoints"] = ["list", "get"]
        result = generate_api_tests(
            no_create, config_with_auth, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        assert "def test_widget_scope_access_denied(" not in result["content"]


class TestComputeConftestAuthImports:
    """The conftest orchestrator's auth-router / main import-path helpers."""

    def test_returns_none_when_auth_off(self) -> None:
        from model_generator.generate import (
            _compute_auth_router_import,
            _compute_main_import,
        )

        assert _compute_auth_router_import({}) is None
        assert _compute_main_import({}) is None
        assert _compute_auth_router_import({"auth": {}}) is None

    def test_derives_dotted_paths_from_config(self) -> None:
        from model_generator.generate import (
            _compute_auth_router_import,
            _compute_main_import,
        )

        config = {
            "auth": {
                "strategy": "bcrypt-session",
                "path": "backend/src/auth/router.py",
            },
            "paths": {"main": "backend/src/main.py"},
        }
        assert _compute_auth_router_import(config) == "backend.src.auth.router"
        assert _compute_main_import(config) == "backend.src.main"

    def test_honors_python_root(self) -> None:
        from model_generator.generate import (
            _compute_auth_router_import,
            _compute_main_import,
        )

        config = {
            "auth": {"strategy": "bcrypt-session", "path": "src/auth/router.py"},
            "paths": {"main": "src/main.py"},
            "python_root": "src",
        }
        assert _compute_auth_router_import(config) == "auth.router"
        assert _compute_main_import(config) == "main"


class TestApiEnabledFiltering:
    """Test that api.enabled: false skips API generation."""

    @pytest.fixture
    def api_disabled_model(self) -> dict[str, Any]:
        """Model with all entities having api.enabled: false."""
        return {
            "domain": "internal",
            "entities": {
                "Secret": {
                    "table": "secrets",
                    "api": {"enabled": False},
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "value": {"type": "text", "max_length": 500, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    @pytest.fixture
    def mixed_model(self) -> dict[str, Any]:
        """Model with one api-enabled and one api-disabled entity."""
        return {
            "domain": "mixed",
            "entities": {
                "Public": {
                    "table": "publics",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                },
                "Hidden": {
                    "table": "hiddens",
                    "api": {"enabled": False},
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "data": {"type": "text", "max_length": 200, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                },
            },
        }

    @pytest.fixture
    def tests_disabled_model(self) -> dict[str, Any]:
        """Model with tests.enabled: false."""
        return {
            "domain": "notested",
            "entities": {
                "Widget": {
                    "table": "widgets",
                    "tests": {"enabled": False},
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "label": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_api_models_skipped_when_disabled(
        self, api_disabled_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_models(api_disabled_model, config, env, project_root)
        assert result is None

    def test_api_routes_skipped_when_disabled(
        self, api_disabled_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            api_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_api_tests_skipped_when_disabled(
        self, api_disabled_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_tests(
            api_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_mixed_model_only_generates_enabled(
        self, mixed_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        results = generate_api_models(mixed_model, config, env, project_root)

        assert results is not None
        response = next(r for r in results if "response" in r["path"].name)
        assert "class PublicResponse" in response["content"]
        assert "Hidden" not in response["content"]

    def test_mixed_model_routes_only_enabled(
        self, mixed_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_routes(
            mixed_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)

        assert result is not None
        assert "public" in result["content"].lower()
        assert "Hidden" not in result["content"]

    def test_tests_disabled_skips_test_generation(
        self, tests_disabled_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_api_tests(
            tests_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_api_enabled_by_default(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Entities without explicit api config default to enabled."""
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is not None


class TestImmutableEntityGeneration:
    """Test generation for immutable entities (no update endpoint)."""

    def test_immutable_entity_no_update_model(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = {
            "domain": "events",
            "entities": {
                "Event": {
                    "table": "events",
                    "description": "An immutable event log",
                    "mutability": "immutable",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "message": {
                            "type": "text",
                            "max_length": 500,
                            "required": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        request = next(r for r in results if "request" in str(r["path"]))

        assert "CreateEventRequest" in request["content"]
        assert "UpdateEventRequest" not in request["content"]

    def test_immutable_entity_no_put_route(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = {
            "domain": "events",
            "entities": {
                "Event": {
                    "table": "events",
                    "mutability": "immutable",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "message": {
                            "type": "text",
                            "max_length": 500,
                            "required": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        result = generate_api_routes(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        assert "@router.put" not in result["content"]
        assert "async def update_event" not in result["content"]
        # POST and DELETE should still exist
        assert "@router.post" in result["content"]
        assert "@router.delete" in result["content"]


class TestApiTestsEndpointGates:
    """Test endpoint-aware gating in contract.py.j2 (§12.6).

    When `entity.api.endpoints` drops one of {list, create, get}, the
    contract test template should suppress the matching test sections —
    plus all tests that internally seed via POST (which require `create`).
    """

    @staticmethod
    def _model(endpoints: list[str]) -> dict[str, Any]:
        return {
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
                            "unique": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                    "api": {"enabled": True, "endpoints": endpoints},
                }
            },
        }

    def test_skips_create_tests_when_create_endpoint_excluded(
        self, project_env: Any
    ) -> None:
        """Dropping `create` suppresses POST tests AND every seeding-required test."""
        project_root, config, env = project_env
        result = generate_api_tests(
            self._model(["list", "get", "update", "delete"]),
            config,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        content = result["content"]

        # Section 2 (CREATE) tests gone
        assert "def test_post_item_success" not in content
        assert "def test_post_item_with_minimal_data" not in content
        assert "def test_post_item_missing_required_fields" not in content
        assert "def test_post_item_duplicate_unique_constraint" not in content

        # Section 6 (FIELD VALIDATION) tests gone — they POST first
        assert "def test_item_response_format_validation" not in content
        assert "def test_item_field_constraints" not in content
        assert "def test_timestamps_valid" not in content

        # PUT/DELETE success still need a created row (no seeded variant) → gone
        assert "def test_put_item_success" not in content
        assert "def test_put_item_partial_update" not in content
        assert "def test_delete_item_success" not in content
        assert "def test_item_immutable_fields" not in content

        # _not_found variants don't seed → still emitted
        assert "def test_get_item_by_id_not_found" in content
        assert "def test_put_item_not_found" in content
        assert "def test_delete_item_not_found" in content

        # Filtering and get-by-id ARE emitted, in data-free / factory-seeded
        # forms, for read-only entities (list+get, no create, no required FK,
        # no one_to_many): filtering asserts each param is accepted (200), and
        # get-by-id seeds via the factory — so no POST seeding anywhere.
        assert "def test_get_items_list_filtering" in content
        assert "def test_get_item_by_id_success" in content
        assert "Factory.create()" in content
        assert "client.post(" not in content

    def test_skips_list_tests_when_list_endpoint_excluded(
        self, project_env: Any
    ) -> None:
        """Dropping `list` suppresses Section 1 (READ list) tests."""
        project_root, config, env = project_env
        result = generate_api_tests(
            self._model(["create", "get", "update", "delete"]),
            config,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert "def test_get_items_list_success" not in content
        assert "def test_get_items_list_pagination" not in content
        assert "def test_get_items_list_invalid_pagination" not in content
        assert "def test_get_items_list_sorting" not in content
        # Other sections unaffected
        assert "def test_post_item_success" in content
        assert "def test_get_item_by_id_success" in content

    def test_skips_get_by_id_tests_when_get_endpoint_excluded(
        self, project_env: Any
    ) -> None:
        """Dropping `get` suppresses Section 3 (INDIVIDUAL READ) tests."""
        project_root, config, env = project_env
        result = generate_api_tests(
            self._model(["list", "create", "update", "delete"]),
            config,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert "def test_get_item_by_id_success" not in content
        assert "def test_get_item_by_id_not_found" not in content
        # Other sections unaffected
        assert "def test_post_item_success" in content
        assert "def test_delete_item_success" in content


class TestApiTestsCounterRangeRefs:
    """Contract test-data builder resolves counter range min_ref/max_ref.

    A counter `range` constraint declared via min_ref/max_ref (no inline
    min/max) previously crashed `_tests.j2` at `constraint.min | int` on an
    Undefined value. The builder must resolve refs from the constraints dict.
    """

    def _counter_model(self) -> dict[str, Any]:
        return {
            "domain": "shop",
            "entities": {
                "Product": {
                    "table": "products",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "stock": {
                            "type": "counter",
                            "required": True,
                            "constraints": [
                                {
                                    "type": "range",
                                    "min_ref": "QTY_MIN",
                                    "max_ref": "QTY_MAX",
                                }
                            ],
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_counter_range_refs_resolve_to_midpoint(self, project_env: Any) -> None:
        project_root, config, env = project_env
        constraints = {"QTY_MIN": {"value": 1}, "QTY_MAX": {"value": 100}}
        result = generate_api_tests(
            self._counter_model(),
            config,
            env,
            project_root,
            enums={},
            constraints=constraints,
        )
        assert isinstance(result, dict)
        content = result["content"]
        # (1 + 100) // 2 == 50 — refs resolved to a literal midpoint.
        assert '"stock": 50,' in content
        # No bare constant name leaks into the test-data value (the ref names
        # legitimately appear in the constraint-doc docstring, so only the
        # data-value form is asserted absent).
        assert '"stock": QTY_MIN' not in content
        assert '"stock": QTY_MAX' not in content

    def test_counter_range_unresolved_refs_fall_back(self, project_env: Any) -> None:
        """Unresolved refs fall back to a literal default (no crash, no names)."""
        project_root, config, env = project_env
        result = generate_api_tests(
            self._counter_model(),
            config,
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert '"stock": 10,' in content
        assert '"stock": QTY_MIN' not in content
        assert '"stock": QTY_MAX' not in content


class TestApiTestsReferenceTextFiltering:
    """Filter-test coverage for `reference` and unique `text` fields.

    The list endpoint generates exact-match filter params for reference and
    unique-text fields (route.py.j2), so the contract tests must exercise them
    in both the create-mode branch (assert the created value filters) and the
    read-only branch (assert the param is accepted).
    """

    def _read_only_model(self) -> dict[str, Any]:
        """Maker (full CRUD) + read-only Gadget with reference + unique text."""
        return {
            "domain": "gadgets",
            "entities": {
                "Maker": {
                    "table": "makers",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "max_length": 100, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                },
                "Gadget": {
                    "table": "gadgets",
                    # Read-only: no create endpoint.
                    "api": {"enabled": True, "endpoints": ["list", "get"]},
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "code": {
                            "type": "text",
                            "max_length": 50,
                            "required": True,
                            "unique": True,
                        },
                        "maker_id": {
                            "type": "reference",
                            "reference_entity": "Maker",
                            "reference_table": "makers",
                            "required": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                },
            },
        }

    def test_create_mode_reference_filter_uses_created_value(
        self, multi_entity_model: dict[str, Any], project_env: Any
    ) -> None:
        """A required reference field filters by the created row's value."""
        project_root, config, env = project_env
        result = generate_api_tests(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # Post.author_id is a required reference → created-value assertion.
        assert 'ref_val = created_post["author_id"]' in content
        assert "?author_id={ref_val}" in content

    def test_read_only_reference_and_text_filters_are_data_free(
        self, project_env: Any
    ) -> None:
        """Read-only entity: reference + unique-text filters accept literals (200)."""
        project_root, config, env = project_env
        result = generate_api_tests(
            self._read_only_model(), config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # Unique text filter: literal value, no seeding POST.
        assert "/api/v1/gadgets?code=test_value" in content
        # Reference filter: literal UUID, no seeding POST.
        assert (
            "/api/v1/gadgets?maker_id=00000000-0000-0000-0000-000000000000" in content
        )
        # The read-only filtering test must not POST seed data.
        assert "created_gadget" not in content

    def test_nullable_reference_filter_is_skipped_in_create_mode(
        self, project_env: Any
    ) -> None:
        """A nullable reference is skipped (its created value may be None)."""
        model = {
            "domain": "things",
            "entities": {
                "Owner": {
                    "table": "owners",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "name": {"type": "text", "max_length": 50, "required": True},
                    },
                    "timestamps": {"created": True, "updated": True},
                },
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        # Nullable reference with an explicit null default —
                        # must NOT get a created-value filter (`default is
                        # defined` is true for None, so the guard also checks
                        # `is not none`).
                        "owner_id": {
                            "type": "reference",
                            "reference_entity": "Owner",
                            "reference_table": "owners",
                            "required": False,
                            "default": None,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                },
            },
        }
        project_root, config, env = project_env
        result = generate_api_tests(
            model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # No created-value filter for the nullable reference (would 500 on None).
        assert 'created_thing["owner_id"]' not in content


class TestResponseModelFromAttributes:
    """TPL-11: response models are always dict-constructed; from_attributes is dead."""

    def test_response_model_has_no_from_attributes(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """ConfigDict in the response model must NOT set from_attributes=True."""
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)
        assert isinstance(results, list)
        response = next(r for r in results if "response" in r["path"].name)
        assert "from_attributes=True" not in response["content"]
        # ConfigDict is still emitted (for json_schema_extra).
        assert "ConfigDict(" in response["content"]


class TestSortBySecretFieldExclusion:
    """TPL-18: api_exclude_response fields must not appear in the sort_by whitelist."""

    _EXCLUDE_MODEL: ClassVar[dict[str, Any]] = {
        "domain": "accounts",
        "entities": {
            "Account": {
                "table": "accounts",
                "api": {
                    "endpoints": ["list", "create", "get", "update", "delete"],
                },
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "username": {"type": "text", "max_length": 50, "required": True},
                    "password_hash": {
                        "type": "text",
                        "max_length": 256,
                        "api_exclude_response": True,
                    },
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }

    def test_excluded_field_absent_from_sort_whitelist(self, project_env: Any) -> None:
        """A field with api_exclude_response:true must not appear in valid_fields."""
        project_root, config, env = project_env
        result = generate_api_routes(
            self._EXCLUDE_MODEL, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # The valid_fields set should contain public fields...
        assert '"username"' in content
        # ...but must NOT include the secret field.
        assert '"password_hash"' not in content.split("valid_fields")[1].split("}")[0]

    def test_public_field_present_in_sort_whitelist(self, project_env: Any) -> None:
        """Non-excluded fields still appear in the sort_by whitelist."""
        project_root, config, env = project_env
        result = generate_api_routes(
            self._EXCLUDE_MODEL, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # valid_fields block should have username
        valid_block = content.split("valid_fields")[1].split("}")[0]
        assert '"username"' in valid_block


class TestSortByInvalidFieldRaises422:
    """TPL-19: an unknown sort_by value must raise HTTPException(422), not be silently
    ignored."""

    _MODEL: ClassVar[dict[str, Any]] = {
        "domain": "posts",
        "entities": {
            "Post": {
                "table": "posts",
                "api": {"endpoints": ["list", "create", "get", "update", "delete"]},
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "title": {"type": "text", "max_length": 200, "required": True},
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }

    def test_invalid_sort_by_raises_http_exception(self, project_env: Any) -> None:
        """The generated list handler must raise HTTPException(422) when sort_by is
        not in valid_fields, so callers get a structured error instead of silence."""
        project_root, config, env = project_env
        result = generate_api_routes(
            self._MODEL, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        # The else branch must exist after the `if sort_by in valid_fields` check.
        assert "else:" in content
        assert "raise HTTPException(" in content
        assert "status_code=422" in content

    def test_valid_sort_by_path_still_present(self, project_env: Any) -> None:
        """The happy path — sort_by in valid_fields — is not removed."""
        project_root, config, env = project_env
        result = generate_api_routes(
            self._MODEL, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert "if sort_by in valid_fields:" in content
        assert "sort_column = getattr(" in content
