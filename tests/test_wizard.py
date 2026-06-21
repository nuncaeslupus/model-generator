"""Tests for the interactive wizard module."""

from pathlib import Path
from unittest.mock import patch

import pytest


class TestWizardImports:
    """Verify wizard module imports work without errors."""

    def test_import_wizard_package(self) -> None:
        from model_generator.wizard import run_wizard

        assert callable(run_wizard)

    def test_import_prompts(self) -> None:
        from model_generator.wizard.prompts import checkbox, confirm, select, text

        assert callable(select)
        assert callable(checkbox)
        assert callable(confirm)
        assert callable(text)

    def test_import_menu(self) -> None:
        from model_generator.wizard.menu import run_menu

        assert callable(run_menu)

    def test_import_actions(self) -> None:
        from model_generator.wizard.actions.clean import run_clean
        from model_generator.wizard.actions.generate import run_generate
        from model_generator.wizard.actions.project_setup import run_setup
        from model_generator.wizard.actions.test_runner import run_tests

        assert callable(run_setup)
        assert callable(run_generate)
        assert callable(run_clean)
        assert callable(run_tests)


class TestPromptsFallback:
    """Test plain-text fallback prompts (without questionary)."""

    @pytest.fixture(autouse=True)
    def no_questionary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Force _questionary to None so the plain-text fallback is exercised."""
        import model_generator.wizard.prompts as p

        monkeypatch.setattr(p, "_questionary", None)

    def test_select_valid_choice(self) -> None:
        from model_generator.wizard.prompts import select

        with patch("builtins.input", return_value="2"):
            result = select("Pick one:", choices=["a", "b", "c"])
        assert result == "b"

    def test_select_first_choice(self) -> None:
        from model_generator.wizard.prompts import select

        with patch("builtins.input", return_value="1"):
            result = select("Pick one:", choices=["first", "second"])
        assert result == "first"

    def test_select_retries_on_invalid(self) -> None:
        from model_generator.wizard.prompts import select

        with patch("builtins.input", side_effect=["0", "abc", "2"]):
            result = select("Pick one:", choices=["a", "b"])
        assert result == "b"

    def test_checkbox_single_selection(self) -> None:
        from model_generator.wizard.prompts import checkbox

        with patch("builtins.input", return_value="1"):
            result = checkbox("Select:", choices=["x", "y", "z"])
        assert result == ["x"]

    def test_checkbox_multiple_selection(self) -> None:
        from model_generator.wizard.prompts import checkbox

        with patch("builtins.input", return_value="1,3"):
            result = checkbox("Select:", choices=["x", "y", "z"])
        assert result == ["x", "z"]

    def test_checkbox_all_selection(self) -> None:
        from model_generator.wizard.prompts import checkbox

        with patch("builtins.input", return_value="all"):
            result = checkbox("Select:", choices=["x", "y", "z"])
        assert result == ["x", "y", "z"]

    def test_confirm_default_yes(self) -> None:
        from model_generator.wizard.prompts import confirm

        with patch("builtins.input", return_value=""):
            result = confirm("Continue?", default=True)
        assert result is True

    def test_confirm_default_no(self) -> None:
        from model_generator.wizard.prompts import confirm

        with patch("builtins.input", return_value=""):
            result = confirm("Continue?", default=False)
        assert result is False

    def test_confirm_explicit_yes(self) -> None:
        from model_generator.wizard.prompts import confirm

        with patch("builtins.input", return_value="y"):
            result = confirm("Continue?", default=False)
        assert result is True

    def test_confirm_explicit_no(self) -> None:
        from model_generator.wizard.prompts import confirm

        with patch("builtins.input", return_value="n"):
            result = confirm("Continue?", default=True)
        assert result is False

    def test_text_with_input(self) -> None:
        from model_generator.wizard.prompts import text

        with patch("builtins.input", return_value="hello"):
            result = text("Enter text:")
        assert result == "hello"

    def test_text_default_on_empty(self) -> None:
        from model_generator.wizard.prompts import text

        with patch("builtins.input", return_value=""):
            result = text("Enter text:", default="fallback")
        assert result == "fallback"


class TestMenuFlow:
    """Test wizard menu dispatches correctly."""

    def test_exit_immediately(self) -> None:
        from model_generator.wizard.menu import run_menu

        with patch("model_generator.wizard.menu.select", return_value="Exit"):
            run_menu()  # Should not raise

    def test_setup_then_exit(self) -> None:
        from model_generator.wizard.menu import run_menu

        with (
            patch(
                "model_generator.wizard.menu.select",
                side_effect=["Setup/update project settings", "Exit"],
            ),
            patch(
                "model_generator.wizard.actions.project_setup.run_setup"
            ) as mock_setup,
        ):
            run_menu()
            mock_setup.assert_called_once()

    def test_generate_then_exit(self) -> None:
        from model_generator.wizard.menu import run_menu

        with (
            patch(
                "model_generator.wizard.menu.select",
                side_effect=["Generate code", "Exit"],
            ),
            patch("model_generator.wizard.actions.generate.run_generate") as mock_gen,
        ):
            run_menu()
            mock_gen.assert_called_once()

    def test_clean_then_exit(self) -> None:
        from model_generator.wizard.menu import run_menu

        with (
            patch(
                "model_generator.wizard.menu.select",
                side_effect=["Clean generated files", "Exit"],
            ),
            patch("model_generator.wizard.actions.clean.run_clean") as mock_clean,
        ):
            run_menu()
            mock_clean.assert_called_once()

    def test_run_tests_then_exit(self) -> None:
        from model_generator.wizard.menu import run_menu

        with (
            patch(
                "model_generator.wizard.menu.select",
                side_effect=["Run tests", "Exit"],
            ),
            patch("model_generator.wizard.actions.test_runner.run_tests") as mock_tests,
        ):
            run_menu()
            mock_tests.assert_called_once()


class TestProjectSetupAction:
    """Test the project setup wizard action."""

    def test_create_config(self, tmp_path: Path) -> None:
        """Test creating a new .model-generator.yaml via wizard."""
        import os

        from model_generator.wizard.actions.project_setup import run_setup

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            with (
                patch(
                    "model_generator.wizard.actions.project_setup.text",
                    side_effect=["My Project", "", "0.1.0"],
                ),
                patch(
                    "model_generator.wizard.actions.project_setup.select",
                    side_effect=["python-fastapi", "full-stack (backend/src/)"],
                ),
                patch(
                    "model_generator.wizard.actions.project_setup.confirm",
                    return_value=False,
                ),
            ):
                run_setup()

            config_path = tmp_path / ".model-generator.yaml"
            assert config_path.exists()
            import yaml

            config = yaml.safe_load(config_path.read_text())
            assert config["project"]["name"] == "My Project"
            assert config["stack"] == "python-fastapi"
            assert "paths" in config
        finally:
            os.chdir(original_cwd)


class TestCleanAction:
    """Test the clean wizard action."""

    def test_clean_no_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test clean action when no config exists."""
        import os

        from model_generator.wizard.actions.clean import run_clean

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            run_clean()
            captured = capsys.readouterr()
            assert "No .model-generator.yaml found" in captured.out
        finally:
            os.chdir(original_cwd)


