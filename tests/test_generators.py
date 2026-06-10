"""Tests for individual code generators."""

import json
import os
import sys
import types
from pathlib import Path
from typing import Any
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
    generate_gitignore,
    generate_infrastructure,
    generate_main,
    generate_pyproject,
    generate_test_conftest_root,
    generate_types,
    generate_utils,
    generate_validators,
)
from model_generator.utils import get_template_env, load_config


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

    _FAKE_DOMAINS = [
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

        db_models_dir = project_root / config["paths"]["database_models"]
        assert result is not None
        assert result["path"] == db_models_dir / "factories" / "items.py"

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

        db_models_dir = project_root / config["paths"]["database_models"]
        assert result["path"] == db_models_dir / "factories" / "models.py"

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
            "author_requests.py",
            "post_response.py",
            "post_requests.py",
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
        """author_requests.py contains Create/UpdateAuthorRequest and not Post."""
        project_root, config, env = project_env_per_entity
        result = generate_api_models(multi_entity_model, config, env, project_root)
        assert isinstance(result, list)
        author_req = next(
            r["content"] for r in result if r["path"].name == "author_requests.py"
        )
        assert "class CreateAuthorRequest(BaseModel):" in author_req
        assert "class UpdateAuthorRequest(BaseModel):" in author_req
        assert "CreatePostRequest" not in author_req


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
        assert "from .author_requests import" in result["content"]
        assert "from .post_response import" in result["content"]
        assert "from .post_requests import" in result["content"]
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
        assert "items_requests.py" in filenames

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
        assert "def validate_percentage" in result["content"]

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


class TestMigrationAutogen:
    """Test generate_migration_autogen."""

    def test_returns_none_when_not_initialized(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_autogen(minimal_model, config, env, project_root)

        assert result is None

    def test_returns_dict_when_initialized(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        result = generate_migration_autogen(minimal_model, config, env, project_root)
        assert isinstance(result, dict)

        assert result is not None
        assert "info" in result
        assert "instructions" in result
        assert result["info"] == (
            "Migration autogeneration requires DATABASE_URL and should be run manually"
        )
        assert "DATABASE_URL" in result["instructions"]

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

    def test_progress_message_when_initialized(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        generate_migration_autogen(minimal_model, config, env, project_root)
        captured = capsys.readouterr()

        expected = "  Running alembic revision --autogenerate..."
        assert captured.out.rstrip("\n") == expected


class TestInfrastructureGenerators:
    """Test infrastructure file generators."""

    def test_generate_pyproject(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)
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

        result = generate_pyproject(config, env, project_root, config)
        assert result is None

    def test_generate_pyproject_with_no_root_files_returns_none(
        self, project_env: Any
    ) -> None:
        """--no-root-files suppresses pyproject.toml even in a fresh project."""
        project_root, config, env = project_env
        result = generate_pyproject(
            config, env, project_root, config, no_root_files=True
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
        result = generate_pyproject(config, env, project_root, config)
        assert isinstance(result, dict)

        assert result is not None
        for dep in config.get("dependencies", {}).get("runtime", []):
            assert dep in result["content"]

    def test_generate_pyproject_mutmut_targets_logic_files(
        self, project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)
        assert isinstance(result, dict)

        assert result is not None
        assert "validators.py" in result["content"]
        assert "utils.py" in result["content"]
        assert "constraints.py" in result["content"]

    def test_generate_pyproject_has_package_discovery(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_pyproject(config, env, project_root, config)
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
        result = generate_pyproject(config, env, project_root, config)
        assert isinstance(result, dict)

        assert result is not None
        assert 'readme = "README.md"' not in result["content"]
        assert "readme = {text" in result["content"]

    def test_generate_pyproject_merges_extra_deps(self, project_env: Any) -> None:
        project_root, config, env = project_env
        extra = ["bcrypt>=4.0.0", "passlib>=1.7.0"]
        result = generate_pyproject(config, env, project_root, config, extra_deps=extra)
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
        result = generate_pyproject(config, env, project_root, config, extra_deps=extra)
        assert isinstance(result, dict)

        assert result is not None
        assert result["content"].count(base_dep) == 1

    def test_generate_pyproject_style_defaults_omit_ruff_hardcodes(
        self, project_env: Any
    ) -> None:
        """With no overrides, ruff-default keys are absent; ruff uses its own."""
        project_root, config, env = project_env
        config.pop("style", None)
        result = generate_pyproject(config, env, project_root, config)
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
        assert 'requires-python = ">=3.11"' in content
        assert 'python_version = "3.11"' in content

    def test_generate_pyproject_style_overrides_emitted(self, project_env: Any) -> None:
        """All four style overrides appear verbatim in the generated pyproject.toml."""
        project_root, config, env = project_env
        config["style"] = {
            "line_length": 100,
            "python_version": "3.12",
            "quote_style": "single",
            "indent_style": "tab",
        }
        result = generate_pyproject(config, env, project_root, config)
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
        result = generate_pyproject(config, env, project_root, config)
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
        result = generate_pyproject(config, env, project_root, config)
        assert isinstance(result, dict)

        assert result is not None
        # Default python_version still applied, no ruff-level overrides emitted.
        assert 'requires-python = ">=3.11"' in result["content"]
        assert 'python_version = "3.11"' in result["content"]
        assert "line-length = " not in result["content"]

    def test_generate_pyproject_project_config_style_wins(
        self, project_env: Any
    ) -> None:
        """project_config.style takes precedence over config.style when both are set."""
        project_root, config, env = project_env
        config["style"] = {"line_length": 88}
        project_config = {**config, "style": {"line_length": 100}}
        result = generate_pyproject(config, env, project_root, project_config)
        assert isinstance(result, dict)

        assert result is not None
        assert "line-length = 100" in result["content"]
        assert "line-length = 88" not in result["content"]

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
        assert 'allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]' in content
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
        }
        new_infra = [f for f in files2 if f.name in skipped_infra]
        assert len(new_infra) == 0


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
        # Serializer is initialized via the helper, not the inline get-with-default.
        assert "URLSafeTimedSerializer(\n    _resolve_session_secret()\n)" in content

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
