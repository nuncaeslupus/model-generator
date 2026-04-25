"""Tests for individual code generators."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from model_generator.generators import (
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
    """Set up a temporary project with config and template environment."""
    config_data = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
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

    def test_owner_field_excluded_from_create_request(
        self, scoped_model, project_env
    ):
        """owner_field is set by the handler, not by the API caller."""
        content = self._request_content(scoped_model, project_env)
        create_start = content.index("class CreateWidgetRequest")
        update_start = content.index("class UpdateWidgetRequest")
        create_block = content[create_start:update_start]
        assert "owner_id" not in create_block

    def test_owner_field_excluded_from_update_request(
        self, scoped_model, project_env
    ):
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
            result["content"].count(
                "current_user: Any = Depends(get_current_user)"
            )
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
            "stmt = stmt.where(Widget.owner_id == current_user.id)"
            in result["content"]
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

        model = {
            "entities": {
                "Widget": {"api": {"scope": {"owner_field": "user_id"}}}
            }
        }
        config = {"auth": {"dependency_path": "x.y.z"}}
        _validate_auth_config(model, config)  # Should not exit

    def test_scope_without_auth_config_exits(self, capsys):
        from model_generator.generate import _validate_auth_config

        model = {
            "entities": {
                "Widget": {"api": {"scope": {"owner_field": "user_id"}}}
            }
        }
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

        model = {
            "entities": {
                "Widget": {"api": {"scope": {"owner_field": "user_id"}}}
            }
        }
        config = {"auth": {"dependency_path": "no_dots_here"}}
        with pytest.raises(SystemExit) as excinfo:
            _validate_auth_config(model, config)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "no_dots_here" in out
        assert "dotted path" in out


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
