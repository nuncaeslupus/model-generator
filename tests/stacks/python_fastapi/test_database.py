"""Tests for database model, __init__, and factory generators."""

import os
import re
import sys
import types
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import pytest

from model_generator.generators import (
    generate_database_model,
    generate_factories,
    generate_init,
)
from model_generator.utils import load_config


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

    def test_missing_entities_key_returns_domain_file(self, project_env: Any) -> None:
        # Characterization: model.get("entities", {}) must not crash when the key
        # is absent — the {} default must be used, not None.
        # Template is mocked: Jinja2 also accesses model.entities directly, so
        # without the mock, UndefinedError masks the Python-level gap.
        project_root, config, env = project_env
        model_no_entities = {"domain": "test", "description": "no entities key"}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_database_model(
                model_no_entities, config, env, project_root
            )
        assert isinstance(result, dict)
        assert result["path"].name == "test.py"


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

    def test_missing_entities_key_does_not_crash(self, project_env: Any) -> None:
        # Characterization: model.get("entities", {}).keys() must not crash when
        # the entities key is absent — the {} default propagates to the domain list.
        project_root, config, env = project_env
        model_no_entities = {"domain": "test"}
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init(model_no_entities, config, env, project_root)
        # Domain "test" with no entities is appended; template renders; returns dict.
        assert isinstance(result, dict)
        assert result["path"].name == "__init__.py"


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

    def test_missing_entities_key_returns_domain_file(self, project_env: Any) -> None:
        # Characterization: model.get("entities", {}) must not crash when the key
        # is absent — the {} default is used for sibling_entities and table_to_entity.
        # Template is mocked: Jinja2 also accesses model.entities directly.
        project_root, config, env = project_env
        model_no_entities = {"domain": "test"}
        with patch.object(env, "get_template") as mock_get:
            mock_get.return_value.render.return_value = "# mocked"
            result = generate_factories(
                model_no_entities, config, env, project_root, constraints={}
            )
        assert isinstance(result, dict)
        assert result["path"].name == "test.py"

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


class TestDatabaseGeneratorEntityConstraints:
    """EX-6: entity-level table constraints (check / unique / depends types)."""

    def _model(self, constraints: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "domain": "trade",
            "entities": {
                "Order": {
                    "table": "orders",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "amount": {"type": "financial", "required": True},
                        "fee": {"type": "financial"},
                        "ref_code": {"type": "text"},
                    },
                    "constraints": constraints,
                }
            },
        }

    def test_check_constraint_emits_check_constraint(self, project_env: Any) -> None:
        project_root, config, env = project_env
        constraint = {
            "type": "check",
            "name": "ck_orders_amount_positive",
            "expression": "CAST(amount AS NUMERIC) >= 0",
        }
        result = generate_database_model(
            self._model([constraint]), config, env, project_root
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert 'CheckConstraint("CAST(amount AS NUMERIC) >= 0"' in content
        assert 'name="ck_orders_amount_positive"' in content

    def test_unique_constraint_emits_unique_constraint(self, project_env: Any) -> None:
        project_root, config, env = project_env
        result = generate_database_model(
            self._model([{"type": "unique", "fields": ["amount", "ref_code"]}]),
            config,
            env,
            project_root,
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert '"amount", "ref_code"' in content
        assert 'name="uq_orders_amount_ref_code"' in content
        assert "UniqueConstraint" in content
        assert "CheckConstraint" not in content

    def test_depends_constraint_emits_check_constraint(self, project_env: Any) -> None:
        project_root, config, env = project_env
        constraint = {
            "type": "depends",
            "field": "fee",
            "operator": "<=",
            "other_field": "amount",
        }
        result = generate_database_model(
            self._model([constraint]), config, env, project_root
        )
        assert isinstance(result, dict)
        content = result["content"]
        assert '"fee <= amount"' in content
        assert 'name="ck_orders_fee_amount"' in content

    def test_check_constraint_imports_check_constraint(self, project_env: Any) -> None:
        project_root, config, env = project_env
        constraint = {"type": "check", "name": "ck_ok", "expression": "amount >= 0"}
        result = generate_database_model(
            self._model([constraint]), config, env, project_root
        )
        assert isinstance(result, dict)
        assert "CheckConstraint" in result["content"]


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

    def test_missing_entities_key_returns_empty_list(
        self, project_env_per_entity: Any
    ) -> None:
        # Characterization: model.get("entities", {}).items() in the per-entity
        # branch must not crash when absent — {} default → empty list returned.
        project_root, config, env = project_env_per_entity
        result = generate_database_model({"domain": "test"}, config, env, project_root)
        assert result == []


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

    def test_missing_entities_key_returns_none(
        self, project_env_per_entity: Any
    ) -> None:
        # Characterization: for name in model.get("entities", {}) in the per-entity
        # branch must not crash when key is absent — empty loop, empty domains → None.
        project_root, config, env = project_env_per_entity
        with patch(
            "model_generator.generators.database.scan_model_files", return_value=[]
        ):
            result = generate_init({"domain": "test"}, config, env, project_root)
        assert result is None


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

    def test_missing_entities_key_returns_empty_list(
        self, project_env_per_entity: Any
    ) -> None:
        # Characterization: model.get("entities", {}).items() inside the per-entity
        # branch must not crash when key is absent — {} default → empty list returned.
        project_root, config, env = project_env_per_entity
        result = generate_factories(
            {"domain": "test"}, config, env, project_root, constraints={}
        )
        assert result == []


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
