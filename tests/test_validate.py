"""Tests for model validation (validate.py)."""

import json

import pytest

from model_generator.validate import load_schema, validate_model, validate_semantics

# ── Schema Loading ──────────────────────────────────────────────────────────


class TestLoadSchema:
    def test_loads_schema_successfully(self):
        schema = load_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema or "type" in schema


# ── validate_model ──────────────────────────────────────────────────────────


class TestValidateModel:
    @pytest.fixture
    def schema(self):
        return load_schema()

    def test_valid_model_returns_no_errors(self, tmp_path, schema):
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

    def test_missing_file(self, tmp_path, schema):
        path = tmp_path / "nonexistent.model.json"
        errors = validate_model(path, schema)
        assert len(errors) == 1
        assert "File not found" in errors[0]

    def test_invalid_json(self, tmp_path, schema):
        path = tmp_path / "bad.model.json"
        path.write_text("{not valid json")

        errors = validate_model(path, schema)
        assert len(errors) == 1
        assert "Invalid JSON" in errors[0]

    def test_schema_violation_fields_wrong_type(self, tmp_path, schema):
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

    def test_schema_error_includes_path(self, tmp_path, schema):
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

    def test_schema_violation_missing_domain(self, tmp_path, schema):
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

    def test_root_level_error_shows_root_label(self, tmp_path, schema):
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

    def test_semantic_validation_runs_after_schema_passes(self, tmp_path, schema):
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

    def test_valid_composite_foreign_key_passes(self, tmp_path, schema):
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

    def test_composite_fk_missing_references_table_rejected(self, tmp_path, schema):
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

    def test_composite_fk_min_items_enforced(self, tmp_path, schema):
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
    def _model(self, entities: dict) -> dict:
        return {"domain": "test", "entities": entities}

    def test_valid_entity_no_errors(self):
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

    def test_missing_primary_key(self):
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

    def test_enum_missing_enum_name(self):
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

    def test_enum_missing_values_and_not_existing(self):
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

    def test_enum_with_existing_flag_no_error(self):
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

    def test_enum_with_values_no_error(self):
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

    def test_reference_missing_reference_table(self):
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

    def test_reference_with_table_no_error(self):
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

    def test_constraint_depends_on_nonexistent_field(self):
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

    def test_constraint_depends_on_existing_field(self):
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

    def test_table_constraint_references_nonexistent_field(self):
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

    def test_table_constraint_valid_fields(self):
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

    def test_index_references_nonexistent_field(self):
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

    def test_index_valid_fields(self):
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

    def test_immutable_with_updated_timestamp(self):
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

    def test_immutable_with_update_endpoint(self):
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

    def test_immutable_with_delete_endpoint(self):
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

    def test_immutable_correct_no_errors(self):
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

    def test_multiple_entities_independent_errors(self):
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
    def test_index_cannot_reference_timestamp_field_when_disabled(self, field, ts_key):
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
    def test_index_can_reference_timestamp_field_when_enabled(self, field, ts_key):
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

    def test_relationship_target_outside_domain_no_error(self):
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

    def test_no_entities_key_returns_empty(self):
        """Model with no 'entities' key should produce no errors."""
        assert validate_semantics({}) == []
        assert validate_semantics({"domain": "x"}) == []

    def test_entity_with_no_fields_key_reports_no_pk(self):
        """Entity with no 'fields' key gets a 'No primary key' error."""
        model = self._model({"Bad": {"table": "bads"}})
        errors = validate_semantics(model)
        assert any("No primary key" in e for e in errors)

    def test_table_constraint_with_no_fields_key_no_error(self):
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

    def test_index_with_no_fields_key_no_error(self):
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
    ):
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
