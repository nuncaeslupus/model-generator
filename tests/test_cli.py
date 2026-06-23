"""Tests for CLI flags and main() entry point."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


class TestInteractiveFlag:
    """Test --interactive CLI flag."""

    def test_interactive_launches_wizard(self) -> None:
        """--interactive should call run_wizard and return."""
        from model_generator.generate import main

        # main() does: from .wizard import run_wizard; run_wizard()
        # Patch at the wizard package level where run_wizard is exported
        with (
            patch("sys.argv", ["model-gen", "--interactive"]),
            patch("model_generator.wizard.run_wizard") as mock_wizard,
        ):
            main()
            mock_wizard.assert_called_once()

    def test_clear_only_without_model(self, tmp_path: Path) -> None:
        """--clear-only should work without a model argument."""
        from model_generator.generate import main

        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "paths": {
                "database_models": "src/db/models",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
            },
        }
        (tmp_path / ".model-generator.yaml").write_text(yaml.dump(config))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with patch("sys.argv", ["model-gen", "--clear-only"]):
                main()  # Should not raise
        finally:
            os.chdir(original_cwd)

    def test_model_required_without_flags(self) -> None:
        """Without --clear-only or --interactive, model is required."""
        from model_generator.generate import main

        with (
            patch("sys.argv", ["model-gen"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1

    def test_nonexistent_model_file(self) -> None:
        """Non-existent model file should exit with error."""
        from model_generator.generate import main

        with (
            patch("sys.argv", ["model-gen", "/nonexistent/path.json"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()
        assert exc_info.value.code == 1


class TestDryRunAndDiff:
    """Test --dry-run and --diff modes."""

    def test_dry_run_creates_no_files(self, tmp_path: Path) -> None:
        from model_generator.generate import generate

        model = {
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
                        "name": {"type": "text", "required": True, "max_length": 100},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "paths": {
                "database_models": "src/db/models",
                "factories": "src/db/models/factories",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
                "base": "src/db/models/base.py",
                "engine": "src/db/engine.py",
                "main": "src/main.py",
                "errors": "src/api/errors.py",
                "validators": "src/api/validators.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }

        config_path = tmp_path / ".model-generator.yaml"
        config_path.write_text(yaml.dump(config))
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "widgets.model.json"
        model_path.write_text(json.dumps(model))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate(model_path=model_path, target="all", dry_run=True)
            # No model files should be created
            assert not (tmp_path / "src/db/models/widgets.py").exists()
            assert not (tmp_path / "tests/api/test_widgets_api.py").exists()
        finally:
            os.chdir(original_cwd)

    def test_diff_creates_no_files(self, tmp_path: Path) -> None:
        from model_generator.generate import generate

        model = {
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
                        "name": {"type": "text", "required": True, "max_length": 100},
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "paths": {
                "database_models": "src/db/models",
                "factories": "src/db/models/factories",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
                "base": "src/db/models/base.py",
                "engine": "src/db/engine.py",
                "main": "src/main.py",
                "errors": "src/api/errors.py",
                "validators": "src/api/validators.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }

        config_path = tmp_path / ".model-generator.yaml"
        config_path.write_text(yaml.dump(config))
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        model_path = model_dir / "widgets.model.json"
        model_path.write_text(json.dumps(model))

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            generate(model_path=model_path, target="all", diff=True)
            # No model files should be created
            assert not (tmp_path / "src/db/models/widgets.py").exists()
            assert not (tmp_path / "tests/api/test_widgets_api.py").exists()
        finally:
            os.chdir(original_cwd)


class TestProjectRootResolution:
    """Test project root resolution when running model-gen from outside the project."""

    def _make_project(self, project_dir: Path) -> Path:
        """Create a minimal project with .model-generator.yaml and one model file."""
        import yaml

        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "paths": {
                "database_models": "backend/src/database/models",
                "factories": "backend/src/database/models/factories",
                "api_models": "backend/src/api/models",
                "api_routes": "backend/src/api/routes",
                "api_tests": "tests/contract/api",
                "base": "backend/src/database/models/base.py",
                "engine": "backend/src/database/engine.py",
                "main": "backend/src/main.py",
                "errors": "backend/src/api/errors.py",
                "validators": "backend/src/api/validators.py",
                "utils": "backend/src/api/utils.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }
        (project_dir / ".model-generator.yaml").write_text(yaml.dump(config))
        models_dir = project_dir / "models"
        models_dir.mkdir()
        model_path = models_dir / "things.model.json"
        model_path.write_text(
            json.dumps(
                {
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
                                "name": {
                                    "type": "text",
                                    "required": True,
                                    "max_length": 50,
                                },
                            },
                            "timestamps": {"created": True, "updated": True},
                        }
                    },
                }
            )
        )
        return models_dir

    def test_no_model_generator_yaml_exits_with_error(self, tmp_path: Path) -> None:
        """main() should exit with error if no .model-generator.yaml is found."""
        from model_generator.generate import main

        # Project has no .model-generator.yaml
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "things.model.json").write_text(
            json.dumps({"domain": "things", "entities": {}})
        )

        original_cwd = os.getcwd()
        # Run from a parent dir with no config
        os.chdir(tmp_path.parent)
        try:
            with (
                patch("sys.argv", ["model-gen", str(models_dir), "--dry-run"]),
                pytest.raises(SystemExit) as exc_info,
            ):
                main()
            assert exc_info.value.code == 1
        finally:
            os.chdir(original_cwd)

    def test_project_root_resolved_from_model_path_when_run_outside_project(
        self, tmp_path: Path
    ) -> None:
        """main() should resolve project root to model's parent.parent, not cwd."""
        from model_generator.generate import main

        # Create a project in a subdirectory
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        models_dir = self._make_project(project_dir)

        original_cwd = os.getcwd()
        # Run from tmp_path (OUTSIDE the project directory)
        os.chdir(tmp_path)
        try:
            with patch(
                "sys.argv",
                ["model-gen", str(models_dir), "--target", "database", "--dry-run"],
            ):
                main()  # Should not raise; project root correctly found as my-project/
        finally:
            os.chdir(original_cwd)

    def test_refuses_to_generate_into_model_generator_own_directory(
        self, tmp_path: Path
    ) -> None:
        """main() should refuse if project_root resolves to model-generator itself."""
        from model_generator.generate import _GENERATOR_OWN_DIR, _validate_project_root

        with pytest.raises(SystemExit) as exc_info:
            _validate_project_root(_GENERATOR_OWN_DIR)
        assert exc_info.value.code == 1

    def test_validate_project_root_passes_for_valid_project(
        self, tmp_path: Path
    ) -> None:
        """_validate_project_root() passes for a dir with .model-generator.yaml."""
        import yaml

        from model_generator.generate import _validate_project_root

        (tmp_path / ".model-generator.yaml").write_text(yaml.dump({"project": {}}))
        _validate_project_root(tmp_path)  # Should not raise


