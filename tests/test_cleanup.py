"""Tests for cleanup functions (_cleanup_full, _cleanup_selective)."""

from model_generator.generate import _cleanup_full, _cleanup_selective

# Reusable paths config matching the example project layout
PATHS = {
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
    "migrations": "alembic",
}


def _scaffold(root, paths=PATHS):
    """Create a realistic generated project structure for cleanup tests."""
    # Database models
    db_dir = root / "src/database/models/factories"
    db_dir.mkdir(parents=True)
    (root / "src/database/models/base.py").write_text("# base")
    (root / "src/database/models/users.py").write_text("# users")
    (root / "src/database/models/factories/users.py").write_text("# factory")
    (root / "src/database/engine.py").write_text("# engine")
    (root / "src/main.py").write_text("# main")

    # API
    (root / "src/api/models").mkdir(parents=True)
    (root / "src/api/routes").mkdir(parents=True)
    (root / "src/api/models/users_response.py").write_text("# response")
    (root / "src/api/routes/users.py").write_text("# routes")
    (root / "src/api/errors.py").write_text("# errors")
    (root / "src/api/validators.py").write_text("# validators")

    # Tests
    (root / "tests/api").mkdir(parents=True)
    (root / "tests/conftest.py").write_text("# conftest")
    (root / "tests/api/test_users_api.py").write_text("# test")

    # Alembic
    (root / "alembic/versions").mkdir(parents=True)
    (root / "alembic.ini").write_text("# alembic")
    (root / "alembic/env.py").write_text("# env")
    (root / "alembic/versions/001_init.py").write_text("# migration")

    # A cache dir
    (root / ".pytest_cache").mkdir()
    (root / ".pytest_cache/v").mkdir()

    # Non-generated file that should survive
    (root / "pyproject.toml").write_text("[project]")
    (root / "models").mkdir()
    (root / "models/users.model.json").write_text("{}")


# ── _cleanup_full ───────────────────────────────────────────────────────────


class TestCleanupFull:
    def test_deletes_generated_directories(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_full(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / "src").exists()
        assert not (tmp_path / "tests").exists()
        assert not (tmp_path / "alembic").exists()

    def test_deletes_alembic_ini(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_full(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / "alembic.ini").exists()

    def test_deletes_cache_directories(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_full(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / ".pytest_cache").exists()

    def test_preserves_non_generated_files(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_full(tmp_path, PATHS, dry_run=False)

        assert (tmp_path / "pyproject.toml").exists()
        assert (tmp_path / "models/users.model.json").exists()

    def test_dry_run_deletes_nothing(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_full(tmp_path, PATHS, dry_run=True)

        assert (tmp_path / "src").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / "alembic").exists()
        assert (tmp_path / "alembic.ini").exists()
        assert (tmp_path / ".pytest_cache").exists()

    def test_handles_missing_directories_gracefully(self, tmp_path):
        """Should not error if directories don't exist."""
        _cleanup_full(tmp_path, PATHS, dry_run=False)  # Nothing to delete

    def test_handles_missing_alembic_ini(self, tmp_path):
        _scaffold(tmp_path)
        (tmp_path / "alembic.ini").unlink()
        _cleanup_full(tmp_path, PATHS, dry_run=False)  # Should not error


# ── _cleanup_selective ──────────────────────────────────────────────────────


class TestCleanupSelective:
    def test_deletes_generated_python_files(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        # Generated .py files should be gone
        assert not (tmp_path / "src/database/models/users.py").exists()
        assert not (tmp_path / "src/database/models/factories/users.py").exists()
        assert not (tmp_path / "src/api/models/users_response.py").exists()
        assert not (tmp_path / "src/api/routes/users.py").exists()
        assert not (tmp_path / "tests/api/test_users_api.py").exists()

    def test_deletes_infrastructure_files(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / "src/database/models/base.py").exists()
        assert not (tmp_path / "src/database/engine.py").exists()
        assert not (tmp_path / "src/main.py").exists()
        assert not (tmp_path / "tests/conftest.py").exists()

    def test_deletes_alembic_ini(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / "alembic.ini").exists()

    def test_deletes_migration_files(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert not (tmp_path / "alembic/versions/001_init.py").exists()

    def test_preserves_directories(self, tmp_path):
        """Selective mode deletes files, not directories."""
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert (tmp_path / "src/database/models").is_dir()
        assert (tmp_path / "tests/api").is_dir()
        assert (tmp_path / "alembic/versions").is_dir()

    def test_preserves_non_generated_files(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert (tmp_path / "pyproject.toml").exists()
        assert (tmp_path / "models/users.model.json").exists()

    def test_dry_run_deletes_nothing(self, tmp_path):
        _scaffold(tmp_path)
        _cleanup_selective(tmp_path, PATHS, dry_run=True)

        assert (tmp_path / "src/database/models/users.py").exists()
        assert (tmp_path / "src/main.py").exists()
        assert (tmp_path / "tests/api/test_users_api.py").exists()
        assert (tmp_path / "alembic.ini").exists()

    def test_skips_pycache_files(self, tmp_path):
        _scaffold(tmp_path)
        cache_file = tmp_path / "src/database/models/__pycache__/models.cpython-312.pyc"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(b"\x00")

        _cleanup_selective(tmp_path, PATHS, dry_run=False)

        assert cache_file.exists()

    def test_handles_empty_project(self, tmp_path):
        """Should not error when nothing exists to delete."""
        _cleanup_selective(tmp_path, PATHS, dry_run=False)  # No files to delete

    def test_handles_missing_alembic_ini(self, tmp_path):
        _scaffold(tmp_path)
        (tmp_path / "alembic.ini").unlink()
        _cleanup_selective(tmp_path, PATHS, dry_run=False)  # Should not error
