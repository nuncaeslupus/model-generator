"""Tests for the interactive wizard module."""

from pathlib import Path
from types import SimpleNamespace
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

    def test_checkbox_empty_returns_empty(self) -> None:
        """Empty input = no selection (matches questionary), not an infinite loop."""
        from model_generator.wizard.prompts import checkbox

        with patch("builtins.input", return_value=""):
            result = checkbox("Select:", choices=["x", "y", "z"])
        assert result == []

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


class TestPromptsOptionalImport:
    """WIZ-2: questionary is an optional extra — the import must be guarded."""

    def test_module_exposes_questionary_sentinel(self) -> None:
        import model_generator.wizard.prompts as p

        # _questionary is either the real module or None (never an AttributeError):
        # the try/except import means a base install still imports cleanly.
        assert hasattr(p, "_questionary")

    def test_fallback_used_when_questionary_absent(self) -> None:
        """With _questionary None the plain input() path is live, not dead code."""
        import model_generator.wizard.prompts as p

        with (
            patch.object(p, "_questionary", None),
            patch("builtins.input", return_value="1"),
        ):
            assert p.select("Pick:", choices=["a", "b"]) == "a"


class TestPromptsCancellation:
    """WIZ-3: aborting a prompt raises PromptCancelled, never a bogus value."""

    @staticmethod
    def _cancelling_questionary() -> SimpleNamespace:
        """A questionary stand-in whose every prompt .ask()s to None (Ctrl-C/ESC)."""
        cancelled = SimpleNamespace(ask=lambda: None)
        return SimpleNamespace(
            select=lambda *a, **k: cancelled,
            checkbox=lambda *a, **k: cancelled,
            confirm=lambda *a, **k: cancelled,
            text=lambda *a, **k: cancelled,
        )

    @pytest.mark.parametrize(
        ("fn", "args"),
        [
            ("select", ("Pick:", ["a", "b"])),
            ("checkbox", ("Pick:", ["a", "b"])),
            ("confirm", ("OK?",)),
            ("text", ("Name?",)),
        ],
    )
    def test_questionary_none_raises(self, fn: str, args: tuple[object, ...]) -> None:
        import model_generator.wizard.prompts as p

        with (
            patch.object(p, "_questionary", self._cancelling_questionary()),
            pytest.raises(p.PromptCancelled),
        ):
            getattr(p, fn)(*args)

    def test_fallback_eof_raises_cancelled(self) -> None:
        """Ctrl-D (EOFError) at the plain prompt maps to PromptCancelled."""
        import model_generator.wizard.prompts as p

        with (
            patch.object(p, "_questionary", None),
            patch("builtins.input", side_effect=EOFError),
            pytest.raises(p.PromptCancelled),
        ):
            p.select("Pick:", choices=["a", "b"])


class TestMenuCancellation:
    """WIZ-3: cancellation control flow in the menu loop."""

    def test_top_level_cancel_exits(self, capsys: pytest.CaptureFixture[str]) -> None:
        from model_generator.wizard.menu import run_menu
        from model_generator.wizard.prompts import PromptCancelled

        with patch("model_generator.wizard.menu.select", side_effect=PromptCancelled):
            run_menu()  # must terminate, not loop forever
        assert "Goodbye" in capsys.readouterr().out

    def test_action_cancel_returns_to_menu(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from model_generator.wizard.menu import run_menu
        from model_generator.wizard.prompts import PromptCancelled

        with (
            patch(
                "model_generator.wizard.menu.select",
                side_effect=["Generate code", "Exit"],
            ),
            patch(
                "model_generator.wizard.actions.generate.run_generate",
                side_effect=PromptCancelled,
            ),
        ):
            run_menu()
        out = capsys.readouterr().out
        assert "Returning to menu" in out


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
                _domains, _routes, _factories, extra_deps, _models = (
                    _prepare_infra_modules([model_path], config)
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

    def test_per_domain_layout_uses_domains_not_entity_stems(self) -> None:
        """Per-domain layout: route_modules / factory_modules = domain names."""
        import json
        import tempfile
        from unittest.mock import patch

        from model_generator.generate import _prepare_infra_modules

        with tempfile.TemporaryDirectory() as tmp:
            model_path = Path(tmp) / "acme.model.json"
            model_path.write_text(
                json.dumps(
                    {
                        "domain": "acme",
                        "entities": {
                            "Widget": {
                                "fields": {"id": {"type": "uuid", "primary_key": True}}
                            },
                            "Gadget": {
                                "fields": {"id": {"type": "uuid", "primary_key": True}}
                            },
                        },
                    }
                )
            )
            config = {"generation": {"layout": "per-domain"}}
            with patch("model_generator.generate._validate_auth_strategy"):
                domains, route_modules, factory_modules, _, _ = _prepare_infra_modules(
                    [model_path], config
                )
        assert "acme" in domains
        assert route_modules == ["acme"]
        assert factory_modules == ["acme"]
        assert "widget" not in route_modules
        assert "gadget" not in route_modules

    def test_api_disabled_entity_excluded_from_route_modules(self) -> None:
        """An entity with api.enabled=false must not appear in route_modules."""
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
                            "Public": {
                                "fields": {"id": {"type": "uuid", "primary_key": True}},
                                "api": {"enabled": True},
                            },
                            "Internal": {
                                "fields": {"id": {"type": "uuid", "primary_key": True}},
                                "api": {"enabled": False},
                            },
                        },
                    }
                )
            )
            config = {"generation": {"layout": "per-entity"}}
            with patch("model_generator.generate._validate_auth_strategy"):
                _, route_modules, _, _, _ = _prepare_infra_modules([model_path], config)
        assert "public" in route_modules
        assert "internal" not in route_modules

    def test_extra_deps_deduplicated_across_models(self) -> None:
        """Same dependency declared in two models appears only once in extra_deps."""
        import json
        import tempfile
        from unittest.mock import patch

        from model_generator.generate import _prepare_infra_modules

        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name in ("alpha", "beta"):
                p = Path(tmp) / f"{name}.model.json"
                p.write_text(
                    json.dumps(
                        {
                            "domain": name,
                            "dependencies": ["shared-lib>=1.0"],
                            "entities": {
                                "Item": {
                                    "fields": {
                                        "id": {"type": "uuid", "primary_key": True}
                                    }
                                }
                            },
                        }
                    )
                )
                paths.append(p)
            config = {"generation": {"layout": "per-entity"}}
            with patch("model_generator.generate._validate_auth_strategy"):
                _, _, _, extra_deps, _ = _prepare_infra_modules(paths, config)
        assert extra_deps.count("shared-lib>=1.0") == 1


