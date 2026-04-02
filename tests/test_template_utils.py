"""Tests for template utilities and custom Jinja2 filters."""

from model_generator.utils.templates import get_template_env, path_to_import, wrap_text


class TestPathToImport:
    """Test file path to Python import conversion."""

    def test_standard_path(self):
        result = path_to_import("backend/src/database/models")
        assert result == "backend.src.database.models"

    def test_with_module(self):
        assert path_to_import("backend/src/api", "routes") == "backend.src.api.routes"

    def test_root_level(self):
        assert path_to_import("models") == "models"

    def test_backslash_path(self):
        assert path_to_import("backend\\src\\models") == "backend.src.models"


class TestWrapText:
    """Test text wrapping utility."""

    def test_short_text_unchanged(self):
        result = wrap_text("Short text", width=88)
        assert result == "Short text"

    def test_long_text_wrapped(self):
        long = "A " * 60  # ~120 chars
        result = wrap_text(long.strip(), width=88)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 88

    def test_width_parameter_respected(self):
        # 50 "word"s > 40 chars: with width=40 every line must be ≤ 40
        long = " ".join(["word"] * 50)
        result = wrap_text(long, width=40)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 40

    def test_custom_indent(self):
        long = "word " * 30
        result = wrap_text(long.strip(), width=60, indent=8)
        lines = result.split("\n")
        # Continuation lines should be indented
        if len(lines) > 1:
            assert lines[1].startswith(" " * 8)

    def test_prefix_stripped(self):
        result = wrap_text("hello world", width=88, prefix="    field: ")
        # Prefix should not appear in output; content must be intact
        assert not result.startswith("    field: ")
        assert result == "hello world"

    def test_empty_text(self):
        assert wrap_text("") == ""

    def test_none_like_empty(self):
        # The function should handle empty strings
        assert wrap_text("") == ""

    def test_default_width_is_88(self):
        # 30 two-char words = 89 chars total; wraps at width=88, stays on one line at 89
        text = " ".join(["aa"] * 30)
        result = wrap_text(text)  # default width
        lines = result.split("\n")
        assert all(len(line) <= 88 for line in lines)

    def test_default_indent_is_zero(self):
        long = " ".join(["word"] * 30)
        result = wrap_text(long, width=40)  # default indent
        lines = result.split("\n")
        assert len(lines) > 1
        assert not lines[1].startswith(" ")

    def test_default_prefix_is_empty(self):
        # 18 "word"s = 89 chars; fits in width=89 only when no prefix eats into width
        text = " ".join(["word"] * 18)
        result = wrap_text(text, width=89)  # default prefix
        assert "\n" not in result


class TestTemplateEnv:
    """Test Jinja2 template environment setup."""

    def test_creates_environment(self):
        env = get_template_env("python-fastapi")
        assert env is not None

    def test_default_stack_loads_templates(self):
        env = get_template_env()  # default stack must be "python-fastapi"
        template = env.get_template("database/model.py.j2")
        assert template is not None

    def test_has_custom_filters(self):
        env = get_template_env("python-fastapi")
        assert "dict2items" in env.filters
        assert "path_to_import" in env.filters
        assert "wrap" in env.filters

    def test_dict2items_filter(self):
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["dict2items"]
        result = filter_fn({"a": 1, "b": 2})
        assert result == [{"key": "a", "value": 1}, {"key": "b", "value": 2}]

    def test_path_to_import_filter(self):
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["path_to_import"]
        assert filter_fn("src/api/models") == "src.api.models"

    def test_wrap_filter(self):
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["wrap"]
        result = filter_fn("short text", 88)
        assert result == "short text"

    def test_template_loading(self):
        env = get_template_env("python-fastapi")
        # Should be able to load key templates
        template = env.get_template("database/model.py.j2")
        assert template is not None

    def test_trim_blocks_and_trailing_newline(self):
        env = get_template_env("python-fastapi")
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True
        assert env.keep_trailing_newline is True
