"""Tests for validate_* helpers — composite FKs, generation config, paths."""

import re
from pathlib import Path
from typing import Any

import pytest

from model_generator.generators import (
    generate_database_model,
)


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

    def test_multiple_errors_accumulate_before_exit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """All validation errors in a FK are collected, not short-circuited on first."""
        from model_generator.generate import _validate_composite_foreign_keys

        # Both length mismatch AND unknown field — both errors must appear in output.
        bad = {
            **self._valid_fk(),
            "fields": ["tenant_id", "ghost_col"],
            "references_columns": ["x"],
        }
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(self._model_with_fk(bad))
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "must match" in out
        assert "ghost_col" in out

    def test_second_fk_label_uses_correct_index(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A second invalid FK must be labelled foreign_keys[1], not [0]."""
        from model_generator.generate import _validate_composite_foreign_keys

        bad_fk = {**self._valid_fk(), "references_table": "ghost"}
        model = {
            "entities": {
                "OrderItem": {
                    "table": "order_items",
                    "fields": {
                        "id": {"type": "uuid"},
                        "tenant_id": {"type": "uuid"},
                        "order_id": {"type": "uuid"},
                    },
                    "foreign_keys": [self._valid_fk(), bad_fk],
                },
                "Order": {"table": "orders", "fields": {}},
            }
        }
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(model)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "foreign_keys[1]" in out
        assert "foreign_keys[0]" not in out

    def test_errors_from_multiple_entities_accumulate(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Bad FKs on two different entities both appear in the error output."""
        from model_generator.generate import _validate_composite_foreign_keys

        model: dict[str, Any] = {
            "entities": {
                "Alpha": {
                    "table": "alphas",
                    "fields": {"id": {"type": "uuid"}},
                    "foreign_keys": [
                        {
                            "fields": ["id"],
                            "references_table": "ghost_a",
                            "references_columns": ["id"],
                        }
                    ],
                },
                "Beta": {
                    "table": "betas",
                    "fields": {"id": {"type": "uuid"}},
                    "foreign_keys": [
                        {
                            "fields": ["id"],
                            "references_table": "ghost_b",
                            "references_columns": ["id"],
                        }
                    ],
                },
            }
        }
        with pytest.raises(SystemExit) as excinfo:
            _validate_composite_foreign_keys(model)
        assert excinfo.value.code == 1
        out = capsys.readouterr().out
        assert "ghost_a" in out
        assert "ghost_b" in out


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

    def test_wrong_filename_error_shows_suggestion(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The wrong-filename error must print the correct suggested path."""
        from model_generator.generate import _validate_paths_base

        with pytest.raises(SystemExit):
            _validate_paths_base(
                {
                    "paths": {
                        "database_models": "src/db/models",
                        "base": "src/db/models/foundation.py",
                    }
                }
            )
        out = capsys.readouterr().out
        assert "src/db/models/base.py" in out

    def test_wrong_parent_error_shows_relative_import_reason(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The wrong-parent error must explain the from .base import constraint."""
        from model_generator.generate import _validate_paths_base

        with pytest.raises(SystemExit):
            _validate_paths_base(
                {
                    "paths": {
                        "database_models": "hub/database/models",
                        "base": "hub/database/base.py",
                    }
                }
            )
        out = capsys.readouterr().out
        assert "from .base import Base" in out

    def test_null_paths_does_not_raise_attribute_error(self) -> None:
        """paths: null in YAML must not AttributeError in _validate_paths_base
        (GEN-10)."""
        from model_generator.generate import _validate_paths_base

        # Direct call: _validate_paths_base must handle None defensively.
        _validate_paths_base({"paths": None})

    def test_loader_normalises_null_paths_to_empty_dict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """load_config normalises `paths: null` to {} so all downstream
        consumers (generate_migration_init, etc.) see a dict, not None (GEN-10)."""
        from model_generator.utils.loaders import load_config

        yaml_path = tmp_path / ".model-generator.yaml"
        yaml_path.write_text("paths: null\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        config = load_config()
        assert isinstance(config["paths"], dict)


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
