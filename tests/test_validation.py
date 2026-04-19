import json

import pytest

from model_generator import generate
from model_generator.utils.loaders import _normalize_indexes


def test_load_model_validates_schema(tmp_path, capsys):
    """Test that load_model validates against the schema."""
    # Create a model with a type mismatch (fields should be object, not list)
    invalid_model = {
        "domain": "invalid_domain",
        "description": "Invalid model",
        "entities": {
            "InvalidEntity": {
                "table": "invalid_entities",
                "fields": [],  # Error: should be an object/dict
            }
        },
    }

    model_path = tmp_path / "invalid.model.json"
    with open(model_path, "w") as f:
        json.dump(invalid_model, f)

    # Run load_model
    # We expect it to print a warning but return the data
    data = generate.load_model(model_path)

    # Check that data is returned
    assert data == invalid_model

    # Check stdout for warning
    captured = capsys.readouterr()
    assert "Model validation warning" in captured.out
    assert "is not of type 'object'" in captured.out


def test_load_model_valid_schema(tmp_path, capsys):
    """Test that load_model is silent for valid schema."""
    valid_model = {
        "domain": "valid_domain",
        "description": "Valid model",
        "entities": {
            "ValidEntity": {
                "table": "valid_entities",
                "fields": {"id": {"type": "uuid", "primary_key": True}},
            }
        },
    }

    model_path = tmp_path / "valid.model.json"
    with open(model_path, "w") as f:
        json.dump(valid_model, f)

    generate.load_model(model_path)

    captured = capsys.readouterr()
    assert "Model validation warning" not in captured.out


@pytest.mark.parametrize(
    "legacy,canonical",
    [
        (
            {"type": "single", "field": "email"},
            {"fields": ["email"]},
        ),
        (
            {"type": "composite", "fields": ["user_id", "created_at"]},
            {"fields": ["user_id", "created_at"]},
        ),
        (
            {"type": "unique", "field": "slug"},
            {"fields": ["slug"], "unique": True},
        ),
        (
            {"type": "unique", "fields": ["user_id", "exchange_id"]},
            {"fields": ["user_id", "exchange_id"], "unique": True},
        ),
    ],
)
def test_normalize_indexes_legacy_shapes(legacy, canonical):
    """Each legacy index shape is rewritten to the schema-accepted form."""
    data = {"entities": {"E": {"indexes": [legacy]}}}
    _normalize_indexes(data)
    assert data["entities"]["E"]["indexes"][0] == canonical


def test_normalize_indexes_leaves_canonical_untouched():
    """Already-canonical entries pass through unchanged."""
    canonical = {"fields": ["email"], "unique": True, "name": "custom_name"}
    data = {"entities": {"E": {"indexes": [dict(canonical)]}}}
    _normalize_indexes(data)
    assert data["entities"]["E"]["indexes"][0] == canonical


def test_normalize_indexes_preserves_explicit_unique_false():
    """Legacy {type: 'unique', unique: false} is a contradiction.

    Respect the explicit value instead of letting the legacy type override it.
    """
    data = {
        "entities": {
            "E": {"indexes": [{"type": "unique", "field": "x", "unique": False}]}
        }
    }
    _normalize_indexes(data)
    assert data["entities"]["E"]["indexes"][0] == {
        "fields": ["x"],
        "unique": False,
    }


def test_load_model_accepts_legacy_index_shape(tmp_path, capsys):
    """End-to-end: a spec using the old docs' shape loads cleanly (no warning)."""
    legacy_model = {
        "domain": "legacy",
        "description": "Uses old index shape from docs",
        "entities": {
            "Widget": {
                "table": "widgets",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True},
                    "email": {"type": "text", "max_length": 255},
                },
                "indexes": [{"type": "single", "field": "email"}],
            }
        },
    }

    model_path = tmp_path / "legacy.model.json"
    with open(model_path, "w") as f:
        json.dump(legacy_model, f)

    data = generate.load_model(model_path)

    captured = capsys.readouterr()
    assert "Model validation warning" not in captured.out
    assert data["entities"]["Widget"]["indexes"] == [{"fields": ["email"]}]
