"""Tests for individual code generators."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from model_generator.generators import (
    generate_api_init,
    generate_api_models,
    generate_api_routes,
    generate_api_tests,
    generate_constraints,
    generate_database_model,
    generate_enums,
    generate_factories,
    generate_init,
    generate_migration_autogen,
    generate_migration_init,
)
from model_generator.generators.constraints import (
    _extract_ref,
    _extract_regex_ref,
    extract_constraint_refs,
)
from model_generator.generators.infrastructure import (
    generate_base,
    generate_engine,
    generate_errors,
    generate_infrastructure,
    generate_main,
    generate_pyproject,
    generate_test_conftest_root,
    generate_types,
    generate_validators,
)
from model_generator.utils import get_template_env, load_config


@pytest.fixture
def minimal_model():
    """Minimal model for testing individual generators."""
    return {
        "domain": "items",
        "description": "Test items domain",
        "entities": {
            "Item": {
                "table": "items",
                "description": "A test item",
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
                    "count": {
                        "type": "counter",
                        "default": 0,
                    },
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }


@pytest.fixture
def scoped_model():
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


@pytest.fixture
def project_env(tmp_path):
    """Set up a temporary project with config and template environment.

    Pinned to per-domain layout so existing assertions about file shape
    (e.g., `items.py`, not `item.py`) stay precise as the default flips.
    """
    config_data = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
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
    config = load_config("python-fastapi")
    env = get_template_env("python-fastapi")
    os.chdir(original_cwd)

    return tmp_path, config, env


class TestDatabaseGenerator:
    """Test database model generation."""

    def test_generates_model_file(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)

        assert result is not None
        assert result["path"] == project_root / "src/database/models/items.py"
        assert "class Item(Base):" in result["content"]
        assert '__tablename__ = "items"' in result["content"]

    def test_contains_fields(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)

        assert "name: Mapped[str] = mapped_column(String(100)" in result["content"]
        assert "mapped_column(Integer" in result["content"]

    def test_contains_timestamps(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)

        assert "created_at" in result["content"]
        assert "updated_at" in result["content"]
        assert "server_default=func.now()" in result["content"]

    def test_path_uses_domain_default_when_key_absent(self, project_env):
        project_root, config, env = project_env
        model_no_domain = {"description": "test", "entities": {}}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_database_model(model_no_domain, config, env, project_root)

        output_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == output_dir / "models.py"


class TestGenerateInit:
    """Test __init__.py generation for database models."""

    _FAKE_DOMAINS = [
        {
            "name": "items",
            "file": "items",
            "section": None,
            "entities": ["Item", "ItemAlt"],
        }
    ]

    def test_includes_current_model_when_no_files_on_disk(
        self, minimal_model, project_env
    ):
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(minimal_model, config, env, project_root)
        # Even with no files on disk, init should include the current model
        assert result is not None
        assert "from .items import" in result["content"]
        assert "Item" in result["content"]

    def test_result_structure(self, minimal_model, project_env):
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files",
            return_value=self._FAKE_DOMAINS,
        ):
            result = generate_init(minimal_model, config, env, project_root)

        output_dir = project_root / config["paths"]["database_models"]
        assert result is not None
        assert result["path"] == output_dir / "__init__.py"
        assert result["mode"] == "write"
        assert result["domain_count"] == 1
        assert result["entity_count"] == 2
        assert "from .items import" in result["content"]

    def test_content_uses_config(self, minimal_model, project_env):
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files",
            return_value=self._FAKE_DOMAINS,
        ):
            result = generate_init(minimal_model, config, env, project_root)
        assert result is not None
        assert "Test Project" in result["content"]


class TestFactoryGenerator:
    """Test factory generation."""

    def test_generates_factory_file(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_factories(minimal_model, config, env, project_root)

        db_models_dir = project_root / config["paths"]["database_models"]
        assert result is not None
        assert result["path"] == db_models_dir / "factories" / "items.py"

    def test_factory_content(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_factories(minimal_model, config, env, project_root)

        assert "ItemFactory" in result["content"]
        assert "factory.Factory" in result["content"] or "Factory" in result["content"]

    def test_path_uses_domain_default_when_key_absent(self, project_env):
        project_root, config, env = project_env
        model_no_domain = {"description": "test", "entities": {}}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_factories(model_no_domain, config, env, project_root)

        db_models_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == db_models_dir / "factories" / "models.py"


@pytest.fixture
def multi_entity_model():
    """Two-entity model exercising both reference fields and one_to_many siblings.

    Post → Author via reference field (drives SubFactory imports).
    Author → Post via one_to_many (drives create_related sibling-factory imports).
    """
    return {
        "domain": "blog",
        "description": "Blog domain with authored posts",
        "entities": {
            "Author": {
                "table": "authors",
                "description": "Post author",
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
                "relationships": {
                    "posts": {
                        "type": "one_to_many",
                        "target": "Post",
                        "back_populates": "author",
                    },
                },
                "timestamps": {"created": True, "updated": True},
            },
            "Post": {
                "table": "posts",
                "description": "Authored post",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "title": {
                        "type": "text",
                        "max_length": 200,
                        "required": True,
                    },
                    "author_id": {
                        "type": "reference",
                        "reference_entity": "Author",
                        "reference_table": "authors",
                        "required": True,
                    },
                },
                "relationships": {
                    "author": {
                        "type": "many_to_one",
                        "target": "Author",
                        "back_populates": "posts",
                    },
                },
                "timestamps": {"created": True, "updated": True},
            },
        },
    }


@pytest.fixture
def project_env_per_entity(tmp_path):
    """Same as project_env but with generation.layout pinned to per-entity."""
    config_data = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
        "generation": {"layout": "per-entity"},
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
    config = load_config("python-fastapi")
    env = get_template_env("python-fastapi")
    os.chdir(original_cwd)

    return tmp_path, config, env


class TestDatabaseGeneratorPerEntity:
    """Per-entity database model emission."""

    def test_returns_list_of_dicts(self, multi_entity_model, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_one_file_per_entity_using_snake_case(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        output_dir = project_root / config["paths"]["database_models"]
        paths = {r["path"] for r in result}
        assert output_dir / "author.py" in paths
        assert output_dir / "post.py" in paths

    def test_each_file_contains_only_its_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "class Author(Base):" in by_name["author.py"]
        assert "class Post" not in by_name["author.py"]
        assert "class Post(Base):" in by_name["post.py"]
        assert "class Author" not in by_name["post.py"]

    def test_section_divider_omitted(self, multi_entity_model, project_env_per_entity):
        """section_divider is gated on per-domain to avoid N redundant headers.

        The docstring header at the top of each file still contains the
        domain name; the section divider is a separate full-width banner
        emitted around the entity classes, which is what should disappear.
        """
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        divider_banner = "# " + "=" * 76 + "\n# BLOG MODELS"
        for entry in result:
            assert divider_banner not in entry["content"]


class TestGenerateInitPerEntity:
    """Per-entity __init__.py emission."""

    def test_emits_one_import_line_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(multi_entity_model, config, env, project_root)
        assert result is not None
        assert "from .author import" in result["content"]
        assert "from .post import" in result["content"]
        assert result["domain_count"] == 2
        assert result["entity_count"] == 2

    def test_no_none_banner_emitted(self, multi_entity_model, project_env_per_entity):
        """section=None must suppress the banner, not render '# None'."""
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(multi_entity_model, config, env, project_root)
        assert result is not None
        assert "# None" not in result["content"]

    def test_existing_per_entity_files_not_redeclared(
        self, multi_entity_model, project_env_per_entity
    ):
        """If scan_model_files lists 'author', model contributes only Post."""
        project_root, config, env = project_env_per_entity
        existing = [
            {
                "name": "author",
                "file": "author",
                "section": None,
                "entities": ["Author"],
            }
        ]
        with patch(
            "model_generator.generators.database.scan_model_files",
            return_value=existing,
        ):
            result = generate_init(multi_entity_model, config, env, project_root)
        assert result is not None
        assert result["domain_count"] == 2  # author (existing) + post (added)
        assert "from .author import" in result["content"]
        assert "from .post import" in result["content"]


class TestFactoryGeneratorPerEntity:
    """Per-entity factory emission and cross-entity import preservation."""

    def test_returns_list_with_one_factory_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"author.py", "post.py"}

    def test_db_model_imports_use_per_entity_paths(
        self, multi_entity_model, project_env_per_entity
    ):
        """Factory imports the model from {db_models}.{entity_snake}, not {domain}."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "from src.database.models.author import Author" in by_name["author.py"]
        assert "from src.database.models.post import Post" in by_name["post.py"]
        # Per-domain import shape must NOT appear.
        assert "from src.database.models.blog import" not in by_name["author.py"]
        assert "from src.database.models.blog import" not in by_name["post.py"]

    def test_subfactory_reference_imports_sibling_factory(
        self, multi_entity_model, project_env_per_entity
    ):
        """Post has author_id reference → post.py imports AuthorFactory."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        post_content = next(r["content"] for r in result if r["path"].name == "post.py")
        assert "from .author import AuthorFactory" in post_content
        assert "factory.SubFactory(AuthorFactory)" in post_content

    def test_create_related_preserved_via_sibling_entities(
        self, multi_entity_model, project_env_per_entity
    ):
        """Author has one_to_many → Post; create_related must survive the
        per-entity slicing of model.entities, and PostFactory must be imported."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        author_content = next(
            r["content"] for r in result if r["path"].name == "author.py"
        )
        assert "from .post import PostFactory" in author_content
        assert "PostFactory.create_batch(count, author=obj)" in author_content


