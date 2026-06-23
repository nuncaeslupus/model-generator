"""Tests for individual code generators."""

import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import types
from datetime import UTC
from pathlib import Path
from typing import Any, ClassVar
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


@pytest.fixture
def minimal_model() -> dict[str, Any]:
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


@pytest.fixture
def project_env(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
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

    def test_generates_model_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert result["path"] == project_root / "src/database/models/items.py"
        assert "class Item(Base):" in result["content"]
        assert '__tablename__ = "items"' in result["content"]

    def test_contains_fields(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        assert "name: Mapped[str] = mapped_column(String(100)" in result["content"]
        assert "mapped_column(Integer" in result["content"]

    def test_contains_timestamps(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_database_model(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        assert "created_at" in result["content"]
        assert "updated_at" in result["content"]
        assert "server_default=func.now()" in result["content"]

    def test_path_uses_domain_default_when_key_absent(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model_no_domain = {"description": "test", "entities": {}}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_database_model(model_no_domain, config, env, project_root)
            assert isinstance(result, dict)

        output_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == output_dir / "models.py"


class TestGenerateInit:
    """Test __init__.py generation for database models."""

    _FAKE_DOMAINS: ClassVar[list[dict[str, Any]]] = [
        {
            "name": "items",
            "file": "items",
            "section": None,
            "entities": ["Item", "ItemAlt"],
        }
    ]

    def test_includes_current_model_when_no_files_on_disk(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(minimal_model, config, env, project_root)
            assert isinstance(result, dict)
        # Even with no files on disk, init should include the current model
        assert result is not None
        assert "from .items import" in result["content"]
        assert "Item" in result["content"]

    def test_result_structure(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files",
            return_value=self._FAKE_DOMAINS,
        ):
            result = generate_init(minimal_model, config, env, project_root)
            assert isinstance(result, dict)

        output_dir = project_root / config["paths"]["database_models"]
        assert result is not None
        assert result["path"] == output_dir / "__init__.py"
        assert result["mode"] == "write"
        assert result["domain_count"] == 1
        assert result["entity_count"] == 2
        assert "from .items import" in result["content"]

    def test_content_uses_config(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        with patch(
            "model_generator.generators.database.scan_model_files",
            return_value=self._FAKE_DOMAINS,
        ):
            result = generate_init(minimal_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert "Test Project" in result["content"]


class TestFactoryGenerator:
    """Test factory generation."""

    def test_generates_factory_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_factories(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        factories_dir = project_root / config["paths"]["factories"]
        assert result is not None
        assert result["path"] == factories_dir / "items.py"

    def test_factory_content(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_factories(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        assert "ItemFactory" in result["content"]
        assert "factory.Factory" in result["content"] or "Factory" in result["content"]

    def test_path_uses_domain_default_when_key_absent(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model_no_domain = {"description": "test", "entities": {}}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_factories(model_no_domain, config, env, project_root)
            assert isinstance(result, dict)

        factories_dir = project_root / config["paths"]["factories"]
        assert result["path"] == factories_dir / "models.py"

    def test_ref_constraints_resolve_to_literals(self, project_env: Any) -> None:
        """financial/counter min_ref/max_ref resolve to literal constant values.

        The factory module never imports the constraints module, so emitting the
        bare constant name (e.g. ``PRICE_MAX``) would NameError at create() time.
        """
        project_root, config, env = project_env
        model = {
            "domain": "shop",
            "entities": {
                "Item": {
                    "table": "items",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "price": {
                            "type": "financial",
                            "constraints": [{"type": "range", "max_ref": "PRICE_MAX"}],
                        },
                        "qty": {
                            "type": "counter",
                            "constraints": [{"type": "range", "min_ref": "QTY_MIN"}],
                        },
                    },
                }
            },
        }
        constraints = {
            "PRICE_MAX": {"value": "5000.00"},
            "QTY_MIN": {"value": 1},
        }
        result = generate_factories(
            model, config, env, project_root, constraints=constraints
        )
        assert isinstance(result, dict)
        content = result["content"]
        # Literal values, not bare constant names.
        assert "max_value=5000.00" in content
        assert "min_value=1," in content
        assert "PRICE_MAX" not in content
        assert "QTY_MIN" not in content

    def test_ref_constraints_fall_back_when_unresolved(self, project_env: Any) -> None:
        """An unresolved ref falls back to default bounds (no bare name leaks)."""
        project_root, config, env = project_env
        model = {
            "domain": "shop",
            "entities": {
                "Item": {
                    "table": "items",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "qty": {
                            "type": "counter",
                            "constraints": [{"type": "range", "max_ref": "MISSING"}],
                        },
                    },
                }
            },
        }
        result = generate_factories(model, config, env, project_root, constraints={})
        assert isinstance(result, dict)
        content = result["content"]
        assert "max_value=999999" in content
        assert "MISSING" not in content

    def test_required_reference_emits_subfactory_without_reference_entity(
        self, project_env: Any
    ) -> None:
        """reference_table resolves to entity name even without reference_entity."""
        project_root, config, env = project_env
        model = {
            "domain": "blog",
            "entities": {
                "Author": {
                    "table": "authors",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        }
                    },
                },
                "Post": {
                    "table": "posts",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "author_id": {
                            "type": "reference",
                            "reference_table": "authors",  # NO reference_entity key
                            "required": True,
                        },
                    },
                },
            },
        }
        config["generation"] = {"layout": "per-domain"}
        result = generate_factories(model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "factory.SubFactory(AuthorFactory)" in content
        assert "from .author import AuthorFactory" not in content  # per-domain layout


def test_factories_not_in_production_package(tmp_path: Path) -> None:
    """Factories must live outside python_root to avoid dev-dep pull in prod.

    factory_boy and faker are dev-only dependencies. If the factories path is
    inside python_root, any import of the production package at runtime would
    transitively import those packages, making them a required production dep.

    TPL-15: default factories path was backend/src/database/models/factories,
    which is inside python_root (backend/src). The correct default is
    backend/tests/factories.
    """
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        config = load_config("python-fastapi")
    finally:
        os.chdir(original_cwd)

    python_root = config.get("python_root", "backend/src")
    factories_path = config["paths"]["factories"]
    assert not factories_path.startswith(python_root.rstrip("/") + "/"), (
        f"Factories path '{factories_path}' is inside python_root '{python_root}' — "
        "factory_boy/faker would be a production dep"
    )


@pytest.fixture
def multi_entity_model() -> dict[str, Any]:
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
def project_env_per_entity(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
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


class TestDatabaseGeneratorTypedRelationships:
    """TPL-5: relationships emit Mapped[...] for same-module (sibling) targets."""

    def test_per_domain_relationships_are_typed(
        self, multi_entity_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env  # per-domain
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert 'posts: Mapped[list["Post"]] = relationship(' in content
        assert 'author: Mapped["Author | None"] = relationship(' in content
        # Same module → forward refs resolve without TYPE_CHECKING imports.
        assert "TYPE_CHECKING" not in content

    def test_per_entity_relationships_typed_with_type_checking_imports(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        author = by_name["author.py"]
        post = by_name["post.py"]
        assert 'posts: Mapped[list["Post"]] = relationship(' in author
        assert "if TYPE_CHECKING:" in author
        assert "from .post import Post" in author
        assert 'author: Mapped["Author | None"] = relationship(' in post
        assert "if TYPE_CHECKING:" in post
        assert "from .author import Author" in post

    def test_cross_module_relationship_is_unannotated(
        self, project_env_per_entity: Any
    ) -> None:
        """A relationship target outside the model's entities (cross-domain)
        can't be imported here, so it stays unannotated — annotating it would
        emit an undefined name under mypy."""
        project_root, config, env = project_env_per_entity
        model = {
            "domain": "blog",
            "entities": {
                "Post": {
                    "table": "posts",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                    },
                    "relationships": {
                        "comments": {
                            "type": "one_to_many",
                            "target": "Comment",
                            "back_populates": "post",
                        },
                    },
                },
            },
        }
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, list)
        content = result[0]["content"]
        assert "comments = relationship(" in content
        assert 'Mapped[list["Comment"]]' not in content
        assert "from .comment import Comment" not in content


class TestDatabaseGeneratorNullability:
    """TPL-16: scalar fields with a default are NOT NULL (non-Optional Mapped)."""

    def _model(self, fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "domain": "shop",
            "entities": {
                "Widget": {
                    "table": "widgets",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        **fields,
                    },
                },
            },
        }

    def test_boolean_without_default_is_not_optional(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = self._model({"active": {"type": "boolean"}})
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "active: Mapped[bool] = mapped_column(Boolean, default=False)" in content
        assert "active: Mapped[bool | None]" not in content

    def test_scalar_with_default_is_not_optional(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = self._model(
            {"label": {"type": "text", "max_length": 50, "default": "x"}}
        )
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert 'label: Mapped[str] = mapped_column(String(50), default="x")' in content
        assert "label: Mapped[str | None]" not in content

    def test_optional_without_default_stays_nullable(self, project_env: Any) -> None:
        project_root, config, env = project_env
        model = self._model({"note": {"type": "text", "max_length": 50}})
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "note: Mapped[str | None] = mapped_column(String(50))" in content

    def test_explicit_null_default_stays_nullable(self, project_env: Any) -> None:
        """An explicit `default: null` is `is defined` but must stay Optional and
        must not emit a bogus `default="None"` column parameter."""
        project_root, config, env = project_env
        model = self._model(
            {"note": {"type": "text", "max_length": 50, "default": None}}
        )
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "note: Mapped[str | None] = mapped_column(String(50))" in content
        assert 'default="None"' not in content


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


class TestDatabaseGeneratorRangeCheck:
    """CHECK-constraint emission for range / range_or_null bounds."""

    def _model(self, constraint: dict[str, Any]) -> dict[str, Any]:
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
                            "constraints": [constraint],
                        },
                    },
                }
            },
        }

    def test_range_both_bounds(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_database_model(
            self._model({"type": "range", "min_ref": "QTY_MIN", "max_ref": "QTY_MAX"}),
            config,
            env,
            project_root,
        )
        assert isinstance(result, dict)
        assert 'f"stock >= {QTY_MIN} AND stock <= {QTY_MAX}"' in result["content"]

    def test_range_max_only_emits_one_sided_check(self, project_env: Any) -> None:
        """A range with only an upper bound must not emit an empty ``{}``."""
        project_root, config, env = project_env
        result = generate_database_model(
            self._model({"type": "range", "max_ref": "QTY_MAX"}),
            config,
            env,
            project_root,
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert 'f"stock <= {QTY_MAX}"' in content
        # The empty-brace f-string bug would render this:
        assert "{}" not in content

    def test_range_min_only_emits_one_sided_check(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_database_model(
            self._model({"type": "range", "min_ref": "QTY_MIN"}),
            config,
            env,
            project_root,
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert 'f"stock >= {QTY_MIN}"' in content
        assert "{}" not in content

    def test_range_or_null_max_only(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_database_model(
            self._model({"type": "range_or_null", "max_ref": "QTY_MAX"}),
            config,
            env,
            project_root,
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert 'f"stock <= {QTY_MAX} OR stock IS NULL"' in content
        assert "{}" not in content


class TestDatabaseGeneratorPerEntity:
    def test_returns_list_of_dicts(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_one_file_per_entity_using_snake_case(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        output_dir = project_root / config["paths"]["database_models"]
        paths = {r["path"] for r in result}
        assert output_dir / "author.py" in paths
        assert output_dir / "post.py" in paths

    def test_each_file_contains_only_its_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "class Author(Base):" in by_name["author.py"]
        assert "class Post" not in by_name["author.py"]
        assert "class Post(Base):" in by_name["post.py"]
        assert "class Author" not in by_name["post.py"]

    def test_section_divider_omitted(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """section_divider is gated on per-domain to avoid N redundant headers.

        The docstring header at the top of each file still contains the
        domain name; the section divider is a separate full-width banner
        emitted around the entity classes, which is what should disappear.
        """
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        divider_banner = "# " + "=" * 76 + "\n# BLOG MODELS"
        for entry in result:
            assert divider_banner not in entry["content"]


@pytest.fixture
def composite_fk_model() -> dict[str, Any]:
    """Composite FK fixture: OrderItem references Order's composite PK.

    Order has a composite PK (tenant_id, id). OrderItem's (tenant_id, order_id)
    pair forms a single composite FK to that PK. The relationship's foreign_keys
    array disambiguates the ORM mapping; the entity-level foreign_keys array
    declares the schema-level FK constraint.
    """
    return {
        "domain": "shop",
        "entities": {
            "Order": {
                "table": "orders",
                "fields": {
                    "tenant_id": {"type": "uuid", "primary_key": True},
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "name": {"type": "text", "max_length": 100, "required": True},
                },
                "relationships": {
                    "items": {
                        "type": "one_to_many",
                        "target": "OrderItem",
                        "back_populates": "order",
                    },
                },
            },
            "OrderItem": {
                "table": "order_items",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "tenant_id": {"type": "uuid", "required": True},
                    "order_id": {"type": "uuid", "required": True},
                    "sku": {"type": "text", "max_length": 64, "required": True},
                },
                "foreign_keys": [
                    {
                        "fields": ["tenant_id", "order_id"],
                        "references_table": "orders",
                        "references_columns": ["tenant_id", "id"],
                        "on_delete": "CASCADE",
                    }
                ],
                "relationships": {
                    "order": {
                        "type": "many_to_one",
                        "target": "Order",
                        "back_populates": "items",
                        "foreign_keys": ["tenant_id", "order_id"],
                    },
                },
            },
        },
    }


@pytest.fixture
def self_ref_composite_fk_model() -> dict[str, Any]:
    """Self-ref composite FK: Node points at its parent in the same tree.

    Composite PK (org_id, node_id); composite FK (org_id, parent_node_id) →
    (org_id, node_id). Exercises the §1 external-review fix for self-ref
    remote_side collecting all PK fields.
    """
    return {
        "domain": "tree",
        "entities": {
            "Node": {
                "table": "nodes",
                "fields": {
                    "org_id": {"type": "uuid", "primary_key": True},
                    "node_id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "parent_node_id": {"type": "uuid"},
                    "label": {"type": "text", "max_length": 100, "required": True},
                },
                "foreign_keys": [
                    {
                        "fields": ["org_id", "parent_node_id"],
                        "references_table": "nodes",
                        "references_columns": ["org_id", "node_id"],
                        "on_delete": "CASCADE",
                    }
                ],
                "relationships": {
                    "parent": {
                        "type": "many_to_one",
                        "target": "Node",
                        "back_populates": "children",
                        "foreign_keys": ["org_id", "parent_node_id"],
                    },
                    "children": {
                        "type": "one_to_many",
                        "target": "Node",
                        "back_populates": "parent",
                        "foreign_keys": ["org_id", "parent_node_id"],
                    },
                },
            },
        },
    }


class TestCompositeForeignKey:
    """Composite FK emission inside __table_args__."""

    def _orderitem_content(self, model: Any, project_env_per_entity: Any) -> str:
        project_root, config, env = project_env_per_entity
        result = generate_database_model(model, config, env, project_root)
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        content = by_name["order_item.py"]
        assert isinstance(content, str)
        return content

    def test_emits_foreign_key_constraint_in_table_args(
        self, composite_fk_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._orderitem_content(composite_fk_model, project_env_per_entity)
        assert "__table_args__" in content
        assert "ForeignKeyConstraint(" in content
        assert '["tenant_id", "order_id"]' in content
        assert '["orders.tenant_id", "orders.id"]' in content
        assert 'ondelete="CASCADE"' in content

    def test_member_fields_emit_as_plain_columns(
        self, composite_fk_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Composite-FK member columns must NOT carry an inline ForeignKey(...)."""
        content = self._orderitem_content(composite_fk_model, project_env_per_entity)
        # Locate the OrderItem class body.
        class_body = content.split("class OrderItem(Base):")[1].split("class ")[0]
        # tenant_id and order_id should be plain typed columns, no ForeignKey wrapping.
        for col in ("tenant_id", "order_id"):
            line_idx = class_body.find(f"{col}: Mapped[")
            assert line_idx != -1, f"missing column {col}"
            # The column declaration spans until the next column (or end of class).
            tail = class_body[line_idx : line_idx + 200]
            assert "ForeignKey(" not in tail.split("\n")[1] if "\n" in tail else True
            assert 'ForeignKey("orders' not in tail

    def test_imports_foreign_key_constraint(
        self, composite_fk_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        content = self._orderitem_content(composite_fk_model, project_env_per_entity)
        # Import block uses parenthesized multi-line form.
        import_section = content.split("from sqlalchemy import (")[1].split(")")[0]
        assert "ForeignKeyConstraint" in import_section

    def test_no_fk_constraint_import_when_unused(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """No composite FKs in fixture → ForeignKeyConstraint must not be imported."""
        project_root, config, env = project_env_per_entity
        result = generate_database_model(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        for entry in result:
            assert "ForeignKeyConstraint" not in entry["content"]

    def test_self_ref_composite_fk(
        self, self_ref_composite_fk_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Self-ref composite FK emits ForeignKeyConstraint and full remote_side."""
        project_root, config, env = project_env_per_entity
        result = generate_database_model(
            self_ref_composite_fk_model, config, env, project_root
        )
        assert isinstance(result, list)
        content = next(r["content"] for r in result if r["path"].name == "node.py")
        assert "ForeignKeyConstraint(" in content
        assert '["org_id", "parent_node_id"]' in content
        assert '["nodes.org_id", "nodes.node_id"]' in content
        # §1 external-review fix: remote_side collects ALL PK fields.
        assert "remote_side=[org_id, node_id]" in content

    def test_configure_mappers_succeeds(
        self, composite_fk_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Live SQLAlchemy probe — composite FK emission must not raise.

        Strips project-local imports (`.base`, `.types`) and substitutes a
        local DeclarativeBase + a String-aliased PortableUuid so the rendered
        module can exec in isolation. Then calls Base.registry.configure() —
        this is the exact step that raises AmbiguousForeignKeysError when
        multiple FK paths exist between two tables.
        """
        import re

        from sqlalchemy import String
        from sqlalchemy.orm import DeclarativeBase

        project_root, config, env = project_env_per_entity
        result = generate_database_model(composite_fk_model, config, env, project_root)
        assert isinstance(result, list)
        # Concatenate the two rendered files so both classes share one Base.
        merged = "\n".join(r["content"] for r in result)
        # Strip relative + project-local imports — Base + PortableUuid are supplied.
        merged = re.sub(r"^from (?:\.|src\.)[^\n]+\n", "", merged, flags=re.MULTILINE)

        class Base(DeclarativeBase):
            pass

        namespace: dict[str, Any] = {"Base": Base, "PortableUuid": String}
        exec(merged, namespace)
        Base.registry.configure()  # would raise AmbiguousForeignKeysError if broken


class TestGenerateInitPerEntity:
    """Per-entity __init__.py emission."""

    def test_emits_one_import_line_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(multi_entity_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert "from .author import" in result["content"]
        assert "from .post import" in result["content"]
        assert result["domain_count"] == 2
        assert result["entity_count"] == 2

    def test_no_none_banner_emitted(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """section=None must suppress the banner, not render '# None'."""
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(multi_entity_model, config, env, project_root)
            assert isinstance(result, dict)
        assert result is not None
        assert "# None" not in result["content"]

    def test_existing_per_entity_files_not_redeclared(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
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
            assert isinstance(result, dict)
        assert result is not None
        assert result["domain_count"] == 2  # author (existing) + post (added)
        assert "from .author import" in result["content"]
        assert "from .post import" in result["content"]


class TestFactoryGeneratorPerEntity:
    """Per-entity factory emission and cross-entity import preservation."""

    def test_returns_list_with_one_factory_per_entity(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        assert len(result) == 2
        names = {r["path"].name for r in result}
        assert names == {"author.py", "post.py"}

    def test_db_model_imports_use_per_entity_paths(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Factory imports the model from {db_models}.{entity_snake}, not {domain}."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        by_name = {r["path"].name: r["content"] for r in result}
        assert "from src.database.models.author import Author" in by_name["author.py"]
        assert "from src.database.models.post import Post" in by_name["post.py"]
        # Per-domain import shape must NOT appear.
        assert "from src.database.models.blog import" not in by_name["author.py"]
        assert "from src.database.models.blog import" not in by_name["post.py"]

    def test_subfactory_reference_imports_sibling_factory(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Post has author_id reference → post.py imports AuthorFactory."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        post_content = next(r["content"] for r in result if r["path"].name == "post.py")
        assert "from .author import AuthorFactory" in post_content
        assert "factory.SubFactory(AuthorFactory)" in post_content

    def test_create_related_preserved_via_sibling_entities(
        self, multi_entity_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Author has one_to_many → Post; create_related must survive the
        per-entity slicing of model.entities, and PostFactory must be imported."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        author_content = next(
            r["content"] for r in result if r["path"].name == "author.py"
        )
        assert "from .post import PostFactory" in author_content
        assert "PostFactory.create_batch(count, author=obj)" in author_content


@pytest.fixture
def self_ref_factory_model() -> dict[str, Any]:
    """Single entity with both a self-ref reference field and a self-loop one_to_many.

    Category.parent_id → Category (reference field, exercises factory.py.j2
    entity_refs collection on the field path). Category.children → Category
    (one_to_many self-rel, exercises the same collection on the relationship
    path). Both paths used to emit ``from .category import CategoryFactory``
    inside category.py — a self-import that ruff catches as F811.
    """
    return {
        "domain": "category",
        "entities": {
            "Category": {
                "table": "categories",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "name": {"type": "text", "max_length": 100, "required": True},
                    "parent_id": {
                        "type": "reference",
                        "reference_entity": "Category",
                        "reference_table": "categories",
                        "required": False,
                    },
                },
                "relationships": {
                    "parent": {
                        "type": "many_to_one",
                        "target": "Category",
                        "back_populates": "children",
                    },
                    "children": {
                        "type": "one_to_many",
                        "target": "Category",
                        "back_populates": "parent",
                    },
                },
            },
        },
    }


class TestFactoryGeneratorSelfRef:
    """Self-referential entities must not import their own factory class."""

    def test_no_self_import_line_emitted(
        self, self_ref_factory_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Generated category.py contains no `from .category import CategoryFactory`."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(self_ref_factory_model, config, env, project_root)
        assert isinstance(result, list)
        content = next(r["content"] for r in result if r["path"].name == "category.py")
        assert "from .category import" not in content

    def test_in_class_subfactory_reference_preserved(
        self, self_ref_factory_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Self-ref SubFactory must emit as a string literal — referencing the
        bare class name in the class body raises NameError at module-load time
        (the class isn't bound until the ``class`` statement completes).
        Factoryboy resolves the string lazily at ``.create()`` time."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(self_ref_factory_model, config, env, project_root)
        assert isinstance(result, list)
        content = next(r["content"] for r in result if r["path"].name == "category.py")
        assert 'factory.SubFactory("CategoryFactory")' in content
        # The bare-class form is the regression mode — must NOT appear for self-ref.
        assert "factory.SubFactory(CategoryFactory)" not in content

    def test_generated_factory_execs_without_nameerror(
        self, self_ref_factory_model: dict[str, Any], project_env_per_entity: Any
    ) -> None:
        """Smoke test: ``exec()`` the generated factory under stubbed
        factoryboy/faker/SQLAlchemy modules. Catches class-body self-references
        (the class of regression Gemini flagged on PR #19) regardless of which
        macro emits them."""
        project_root, config, env = project_env_per_entity
        result = generate_factories(self_ref_factory_model, config, env, project_root)
        assert isinstance(result, list)
        content = next(r["content"] for r in result if r["path"].name == "category.py")

        factory_stub = types.ModuleType("factory")
        factory_stub.LazyFunction = lambda *_a, **_k: object()  # type: ignore[attr-defined]
        factory_stub.SubFactory = lambda *_a, **_k: object()  # type: ignore[attr-defined]
        factory_stub.Faker = lambda *_a, **_k: object()  # type: ignore[attr-defined]
        factory_stub.Sequence = lambda *_a, **_k: object()  # type: ignore[attr-defined]
        factory_stub.post_generation = lambda fn: fn  # type: ignore[attr-defined]
        alchemy_stub = types.ModuleType("factory.alchemy")

        class _SQLAlchemyModelFactory:
            pass

        alchemy_stub.SQLAlchemyModelFactory = _SQLAlchemyModelFactory  # type: ignore[attr-defined]
        factory_stub.alchemy = alchemy_stub  # type: ignore[attr-defined]

        faker_stub = types.ModuleType("faker")

        class _FakerStub:
            def __getattr__(self, _name: str) -> Any:
                return lambda *_a, **_k: ""

        faker_stub.Faker = _FakerStub  # type: ignore[attr-defined]

        cat_stub = types.ModuleType("src.database.models.category")

        class Category:
            pass

        cat_stub.Category = Category  # type: ignore[attr-defined]

        stubbed = {
            "factory": factory_stub,
            "factory.alchemy": alchemy_stub,
            "faker": faker_stub,
            "src": types.ModuleType("src"),
            "src.database": types.ModuleType("src.database"),
            "src.database.models": types.ModuleType("src.database.models"),
            "src.database.models.category": cat_stub,
        }
        saved = {k: sys.modules.get(k) for k in stubbed}
        try:
            sys.modules.update(stubbed)
            ns: dict[str, Any] = {"__name__": "category_factory_test"}
            exec(content, ns)
            assert "CategoryFactory" in ns
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v


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


class TestFactoryDocstringUsage:
    """TPL-20: factory docstring Usage line must not be glued to 'Usage:'.

    Regression: {%- set %} statements inside the docstring stripped the
    newline after 'Usage:', producing 'Usage:    from ...' on one line.
    """

    def test_usage_line_is_on_separate_line_from_usage_label(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_factories(minimal_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]
        assert "Usage:\n    from " in content, (
            "Usage: label and the import must be on separate lines"
        )
        assert "Usage:    from " not in content


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


class TestValidateCompositeForeignKeys:
    """Test the _validate_composite_foreign_keys helper."""

    def _model_with_fk(self, fk: dict[str, Any]) -> dict[str, Any]:
        return {
            "entities": {
                "Order": {
                    "table": "orders",
                    "fields": {
                        "tenant_id": {"type": "uuid", "primary_key": True},
                        "id": {"type": "uuid", "primary_key": True},
                    },
                },
                "OrderItem": {
                    "table": "order_items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "tenant_id": {"type": "uuid"},
                        "order_id": {"type": "uuid"},
                    },
                    "foreign_keys": [fk],
                },
            }
        }

    def _valid_fk(self) -> dict[str, Any]:
        return {
            "fields": ["tenant_id", "order_id"],
            "references_table": "orders",
            "references_columns": ["tenant_id", "id"],
            "on_delete": "CASCADE",
        }

    def test_no_foreign_keys_passes(self) -> None:
        from model_generator.generate import _validate_composite_foreign_keys

        _validate_composite_foreign_keys({"entities": {}})  # no entities, no FKs

    def test_valid_composite_fk_passes(self) -> None:
        from model_generator.generate import _validate_composite_foreign_keys

        _validate_composite_foreign_keys(self._model_with_fk(self._valid_fk()))

    def test_length_mismatch_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_composite_foreign_keys

        bad = {**self._valid_fk(), "references_columns": ["tenant_id"]}
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(self._model_with_fk(bad))
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "must match" in out
        assert "OrderItem.foreign_keys[0]" in out

    def test_unknown_field_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_composite_foreign_keys

        bad = {**self._valid_fk(), "fields": ["tenant_id", "ghost_col"]}
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(self._model_with_fk(bad))
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "ghost_col" in out
        assert "not declared" in out

    def test_reference_typed_member_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Composite-FK members must use the underlying type, not 'reference'."""
        from model_generator.generate import _validate_composite_foreign_keys

        model = self._model_with_fk(self._valid_fk())
        model["entities"]["OrderItem"]["fields"]["tenant_id"] = {
            "type": "reference",
            "reference_table": "orders",
        }
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(model)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert 'type "reference"' in out
        assert "mutex" in out

    def test_unknown_references_table_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_composite_foreign_keys

        bad = {**self._valid_fk(), "references_table": "ghost_table"}
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(self._model_with_fk(bad))
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "ghost_table" in out
        assert "not found in this model" in out


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


class TestValidateGenerationConfig:
    """Test the _validate_generation_config helper."""

    def test_default_layout_passes(self) -> None:
        from model_generator.generate import _validate_generation_config

        _validate_generation_config(config={})

    def test_per_entity_passes(self) -> None:
        from model_generator.generate import _validate_generation_config

        _validate_generation_config({"generation": {"layout": "per-entity"}})

    def test_per_domain_passes(self) -> None:
        from model_generator.generate import _validate_generation_config

        _validate_generation_config({"generation": {"layout": "per-domain"}})

    def test_unknown_layout_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_generation_config

        with pytest.raises(SystemExit) as excinfo:
            _validate_generation_config({"generation": {"layout": "weird"}})
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "weird" in out
        assert "generation.layout" in out


class TestValidatePathsBase:
    """Test the _validate_paths_base helper."""

    def test_default_paths_pass(self) -> None:
        from model_generator.generate import _validate_paths_base

        _validate_paths_base(config={})

    def test_base_inside_database_models_passes(self) -> None:
        from model_generator.generate import _validate_paths_base

        _validate_paths_base(
            {
                "paths": {
                    "database_models": "src/db/models",
                    "base": "src/db/models/base.py",
                }
            }
        )

    def test_default_base_derives_from_custom_database_models(self) -> None:
        """When database_models is custom but base is omitted, the default
        derives the base path from database_models — so no mismatch fires."""
        from model_generator.generate import _validate_paths_base

        _validate_paths_base({"paths": {"database_models": "lib/db/models"}})

    def test_non_base_filename_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.generate import _validate_paths_base

        with pytest.raises(SystemExit) as excinfo:
            _validate_paths_base(
                {
                    "paths": {
                        "database_models": "src/db/models",
                        "base": "src/db/models/foundation.py",
                    }
                }
            )
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "base.py" in out
        assert "foundation.py" in out

    def test_base_outside_database_models_exits(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.generate import _validate_paths_base

        with pytest.raises(SystemExit) as excinfo:
            _validate_paths_base(
                {
                    "paths": {
                        "database_models": "hub/database/models",
                        "base": "hub/database/base.py",
                    }
                }
            )
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "paths.base" in out
        assert "hub/database/base.py" in out
        assert "hub/database/models" in out
        assert "from .base import Base" in out


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


class TestEnumsGenerator:
    """Test enum generation."""

    def test_creates_enums_file(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)

        assert result is not None
        assert result["mode"] == "write"
        assert result["skipped"] == 0
        assert result["new_count"] == 1
        enums_file = project_root / config["paths"]["database_models"] / "enums.py"
        assert result["path"] == enums_file
        assert "class ItemType(StrEnum):" in result["content"]
        assert "STANDARD" in result["content"]

    def test_append_mode_adds_new_enums(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)

        assert result is not None
        assert result["mode"] == "append"
        assert result["path"] == enums_file
        assert result["new_count"] == 1
        assert result["skipped"] == 1
        assert "class OrderStatus(StrEnum):" in result["content"]
        assert "ItemType" not in result["content"]

    def test_no_enums_returns_none(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Generate enums when no _shared/enums.json exists."""
        project_root, config, env = project_env

        models_dir = project_root / "models"
        models_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))

        result = generate_enums(minimal_model, config, env, project_root, model_file)
        assert result is None

    def test_append_mode_skips_existing(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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

    def _setup_enums(
        self,
        project_root: Any,
        config: Any,
        minimal_model: dict[str, Any],
        enums_data: Any,
    ) -> Path:
        """Helper: create model file and shared enums.json, return model_file path."""
        models_dir = project_root / "models"
        shared_dir = models_dir / "_shared"
        shared_dir.mkdir(parents=True)
        model_file = models_dir / "items.model.json"
        model_file.write_text(json.dumps(minimal_model))
        (shared_dir / "enums.json").write_text(json.dumps(enums_data))
        assert isinstance(model_file, Path)
        return model_file

    def test_create_mode_includes_imports(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)
        assert result is not None
        assert "from enum import StrEnum" in result["content"]

    def test_create_mode_includes_section_header(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_append_content_starts_with_newline(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)
        assert result is not None
        assert result["content"].startswith("\n")

    def test_append_includes_enums_section_header(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
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
        assert isinstance(result, dict)
        assert result is not None
        assert "# ENUMS" in result["content"]

    def test_no_enums_prints_message(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
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

    def test_no_constraints_returns_none(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Model without constraints returns None."""
        project_root, config, env = project_env
        # No _shared/constraints.json and no field constraints
        result = generate_constraints(minimal_model, config, env, project_root)
        assert result is None

    def test_generates_constraints(self, project_env: Any) -> None:
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
            assert isinstance(result, dict)
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
        # Helper functions are not emitted (they were never imported by any
        # generated file; SQL CHECKs are inlined in model.py.j2).
        assert "def validate_percentage" not in result["content"]

    def test_append_mode_for_existing_file(self, project_env: Any) -> None:
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
        constraints_data: dict[str, Any] = {"constraints": {}}
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
            assert isinstance(result, dict)
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

    def _make_refs(self) -> tuple[list[Any], set[Any]]:
        return [], set()

    def test_extract_ref_type_from_ref_def(self) -> None:
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

    def test_extract_ref_type_from_constraint(self) -> None:
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

    def test_extract_ref_type_default_decimal(self) -> None:
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

    def test_extract_regex_ref_unknown_ref_ok(self) -> None:
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

    def test_extract_regex_ref_deduplication(self) -> None:
        """Same regex_ref is only extracted once."""
        refs, seen = self._make_refs()
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field1", refs, seen)
        _extract_regex_ref({"regex_ref": "PAT"}, {}, "field2", refs, seen)
        assert len(refs) == 1

    def test_extract_constraint_refs_field_name_propagates(self) -> None:
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

    def test_creates_migration_directories(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)

        migrations_dir = project_root / "alembic"
        assert migrations_dir.is_dir()
        assert (migrations_dir / "versions").is_dir()

    def test_returns_all_migration_files(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        assert isinstance(result, list)
        assert len(result) == 5
        paths = [r["path"] for r in result]
        migrations_dir = project_root / "alembic"
        assert project_root / "alembic.ini" in paths
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_env_py_content_uses_config(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        migrations_dir = project_root / "alembic"
        env_py = next(r for r in result if r["path"] == migrations_dir / "env.py")
        # config.paths.database_models is used in the import path
        assert "src.database.models" in env_py["content"]

    def _env_py(self, minimal_model: dict[str, Any], project_env: Any) -> str:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)
        env_py = next(
            r for r in result if r["path"] == project_root / "alembic" / "env.py"
        )
        content = env_py["content"]
        assert isinstance(content, str)
        return content

    def test_env_py_is_valid_python(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """The rendered env.py must parse — guards the new helper blocks."""
        import ast

        ast.parse(self._env_py(minimal_model, project_env))

    def test_env_py_coerces_async_drivers_to_sync(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Alembic runs sync, so get_url() must coerce async drivers."""
        content = self._env_py(minimal_model, project_env)
        assert "def _coerce_sync_driver(url: str) -> str:" in content
        assert '"+asyncpg": "+psycopg2",' in content
        assert '"+aiosqlite": "",' in content
        # get_url returns the coerced URL, not the raw one.
        assert "return _coerce_sync_driver(url)" in content
        # Only the scheme is rewritten, so credentials/db names are never mangled.
        assert 'scheme, sep, rest = url.partition("://")' in content
        assert "scheme.endswith(async_driver)" in content

    def test_coerce_sync_driver_behaviour(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Exercise the generated _coerce_sync_driver in isolation (executing
        the whole module would run migrations)."""
        import ast

        content = self._env_py(minimal_model, project_env)
        tree = ast.parse(content)
        wanted = {"_ASYNC_TO_SYNC_DRIVERS", "_coerce_sync_driver"}
        nodes: list[ast.stmt] = [
            n
            for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name in wanted)
            or (
                isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) in wanted for t in n.targets)
            )
        ]
        ns: dict[str, Any] = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<env>", "exec"), ns)
        coerce = ns["_coerce_sync_driver"]
        assert (
            coerce("postgresql+asyncpg://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
        )
        assert coerce("sqlite+aiosqlite:///x.db") == "sqlite:///x.db"
        # A driver substring inside credentials must NOT be rewritten.
        assert coerce("postgresql://u:+asyncpg@h/db") == "postgresql://u:+asyncpg@h/db"
        # Already-sync URLs pass through untouched.
        assert coerce("postgresql://u:p@h/db") == "postgresql://u:p@h/db"

    def test_env_py_renders_custom_types_with_import(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """render_item must be wired into both configure() calls and import
        the project's custom column types into generated migrations."""
        content = self._env_py(minimal_model, project_env)
        assert "def render_item(type_: str, obj: Any, autogen_context: Any)" in content
        assert '_CUSTOM_TYPE_MODULE = "src.database.types"' in content
        # Wired into offline and online configure() calls.
        assert content.count("render_item=render_item,") == 2

    def test_custom_migrations_path(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "custom_migrations").is_dir()
        assert (project_root / "custom_migrations" / "versions").is_dir()

    def test_alembic_ini_content_uses_migrations_path(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        ini = next(r for r in result if r["path"] == project_root / "alembic.ini")
        assert "script_location = custom_migrations" in ini["content"]

    def test_default_path_when_key_absent(
        self, minimal_model: dict[str, Any], project_env: Any, tmp_path: Path
    ) -> None:
        project_root, config, env = project_env
        del config["paths"]["migrations"]
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "alembic").is_dir()
        assert (project_root / "alembic" / "versions").is_dir()

    def test_creates_nested_project_root(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        deep_root = project_root / "subdir"
        generate_migration_init(minimal_model, config, env, deep_root)

        assert (deep_root / "alembic").is_dir()
        assert (deep_root / "alembic" / "versions").is_dir()

    def test_idempotent_mkdir(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)
        # Second call must not raise FileExistsError
        generate_migration_init(minimal_model, config, env, project_root)

    def test_gitkeep_content_is_empty(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        migrations_dir = project_root / "alembic"
        gitkeep = next(
            r for r in result if r["path"] == migrations_dir / "versions" / ".gitkeep"
        )
        assert gitkeep["content"] == ""

    def test_generate_migration_init_skips_alembic_ini_when_exists(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Pre-existing alembic.ini stays put; in-tree alembic/ files still emit."""
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text(
            "[alembic]\nscript_location = custom\n"
        )

        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        paths = [r["path"] for r in result]
        assert project_root / "alembic.ini" not in paths
        migrations_dir = project_root / "alembic"
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_generate_migration_init_with_no_root_files_skips_alembic_ini(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """--no-root-files suppresses alembic.ini; in-tree alembic/ files still emit."""
        project_root, config, env = project_env

        result = generate_migration_init(
            minimal_model, config, env, project_root, no_root_files=True
        )
        assert isinstance(result, list)

        paths = [r["path"] for r in result]
        assert project_root / "alembic.ini" not in paths
        assert not (project_root / "alembic.ini").exists()
        # In-tree alembic/ scaffolding still emits (lives inside the migrations dir).
        migrations_dir = project_root / "alembic"
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_generate_migration_init_dry_run_skips_mkdir(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """dry_run=True returns file specs but does not create directories."""
        project_root, config, env = project_env

        result = generate_migration_init(
            minimal_model, config, env, project_root, dry_run=True
        )
        assert isinstance(result, list)
        assert len(result) > 0

        # No directories were actually created on disk.
        assert not (project_root / "alembic").exists()
        assert not (project_root / "alembic" / "versions").exists()

    def test_migration_env_custom_type_names_constant(self) -> None:
        """_CUSTOM_TYPE_NAMES in migrations.py is the single source of truth
        for which custom types env.py must import — not a template literal."""
        from model_generator.generators.migrations import _CUSTOM_TYPE_NAMES

        assert "PortableNumeric" in _CUSTOM_TYPE_NAMES
        assert "PortableUuid" in _CUSTOM_TYPE_NAMES

    def test_migration_env_renders_custom_type_names(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Rendered env.py _CUSTOM_TYPE_NAMES must reflect the generator constant,
        not a hardcoded literal — so renaming a type in migrations.py propagates."""
        from model_generator.generators.migrations import _CUSTOM_TYPE_NAMES

        content = self._env_py(minimal_model, project_env)
        for name in _CUSTOM_TYPE_NAMES:
            assert f'"{name}"' in content, (
                f"Expected '{name}' to appear in rendered env.py _CUSTOM_TYPE_NAMES"
            )
        # The assignment must be present and be a tuple, not a hardcoded one-liner.
        assert "_CUSTOM_TYPE_NAMES = (" in content


class TestMigrationAutogen:
    """Test generate_migration_autogen."""

    # GEN-12: the target is instruction-only and emits no file, so it returns
    # ``None`` rather than a sentinel dict the output dispatch had to
    # special-case. The ``-> None`` signature (CI-enforced by mypy) is the
    # guard against a dict being reintroduced; behaviour is covered below.

    def test_warning_message_when_not_initialized(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root, config, env = project_env
        generate_migration_autogen(minimal_model, config, env, project_root)
        captured = capsys.readouterr()

        assert (
            captured.out.rstrip("\n")
            == "  ⚠️  Alembic not initialized. Run with --target migration-init first."
        )

    def test_prints_project_agnostic_instructions_when_initialized(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        generate_migration_autogen(minimal_model, config, env, project_root)
        out = capsys.readouterr().out

        # Honest: no false "Running alembic…" line — nothing is actually run.
        assert "Running alembic revision --autogenerate..." not in out
        # GEN-6: instructions must be project-agnostic — no hardcoded
        # TimescaleDB / docker-compose orchestration.
        assert "timescale" not in out.lower()
        assert "docker-compose" not in out
        assert "docker compose" not in out
        # Still surfaces the actionable guidance.
        assert "DATABASE_URL" in out
        assert "alembic revision --autogenerate" in out
        assert "alembic upgrade head" in out


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
        result = generate_pyproject(
            config, env, project_root, no_root_files=True
        )
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
        result = generate_env_example(
            config, env, project_root, no_root_files=True
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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

        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert result is None

    def test_generate_main_no_auth_router_when_strategy_unset(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert isinstance(result, dict)
        content = result["content"]
        # Auth + CSRF still wired, rate-limit pieces absent
        assert "auth_router" in content
        assert "RateLimitExceeded" not in content
        assert "app.state.limiter" not in content

    def test_generate_main_cors_no_wildcard_default(self, project_env: Any) -> None:
        """CORS default is a concrete dev origin, never the wildcard."""
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert isinstance(result, dict)
        assert '"X-CSRF-Token",' in result["content"]

    def test_generate_main_cors_omits_csrf_header_when_no_auth(
        self, project_env: Any
    ) -> None:
        """No auth/CSRF → the X-CSRF-Token header is absent from the allowlist."""
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
        assert isinstance(result, dict)
        assert "RequestBodySizeLimitMiddleware" not in result["content"]

    def test_generate_main_body_limit_before_cors(self, project_env: Any) -> None:
        """P3: body limit is added before CORS so CORS stays outermost."""
        project_root, config, env = project_env
        result = generate_main(
            config, env, project_root, domains=["users"], project_config=config
        )
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
            project_config=config,
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
        import sys
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
        import sys
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


class TestAuthRouterGenerator:
    """Smoke-test the §12 auth_router emission helper."""

    def _project_config(self) -> dict[str, Any]:
        return {"project": {"name": "Test"}}

    def test_returns_none_when_strategy_unset(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        result = generate_auth_router(config, env, project_root, self._project_config())
        assert result is None

    def test_emits_router_when_strategy_set(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
        }

        result = generate_auth_router(config, env, project_root, self._project_config())
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
        import ast

        ast.parse(content)

    def test_emits_per_entity_imports(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_auth_router

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "bcrypt-session", "pepper_env": "X"},
        }

        result = generate_auth_router(config, env, project_root, self._project_config())
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

        result = generate_auth_router(config, env, project_root, self._project_config())
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

        result = generate_auth_router(config, env, project_root, self._project_config())
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

        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        import ast

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
        result = generate_auth_router(config, env, project_root, self._project_config())
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
        assert (
            generate_api_key_auth(config, env, project_root, self._project_config())
            is None
        )

    def test_returns_none_for_session_strategy(
        self, project_env_per_entity: Any
    ) -> None:
        """api-key generator must not fire for the session strategy."""
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "bcrypt-session", "pepper_env": "X"}}
        assert (
            generate_api_key_auth(config, env, project_root, self._project_config())
            is None
        )

    def test_emits_dependency_when_strategy_api_key(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {**config, "auth": {"strategy": "api-key"}}
        result = generate_api_key_auth(
            config, env, project_root, self._project_config()
        )
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
        result = generate_api_key_auth(
            config, env, project_root, self._project_config()
        )
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
        import ast

        from model_generator.generators.infrastructure import generate_api_key_auth

        project_root, config, env = project_env_per_entity
        config = {
            **config,
            "auth": {"strategy": "api-key", "header_name": "1 Weird.Header!"},
        }
        result = generate_api_key_auth(
            config, env, project_root, self._project_config()
        )
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
        assert (
            generate_api_key_auth(config, env, project_root, self._project_config())
            is None
        )

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
        assert (
            generate_auth_router(config, env, project_root, self._project_config())
            is None
        )
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
        import ast

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
        import ast

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


class TestEncryptedBytesGenerator:
    """Smoke-test the §13 EncryptedBytes TypeDecorator emission helper.

    Closes the latent emission gap: ``model.py.j2`` conditionally imports
    ``from .encrypted_bytes import EncryptedBytes`` when any field declares
    ``type: binary`` + ``encrypt: {...}``, but until this generator landed
    no infrastructure code emitted the imported module.
    """

    def test_returns_none_when_no_encrypted_binary(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        # has_encrypted_binary defaults to False — common-case projects with
        # no binary+encrypt fields must not get a stray cryptography import.
        assert generate_encrypted_bytes(config, env, project_root) is None

    def test_emits_when_flag_set(self, project_env_per_entity: Any) -> None:
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        result = generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)

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

    def test_signatures_are_fully_annotated(self, project_env_per_entity: Any) -> None:
        """TPL-10: every method/function carries annotations so the file passes
        the strict mypy config the generator also ships.

        Mirrors the ``types.py`` TypeDecorator convention (``dialect: Any``);
        an unannotated ``_get_fernet`` or ``dialect`` param fails
        ``disallow_untyped_defs``. ``_get_fernet`` is typed ``-> Fernet`` (not
        ``Any``) so the bind/result values stay ``bytes``, dodging
        ``warn_return_any``.
        """
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, config, env = project_env_per_entity
        result = generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)
        content = result["content"]

        assert "from typing import TYPE_CHECKING, Any" in content
        assert 'def _get_fernet() -> "Fernet":' in content
        assert "from cryptography.fernet import Fernet" in content
        assert "value: bytes | None, dialect: Any" in content
        assert "def load_dialect_impl(self, dialect: Any) -> Any:" in content
        # No bare (unannotated) `dialect` parameter should remain.
        assert "dialect)" not in content

        # The annotated file must parse cleanly.
        import ast

        ast.parse(content)

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:
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

    def test_path_follows_custom_database_models(
        self, project_env_per_entity: Any
    ) -> None:
        from model_generator.generators.infrastructure import generate_encrypted_bytes

        project_root, _config, env = project_env_per_entity
        # Custom layout: adopter put models elsewhere; emission must follow.
        custom_config = {
            "paths": {"database_models": "backend/lib/db/models"},
        }
        result = generate_encrypted_bytes(
            custom_config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)

        assert result is not None
        assert (
            result["path"] == project_root / "backend/lib/db/models/encrypted_bytes.py"
        )

    def test_emission_wired_into_generate_infrastructure(
        self, project_env_per_entity: Any
    ) -> None:
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

    def test_aggregator_skips_when_flag_unset(
        self, project_env_per_entity: Any
    ) -> None:
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


class TestHasEncryptedBinaryField:
    """Test the _has_encrypted_binary_field helper (§13 emission gate)."""

    def test_empty_models_returns_false(self) -> None:
        from model_generator.generate import _has_encrypted_binary_field

        assert _has_encrypted_binary_field([]) is False

    def test_model_without_binary_field_returns_false(self) -> None:
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "User": {"fields": {"email": {"type": "text"}}},
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is False

    def test_binary_field_without_encrypt_returns_false(self) -> None:
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

    def test_binary_with_encrypt_returns_true(self) -> None:
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

    def test_detected_in_later_model_in_list(self) -> None:
        """Mixed-project case: only the second model carries an encrypted field."""
        from model_generator.generate import _has_encrypted_binary_field

        models: list[dict[str, Any]] = [
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
    config = load_config("python-fastapi")
    env = get_template_env("python-fastapi", config=config)
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


@pytest.fixture
def cross_domain_models() -> list[dict[str, Any]]:
    """Two SEPARATE domain specs whose relationships cross the domain boundary.

    blog.Post --one_to_many--> engagement.Comment (and back). In a real
    generated project each domain is its own module; SQLAlchemy only sees one
    registry once every module is imported. The existing mapper probe
    (TestCompositeForeignKey::test_configure_mappers_succeeds) only configures
    a SINGLE composite-FK model, so a back_populates / join-condition mistake
    that only manifests once two domains share a registry would go unnoticed.
    """
    blog = {
        "domain": "blog",
        "entities": {
            "Author": {
                "table": "authors",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "name": {"type": "text", "max_length": 100, "required": True},
                },
                "relationships": {
                    "posts": {
                        "type": "one_to_many",
                        "target": "Post",
                        "back_populates": "author",
                    },
                },
            },
            "Post": {
                "table": "posts",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "title": {"type": "text", "max_length": 200, "required": True},
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
                    # Cross-domain: Comment lives in the `engagement` model.
                    "comments": {
                        "type": "one_to_many",
                        "target": "Comment",
                        "back_populates": "post",
                    },
                },
            },
        },
    }
    engagement = {
        "domain": "engagement",
        "entities": {
            "Comment": {
                "table": "comments",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "body": {"type": "text", "max_length": 500, "required": True},
                    # Cross-domain FK back to blog.Post.
                    "post_id": {
                        "type": "reference",
                        "reference_entity": "Post",
                        "reference_table": "posts",
                        "required": True,
                    },
                },
                "relationships": {
                    "post": {
                        "type": "many_to_one",
                        "target": "Post",
                        "back_populates": "comments",
                    },
                },
            },
        },
    }
    return [blog, engagement]


class TestCrossDomainMapperConfig:
    """TST-5: probe SQLAlchemy mapper configuration across domain boundaries.

    Generates two independent domain specs, merges every emitted model file
    into one shared registry (exactly what happens at import time in a real
    project), and calls ``registry.configure()`` — the step that raises if a
    cross-domain ``back_populates`` / join condition is misconfigured.
    """

    def _merged_namespace(
        self,
        models: list[dict[str, Any]],
        project_env_per_entity: Any,
    ) -> dict[str, Any]:
        from sqlalchemy import String
        from sqlalchemy.orm import DeclarativeBase

        project_root, config, env = project_env_per_entity
        contents: list[str] = []
        for model in models:
            result = generate_database_model(model, config, env, project_root)
            assert isinstance(result, list)  # per-entity → one file per entity
            contents.extend(entry["content"] for entry in result)

        merged = "\n".join(contents)
        # Strip relative + project-local imports; Base + PortableUuid are supplied.
        merged = re.sub(r"^from (?:\.|src\.)[^\n]+\n", "", merged, flags=re.MULTILINE)

        class Base(DeclarativeBase):
            pass

        namespace: dict[str, Any] = {"Base": Base, "PortableUuid": String}
        exec(merged, namespace)
        return namespace

    def test_cross_domain_configure_mappers_succeeds(
        self, cross_domain_models: list[dict[str, Any]], project_env_per_entity: Any
    ) -> None:
        namespace = self._merged_namespace(cross_domain_models, project_env_per_entity)
        from sqlalchemy.orm import DeclarativeBase

        base = namespace["Base"]
        assert issubclass(base, DeclarativeBase)
        # All three classes from both domains land in one registry.
        for cls_name in ("Author", "Post", "Comment"):
            assert cls_name in namespace, f"{cls_name} missing from merged module"
        # The real assertion: configuring the shared registry must not raise
        # (ArgumentError / InvalidRequestError on a broken cross-domain rel).
        base.registry.configure()

    def test_cross_domain_relationships_resolve_both_directions(
        self, cross_domain_models: list[dict[str, Any]], project_env_per_entity: Any
    ) -> None:
        """After configure(), the cross-domain relationship is mapped on both
        ends with a usable join condition."""
        namespace = self._merged_namespace(cross_domain_models, project_env_per_entity)
        post = namespace["Post"]
        comment = namespace["Comment"]
        post.registry.configure()

        from sqlalchemy import inspect as sa_inspect

        post_rels = sa_inspect(post).relationships
        comment_rels = sa_inspect(comment).relationships
        assert "comments" in post_rels
        assert "post" in comment_rels
        # The pair is wired as inverses of each other.
        assert post_rels["comments"].back_populates == "post"
        assert comment_rels["post"].back_populates == "comments"


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


class TestPyprojectAsyncioMode:
    """TPL-13: asyncio_mode must not be emitted — the generated tests are sync."""

    def test_asyncio_mode_absent_from_pyproject(self, project_env: Any) -> None:
        """asyncio_mode = 'auto' must not appear; it needs pytest-asyncio which
        is not in the generated dev deps, and the contract tests are sync."""
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root)
        assert isinstance(result, dict)
        assert "asyncio_mode" not in result["content"]


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


class TestDocstringEscaping:
    """Descriptions with triple-quotes must not break generated docstrings (SEC-8)."""

    @pytest.fixture
    def triple_quote_model(self) -> dict[str, Any]:
        return {
            "domain": "items",
            "description": 'Has """triple quotes""" in description.',
            "entities": {
                "Item": {
                    "table": "items",
                    "description": 'Entity with """triple""" quotes.',
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                            "description": 'A field with """quotes""".',
                        },
                        "name": {
                            "type": "text",
                            "max_length": 100,
                            "required": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_factory_docstring_escapes_triple_quotes(
        self,
        triple_quote_model: dict[str, Any],
        project_env: Any,
    ) -> None:
        project_root, config, env = project_env
        result = generate_factories(triple_quote_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]

        # The raw triple-quote sequence must not appear in the output
        assert '"""triple"""' not in content
        # Output must be valid Python
        ast.parse(content)

    def test_database_model_docstring_escapes_triple_quotes(
        self,
        triple_quote_model: dict[str, Any],
        project_env: Any,
    ) -> None:
        project_root, config, env = project_env
        result = generate_database_model(triple_quote_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]

        assert '"""triple"""' not in content
        ast.parse(content)


# ---------------------------------------------------------------------------
# TST-8: Unicode / special-character content and large-spec characterisation
# ---------------------------------------------------------------------------


class TestUnicodeDescriptions:
    """Generator output must be valid UTF-8 and parseable when descriptions
    contain accented characters, emoji, or other non-ASCII unicode.

    These are characterisation tests — the generator already handles unicode
    correctly; the tests lock in that behaviour.
    """

    def _unicode_model(self) -> dict[str, Any]:
        return {
            "domain": "users",
            "description": "Représentation d'un utilisateur (用户)",
            "entities": {
                "User": {
                    "table": "users",
                    "description": "Représentation d'un utilisateur (用户)",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "email": {
                            "type": "text",
                            "max_length": 254,
                            "required": True,
                            "unique": True,
                            "description": "Email address 📧 of the user",
                        },
                        "name": {
                            "type": "text",
                            "max_length": 200,
                            "required": True,
                            "description": "Full name — prénom et nom de famille",
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_generate_factories_succeeds_with_unicode(self, project_env: Any) -> None:
        """generate_factories must not raise and must return content."""
        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        assert result["content"]

    def test_generate_factories_output_is_valid_utf8(
        self, project_env: Any, tmp_path: Path
    ) -> None:
        """Generated factory file must be encodable / decodable as UTF-8."""
        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        out_file = tmp_path / "users_factory.py"
        out_file.write_text(result["content"], encoding="utf-8")
        content = out_file.read_text(encoding="utf-8")
        assert content == result["content"]

    def test_generate_factories_output_is_ast_parseable(self, project_env: Any) -> None:
        """Generated factory file must be syntactically valid Python."""
        import ast

        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        ast.parse(result["content"])  # raises SyntaxError on failure

    def test_generate_api_models_succeeds_with_unicode(self, project_env: Any) -> None:
        """generate_api_models must not raise with unicode descriptions."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_generate_api_models_output_contains_unicode(
        self, project_env: Any
    ) -> None:
        """Unicode description text must survive template rendering unchanged."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        all_content = "\n".join(r["content"] for r in results)
        assert "📧" in all_content or "Email address" in all_content

    def test_generate_api_models_output_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Every api-models file must be syntactically valid Python."""
        import ast

        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])  # raises SyntaxError on failure

    def test_generate_api_models_output_is_valid_utf8(
        self, project_env: Any, tmp_path: Path
    ) -> None:
        """All generated API-model files must be round-trip safe as UTF-8."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        for i, item in enumerate(results):
            out_file = tmp_path / f"api_model_{i}.py"
            out_file.write_text(item["content"], encoding="utf-8")
            assert out_file.read_text(encoding="utf-8") == item["content"]


class TestSpecialCharDescriptions:
    """Generator output must remain parseable when descriptions contain
    backslashes, single/double quotes, newlines, or triple-quote sequences.

    These are characterisation tests — they document safe behaviour and pin
    it against regressions.  The triple-quote test is marked xfail if the
    current generator does not yet escape triple-quotes inside docstrings
    (tracked as SEC-8).
    """

    def _model_with_description(self, description: str) -> dict[str, Any]:
        return {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "description": description,
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "label": {
                            "type": "text",
                            "max_length": 100,
                            "required": True,
                            "description": description,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    @pytest.mark.xfail(
        reason="SEC-8: backslashes in descriptions are not escaped in docstrings; "
        "renders as an invalid unicode escape sequence inside the triple-quoted "
        "docstring body"
    )
    def test_backslash_in_description_is_ast_parseable(self, project_env: Any) -> None:
        """Backslashes in descriptions must not break template rendering.

        This test documents the expected safe behaviour once SEC-8 is fixed.
        Until then it is expected to fail (xfail) so it does not block CI.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description(r"Path is C:\Users\name")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    def test_double_quotes_in_description_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Double quotes in descriptions must not break template rendering."""
        import ast

        project_root, config, env = project_env
        model = self._model_with_description("He said \"hello\" and she said 'bye'")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    @pytest.mark.xfail(
        reason="SEC-8: newlines in descriptions are not escaped in Field() "
        "description strings; renders as an unterminated string literal"
    )
    def test_newlines_in_description_is_ast_parseable(self, project_env: Any) -> None:
        """Embedded newlines in descriptions must not break template rendering.

        This test documents the expected safe behaviour once SEC-8 is fixed.
        Until then it is expected to fail (xfail) so it does not block CI.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description("Line one\nLine two\nLine three")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    def test_triple_quotes_in_description_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Triple-quote sequences in descriptions must not break docstrings.

        SEC-8 fixed: triple-quotes are now escaped via the safe_docstring
        Jinja2 filter applied to all description sites in the templates.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description('Open """triple""" quotes here')
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])


class TestLargeSpecGeneration:
    """Regression guard: generating a spec with many entities and fields must
    complete without error and within a reasonable wall-clock time.

    This catches O(N^2) behaviours, truncation bugs, and memory issues that
    only appear at scale.  The tests are marked ``slow`` so ``make test``
    skips them; ``make test-all`` runs them.
    """

    @staticmethod
    def _build_large_model(
        num_entities: int = 15, fields_per_entity: int = 8
    ) -> dict[str, Any]:
        """Build a model dict with *num_entities* entities, each with
        *fields_per_entity* fields drawn from a variety of types."""
        field_types: list[dict[str, Any]] = [
            {"type": "text", "max_length": 200, "required": True},
            {"type": "text", "max_length": 100},
            {"type": "counter", "default": 0},
            {"type": "counter", "default": 1},
            {"type": "financial"},
            {"type": "text", "max_length": 50, "unique": True},
            {"type": "text", "max_length": 500},
            {"type": "counter"},
        ]
        entities: dict[str, Any] = {}
        for i in range(num_entities):
            entity_name = f"Entity{i:02d}"
            fields: dict[str, Any] = {
                "id": {
                    "type": "uuid",
                    "primary_key": True,
                    "auto_generate": True,
                }
            }
            for j in range(fields_per_entity):
                field_def = dict(field_types[j % len(field_types)])
                field_def["description"] = (
                    f"Field {j} of entity {i} — description with some text"
                )
                fields[f"field_{j:02d}"] = field_def
            entities[entity_name] = {
                "table": f"entity_{i:02d}s",
                "description": f"Entity number {i} in the large-spec test",
                "fields": fields,
                "timestamps": {"created": True, "updated": True},
            }
        return {
            "domain": "largescale",
            "description": "Large-scale model for regression testing",
            "entities": entities,
        }

    @pytest.mark.slow
    def test_generate_factories_large_spec(self, project_env: Any) -> None:
        """generate_factories on a 15-entity spec must complete in under 5 s."""
        import ast
        import time

        project_root, config, env = project_env
        model = self._build_large_model()

        start = time.monotonic()
        result = generate_factories(model, config, env, project_root)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"generate_factories took {elapsed:.2f}s (limit 5s)"
        assert isinstance(result, dict)
        ast.parse(result["content"])

    @pytest.mark.slow
    def test_generate_api_models_large_spec(self, project_env: Any) -> None:
        """generate_api_models on a 15-entity spec must complete in under 5 s."""
        import ast
        import time

        project_root, config, env = project_env
        model = self._build_large_model()

        start = time.monotonic()
        results = generate_api_models(model, config, env, project_root)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"generate_api_models took {elapsed:.2f}s (limit 5s)"
        assert isinstance(results, list)
        assert len(results) >= 1
        for item in results:
            ast.parse(item["content"])

    @pytest.mark.slow
    def test_large_spec_factory_per_domain_single_file(self, project_env: Any) -> None:
        """Per-domain layout: generate_factories returns one dict for 15 entities."""
        project_root, config, env = project_env
        model = self._build_large_model(num_entities=15, fields_per_entity=8)
        result = generate_factories(model, config, env, project_root)
        # Per-domain layout returns a single dict, not a list
        assert isinstance(result, dict)
        assert result["content"]

    @pytest.mark.slow
    def test_large_spec_per_entity_produces_one_factory_per_entity(
        self, project_env_per_entity: Any
    ) -> None:
        """Per-entity layout: exactly one factory file per entity."""
        import ast

        project_root, config, env = project_env_per_entity
        num_entities = 15
        model = self._build_large_model(num_entities=num_entities, fields_per_entity=8)
        results = generate_factories(model, config, env, project_root)
        assert isinstance(results, list)
        assert len(results) == num_entities
        for item in results:
            ast.parse(item["content"])