class TestNoRootFilesFlag:
    """Test that --no-root-files propagates through main() into generators."""

    def _make_project(self, project_dir: Path) -> Path:
        config = {
            "project": {"name": "Test"},
            "stack": "python-fastapi",
            "paths": {
                "database_models": "src/db/models",
                "factories": "src/db/models/factories",
                "api_models": "src/api/models",
                "api_routes": "src/api/routes",
                "api_tests": "tests/api",
                "base": "src/db/models/base.py",
                "engine": "src/db/engine.py",
                "main": "src/main.py",
                "errors": "src/api/errors.py",
                "validators": "src/api/validators.py",
                "test_conftest_root": "tests/conftest.py",
                "migrations": "alembic",
            },
        }
        (project_dir / ".model-generator.yaml").write_text(yaml.dump(config))
        models_dir = project_dir / "models"
        models_dir.mkdir()
        (models_dir / "widgets.model.json").write_text(
            json.dumps(
                {
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
                                    "required": True,
                                    "max_length": 50,
                                },
                            },
                            "timestamps": {"created": True, "updated": True},
                        }
                    },
                }
            )
        )
        return models_dir

    def test_no_root_files_flag_propagates(self, tmp_path: Path) -> None:
        """--no-root-files reaches generate_infrastructure and generate()."""
        from model_generator.generate import main

        models_dir = self._make_project(tmp_path)

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with (
                patch(
                    "sys.argv",
                    [
                        "model-gen",
                        str(models_dir),
                        "--no-root-files",
                        "--dry-run",
                    ],
                ),
                patch("model_generator.generate.generate_infrastructure") as mock_infra,
                patch("model_generator.generate.generate") as mock_generate,
            ):
                mock_infra.return_value = []
                main()

            mock_infra.assert_called_once()
            assert mock_infra.call_args.kwargs.get("no_root_files") is True

            mock_generate.assert_called_once()
            assert mock_generate.call_args.kwargs.get("no_root_files") is True
        finally:
            os.chdir(original_cwd)


class TestStackResolution:
    """Test that `stack:` in .model-generator.yaml is picked up automatically."""

    def _flutter_project(self, project_dir: Path) -> Path:
        """Minimal flutter-stack project: .model-generator.yaml + one model file."""
        config = {
            "project": {"name": "Test"},
            "stack": "flutter",
            "flutter": {"package_name": "test_pkg"},
        }
        (project_dir / ".model-generator.yaml").write_text(yaml.dump(config))
        models_dir = project_dir / "models"
        models_dir.mkdir()
        model_path = models_dir / "items.model.json"
        model_path.write_text(
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
                                "name": {"type": "text", "required": True},
                            },
                        }
                    },
                }
            )
        )
        return models_dir

    def test_main_reads_stack_from_project_yaml(self, tmp_path: Path) -> None:
        """main() uses stack from .model-generator.yaml when --stack is not passed."""
        from model_generator.generate import main

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        models_dir = self._flutter_project(project_dir)

        original_cwd = os.getcwd()
        os.chdir(project_dir)
        try:
            with (
                patch(
                    "sys.argv",
                    ["model-gen", str(models_dir), "--dry-run"],
                ),
                patch(
                    "model_generator.generators.flutter.generators.flutter_infra_orchestrator"
                ) as mock_infra,
                patch("model_generator.generate.generate") as mock_gen,
            ):
                mock_infra.return_value = []
                main()
            # When flutter stack is selected, generate() is called with stack="flutter"
            mock_gen.assert_called_once()
            assert mock_gen.call_args.kwargs.get("stack") == "flutter"
        finally:
            os.chdir(original_cwd)

    def test_generate_resolves_stack_from_config(self, tmp_path: Path) -> None:
        """generate() uses the correct stack spec when project yaml overrides stack."""
        from model_generator.generate import generate
        from model_generator.generators.registry import get_stack

        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        models_dir = self._flutter_project(project_dir)
        model_path = models_dir / "items.model.json"

        original_cwd = os.getcwd()
        os.chdir(project_dir)
        try:
            with patch("model_generator.generate._process_outputs") as mock_out:
                mock_out.return_value = []
                # Default stack arg; project yaml overrides to flutter
                generate(model_path, target="enums", dry_run=True)
            # The generate() call should have resolved the flutter stack spec.
            flutter_spec = get_stack("flutter")
            assert "enums" in flutter_spec.all_targets
        finally:
            os.chdir(original_cwd)