class TestApiModelsGeneratorPerEntity:
    """Per-entity api-models emission: two files per entity."""

    def test_returns_one_response_and_one_request_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 4
        names = {r["path"].name for r in result}
        assert names == {
            "author_response.py",
            "author_requests.py",
            "post_response.py",
            "post_requests.py",
        }

    def test_response_file_contains_only_one_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        """author_response.py contains AuthorResponse and not PostResponse."""
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        author_resp = next(
            r["content"] for r in result if r["path"].name == "author_response.py"
        )
        assert "class AuthorResponse(BaseModel):" in author_resp
        assert "class PostResponse" not in author_resp

    def test_request_file_contains_only_one_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        """author_requests.py contains Create/UpdateAuthorRequest and not Post."""
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        author_req = next(
            r["content"] for r in result if r["path"].name == "author_requests.py"
        )
        assert "class CreateAuthorRequest(BaseModel):" in author_req
        assert "class UpdateAuthorRequest(BaseModel):" in author_req
        assert "CreatePostRequest" not in author_req


class TestGenerateApiInitPerEntity:
    """Per-entity api __init__.py emission."""

    def test_emits_one_import_block_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.api.scan_api_model_files", return_value=[]
        ):
            result = generate_api_init(multi_entity_model, config, env, project_root)
        assert result is not None
        assert "from .author_response import" in result["content"]
        assert "from .author_requests import" in result["content"]
        assert "from .post_response import" in result["content"]
        assert "from .post_requests import" in result["content"]
        assert result["domain_count"] == 2

    def test_no_none_banner_emitted(self, multi_entity_model, project_env_per_entity):
        """section=None must suppress the banner, not render '# None'."""
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.api.scan_api_model_files", return_value=[]
        ):
            result = generate_api_init(multi_entity_model, config, env, project_root)
        assert result is not None
        assert "# None" not in result["content"]

    def test_existing_per_entity_files_not_redeclared(
        self, multi_entity_model, project_env_per_entity
    ):
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
        assert result is not None
        assert result["domain_count"] == 2  # author (existing) + post (added)
        assert "from .author_response import" in result["content"]
        assert "from .post_response import" in result["content"]


class TestApiRoutesGeneratorPerEntity:
    """Per-entity api routes emission."""

    def test_returns_list_with_one_route_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"author.py", "post.py"}

    def test_db_model_imports_use_per_entity_paths(
        self, multi_entity_model, project_env_per_entity
    ):
        """DB model is imported from {db_models}.{entity_snake}, not {domain}."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        by_name = {r["path"].name: r["content"] for r in result}
        assert "from src.database.models.author import Author" in by_name["author.py"]
        assert "from src.database.models.post import Post" in by_name["post.py"]
        # Per-domain import shape must NOT appear.
        assert "from src.database.models.blog import" not in by_name["author.py"]
        assert "from src.database.models.blog import" not in by_name["post.py"]

    def test_api_model_imports_use_per_entity_paths(
        self, multi_entity_model, project_env_per_entity
    ):
        """API models are imported from per-entity files, not per-domain combined."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        by_name = {r["path"].name: r["content"] for r in result}
        assert (
            "from src.api.models.author_requests import CreateAuthorRequest"
            in by_name["author.py"]
        )
        assert (
            "from src.api.models.author_response import AuthorResponse"
            in by_name["author.py"]
        )
        # Per-domain combined imports must NOT appear.
        assert "from src.api.models.blog_requests" not in by_name["author.py"]
        assert "from src.api.models.blog_response" not in by_name["author.py"]

    def test_content_isolated_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        """author.py only has Author handlers; post.py only has Post handlers."""
        project_root, config, env = project_env_per_entity
        result = generate_api_routes(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        by_name = {r["path"].name: r["content"] for r in result}
        assert "async def create_author" in by_name["author.py"]
        assert "async def create_post" not in by_name["author.py"]
        assert "async def create_post" in by_name["post.py"]
        assert "async def create_author" not in by_name["post.py"]


class TestApiTestsGeneratorPerEntity:
    """Per-entity api contract test emission."""

    def test_returns_list_with_one_test_file_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        project_root, config, env = project_env_per_entity
        result = generate_api_tests(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"test_author_api.py", "test_post_api.py"}

    def test_content_isolated_per_entity(
        self, multi_entity_model, project_env_per_entity
    ):
        """test_author_api.py only references Author response/request models."""
        project_root, config, env = project_env_per_entity
        result = generate_api_tests(
            multi_entity_model, config, env, project_root, enums={}, constraints={}
        )
        by_name = {r["path"].name: r["content"] for r in result}
        assert "AuthorResponse" in by_name["test_author_api.py"]
        assert "PostResponse" not in by_name["test_author_api.py"]
        assert "PostResponse" in by_name["test_post_api.py"]
        assert "AuthorResponse" not in by_name["test_post_api.py"]


class TestApiModelsGenerator:
    """Test API models (request/response) generation."""

    def test_generates_two_files(self, minimal_model, project_env):
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)

        assert isinstance(results, list)
        assert len(results) == 2
        filenames = [str(r["path"].name) for r in results]
        assert "items_response.py" in filenames
        assert "items_requests.py" in filenames

    def test_response_model_content(self, minimal_model, project_env):
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)
        response = next(r for r in results if "response" in r["path"].name)

        assert "class ItemResponse(BaseModel):" in response["content"]

    def test_request_model_content(self, minimal_model, project_env):
        project_root, config, env = project_env
        results = generate_api_models(minimal_model, config, env, project_root)
        request = next(r for r in results if "request" in r["path"].name)

        assert "class CreateItemRequest(BaseModel):" in request["content"]
        assert "class UpdateItemRequest(BaseModel):" in request["content"]

    def test_field_description_not_truncated(self, project_env):
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
        request = next(r for r in results if "request" in r["path"].name)
        assert long_desc in request["content"]