class TestTestRunnerAction:
    """Test the test runner wizard action."""

    def test_no_tests_dir(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test runner when no tests directory exists."""
        import os

        from model_generator.wizard.actions.test_runner import run_tests

        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            (tmp_path / ".model-generator.yaml").write_text("project: {name: test}")
            run_tests()
            captured = capsys.readouterr()
            assert "No tests/ directory found" in captured.out
        finally:
            os.chdir(original_cwd)


class TestPrepareInfraModules:
    """Tests for the shared _prepare_infra_modules() helper."""

    def test_collects_auth_extra_deps(self) -> None:
        """Auth extra deps appear in extra_deps when auth.strategy is configured."""

        import json
        import tempfile
        from unittest.mock import patch

        from model_generator.generate import _prepare_infra_modules

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "test.model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "domain": "test",
                        "entities": {
                            "Widget": {
                                "fields": {
                                    "id": {
                                        "type": "uuid",
                                        "primary_key": True,
                                        "auto_generate": True,
                                    }
                                },
                            }
                        },
                    }
                )
            )
            config = {
                "auth": {"strategy": "bcrypt-session", "pepper_env": "PEPPER"},
                "generation": {"layout": "per-entity"},
            }
            with patch("model_generator.generate._validate_auth_strategy"):
                domains, routes, factories, extra_deps, models = _prepare_infra_modules(
                    [model_path], config
                )
            assert "bcrypt>=4.0.0" in extra_deps
            assert "itsdangerous>=2.0" in extra_deps

    def test_collects_model_dependencies(self) -> None:
        """Model-declared dependencies appear in extra_deps."""
        import json
        import tempfile
        from unittest.mock import patch

        from model_generator.generate import _prepare_infra_modules

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "test.model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "domain": "test",
                        "dependencies": ["pandas>=2.0.0"],
                        "entities": {
                            "Widget": {
                                "fields": {
                                    "id": {
                                        "type": "uuid",
                                        "primary_key": True,
                                        "auto_generate": True,
                                    }
                                },
                            }
                        },
                    }
                )
            )
            config = {"generation": {"layout": "per-entity"}}
            with patch("model_generator.generate._validate_auth_strategy"):
                _, _, _, extra_deps, _ = _prepare_infra_modules([model_path], config)
            assert "pandas>=2.0.0" in extra_deps
