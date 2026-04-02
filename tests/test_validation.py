import json

from model_generator import generate


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