class TestApiModelsGeneratorScope:
    """Test API request model generation when entities declare api.scope."""

    def _request_content(self, model, project_env):
        project_root, config, env = project_env
        results = generate_api_models(model, config, env, project_root)
        return next(r for r in results if "request" in r["path"].name)["content"]

    def test_owner_field_excluded_from_create_request(self, scoped_model, project_env):
        """owner_field is set by the handler, not by the API caller."""
        content = self._request_content(scoped_model, project_env)
        create_start = content.index("class CreateWidgetRequest")
        update_start = content.index("class UpdateWidgetRequest")
        create_block = content[create_start:update_start]
        assert "owner_id" not in create_block

    def test_owner_field_excluded_from_update_request(self, scoped_model, project_env):
        """owner_field is immutable from the API; update payloads cannot reassign it."""
        content = self._request_content(scoped_model, project_env)
        update_start = content.index("class UpdateWidgetRequest")
        update_block = content[update_start:]
        assert "owner_id" not in update_block


class TestApiRoutesGenerator:
    """Test API routes generation."""

    def test_generates_route_file(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )

        assert result is not None
        assert result["path"] == project_root / "src/api/routes/items.py"
        assert "@router.post" in result["content"]
        assert "@router.get" in result["content"]
        assert "@router.put" in result["content"]
        assert "@router.delete" in result["content"]

    def test_crud_endpoints(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )

        assert "async def create_item" in result["content"]
        assert "async def list_items" in result["content"]
        assert "async def get_item" in result["content"]
        assert "async def update_item" in result["content"]
        assert "async def delete_item" in result["content"]


