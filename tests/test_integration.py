import json
import os

import pytest
import yaml

from model_generator import generate


@pytest.fixture
def project_setup(tmp_path):
    """Set up a temporary project structure."""
    # Create project config with GENERIC paths to prove tool is agnostic
    config = {
        "project": {"name": "Generic Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
        "generation": {"layout": "per-domain"},
        "paths": {
            "database_models": "lib/db/models",  # Custom path 1
            "api_models": "lib/api/schemas",  # Custom path 2
            "api_routes": "lib/api/endpoints",  # Custom path 3
            "api_tests": "tests/integration",  # Custom path 4
            "migrations": "db_migrations",  # Custom path 5
        },
    }

    with open(tmp_path / ".model-generator.yaml", "w") as f:
        yaml.dump(config, f)

    # Create a dummy model
    model = {
        "domain": "widgets",
        "description": "Widget domain",
        "entities": {
            "Widget": {
                "table": "widgets",
                "description": "A test widget",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "name": {"type": "text", "required": True, "max_length": 100},
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    model_path = model_dir / "widgets.model.json"

    with open(model_path, "w") as f:
        json.dump(model, f)

    return tmp_path, model_path


def test_generate_all(project_setup):
    """Test full generation for a simple model with custom paths."""
    project_root, model_path = project_setup

    # Change CWD to temp project root so generate.py finds config
    original_cwd = os.getcwd()
    os.chdir(project_root)

    try:
        # Run generation
        generate.generate(
            model_path=model_path,
            target="all",
            diff=False,
            dry_run=False,
            stack="python-fastapi",
        )

        # Verify files exist at the CUSTOM paths
        # 1. Database Model
        db_model = project_root / "lib/db/models/widgets.py"
        assert db_model.exists()
        assert "class Widget(Base):" in db_model.read_text()

        # 2. API Models
        api_req = project_root / "lib/api/schemas/widgets_requests.py"
        assert api_req.exists()
        assert "class CreateWidgetRequest(BaseModel):" in api_req.read_text()

        # 3. API Routes
        api_routes = project_root / "lib/api/endpoints/widgets.py"
        assert api_routes.exists()
        assert "@router.post" in api_routes.read_text()

        # 4. Tests
        tests = project_root / "tests/integration/test_widgets_api.py"
        assert tests.exists()
        assert "def test_post_widget_success" in tests.read_text()

    finally:
        os.chdir(original_cwd)
