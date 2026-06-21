"""Tests for model validation (validate.py)."""

import json
from pathlib import Path
from typing import Any

import pytest

from model_generator.validate import load_schema, validate_model, validate_semantics

# ── Schema Loading ──────────────────────────────────────────────────────────


class TestLoadSchema:
    def test_loads_schema_successfully(self) -> None:
        schema = load_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema


# ── validate_model ──────────────────────────────────────────────────────────


class TestValidateModel:
    @pytest.fixture
    def schema(self) -> dict[str, Any]:
        return load_schema()

    def test_valid_model_returns_no_errors(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        model = {
            "domain": "users",
            "description": "User management",
            "entities": {
                "User": {
                    "table": "users",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "name": {"type": "text", "max_length": 100},
                    },
                }
            },
        }
        path = tmp_path / "users.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert errors == []

    def test_missing_file(self, tmp_path: Path, schema: dict[str, Any]) -> None:
        path = tmp_path / "nonexistent.model.json"
        errors = validate_model(path, schema)
        assert len(errors) == 1
        assert "File not found" in errors[0]

    def test_accepts_json_comments(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """GEN-3: model-val parses the same // -comment dialect as model-gen."""
        path = tmp_path / "users.model.json"
        path.write_text(
            "{\n"
            "  // domain comment\n"
            '  "domain": "users",\n'
            '  "entities": {\n'
            '    "User": {\n'
            '      "table": "users",\n'
            '      "fields": {"id": {"type": "uuid", "primary_key": true}}\n'
            "    }\n"
            "  }\n"
            "}\n"
        )
        assert validate_model(path, schema) == []

    def test_accepts_legacy_index_shape(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """GEN-3: legacy index shapes model-gen normalizes must pass model-val."""
        model = {
            "domain": "users",
            "entities": {
                "User": {
                    "table": "users",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "email": {"type": "text", "max_length": 100},
                    },
                    "indexes": [{"type": "unique", "field": "email"}],
                }
            },
        }
        path = tmp_path / "users.model.json"
        path.write_text(json.dumps(model))
        assert validate_model(path, schema) == []

    def test_accepts_integer_alias(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """GEN-3: the `integer` alias model-gen normalizes must pass model-val."""
        model = {
            "domain": "users",
            "entities": {
                "User": {
                    "table": "users",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "login_count": {"type": "integer", "default": 0},
                    },
                }
            },
        }
        path = tmp_path / "users.model.json"
        path.write_text(json.dumps(model))
        assert validate_model(path, schema) == []

    def test_invalid_json(self, tmp_path: Path, schema: dict[str, Any]) -> None:
        path = tmp_path / "bad.model.json"
        path.write_text("{not valid json")

        errors = validate_model(path, schema)
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_non_dict_json_reports_schema_error_not_crash(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """Valid-but-non-object JSON must surface a schema error, not AttributeError."""
        path = tmp_path / "list.model.json"
        path.write_text("[]")
        errors = validate_model(path, schema)
        assert len(errors) > 0
        assert any("is not of type" in e for e in errors)

    def test_accepts_encrypted_binary_field(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """EX-5: a binary field with an `encrypt` block is expressible/valid."""
        model = {
            "domain": "secrets",
            "entities": {
                "Secret": {
                    "table": "secrets",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "blob": {
                            "type": "binary",
                            "required": True,
                            "encrypt": {"key_env": "FERNET_KEY"},
                        },
                    },
                }
            },
        }
        path = tmp_path / "secrets.model.json"
        path.write_text(json.dumps(model))
        assert validate_model(path, schema) == []

    def test_rejects_unknown_key_in_encrypt(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """`encrypt` is a closed object — typos surface instead of silently passing."""
        model = {
            "domain": "secrets",
            "entities": {
                "Secret": {
                    "table": "secrets",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "blob": {"type": "binary", "encrypt": {"bogus": "x"}},
                    },
                }
            },
        }
        path = tmp_path / "secrets.model.json"
        path.write_text(json.dumps(model))
        assert len(validate_model(path, schema)) > 0

    def test_schema_violation_fields_wrong_type(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """fields should be an object, not a list."""
        model = {
            "domain": "bad",
            "entities": {
                "Bad": {
                    "table": "bads",
                    "fields": ["not", "a", "dict"],
                }
            },
        }
        path = tmp_path / "bad.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert len(errors) > 0
        assert any("is not of type" in e for e in errors)

    def test_schema_error_includes_path(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """Schema errors for nested fields should include a path."""
        model = {
            "domain": "bad",
            "entities": {
                "Bad": {
                    "table": "bads",
                    "fields": ["not", "a", "dict"],
                }
            },
        }
        path = tmp_path / "bad.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert any(": " in e for e in errors)
        assert any(" -> " in e for e in errors)
        assert any("fields" in e for e in errors)
        # Adjacent elements must be joined with " -> ", not "XX -> XX"
        assert any("Bad -> fields" in e for e in errors)

    def test_schema_violation_missing_domain(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        model = {
            "entities": {
                "X": {
                    "table": "xs",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                }
            }
        }
        path = tmp_path / "nodomain.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert len(errors) > 0

    def test_root_level_error_shows_root_label(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """Root-level schema errors should show '(root)' as path."""
        model = {
            "entities": {
                "X": {
                    "table": "xs",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                }
            }
        }
        path = tmp_path / "nodomain.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert any("  (root):" in e for e in errors)

    def test_semantic_validation_runs_after_schema_passes(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """A schema-valid model missing a PK should get a semantic error."""
        model = {
            "domain": "test",
            "entities": {
                "NoPK": {
                    "table": "no_pks",
                    "fields": {
                        "name": {"type": "text", "max_length": 50},
                    },
                }
            },
        }
        path = tmp_path / "nopk.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert any("No primary key" in e for e in errors)

    def test_valid_composite_foreign_key_passes(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """A well-formed entity-level foreign_keys array passes schema validation."""
        model = {
            "domain": "shop",
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
                    "foreign_keys": [
                        {
                            "fields": ["tenant_id", "order_id"],
                            "references_table": "orders",
                            "references_columns": ["tenant_id", "id"],
                            "on_delete": "CASCADE",
                        }
                    ],
                },
            },
        }
        path = tmp_path / "shop.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert errors == []

    def test_composite_fk_missing_references_table_rejected(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """references_table is required."""
        model = {
            "domain": "shop",
            "entities": {
                "OrderItem": {
                    "table": "order_items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "tenant_id": {"type": "uuid"},
                        "order_id": {"type": "uuid"},
                    },
                    "foreign_keys": [
                        {
                            "fields": ["tenant_id", "order_id"],
                            "references_columns": ["tenant_id", "id"],
                        }
                    ],
                }
            },
        }
        path = tmp_path / "shop.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert any("references_table" in e for e in errors)

    def test_composite_fk_min_items_enforced(
        self, tmp_path: Path, schema: dict[str, Any]
    ) -> None:
        """fields and references_columns must each have minItems: 2.

        Single-column FKs go through `type: reference`, not foreign_keys.
        """
        model = {
            "domain": "shop",
            "entities": {
                "OrderItem": {
                    "table": "order_items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "tenant_id": {"type": "uuid"},
                    },
                    "foreign_keys": [
                        {
                            "fields": ["tenant_id"],
                            "references_table": "orders",
                            "references_columns": ["tenant_id"],
                        }
                    ],
                }
            },
        }
        path = tmp_path / "shop.model.json"
        path.write_text(json.dumps(model))

        errors = validate_model(path, schema)
        assert any("too short" in e or "minItems" in e for e in errors)


# ── validate_semantics ─────────────────────────────────────────────────────


class TestValidateSemantics:
    def _model(self, entities: dict[str, Any]) -> dict[str, Any]:
        return {"domain": "test", "entities": entities}

    def test_valid_entity_no_errors(self) -> None:
        model = self._model(
            {
                "Widget": {
                    "table": "widgets",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "name": {"type": "text"},
                    },
                }
            }
        )
        assert validate_semantics(model) == []

    # ── Primary Key ─────────────────────────────────────────────────────

    def test_missing_primary_key(self) -> None:
        model = self._model(
            {
                "NoPK": {
                    "table": "no_pks",
                    "fields": {"name": {"type": "text"}},
                }
            }
        )
        errors = validate_semantics(model)
        assert any("No primary key" in e for e in errors)

    # ── Enum Fields ─────────────────────────────────────────────────────

    def test_enum_missing_enum_name(self) -> None:
        model = self._model(
            {
                "E": {
                    "table": "es",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "status": {
                            "type": "enum",
                            "enum_values": ["a", "b"],
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert any("missing enum_name" in e for e in errors)

    def test_enum_missing_values_and_not_existing(self) -> None:
        model = self._model(
            {
                "E": {
                    "table": "es",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "status": {
                            "type": "enum",
                            "enum_name": "StatusEnum",
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert any("' needs enum_values or enum_existing=true" in e for e in errors)

    def test_enum_with_existing_flag_no_error(self) -> None:
        model = self._model(
            {
                "E": {
                    "table": "es",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "status": {
                            "type": "enum",
                            "enum_name": "StatusEnum",
                            "enum_existing": True,
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("enum_values or enum_existing" in e for e in errors)

    def test_enum_with_values_no_error(self) -> None:
        model = self._model(
            {
                "E": {
                    "table": "es",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "status": {
                            "type": "enum",
                            "enum_name": "StatusEnum",
                            "enum_values": ["active", "inactive"],
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("enum" in e.lower() for e in errors)

    # ── Reference Fields ────────────────────────────────────────────────

    def test_reference_missing_reference_table(self) -> None:
        model = self._model(
            {
                "R": {
                    "table": "rs",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "parent_id": {"type": "reference"},
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert any("' missing reference_table" in e for e in errors)

    def test_reference_with_table_no_error(self) -> None:
        model = self._model(
            {
                "R": {
                    "table": "rs",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "parent_id": {
                            "type": "reference",
                            "reference_table": "parents",
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("reference_table" in e for e in errors)

    # ── Field Constraint Cross-References ───────────────────────────────

    def test_constraint_depends_on_nonexistent_field(self) -> None:
        model = self._model(
            {
                "C": {
                    "table": "cs",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "start_date": {
                            "type": "datetime",
                            "constraints": [
                                {"type": "depends", "other_field": "end_date"}
                            ],
                        },
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert any("non-existent field 'end_date'" in e for e in errors)

    def test_constraint_depends_on_existing_field(self) -> None:
        model = self._model(
            {
                "C": {
                    "table": "cs",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "start_date": {
                            "type": "datetime",
                            "constraints": [
                                {"type": "depends", "other_field": "end_date"}
                            ],
                        },
                        "end_date": {"type": "datetime"},
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("non-existent field" in e for e in errors)

    # ── Table Constraints ───────────────────────────────────────────────

    def test_table_constraint_references_nonexistent_field(self) -> None:
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "constraints": [
                        {"type": "unique_together", "fields": ["id", "ghost_field"]}
                    ],
                }
            }
        )
        errors = validate_semantics(model)
        assert any("non-existent field 'ghost_field'" in e for e in errors)

    def test_table_constraint_valid_fields(self) -> None:
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "name": {"type": "text"},
                    },
                    "constraints": [
                        {"type": "unique_together", "fields": ["id", "name"]}
                    ],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("Table constraint" in e for e in errors)

    # ── Index Field References ──────────────────────────────────────────

    def test_index_references_nonexistent_field(self) -> None:
        model = self._model(
            {
                "I": {
                    "table": "items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "indexes": [{"fields": ["missing_field"]}],
                }
            }
        )
        errors = validate_semantics(model)
        assert any(
            "Index references non-existent field 'missing_field'" in e for e in errors
        )

    def test_index_valid_fields(self) -> None:
        model = self._model(
            {
                "I": {
                    "table": "items",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                        "name": {"type": "text"},
                    },
                    "indexes": [{"fields": ["name"]}],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("Index" in e for e in errors)

    # ── Immutable Entity Checks ─────────────────────────────────────────

    def test_immutable_with_updated_timestamp(self) -> None:
        model = self._model(
            {
                "Imm": {
                    "table": "imms",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "mutability": "immutable",
                    "timestamps": {"created": True, "updated": True},
                }
            }
        )
        errors = validate_semantics(model)
        assert any("should not have updated_at" in e for e in errors)

    def test_immutable_with_update_endpoint(self) -> None:
        model = self._model(
            {
                "Imm": {
                    "table": "imms",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "mutability": "immutable",
                    "api": {"endpoints": ["create", "read", "update"]},
                }
            }
        )
        errors = validate_semantics(model)
        assert any("should not have 'update' or 'delete'" in e for e in errors)

    def test_immutable_with_delete_endpoint(self) -> None:
        model = self._model(
            {
                "Imm": {
                    "table": "imms",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "mutability": "immutable",
                    "api": {"endpoints": ["create", "read", "delete"]},
                }
            }
        )
        errors = validate_semantics(model)
        assert any("should not have 'update' or 'delete'" in e for e in errors)

    def test_immutable_correct_no_errors(self) -> None:
        model = self._model(
            {
                "Imm": {
                    "table": "imms",
                    "fields": {
                        "id": {"type": "uuid", "primary_key": True},
                    },
                    "mutability": "immutable",
                    "timestamps": {"created": True},
                    "api": {"endpoints": ["create", "read", "list"]},
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("Immutable" in e or "immutable" in e for e in errors)

    # ── Multiple Entities ───────────────────────────────────────────────

    def test_multiple_entities_independent_errors(self) -> None:
        model = self._model(
            {
                "Good": {
                    "table": "goods",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                },
                "Bad": {
                    "table": "bads",
                    "fields": {"name": {"type": "text"}},
                },
            }
        )
        errors = validate_semantics(model)
        assert any("[Bad]" in e and "No primary key" in e for e in errors)
        assert not any("[Good]" in e for e in errors)

    @pytest.mark.parametrize(
        "field,ts_key",
        [
            ("created_at", "created"),
            ("updated_at", "updated"),
        ],
    )
    def test_index_cannot_reference_timestamp_field_when_disabled(
        self, field: Any, ts_key: Any
    ) -> None:
        """Timestamp-generated fields are invalid index targets when disabled."""
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "timestamps": {ts_key: False},
                    "indexes": [{"fields": [field]}],
                }
            }
        )
        errors = validate_semantics(model)
        assert any(f"non-existent field '{field}'" in e for e in errors)

    @pytest.mark.parametrize(
        "field,ts_key",
        [
            ("created_at", "created"),
            ("updated_at", "updated"),
        ],
    )
    def test_index_can_reference_timestamp_field_when_enabled(
        self, field: Any, ts_key: Any
    ) -> None:
        """Timestamp-generated fields are valid index targets when enabled."""
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "timestamps": {ts_key: True},
                    "indexes": [{"fields": [field]}],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any(f"non-existent field '{field}'" in e for e in errors)

    # ── Relationship Targets (non-error, just coverage) ─────────────────

    def test_relationship_target_outside_domain_no_error(self) -> None:
        """Relationship to entity not in this domain is allowed (cross-domain)."""
        model = self._model(
            {
                "Order": {
                    "table": "orders",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "relationships": {
                        "customer": {"target": "Customer", "type": "many-to-one"}
                    },
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("relationship" in e.lower() for e in errors)

    # ── Missing-key defensive tests ─────────────────────────────────────

    def test_no_entities_key_returns_empty(self) -> None:
        """Model with no 'entities' key should produce no errors."""
        assert validate_semantics({}) == []
        assert validate_semantics({"domain": "x"}) == []

    def test_entity_with_no_fields_key_reports_no_pk(self) -> None:
        """Entity with no 'fields' key gets a 'No primary key' error."""
        model = self._model({"Bad": {"table": "bads"}})
        errors = validate_semantics(model)
        assert any("No primary key" in e for e in errors)

    def test_table_constraint_with_no_fields_key_no_error(self) -> None:
        """Constraint with no 'fields' key does not raise and produces no error."""
        model = self._model(
            {
                "C": {
                    "table": "cs",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "constraints": [{"type": "unique"}],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("Table constraint" in e for e in errors)

    def test_index_with_no_fields_key_no_error(self) -> None:
        """Index with no 'fields' key does not raise and produces no error."""
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "indexes": [{"name": "some_index"}],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any("Index references" in e for e in errors)

    @pytest.mark.parametrize("field", ["created_at", "updated_at"])
    def test_index_can_reference_timestamp_field_when_timestamps_dict_empty(
        self, field: str
    ) -> None:
        """When timestamps dict has no key for a field, it defaults to enabled."""
        model = self._model(
            {
                "T": {
                    "table": "ts",
                    "fields": {"id": {"type": "uuid", "primary_key": True}},
                    "timestamps": {},
                    "indexes": [{"fields": [field]}],
                }
            }
        )
        errors = validate_semantics(model)
        assert not any(f"non-existent field '{field}'" in e for e in errors)
