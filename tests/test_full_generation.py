import os
import shutil

import pytest

from model_generator import generate


@pytest.fixture
def example_project(tmp_path, project_root):
    """
    Setup a temporary project directory with:
    1. The example project config
    2. The example domain models
    """
    # Source paths
    config_src = project_root / "examples/user-auth-project/.model-generator.yaml"
    model_dir_src = project_root / "examples/user-auth-project/models"

    # Destination paths in tmp_path
    config_dest = tmp_path / ".model-generator.yaml"
    model_dir = tmp_path / "models"
    model_dir.mkdir()

    # Copy config
    shutil.copy(config_src, config_dest)

    # Copy all model files
    for model_file in model_dir_src.glob("*.model.json"):
        shutil.copy(model_file, model_dir / model_file.name)

    model_dest = model_dir / "users.model.json"

    return tmp_path, model_dest


def test_generate_from_examples(example_project):
    """
    Integration test that runs the generator against the repository's
    actual examples.
    """
    project_dir, model_path = example_project

    # Switch to temp directory context
    original_cwd = os.getcwd()
    os.chdir(project_dir)

    try:
        # Run generation targeting 'all'
        generate.generate(
            model_path=model_path,
            target="all",
            diff=False,
            dry_run=False,
            # stack defaults to config file value (python-fastapi)
        )

        # --- Verification ---

        # 1. Check Directory Structure
        assert (project_dir / "backend/src/database/models").exists()
        assert (project_dir / "backend/src/api/routes").exists()
        assert (project_dir / "tests/contract/api").exists()
        assert (project_dir / "alembic").exists()

        # 2. Check Key Files Exist
        # Database Model
        assert (project_dir / "backend/src/database/models/users.py").exists()
        # API Routes
        assert (project_dir / "backend/src/api/routes/users.py").exists()
        # Contract Tests
        assert (project_dir / "tests/contract/api/test_users_api.py").exists()

        # 3. Basic Content Checks
        user_model = (project_dir / "backend/src/database/models/users.py").read_text()
        assert "class User(Base):" in user_model
        assert "username: Mapped[str] = mapped_column(String" in user_model

        api_route = (project_dir / "backend/src/api/routes/users.py").read_text()
        assert "@router.post" in api_route
        assert "async def create_user" in api_route

    finally:
        os.chdir(original_cwd)


def test_clean_command(example_project):
    """Test that the cleanup command works correctly."""
    project_dir, model_path = example_project
    original_cwd = os.getcwd()
    os.chdir(project_dir)

    try:
        # 1. Generate first
        generate.generate(model_path=model_path, target="all")
        assert (project_dir / "backend/src/database/models/users.py").exists()

        # 2. Run Clean (Selective)
        # We need to mock sys.argv or call the cleanup function directly if exposed,
        # but generate.py main logic handles --clean.
        # Since 'generate' function doesn't expose clean directly (it's in main),
        # we might need to import cleanup_generated if we want to test it functionally,
        # or rely on the fact that we are testing the generator logic here.

        # Let's import the cleanup function directly for this test
        from model_generator.generate import cleanup_generated

        cleanup_generated(project_dir, scope="selective", dry_run=False)

        # 3. Verify files are gone
        assert not (project_dir / "backend/src/database/models/users.py").exists()
        # Directories should still exist
        assert (project_dir / "backend/src").exists()

    finally:
        os.chdir(original_cwd)