class TestApiRoutesGeneratorScope:
    """Test API route generation when entities declare api.scope."""

    AUTH_PATH = "backend.src.auth.get_current_user"

    def _config_with_auth(self, config):
        return {**config, "auth": {"dependency_path": self.AUTH_PATH}}

    def test_imports_auth_dependency(self, scoped_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert "from backend.src.auth import get_current_user" in result["content"]

    def test_all_handlers_receive_current_user(self, scoped_model, project_env):
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
        assert (
            result["content"].count("current_user: Any = Depends(get_current_user)")
            == 5
        )

    def test_create_handler_auto_sets_owner_field(self, scoped_model, project_env):
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
        assert "widget.owner_id = current_user.id" in result["content"]

    def test_list_query_filters_by_owner(self, scoped_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            scoped_model,
            self._config_with_auth(config),
            env,
            project_root,
            enums={},
            constraints={},
        )
        assert (
            "stmt = stmt.where(Widget.owner_id == current_user.id)" in result["content"]
        )
        assert (
            "count_stmt = count_stmt.where(Widget.owner_id == current_user.id)"
            in result["content"]
        )

    def test_default_miss_status_uses_not_found(self, scoped_model, project_env):
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
        assert "if widget.owner_id != current_user.id:" in result["content"]
        assert "from fastapi import HTTPException" not in result["content"]

    def test_custom_miss_status_uses_http_exception(self, scoped_model, project_env):
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
        assert "from fastapi import HTTPException" in result["content"]
        assert "status_code=403" in result["content"]


class TestValidateAuthConfig:
    """Test the _validate_auth_config helper."""

    def test_no_scope_passes_without_auth_config(self):
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Item": {"api": {"enabled": True}}}}
        _validate_auth_config(model, config={})  # Should not exit

    def test_scope_with_auth_config_passes(self):
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        config = {"auth": {"dependency_path": "x.y.z"}}
        _validate_auth_config(model, config)  # Should not exit

    def test_scope_without_auth_config_exits(self, capsys):
        from model_generator.generate import _validate_auth_config

        model = {"entities": {"Widget": {"api": {"scope": {"owner_field": "user_id"}}}}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_config(model, config={})
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "Widget" in out
        assert "auth.dependency_path" in out
        assert "api.scope" in out

    def test_scope_with_dotless_auth_path_exits(self, capsys):
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

    def _user_model(self):
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

    def test_no_strategy_passes(self):
        from model_generator.generate import _validate_auth_strategy

        _validate_auth_strategy([self._user_model()], config={})

    def test_bcrypt_session_with_user_and_pepper_passes(self):
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        _validate_auth_strategy([self._user_model()], config)

    def test_unknown_strategy_exits(self, capsys):
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "magic-jwt", "pepper_env": "X"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "magic-jwt" in out
        assert "bcrypt-session" in out

    def test_missing_pepper_env_exits(self, capsys):
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy([self._user_model()], config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "pepper_env" in out

    def test_missing_user_entity_exits(self, capsys):
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        models = [{"entities": {"Item": {"fields": {}}}}]
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy(models, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "User" in out

    def test_user_without_password_hash_exits(self, capsys):
        from model_generator.generate import _validate_auth_strategy

        config = {"auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        models = [{"entities": {"User": {"fields": {"username": {"type": "text"}}}}}]
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_strategy(models, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "password_hash" in out

    def test_per_domain_layout_with_strategy_exits(self, capsys):
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
    def test_user_missing_router_field_exits(self, capsys, missing):
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


class TestValidateGenerationConfig:
    """Test the _validate_generation_config helper."""

    def test_default_layout_passes(self):
        from model_generator.generate import _validate_generation_config

        _validate_generation_config(config={})

    def test_per_entity_passes(self):
        from model_generator.generate import _validate_generation_config

        _validate_generation_config({"generation": {"layout": "per-entity"}})

    def test_per_domain_passes(self):
        from model_generator.generate import _validate_generation_config

        _validate_generation_config({"generation": {"layout": "per-domain"}})

    def test_unknown_layout_exits(self, capsys):
        from model_generator.generate import _validate_generation_config

        with pytest.raises(SystemExit) as excinfo:
            _validate_generation_config({"generation": {"layout": "weird"}})
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "weird" in out
        assert "generation.layout" in out


class TestApiTestsGenerator:
    """Test contract test generation."""

    def test_generates_test_file(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_api_tests(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )

        assert result is not None
        assert result["path"] == project_root / "tests/api/test_items_api.py"

    def test_test_content(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_api_tests(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )

        assert "class TestItemsAPI:" in result["content"]
        assert "def test_get_items_list_success" in result["content"]
        assert "def test_post_item_success" in result["content"]
        assert "def test_get_item_by_id_success" in result["content"]
        assert "def test_delete_item_success" in result["content"]

    def test_skips_put_tests_when_update_endpoint_excluded(self, project_env):
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
        assert "def test_put_item" not in result["content"]
        assert "def test_item_immutable_fields" not in result["content"]
        # Sections that ARE in endpoints should still emit
        assert "def test_delete_item" in result["content"]
        assert "def test_post_item" in result["content"]

    def test_skips_delete_tests_when_delete_endpoint_excluded(self, project_env):
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
        assert "def test_delete_item" not in result["content"]
        assert "def test_put_item" not in result["content"]
        # READ + CREATE still emitted
        assert "def test_post_item" in result["content"]
        assert "def test_get_item_by_id_success" in result["content"]


class TestApiTestsGeneratorScope:
    """Test contract test generation when entities declare api.scope."""

    AUTH_PATH = "backend.src.auth.get_current_user"

    def test_main_import_module_derived_from_paths(self, scoped_model, project_env):
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
        assert "from src.app import app" in result["content"]
        assert "from src.main import app" not in result["content"]


class TestApiEnabledFiltering:
    """Test that api.enabled: false skips API generation."""

    @pytest.fixture
    def api_disabled_model(self):
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
    def mixed_model(self):
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
    def tests_disabled_model(self):
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

    def test_api_models_skipped_when_disabled(self, api_disabled_model, project_env):
        project_root, config, env = project_env
        result = generate_api_models(api_disabled_model, config, env, project_root)
        assert result is None

    def test_api_routes_skipped_when_disabled(self, api_disabled_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            api_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_api_tests_skipped_when_disabled(self, api_disabled_model, project_env):
        project_root, config, env = project_env
        result = generate_api_tests(
            api_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_mixed_model_only_generates_enabled(self, mixed_model, project_env):
        project_root, config, env = project_env
        results = generate_api_models(mixed_model, config, env, project_root)

        assert results is not None
        response = next(r for r in results if "response" in r["path"].name)
        assert "class PublicResponse" in response["content"]
        assert "Hidden" not in response["content"]

    def test_mixed_model_routes_only_enabled(self, mixed_model, project_env):
        project_root, config, env = project_env
        result = generate_api_routes(
            mixed_model, config, env, project_root, enums={}, constraints={}
        )

        assert result is not None
        assert "public" in result["content"].lower()
        assert "Hidden" not in result["content"]

    def test_tests_disabled_skips_test_generation(
        self, tests_disabled_model, project_env
    ):
        project_root, config, env = project_env
        result = generate_api_tests(
            tests_disabled_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is None

    def test_api_enabled_by_default(self, minimal_model, project_env):
        """Entities without explicit api config default to enabled."""
        project_root, config, env = project_env
        result = generate_api_routes(
            minimal_model, config, env, project_root, enums={}, constraints={}
        )
        assert result is not None


class TestEnumsGenerator:
    """Test enum generation."""

    def test_creates_enums_file(self, minimal_model, project_env):
        """Generate enums when _shared/enums.json exists."""
        project_root, config, env = project_env

        # Create model dir with shared enums
        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [
                        {"name": "STANDARD", "value": "STANDARD"},
                        {"name": "PREMIUM", "value": "PREMIUM"},
                    ],
                }
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        result = generate_enums(minimal_model, config, env, project_root, model_file)

        assert result is not None
        assert result["mode"] == "write"
        assert result["skipped"] == 0
        assert result["new_count"] == 1
        enums_file = project_root / config["paths"]["database_models"] / "enums.py"
        assert result["path"] == enums_file
        assert "class ItemType(StrEnum):" in result["content"]
        assert "STANDARD" in result["content"]

    def test_append_mode_adds_new_enums(self, minimal_model, project_env):
        """Append mode: existing enums skipped, new ones included in result."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [{"name": "STANDARD", "value": "STANDARD"}],
                },
                "OrderStatus": {
                    "description": "Status of order",
                    "values": [{"name": "PENDING", "value": "PENDING"}],
                },
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        enums_file = output_dir / "enums.py"
        enums_file.write_text(
            "from enum import StrEnum\n"
            "class ItemType(StrEnum):\n"
            "    STANDARD = 'STANDARD'\n"
        )

        result = generate_enums(minimal_model, config, env, project_root, model_file)

        assert result is not None
        assert result["mode"] == "append"
        assert result["path"] == enums_file
        assert result["new_count"] == 1
        assert result["skipped"] == 1
        assert "class OrderStatus(StrEnum):" in result["content"]
        assert "ItemType" not in result["content"]

    def test_no_enums_returns_none(self, minimal_model, project_env):
        """Generate enums when no _shared/enums.json exists."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        models_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is None

    def test_append_mode_skips_existing(self, minimal_model, project_env):
        """Enums that already exist in file are skipped."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type of item",
                    "values": [{"name": "STANDARD", "value": "STANDARD"}],
                }
            }
        }
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))

        # Create existing enums file
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\n"
            "class ItemType(StrEnum):\n"
            "    STANDARD = 'STANDARD'\n"
        )

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is None  # All enums already exist

    def _setup_enums(self, project_root, config, minimal_model, enums_data):
        """Helper: create model file and shared enums.json, return model_file path."""
        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))
        return model_file

    def test_create_mode_includes_imports(self, minimal_model, project_env):
        """Create mode output includes StrEnum import."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                }
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is not None
        assert "from enum import StrEnum" in result["content"]

    def test_create_mode_includes_section_header(self, minimal_model, project_env):
        """Create mode output includes ENUMS section divider."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                }
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_append_content_starts_with_newline(self, minimal_model, project_env):
        """Append mode content starts with newline separator."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                },
                "OtherType": {
                    "description": "Other",
                    "values": [{"name": "B", "value": "B"}],
                },
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\nclass ItemType(StrEnum):\n    A = 'A'\n"
        )
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is not None
        assert result["content"].startswith("\n")

    def test_append_includes_enums_section_header(self, minimal_model, project_env):
        """Append mode content includes ENUMS section divider."""
        project_root, config, env = project_env
        enums_data = {
            "enums": {
                "ItemType": {
                    "description": "Type",
                    "values": [{"name": "A", "value": "A"}],
                },
                "OtherType": {
                    "description": "Other",
                    "values": [{"name": "B", "value": "B"}],
                },
            }
        }
        model_file = self._setup_enums(project_root, config, minimal_model, enums_data)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True)
        (output_dir / "enums.py").write_text(
            "from enum import StrEnum\nclass ItemType(StrEnum):\n    A = 'A'\n"
        )
        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_no_enums_prints_message(self, minimal_model, project_env, capsys):
        """When no enums file exists, prints informational message."""
        project_root, config, env = project_env
        models_dir = project_root / "models"
        models_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))
        # No _shared dir → load_shared_enums returns {}

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        captured = capsys.readouterr()
        assert result is None
        expected = "  ℹ️  No enums found in models/_shared/enums.json"
        assert captured.out.rstrip("\n") == expected


class TestConstraintsGenerator:
    """Test constraint generation."""

    def test_no_constraints_returns_none(self, minimal_model, project_env):
        """Model without constraints returns None."""
        project_root, config, env = project_env
        # No _shared/constraints.json and no field constraints
        result = generate_constraints(minimal_model, config, env, project_root)
        assert result is None

    def test_generates_constraints(self, project_env):
        """Model with constraint refs generates constraints file."""
        project_root, config, env = project_env

        model = {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "label": {
                            "type": "text",
                            "max_length": 50,
                            "required": True,
                            "constraints": [
                                {"type": "length", "min_ref": "LABEL_MIN_LENGTH"}
                            ],
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        # Create shared constraints
        shared_dir = project_root / "models" / "_shared"
        shared_dir.mkdir(parents=True)
        constraints_data = {
            "constraints": {
                "LABEL": {
                    "description": "Label length constraints",
                    "min": {
                        "name": "LABEL_MIN_LENGTH",
                        "type": "length",
                        "value": 2,
                        "description": "Minimum label length",
                    },
                }
            }
        }
        (shared_dir / "constraints.json").write_text(json.dumps(constraints_data))

        original_cwd = os.getcwd()
        os.chdir(project_root)
        try:
            result = generate_constraints(model, config, env, project_root)
        finally:
            os.chdir(original_cwd)

        assert result is not None
        assert "LABEL_MIN_LENGTH" in result["content"]
        assert result["mode"] == "write"
        output_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == output_dir / "constraints.py"
        assert result["new_count"] == 1
        assert result["skipped"] == 0
        assert "# CONSTRAINTS" in result["content"]
        assert "from decimal import Decimal" in result["content"]
        assert "def validate_percentage" in result["content"]

    def test_append_mode_for_existing_file(self, project_env):
        """When constraints.py already exists, new refs are appended, not full file."""
        project_root, config, env = project_env

        model = {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "price": {
                            "type": "decimal",
                            "constraints": [
                                {
                                    "type": "decimal",
                                    "min_ref": "PRICE_MIN",
                                    "max_ref": "PRICE_MAX",
                                }
                            ],
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        shared_dir = project_root / "models" / "_shared"
        shared_dir.mkdir(parents=True)
        constraints_data: dict = {"constraints": {}}
        (shared_dir / "constraints.json").write_text(json.dumps(constraints_data))

        # Create an existing constraints.py (but without the refs we need)
        output_dir = project_root / config["paths"]["database_models"]
        output_dir.mkdir(parents=True, exist_ok=True)
        constraints_file = output_dir / "constraints.py"
        constraints_file.write_text("# existing\nSOME_OTHER = 1\n")

        original_cwd = os.getcwd()
        os.chdir(project_root)
        try:
            result = generate_constraints(model, config, env, project_root)
        finally:
            os.chdir(original_cwd)

        assert result is not None
        assert result["mode"] == "append"
        assert result["path"] == constraints_file
        assert result["content"].startswith("\n")
        assert result["new_count"] == 2
        assert result["skipped"] == 0
        assert "# CONSTRAINTS" in result["content"]
        # Helpers should NOT be included when appending
        assert "validate_percentage" not in result["content"]


class TestConstraintExtraction:
    """Unit tests for constraint extraction helpers."""

    def _make_refs(self):
        return [], set()

    def test_extract_ref_type_from_ref_def(self):
        """When ref_def has 'type', it takes priority over constraint type."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF", "type": "decimal"},
            "min_ref",
            {"MY_REF": {"type": "length", "value": 3}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "length"

    def test_extract_ref_type_from_constraint(self):
        """When ref_def lacks 'type', falls back to constraint type."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF", "type": "range"},
            "min_ref",
            {"MY_REF": {}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "range"

    def test_extract_ref_type_default_decimal(self):
        """When neither ref_def nor constraint has 'type', defaults to 'decimal'."""
        refs, seen = self._make_refs()
        _extract_ref(
            {"min_ref": "MY_REF"},
            "min_ref",
            {"MY_REF": {}},
            "my_field",
            refs,
            seen,
            is_min=True,
        )
        assert refs[0]["type"] == "decimal"

    def test_extract_regex_ref_unknown_ref_ok(self):
        """When regex_ref is not in shared_constraints, falls back to empty dict."""
        refs, seen = self._make_refs()
        _extract_regex_ref(
            {"regex_ref": "UNKNOWN_PATTERN"},
            {},
            "my_field",
            refs,
            seen,
        )
        assert len(refs) == 1
        assert refs[0]["field"] == "my_field"
        assert refs[0]["name"] == "UNKNOWN_PATTERN"

    def test_extract_regex_ref_deduplication(self):
        """Same regex_ref is only extracted once."""
        refs, seen = self._make_refs()
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field1", refs, seen)
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field2", refs, seen)
        assert len(refs) == 1

    def test_extract_constraint_refs_field_name_propagates(self):
        """Field name from model is correctly propagated to extracted refs."""
        model = {
            "entities": {
                "Thing": {
                    "fields": {
                        "price": {
                            "constraints": [{"type": "decimal", "min_ref": "PRICE_MIN"}]
                        }
                    }
                }
            }
        }
        refs = extract_constraint_refs(model, {})
        assert len(refs) == 1
        assert refs[0]["field"] == "price"


class TestMigrationGenerator:
    """Test Alembic migration init generation."""

    def test_creates_migration_directories(self, minimal_model, project_env):
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)

        migrations_dir = project_root / "alembic"
        assert migrations_dir.is_dir()
        assert (migrations_dir / "versions").is_dir()

    def test_returns_all_migration_files(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)

        assert isinstance(result, list)
        assert len(result) == 5
        paths = [r["path"] for r in result]
        migrations_dir = project_root / "alembic"
        assert project_root / "alembic.ini" in paths
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_env_py_content_uses_config(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)

        migrations_dir = project_root / "alembic"
        env_py = next(r for r in result if r["path"] == migrations_dir / "env.py")
        # config.paths.database_models is used in the import path
        assert "src.database.models" in env_py["content"]

    def test_custom_migrations_path(self, minimal_model, project_env):
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "custom_migrations").is_dir()
        assert (project_root / "custom_migrations" / "versions").is_dir()

    def test_alembic_ini_content_uses_migrations_path(self, minimal_model, project_env):
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        result = generate_migration_init(minimal_model, config, env, project_root)

        ini = next(r for r in result if r["path"] == project_root / "alembic.ini")
        assert "script_location = custom_migrations" in ini["content"]

    def test_default_path_when_key_absent(self, minimal_model, project_env, tmp_path):
        project_root, config, env = project_env
        del config["paths"]["migrations"]
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "alembic").is_dir()
        assert (project_root / "alembic" / "versions").is_dir()

    def test_creates_nested_project_root(self, minimal_model, project_env):
        project_root, config, env = project_env
        deep_root = project_root / "subdir"
        generate_migration_init(minimal_model, config, env, deep_root)

        assert (deep_root / "alembic").is_dir()
        assert (deep_root / "alembic" / "versions").is_dir()

    def test_idempotent_mkdir(self, minimal_model, project_env):
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)
        # Second call must not raise FileExistsError
        generate_migration_init(minimal_model, config, env, project_root)

    def test_gitkeep_content_is_empty(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)

        migrations_dir = project_root / "alembic"
        gitkeep = next(
            r for r in result if r["path"] == migrations_dir / "versions" / ".gitkeep"
        )
        assert gitkeep["content"] == ""


class TestMigrationAutogen:
    """Test generate_migration_autogen."""

    def test_returns_none_when_not_initialized(self, minimal_model, project_env):
        project_root, config, env = project_env
        result = generate_migration_autogen(minimal_model, config, env, project_root)

        assert result is None

    def test_returns_dict_when_initialized(self, minimal_model, project_env):
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        result = generate_migration_autogen(minimal_model, config, env, project_root)

        assert result is not None
        assert "info" in result
        assert "instructions" in result
        assert result["info"] == (
            "Migration autogeneration requires DATABASE_URL and should be run manually"
        )
        assert "DATABASE_URL" in result["instructions"]

    def test_warning_message_when_not_initialized(
        self, minimal_model, project_env, capsys
    ):
        project_root, config, env = project_env
        generate_migration_autogen(minimal_model, config, env, project_root)
        captured = capsys.readouterr()

        assert (
            captured.out.rstrip("\n")
            == "  ⚠️  Alembic not initialized. Run with --target migration-init first."
        )

    def test_progress_message_when_initialized(
        self, minimal_model, project_env, capsys
    ):
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        generate_migration_autogen(minimal_model, config, env, project_root)
        captured = capsys.readouterr()

        expected = "  Running alembic revision --autogenerate..."
        assert captured.out.rstrip("\n") == expected


class TestInfrastructureGenerators:
    """Test infrastructure file generators."""

    def test_generate_pyproject(self, project_env):
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        assert result["path"] == project_root / "pyproject.toml"
        assert "[project]" in result["content"]
        assert "test-project" in result["content"]
        assert "[tool.mutmut]" in result["content"]
        assert "[tool.ruff.lint]" in result["content"]
        assert "[tool.ruff.format]" in result["content"]
        assert "[tool.mypy]" in result["content"]

    def test_generate_pyproject_skips_existing(self, project_env):
        project_root, config, env = project_env
        (project_root / "pyproject.toml").write_text("[project]\nname = 'existing'\n")

        result = generate_pyproject(config, env, project_root, config)
        assert result is None

    def test_generate_pyproject_contains_runtime_deps(self, project_env):
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        for dep in config.get("dependencies", {}).get("runtime", []):
            assert dep in result["content"]

    def test_generate_pyproject_mutmut_targets_logic_files(self, project_env):
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        assert "validators.py" in result["content"]
        assert "utils.py" in result["content"]
        assert "constraints.py" in result["content"]

    def test_generate_pyproject_has_package_discovery(self, project_env):
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        assert "[tool.setuptools.packages.find]" in result["content"]
        # Derived from main path's parent directory
        main_path = config["paths"].get("main", "backend/src/main.py")
        expected_root = str(Path(main_path).parent)
        assert f'where = ["{expected_root}"]' in result["content"]

    def test_generate_pyproject_no_readme_file_reference(self, project_env):
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        assert 'readme = "README.md"' not in result["content"]
        assert "readme = {text" in result["content"]

    def test_generate_pyproject_merges_extra_deps(self, project_env):
        project_root, config, env = project_env
        extra = ["bcrypt>=4.0.0", "passlib>=1.7.0"]
        result = generate_pyproject(config, env, project_root, config, extra_deps=extra)

        assert result is not None
        assert "bcrypt>=4.0.0" in result["content"]
        assert "passlib>=1.7.0" in result["content"]
        # Base runtime deps still present
        assert "fastapi" in result["content"]

    def test_generate_pyproject_extra_deps_deduplicated(self, project_env):
        project_root, config, env = project_env
        base_dep = config["dependencies"]["runtime"][0]
        extra = [base_dep, "bcrypt>=4.0.0"]
        result = generate_pyproject(config, env, project_root, config, extra_deps=extra)

        assert result is not None
        assert result["content"].count(base_dep) == 1

    def test_generate_pyproject_style_defaults_omit_ruff_hardcodes(self, project_env):
        """With no overrides, ruff-default keys are absent; ruff uses its own."""
        project_root, config, env = project_env
        config.pop("style", None)
        result = generate_pyproject(config, env, project_root, config)

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
        assert 'requires-python = ">=3.11"' in content
        assert 'python_version = "3.11"' in content

    def test_generate_pyproject_style_overrides_emitted(self, project_env):
        """All four style overrides appear verbatim in the generated pyproject.toml."""
        project_root, config, env = project_env
        config["style"] = {
            "line_length": 100,
            "python_version": "3.12",
            "quote_style": "single",
            "indent_style": "tab",
        }
        result = generate_pyproject(config, env, project_root, config)

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

    def test_generate_pyproject_python_version_drives_both_pins(self, project_env):
        """Setting only python_version updates requires-python AND mypy python_version,
        without emitting any ruff-level keys."""
        project_root, config, env = project_env
        config["style"] = {"python_version": "3.12"}
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        content = result["content"]
        assert 'requires-python = ">=3.12"' in content
        assert 'python_version = "3.12"' in content
        assert "line-length = " not in content
        assert "target-version = " not in content
        assert "quote-style = " not in content
        assert "indent-style = " not in content

    def test_generate_pyproject_handles_null_style(self, project_env):
        """`style: null` in YAML parses as None — must not crash the generator."""
        project_root, config, env = project_env
        config["style"] = None
        result = generate_pyproject(config, env, project_root, config)

        assert result is not None
        # Default python_version still applied, no ruff-level overrides emitted.
        assert 'requires-python = ">=3.11"' in result["content"]
        assert 'python_version = "3.11"' in result["content"]
        assert "line-length = " not in result["content"]

    def test_generate_pyproject_project_config_style_wins(self, project_env):
        """project_config.style takes precedence over config.style when both are set."""
        project_root, config, env = project_env
        config["style"] = {"line_length": 88}
        project_config = {**config, "style": {"line_length": 100}}
        result = generate_pyproject(config, env, project_root, project_config)

        assert result is not None
        assert "line-length = 100" in result["content"]
        assert "line-length = 88" not in result["content"]

    def test_generate_base(self, project_env):
        project_root, config, env = project_env
        result = generate_base(config, env, project_root)

        assert result is not None
        assert "base.py" in str(result["path"])
        assert "Base" in result["content"]

    def test_generate_base_skips_existing(self, project_env):
        project_root, config, env = project_env
        output_path = project_root / config["paths"]["base"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("existing")

        result = generate_base(config, env, project_root)
        assert result is None

    def test_generate_engine(self, project_env):
        project_root, config, env = project_env
        result = generate_engine(config, env, project_root)

        assert result is not None
        assert "engine.py" in str(result["path"])

    def test_generate_types(self, project_env):
        project_root, config, env = project_env
        result = generate_types(config, env, project_root)

        assert result is not None
        assert "types.py" in str(result["path"])
        assert "SqliteNumeric" in result["content"]

    def test_generate_errors(self, project_env):
        project_root, config, env = project_env
        result = generate_errors(config, env, project_root)

        assert result is not None
        assert "errors.py" in str(result["path"])

    def test_generate_validators(self, project_env):
        project_root, config, env = project_env
        result = generate_validators(config, env, project_root)

        assert result is not None
        assert "validators.py" in str(result["path"])

    def test_generate_main(self, project_env):
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )

        assert result is not None
        assert "main.py" in str(result["path"])
        assert "FastAPI" in result["content"]
        assert "users" in result["content"]

    def test_generate_main_no_auth_router_when_strategy_unset(self, project_env):
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        # No auth.strategy → no auth-router import or include.
        assert "auth_router" not in result["content"]
        assert "/api/v1/auth" not in result["content"]

    def test_generate_main_with_auth_router(self, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        # Default auth.path resolves to backend.src.auth.router.
        assert (
            "from backend.src.auth.router import router as auth_router"
            in result["content"]
        )
        assert (
            'app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])'
            in result["content"]
        )

    def test_generate_main_honors_custom_auth_path(self, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "path": "src/api/auth.py",
            },
        }
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert "from src.api.auth import router as auth_router" in result["content"]

    def test_generate_main_includes_csrf_when_auth_set(self, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        # CSRF middleware imported from sibling of auth.path
        assert "from backend.src.auth.csrf import CsrfMiddleware" in result["content"]
        # Registered before CORS so CORS stays outermost
        assert "app.add_middleware(CsrfMiddleware)" in result["content"]
        csrf_idx = result["content"].index("app.add_middleware(CsrfMiddleware)")
        cors_idx = result["content"].index("app.add_middleware(\n    CORSMiddleware")
        assert csrf_idx < cors_idx, "CSRF must be added before CORS"

    def test_generate_main_no_csrf_when_strategy_unset(self, project_env):
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert "CsrfMiddleware" not in result["content"]

    def test_generate_main_includes_rate_limit_when_set(self, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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

    def test_generate_main_no_rate_limit_when_strategy_unset(self, project_env):
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        content = result["content"]
        assert "RateLimitExceeded" not in content
        assert "app.state.limiter" not in content

    def test_generate_main_no_rate_limit_when_disabled(self, project_env_per_entity):
        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {
                "strategy": "bcrypt-session",
                "pepper_env": "X",
                "rate_limit": {"enabled": False},
            },
        }
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        content = result["content"]
        # Auth + CSRF still wired, rate-limit pieces absent
        assert "auth_router" in content
        assert "RateLimitExceeded" not in content
        assert "app.state.limiter" not in content

    def test_generate_test_conftest_root(self, project_env):
        project_root, config, env = project_env
        result = generate_test_conftest_root(
            config, env, project_root, domains=["users"]
        )

        assert result is not None
        assert "conftest.py" in str(result["path"])
        assert "client" in result["content"]

    def test_generate_infrastructure_creates_all(self, project_env):
        project_root, config, env = project_env
        files = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
            project_config=config,
        )

        assert isinstance(files, list)
        assert len(files) > 0
        file_names = [f.name for f in files]
        assert "base.py" in file_names
        assert "main.py" in file_names
        assert "pyproject.toml" in file_names

    def test_infrastructure_skips_existing(self, project_env):
        """Infrastructure: some files skip if existing, others always regenerate."""
        project_root, config, env = project_env

        # First run
        files1 = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
            project_config=config,
        )

        # Second run — should skip some files
        files2 = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["items"],
            project_config=config,
        )

        assert len(files1) > 0
        # base, engine, types, errors should be skipped on second run
        # main.py, conftest.py, validators.py, utils.py always regenerate (by design)
        skipped_infra = {"base.py", "engine.py", "types.py", "errors.py"}
        new_infra = [f for f in files2 if f.name in skipped_infra]
        assert len(new_infra) == 0


class TestImmutableEntityGeneration:
    """Test generation for immutable entities (no update endpoint)."""

    def test_immutable_entity_no_update_model(self, project_env):
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
        request = next(r for r in results if "request" in str(r["path"]))

        assert "CreateEventRequest" in request["content"]
        assert "UpdateEventRequest" not in request["content"]

    def test_immutable_entity_no_put_route(self, project_env):
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
        assert "@router.put" not in result["content"]
        assert "async def update_event" not in result["content"]
        # POST and DELETE should still exist
        assert "@router.post" in result["content"]
        assert "@router.delete" in result["content"]


class TestAuthRouterGenerator:
    """Smoke-test the §12 auth_router emission helper."""

    def _project_config(self):
        return {"project": {"name": "Test"}}

    def test_returns_none_when_strategy_unset(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        result = generate_auth_router(config, env, project_root, self._project_config())
        assert result is None

    def test_emits_router_when_strategy_set(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }

        result = generate_auth_router(config, env, project_root, self._project_config())

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

    def test_emits_per_entity_imports(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_auth_router(config, env, project_root, self._project_config())
        content = result["content"]
        assert "from src.database.models.user import User" in content
        assert "from src.database.models.user_session import UserSession" in content
        assert "from src.database.engine import get_session" in content

    def test_returns_none_when_file_exists(self, project_env_per_entity):
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

        result = generate_auth_router(config, env, project_root, self._project_config())
        assert result is None

    def test_honors_custom_auth_path(self, project_env_per_entity):
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

        result = generate_auth_router(config, env, project_root, self._project_config())
        assert result is not None
        assert result["path"] == project_root / "src/auth/api.py"

    def test_wires_csrf_cookies_in_login_logout(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_auth_router(config, env, project_root, self._project_config())
        content = result["content"]
        # Relative import keeps router and csrf in the same package
        assert "from .csrf import clear_csrf_cookie, set_csrf_cookie" in content
        # Login mints the CSRF cookie alongside the session cookie
        assert "set_csrf_cookie(response)" in content
        # Logout clears it alongside the session cookie
        assert "clear_csrf_cookie(response)" in content

    def test_emits_rate_limit_decorators_by_default(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_auth_router(config, env, project_root, self._project_config())
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

    def test_no_rate_limit_when_disabled(self, project_env_per_entity):
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
        result = generate_auth_router(config, env, project_root, self._project_config())
        content = result["content"]
        assert "@limiter.limit" not in content
        assert "from .rate_limit" not in content
        # register and forgot drop the unused request: Request param
        register_block = content.split("async def register(")[1].split(") ->")[0]
        assert "request: Request" not in register_block
        forgot_block = content.split("async def forgot_password(")[1].split(") ->")[0]
        assert "request: Request" not in forgot_block

    def test_resolves_session_secret_via_helper(self, project_env_per_entity):
        """Production must fail-closed when SESSION_SECRET_KEY is missing."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root, self._project_config())
        content = result["content"]
        assert "def _resolve_session_secret() -> str:" in content
        assert 'os.environ.get("APP_ENV") == "production"' in content
        assert "SESSION_SECRET_KEY environment variable must be set" in content
        # The dev fallback string still exists for non-production use.
        assert '"DEV-ONLY-CHANGE-ME-IN-PRODUCTION"' in content
        # Serializer is initialized via the helper, not the inline get-with-default.
        assert "URLSafeTimedSerializer(\n    _resolve_session_secret()\n)" in content

    def test_password_reset_email_is_async(self, project_env_per_entity):
        """Email send must be async to avoid blocking the event loop."""
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }
        result = generate_auth_router(config, env, project_root, self._project_config())
        content = result["content"]
        assert "async def _send_password_reset_email(" in content
        # forgot_password must await it
        assert "await _send_password_reset_email(user.email, token)" in content


class TestCsrfGenerator:
    """Smoke-test the §12.4 CSRF middleware emission helper."""

    def test_returns_none_when_strategy_unset(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        assert generate_csrf(config, env, project_root) is None

    def test_emits_csrf_when_strategy_set(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_csrf

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_csrf(config, env, project_root)

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

    def test_session_cookie_name_follows_auth_cookie_name(self, project_env_per_entity):
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
        assert result is not None
        # Custom cookie_name flows from config into SESSION_COOKIE_NAME so the
        # gating check matches what the auth router actually sets.
        assert 'SESSION_COOKIE_NAME = "sid"' in result["content"]

    def test_returns_none_when_file_exists(self, project_env_per_entity):
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

    def test_csrf_path_follows_custom_auth_path(self, project_env_per_entity):
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
        # csrf.py is sibling of auth.path
        assert result["path"] == project_root / "src/api/csrf.py"


class TestEncryptedBytesGenerator:
    """Smoke-test the §13 EncryptedBytes TypeDecorator emission helper.

    Closes the latent emission gap: ``model.py.j2`` conditionally imports
    ``from .encrypted_bytes import EncryptedBytes`` when any field declares
    ``type: binary`` + ``encrypt: {...}``, but until this generator landed
    no infrastructure code emitted the imported module.
    """

    def test_returns_none_when_no_encrypted_binary(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        # has_encrypted_binary defaults to False — common-case projects with
        # no binary+encrypt fields must not get a stray cryptography import.
        assert generate_encrypted_bytes(config, env, project_root) is None

    def test_emits_when_flag_set(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        result = generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=True
        )

        assert result is not None
        # Lives next to the model files so `from .encrypted_bytes import …`
        # in model.py.j2 resolves via the package's relative import.
        assert result["path"] == project_root / "src/database/models/encrypted_bytes.py"
        content = result["content"]
        # Core TypeDecorator surface
        assert "class EncryptedBytes(TypeDecorator):" in content
        assert "impl = LargeBinary" in content
        assert "cache_ok = True" in content
        # Fernet wiring + lazy import (avoids hard cryptography dep at module load)
        assert 'FERNET_KEY = os.environ.get("FERNET_KEY")' in content
        assert "from cryptography.fernet import Fernet" in content
        # Postgres dialect-specific type
        assert "from sqlalchemy.dialects.postgresql import BYTEA" in content
        assert 'dialect.name == "postgresql"' in content
        # Template bug fix: the opener `{#-` must render to nothing, not
        # leak literal text. Catch any regression where the typo `{-#`
        # would surface as raw output.
        assert "{-#" not in content
        assert "{#-" not in content

    def test_returns_none_when_file_exists(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        # Adopter has customized encrypted_bytes.py; bootstrap helper must skip.
        out = project_root / "src/database/models/encrypted_bytes.py"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# adopter has customized this\n")

        assert (
            generate_encrypted_bytes(
                config, env, project_root, has_encrypted_binary=True
            )
            is None
        )

    def test_path_follows_custom_database_models(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, _config, env = project_env_per_entity
        # Custom layout: adopter put models elsewhere; emission must follow.
        custom_config = {
            "paths": {"database_models": "backend/lib/db/models"},
        }
        result = generate_encrypted_bytes(
            custom_config, env, project_root, has_encrypted_binary=True
        )

        assert result is not None
        assert (
            result["path"] == project_root / "backend/lib/db/models/encrypted_bytes.py"
        )

    def test_emission_wired_into_generate_infrastructure(self, project_env_per_entity):
        """The aggregator must include encrypted_bytes.py when the flag is set."""
        from model_generator.generators.infrastructure import generate_infrastructure

        project_root, config, env = project_env_per_entity

        generated = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["users"],
            project_config=config,
            has_encrypted_binary=True,
        )

        emitted_names = {p.name for p in generated}
        assert "encrypted_bytes.py" in emitted_names

    def test_aggregator_skips_when_flag_unset(self, project_env_per_entity):
        """No binary+encrypt fields anywhere → no encrypted_bytes.py."""
        from model_generator.generators.infrastructure import generate_infrastructure

        project_root, config, env = project_env_per_entity

        generated = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["users"],
            project_config=config,
            # has_encrypted_binary omitted — defaults to False
        )

        emitted_names = {p.name for p in generated}
        assert "encrypted_bytes.py" not in emitted_names


class TestRateLimitGenerator:
    """Smoke-test the §12.5 rate-limit module emission helper."""

    def test_returns_none_when_strategy_unset(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        assert generate_rate_limit(config, env, project_root) is None

    def test_returns_none_when_explicitly_disabled(self, project_env_per_entity):
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

    def test_emits_module_with_default_limits(self, project_env_per_entity):
        from model_generator.generators.infrastructure import generate_rate_limit

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }
        result = generate_rate_limit(config, env, project_root)

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

    def test_uses_configured_limits(self, project_env_per_entity):
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
        content = result["content"]
        assert 'LOGIN_LIMIT = "10/minute"' in content
        assert 'REGISTER_LIMIT = "5/hour"' in content
        assert 'FORGOT_LIMIT = "2/hour"' in content

    def test_uses_redis_default_uri_when_backend_redis(self, project_env_per_entity):
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
        content = result["content"]
        assert (
            'os.environ.get("RATELIMIT_STORAGE_URI", "redis://localhost:6379/0")'
            in content
        )
        # Memory default is replaced, not just appended.
        assert 'os.environ.get("RATELIMIT_STORAGE_URI", "memory://")' not in content

    def test_returns_none_when_file_exists(self, project_env_per_entity):
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

    def test_module_path_follows_custom_auth_path(self, project_env_per_entity):
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
        # rate_limit.py is sibling of auth.path
        assert result["path"] == project_root / "src/api/rate_limit.py"


class TestApiTestsEndpointGates:
    """Test endpoint-aware gating in contract.py.j2 (§12.6).

    When `entity.api.endpoints` drops one of {list, create, get}, the
    contract test template should suppress the matching test sections —
    plus all tests that internally seed via POST (which require `create`).
    """

    @staticmethod
    def _model(endpoints: list[str]) -> dict:
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

    def test_skips_create_tests_when_create_endpoint_excluded(self, project_env):
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

        # Seeding-required tests inside kept sections are also gone
        assert "def test_get_item_by_id_success" not in content
        assert "def test_put_item_success" not in content
        assert "def test_put_item_partial_update" not in content
        assert "def test_delete_item_success" not in content
        assert "def test_item_immutable_fields" not in content
        assert "def test_get_items_list_filtering" not in content

        # _not_found variants don't seed → still emitted
        assert "def test_get_item_by_id_not_found" in content
        assert "def test_put_item_not_found" in content
        assert "def test_delete_item_not_found" in content

    def test_skips_list_tests_when_list_endpoint_excluded(self, project_env):
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
        content = result["content"]
        assert "def test_get_items_list_success" not in content
        assert "def test_get_items_list_pagination" not in content
        assert "def test_get_items_list_invalid_pagination" not in content
        assert "def test_get_items_list_sorting" not in content
        # Other sections unaffected
        assert "def test_post_item_success" in content
        assert "def test_get_item_by_id_success" in content

    def test_skips_get_by_id_tests_when_get_endpoint_excluded(self, project_env):
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
        content = result["content"]
        assert "def test_get_item_by_id_success" not in content
        assert "def test_get_item_by_id_not_found" not in content
        # Other sections unaffected
        assert "def test_post_item_success" in content
        assert "def test_delete_item_success" in content


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

    def test_no_reset_fixture_when_rate_limiter_import_none(self, tmp_path):
        from model_generator.utils.conftest_generator import (
            generate_conftest_content,
        )

        content, _ = generate_conftest_content(self._models_dir(tmp_path))
        assert "rate_limit" not in content
        assert "_reset_rate_limiter" not in content
        assert "limiter.reset()" not in content

    def test_emits_reset_fixture_when_rate_limiter_import_set(self, tmp_path):
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


class TestComputeAuthExtra:
    """Test the _compute_auth_extra helper (§12 review #2)."""

    def test_no_strategy_returns_empty(self):
        from model_generator.generate import _compute_auth_extra

        assert _compute_auth_extra({}) == []
        assert _compute_auth_extra({"auth": {}}) == []

    def test_strategy_set_includes_bcrypt_itsdangerous_email_validator(self):
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

    def test_rate_limit_disabled_omits_slowapi(self):
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

    def test_redis_backend_adds_redis_dep(self):
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


class TestHasEncryptedBinaryField:
    """Test the _has_encrypted_binary_field helper (§13 emission gate)."""

    def test_empty_models_returns_false(self):
        from model_generator.generate import _has_encrypted_binary_field

        assert _has_encrypted_binary_field([]) is False

    def test_model_without_binary_field_returns_false(self):
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "User": {"fields": {"email": {"type": "text"}}},
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is False

    def test_binary_field_without_encrypt_returns_false(self):
        """Plain ``binary`` (no encrypt block) goes to LargeBinary directly —
        no EncryptedBytes TypeDecorator needed."""
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "File": {"fields": {"blob": {"type": "binary"}}},
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is False

    def test_binary_with_encrypt_returns_true(self):
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "Token": {
                        "fields": {
                            "value": {
                                "type": "binary",
                                "encrypt": {"key_env": "FERNET_KEY"},
                            }
                        }
                    }
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is True

    def test_detected_in_later_model_in_list(self):
        """Mixed-project case: only the second model carries an encrypted field."""
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {"entities": {"User": {"fields": {"email": {"type": "text"}}}}},
            {
                "entities": {
                    "ApiKey": {
                        "fields": {
                            "secret": {
                                "type": "binary",
                                "encrypt": {"key_env": "FERNET_KEY"},
                            }
                        }
                    }
                }
            },
        ]
        assert _has_encrypted_binary_field(models) is True
