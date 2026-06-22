"""Tests for the stack registry and the generalized quality runner.

Phase 0 of the Flutter stack plan: ``generate.py`` drives any stack via a
``StackSpec`` descriptor. These tests pin the registry contract and the
config-driven quality runner (formatter-vs-analyzer asymmetry, graceful no-op
when an SDK is absent).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from model_generator.generate import PYTHON_FASTAPI_STACK
from model_generator.generators.registry import (
    STACKS,
    CleanupSpec,
    GenContext,
    StackSpec,
    get_stack,
    register_stack,
)
from model_generator.utils.quality import (
    _find_dart,
    _find_ruff,
    run_config_quality,
    run_quality_tools,
    run_ruff_quality,
)


class TestStackRegistration:
    """The python-fastapi stack is registered and resolvable."""

    def test_python_fastapi_registered(self) -> None:
        assert "python-fastapi" in STACKS
        assert get_stack("python-fastapi") is PYTHON_FASTAPI_STACK

    def test_unknown_stack_raises_systemexit(self) -> None:
        with pytest.raises(SystemExit):
            get_stack("does-not-exist")

    def test_register_and_resolve_roundtrip(self) -> None:
        spec = StackSpec(
            name="test-stack-temp",
            infrastructure_targets=["infra-a"],
            domain_targets=["dom-a"],
            generators={},
            infra_orchestrator=lambda **kw: [],
            quality_runner=run_ruff_quality,
            cleanup_spec=CleanupSpec(
                source_path_keys=("src",),
                test_path_key="tests",
                migrations_path_key=None,
                file_glob="*.dart",
            ),
        )
        try:
            register_stack(spec)
            assert get_stack("test-stack-temp") is spec
        finally:
            STACKS.pop("test-stack-temp", None)


class TestPythonFastapiSpec:
    """The python-fastapi descriptor preserves the historical target sets."""

    def test_infrastructure_targets(self) -> None:
        assert PYTHON_FASTAPI_STACK.infrastructure_targets == [
            "base",
            "engine",
            "main",
            "test-conftest-root",
        ]

    def test_domain_targets(self) -> None:
        assert PYTHON_FASTAPI_STACK.domain_targets == [
            "enums",
            "constraints",
            "init",
            "database",
            "factories",
            "api-models",
            "api-init",
            "api-pagination",
            "api-tests",
            "api-tests-config",
            "api-routes",
            "migration-init",
            "migration-autogen",
        ]

    def test_all_targets_includes_aggregates(self) -> None:
        all_targets = PYTHON_FASTAPI_STACK.all_targets
        assert all_targets[-2:] == ["infrastructure", "all"]
        # Mirrors the former module-level TARGETS list exactly.
        assert all_targets == [
            *PYTHON_FASTAPI_STACK.infrastructure_targets,
            *PYTHON_FASTAPI_STACK.domain_targets,
            "infrastructure",
            "all",
        ]

    def test_generation_targets_excludes_aggregates(self) -> None:
        gen = PYTHON_FASTAPI_STACK.generation_targets
        assert "all" not in gen
        assert "infrastructure" not in gen

    def test_every_domain_target_has_a_generator(self) -> None:
        for target in PYTHON_FASTAPI_STACK.domain_targets:
            assert target in PYTHON_FASTAPI_STACK.generators

    def test_infra_targets_have_no_domain_generator(self) -> None:
        # Infrastructure is emitted by infra_orchestrator, not domain dispatch.
        for target in PYTHON_FASTAPI_STACK.infrastructure_targets:
            assert target not in PYTHON_FASTAPI_STACK.generators

    def test_has_validators_and_extra_deps(self) -> None:
        assert PYTHON_FASTAPI_STACK.validators
        assert PYTHON_FASTAPI_STACK.infra_validators
        assert PYTHON_FASTAPI_STACK.extra_deps_fn is not None

    def test_quality_runner_is_ruff(self) -> None:
        assert PYTHON_FASTAPI_STACK.quality_runner is run_ruff_quality


class TestGeneratorDispatch:
    """A domain generator is invoked through the spec's dispatch table."""

    def test_dispatch_calls_underlying_generator(self, tmp_path: Path) -> None:
        ctx = GenContext(
            model={"domain": "x", "entities": {}},
            config={"paths": {}},
            env=None,
            project_root=tmp_path,
            model_path=tmp_path / "x.model.json",
            enums={},
            constraints={},
        )
        sentinel = {"path": tmp_path / "out.py", "content": "x"}
        with patch(
            "model_generator.generate.generate_enums", return_value=sentinel
        ) as mock_enums:
            result = PYTHON_FASTAPI_STACK.generators["enums"](ctx)
        mock_enums.assert_called_once()
        assert result is sentinel


class TestFindDart:
    """Test _find_dart SDK discovery (mirrors _find_ruff)."""

    def test_finds_dart_tool_sdk(self, tmp_path: Path) -> None:
        (tmp_path / ".dart_tool" / "bin").mkdir(parents=True)
        (tmp_path / ".dart_tool" / "bin" / "dart").touch()
        assert _find_dart(tmp_path) == str(tmp_path / ".dart_tool" / "bin" / "dart")

    def test_finds_vendored_flutter_dart(self, tmp_path: Path) -> None:
        (tmp_path / "flutter" / "bin").mkdir(parents=True)
        (tmp_path / "flutter" / "bin" / "dart").touch()
        assert _find_dart(tmp_path) == str(tmp_path / "flutter" / "bin" / "dart")

    def test_falls_back_to_system_dart(self, tmp_path: Path) -> None:
        assert _find_dart(tmp_path) == "dart"


