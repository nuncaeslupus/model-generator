"""Tests for migration init and autogen generators."""

import ast
from pathlib import Path
from typing import Any

import pytest

from model_generator.generators import (
    generate_migration_autogen,
    generate_migration_init,
)


class TestMigrationGenerator:
    """Test Alembic migration init generation."""

    def test_creates_migration_directories(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)

        migrations_dir = project_root / "alembic"
        assert migrations_dir.is_dir()
        assert (migrations_dir / "versions").is_dir()

    def test_returns_all_migration_files(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        assert isinstance(result, list)
        assert len(result) == 5
        paths = [r["path"] for r in result]
        migrations_dir = project_root / "alembic"
        assert project_root / "alembic.ini" in paths
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_env_py_content_uses_config(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        migrations_dir = project_root / "alembic"
        env_py = next(r for r in result if r["path"] == migrations_dir / "env.py")
        # config.paths.database_models is used in the import path
        assert "src.database.models" in env_py["content"]

    def _env_py(self, minimal_model: dict[str, Any], project_env: Any) -> str:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)
        env_py = next(
            r for r in result if r["path"] == project_root / "alembic" / "env.py"
        )
        content = env_py["content"]
        assert isinstance(content, str)
        return content

    def test_env_py_is_valid_python(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """The rendered env.py must parse — guards the new helper blocks."""

        ast.parse(self._env_py(minimal_model, project_env))

    def test_env_py_coerces_async_drivers_to_sync(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Alembic runs sync, so get_url() must coerce async drivers."""
        content = self._env_py(minimal_model, project_env)
        assert "def _coerce_sync_driver(url: str) -> str:" in content
        assert '"+asyncpg": "+psycopg2",' in content
        assert '"+aiosqlite": "",' in content
        # get_url returns the coerced URL, not the raw one.
        assert "return _coerce_sync_driver(url)" in content
        # Only the scheme is rewritten, so credentials/db names are never mangled.
        assert 'scheme, sep, rest = url.partition("://")' in content
        assert "scheme.endswith(async_driver)" in content

    def test_coerce_sync_driver_behaviour(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Exercise the generated _coerce_sync_driver in isolation (executing
        the whole module would run migrations)."""

        content = self._env_py(minimal_model, project_env)
        tree = ast.parse(content)
        wanted = {"_ASYNC_TO_SYNC_DRIVERS", "_coerce_sync_driver"}
        nodes: list[ast.stmt] = [
            n
            for n in tree.body
            if (isinstance(n, ast.FunctionDef) and n.name in wanted)
            or (
                isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) in wanted for t in n.targets)
            )
        ]
        ns: dict[str, Any] = {}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<env>", "exec"), ns)
        coerce = ns["_coerce_sync_driver"]
        assert (
            coerce("postgresql+asyncpg://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
        )
        assert coerce("sqlite+aiosqlite:///x.db") == "sqlite:///x.db"
        # A driver substring inside credentials must NOT be rewritten.
        assert coerce("postgresql://u:+asyncpg@h/db") == "postgresql://u:+asyncpg@h/db"
        # Already-sync URLs pass through untouched.
        assert coerce("postgresql://u:p@h/db") == "postgresql://u:p@h/db"

    def test_env_py_renders_custom_types_with_import(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """render_item must be wired into both configure() calls and import
        the project's custom column types into generated migrations."""
        content = self._env_py(minimal_model, project_env)
        assert "def render_item(type_: str, obj: Any, autogen_context: Any)" in content
        assert '_CUSTOM_TYPE_MODULE = "src.database.types"' in content
        # Wired into offline and online configure() calls.
        assert content.count("render_item=render_item,") == 2

    def test_custom_migrations_path(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "custom_migrations").is_dir()
        assert (project_root / "custom_migrations" / "versions").is_dir()

    def test_alembic_ini_content_uses_migrations_path(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        config["paths"]["migrations"] = "custom_migrations"
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        ini = next(r for r in result if r["path"] == project_root / "alembic.ini")
        assert "script_location = custom_migrations" in ini["content"]

    def test_default_path_when_key_absent(
        self, minimal_model: dict[str, Any], project_env: Any, tmp_path: Path
    ) -> None:
        project_root, config, env = project_env
        del config["paths"]["migrations"]
        generate_migration_init(minimal_model, config, env, project_root)

        assert (project_root / "alembic").is_dir()
        assert (project_root / "alembic" / "versions").is_dir()

    def test_creates_nested_project_root(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        deep_root = project_root / "subdir"
        generate_migration_init(minimal_model, config, env, deep_root)

        assert (deep_root / "alembic").is_dir()
        assert (deep_root / "alembic" / "versions").is_dir()

    def test_idempotent_mkdir(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        generate_migration_init(minimal_model, config, env, project_root)
        # Second call must not raise FileExistsError
        generate_migration_init(minimal_model, config, env, project_root)

    def test_gitkeep_content_is_empty(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        project_root, config, env = project_env
        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        migrations_dir = project_root / "alembic"
        gitkeep = next(
            r for r in result if r["path"] == migrations_dir / "versions" / ".gitkeep"
        )
        assert gitkeep["content"] == ""

    def test_generate_migration_init_skips_alembic_ini_when_exists(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Pre-existing alembic.ini stays put; in-tree alembic/ files still emit."""
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text(
            "[alembic]\nscript_location = custom\n"
        )

        result = generate_migration_init(minimal_model, config, env, project_root)
        assert isinstance(result, list)

        paths = [r["path"] for r in result]
        assert project_root / "alembic.ini" not in paths
        migrations_dir = project_root / "alembic"
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_generate_migration_init_with_no_root_files_skips_alembic_ini(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """--no-root-files suppresses alembic.ini; in-tree alembic/ files still emit."""
        project_root, config, env = project_env

        result = generate_migration_init(
            minimal_model, config, env, project_root, no_root_files=True
        )
        assert isinstance(result, list)

        paths = [r["path"] for r in result]
        assert project_root / "alembic.ini" not in paths
        assert not (project_root / "alembic.ini").exists()
        # In-tree alembic/ scaffolding still emits (lives inside the migrations dir).
        migrations_dir = project_root / "alembic"
        assert migrations_dir / "env.py" in paths
        assert migrations_dir / "script.py.mako" in paths
        assert migrations_dir / "README.md" in paths
        assert migrations_dir / "versions" / ".gitkeep" in paths

    def test_generate_migration_init_dry_run_skips_mkdir(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """dry_run=True returns file specs but does not create directories."""
        project_root, config, env = project_env

        result = generate_migration_init(
            minimal_model, config, env, project_root, dry_run=True
        )
        assert isinstance(result, list)
        assert len(result) > 0

        # No directories were actually created on disk.
        assert not (project_root / "alembic").exists()
        assert not (project_root / "alembic" / "versions").exists()

    def test_generate_migration_init_diff_skips_mkdir(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """diff=True returns file specs but does not create directories (GEN-7)."""
        project_root, config, env = project_env

        result = generate_migration_init(
            minimal_model, config, env, project_root, diff=True
        )
        assert isinstance(result, list)
        assert len(result) > 0

        assert not (project_root / "alembic").exists()
        assert not (project_root / "alembic" / "versions").exists()

    def test_migration_env_custom_type_names_constant(self) -> None:
        """_CUSTOM_TYPE_NAMES in migrations.py is the single source of truth
        for which custom types env.py must import — not a template literal."""
        from model_generator.generators.migrations import _CUSTOM_TYPE_NAMES

        assert "PortableNumeric" in _CUSTOM_TYPE_NAMES
        assert "PortableUuid" in _CUSTOM_TYPE_NAMES

    def test_migration_env_renders_custom_type_names(
        self, minimal_model: dict[str, Any], project_env: Any
    ) -> None:
        """Rendered env.py _CUSTOM_TYPE_NAMES must reflect the generator constant,
        not a hardcoded literal — so renaming a type in migrations.py propagates."""
        from model_generator.generators.migrations import _CUSTOM_TYPE_NAMES

        content = self._env_py(minimal_model, project_env)
        for name in _CUSTOM_TYPE_NAMES:
            assert f'"{name}"' in content, (
                f"Expected '{name}' to appear in rendered env.py _CUSTOM_TYPE_NAMES"
            )
        # The assignment must be present and be a tuple, not a hardcoded one-liner.
        assert "_CUSTOM_TYPE_NAMES = (" in content


class TestMigrationAutogen:
    """Test generate_migration_autogen."""

    # GEN-12: the target is instruction-only and emits no file, so it returns
    # ``None`` rather than a sentinel dict the output dispatch had to
    # special-case. The ``-> None`` signature (CI-enforced by mypy) is the
    # guard against a dict being reintroduced; behaviour is covered below.

    def test_warning_message_when_not_initialized(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root, config, env = project_env
        generate_migration_autogen(minimal_model, config, env, project_root)
        captured = capsys.readouterr()

        assert (
            captured.out.rstrip("\n")
            == "  ⚠️  Alembic not initialized. Run with --target migration-init first."
        )

    def test_prints_project_agnostic_instructions_when_initialized(
        self,
        minimal_model: dict[str, Any],
        project_env: Any,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        project_root, config, env = project_env
        (project_root / "alembic.ini").write_text("[alembic]\n")
        generate_migration_autogen(minimal_model, config, env, project_root)
        out = capsys.readouterr().out

        # Honest: no false "Running alembic…" line — nothing is actually run.
        assert "Running alembic revision --autogenerate..." not in out
        # GEN-6: instructions must be project-agnostic — no hardcoded
        # TimescaleDB / docker-compose orchestration.
        assert "timescale" not in out.lower()
        assert "docker-compose" not in out
        assert "docker compose" not in out
        # Still surfaces the actionable guidance.
        assert "DATABASE_URL" in out
        assert "alembic revision --autogenerate" in out
        assert "alembic upgrade head" in out