class TestRunGenerateAction:
    """WIZ-5 / WIZ-4: run_generate's real control flow (not a mock dispatch)."""

    @staticmethod
    def _setup_project(tmp_path: Path) -> Path:
        """A minimal project tree run_generate can discover: config + one model."""
        import json

        (tmp_path / ".model-generator.yaml").write_text(
            "project: {name: demo}\nstack: python-fastapi\n"
        )
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "widget.model.json").write_text(
            json.dumps(
                {
                    "domain": "widget",
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
        return tmp_path

    def test_domain_target_calls_generate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-infra target scans models and calls generate() per file."""
        from model_generator.wizard.actions import generate as gen_action

        self._setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        with (
            patch.object(gen_action, "select", return_value="database"),
            patch.object(gen_action, "confirm", return_value=True),
            patch("model_generator.generate.generate") as mock_generate,
        ):
            gen_action.run_generate()

        mock_generate.assert_called_once()
        _, kwargs = mock_generate.call_args
        assert kwargs["target"] == "database"
        assert kwargs["no_root_files"] is False
        assert kwargs["model_path"].name == "widget.model.json"

    def test_no_root_files_threaded_when_declined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WIZ-4: declining root files threads no_root_files=True into both calls."""
        from model_generator.wizard.actions import generate as gen_action

        self._setup_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        with (
            patch.object(gen_action, "select", return_value="all"),
            # confirm calls: root-files? -> No, then Proceed? -> Yes.
            patch.object(gen_action, "confirm", side_effect=[False, True]),
            patch("model_generator.utils.load_config", return_value={}),
            patch("model_generator.utils.get_template_env"),
            patch("model_generator.utils.run_quality_tools"),
            patch(
                "model_generator.generate._prepare_infra_modules",
                return_value=([], [], [], [], []),
            ),
            patch(
                "model_generator.generate._has_encrypted_binary_field",
                return_value=False,
            ),
            patch(
                "model_generator.generators.infrastructure.generate_infrastructure",
                return_value=[],
            ) as mock_infra,
            patch("model_generator.generate.generate") as mock_generate,
        ):
            gen_action.run_generate()

        assert mock_infra.call_args.kwargs["no_root_files"] is True
        assert mock_generate.call_args.kwargs["no_root_files"] is True


class TestFindProjectRoot:
    """Test wizard find_project_root sentinel-file lookup."""

    def test_cwd_returned_when_cwd_has_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CWD is returned when it has the marker; parent config does not override it.

        Both directories carry the marker so a mutation that breaks the CWD check
        falls through to the parent check (returning parent instead of cwd), which
        makes the assertion fail.
        """
        from model_generator.wizard.actions._common import find_project_root

        cwd_dir = tmp_path / "project"
        cwd_dir.mkdir()
        (tmp_path / ".model-generator.yaml").touch()
        (cwd_dir / ".model-generator.yaml").touch()
        monkeypatch.chdir(cwd_dir)
        assert find_project_root() == cwd_dir

    def test_parent_returned_when_only_parent_has_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parent directory is returned when only the parent has the marker file."""
        from model_generator.wizard.actions._common import find_project_root

        cwd_dir = tmp_path / "project"
        cwd_dir.mkdir()
        (tmp_path / ".model-generator.yaml").touch()
        monkeypatch.chdir(cwd_dir)
        assert find_project_root() == tmp_path

    def test_falls_back_to_cwd_when_no_config_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CWD is returned as a fallback when no marker exists in cwd or parent."""
        from model_generator.wizard.actions._common import find_project_root

        monkeypatch.chdir(tmp_path)
        assert find_project_root() == tmp_path