class TestRunQualityToolsDispatch:
    """run_quality_tools dispatches to the supplied stack runner."""

    def test_defaults_to_ruff_runner(self, tmp_path: Path) -> None:
        file1 = tmp_path / "a.py"
        with (
            patch("model_generator.utils.quality.run_ruff_quality") as mock_ruff,
        ):
            run_quality_tools({}, tmp_path, [file1])
        mock_ruff.assert_called_once_with({}, tmp_path, [file1])

    def test_uses_explicit_runner(self, tmp_path: Path) -> None:
        calls: list[tuple[object, ...]] = []

        def fake_runner(
            config: dict[str, object], root: Path, files: list[Path]
        ) -> None:
            calls.append((config, root, files))

        run_quality_tools({"k": 1}, tmp_path, [tmp_path / "a.dart"], fake_runner)
        assert calls == [({"k": 1}, tmp_path, [tmp_path / "a.dart"])]


class TestRunConfigQuality:
    """The generic config-driven runner (formatter / analyzer asymmetry)."""

    def test_returns_early_for_empty_files(self, tmp_path: Path) -> None:
        with patch("model_generator.utils.quality.subprocess.run") as mock_run:
            run_config_quality(
                {"quality": {"formatter": "dart format ."}}, tmp_path, []
            )
        mock_run.assert_not_called()

    def test_formatter_targets_file_list(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.dart"
        f2 = tmp_path / "b.dart"
        config = {"quality": {"formatter": "dart format ."}}
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch(
                "model_generator.utils.quality.shutil.which",
                return_value="/usr/bin/dart",
            ),
        ):
            mock_run.return_value.returncode = 0
            run_config_quality(config, tmp_path, [f1, f2])
        assert mock_run.call_count == 1
        argv = mock_run.call_args_list[0].args[0]
        # Trailing "." placeholder replaced by the explicit file list.
        assert argv[:2] == ["dart", "format"]
        assert str(f1) in argv and str(f2) in argv
        assert "." not in argv

    def test_analyzer_targets_package_root(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.dart"
        config = {
            "quality": {
                "analyzer": {"command": "dart analyze", "target": "package-root"}
            }
        }
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch(
                "model_generator.utils.quality.shutil.which",
                return_value="/usr/bin/dart",
            ),
        ):
            mock_run.return_value.returncode = 0
            run_config_quality(config, tmp_path, [f1])
        assert mock_run.call_count == 1
        argv = mock_run.call_args_list[0].args[0]
        # Package-root command carries no file arguments.
        assert argv == ["dart", "analyze"]
        assert str(f1) not in argv

    def test_formatter_runs_before_analyzer(self, tmp_path: Path) -> None:
        config = {
            "quality": {
                "analyzer": {"command": "dart analyze", "target": "package-root"},
                "formatter": "dart format .",
            }
        }
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch(
                "model_generator.utils.quality.shutil.which",
                return_value="/usr/bin/dart",
            ),
        ):
            mock_run.return_value.returncode = 0
            run_config_quality(config, tmp_path, [tmp_path / "a.dart"])
        first = mock_run.call_args_list[0].args[0]
        second = mock_run.call_args_list[1].args[0]
        assert first[1] == "format"
        assert second[1] == "analyze"

    def test_missing_tool_warns_and_skips(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = {"quality": {"formatter": "dart format ."}}
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch("model_generator.utils.quality.shutil.which", return_value=None),
        ):
            run_config_quality(config, tmp_path, [tmp_path / "a.dart"])
        mock_run.assert_not_called()
        assert "dart not found" in capsys.readouterr().out

    def test_subprocess_no_shell_with_cwd_and_capture(self, tmp_path: Path) -> None:
        config = {"quality": {"formatter": "dart format ."}}
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch(
                "model_generator.utils.quality.shutil.which",
                return_value="/usr/bin/dart",
            ),
        ):
            mock_run.return_value.returncode = 0
            run_config_quality(config, tmp_path, [tmp_path / "a.dart"])
        for c in mock_run.call_args_list:
            assert "shell" not in c.kwargs
            assert c.kwargs["cwd"] == tmp_path
            assert c.kwargs["capture_output"] is True

    def test_resolves_ruff_via_finder(self, tmp_path: Path) -> None:
        # A "ruff format ." command resolves the ruff executable through the
        # project-aware finder, like the dedicated ruff runner does.
        (tmp_path / ".venv" / "bin").mkdir(parents=True)
        (tmp_path / ".venv" / "bin" / "ruff").touch()
        config = {"quality": {"formatter": "ruff format ."}}
        expected = _find_ruff(tmp_path)
        with (
            patch("model_generator.utils.quality.subprocess.run") as mock_run,
            patch(
                "model_generator.utils.quality.shutil.which",
                return_value=expected,
            ),
        ):
            mock_run.return_value.returncode = 0
            run_config_quality(config, tmp_path, [tmp_path / "a.py"])
        argv = mock_run.call_args_list[0].args[0]
        assert argv[0] == expected
