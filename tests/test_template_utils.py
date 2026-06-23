"""Tests for template utilities and custom Jinja2 filters."""

from model_generator.utils.templates import (
    camel_case,
    get_template_env,
    path_to_import,
    snake_case,
    wrap_text,
)


class TestPathToImport:
    """Test file path to Python import conversion."""

    def test_standard_path(self) -> None:
        result = path_to_import("backend/src/database/models")
        assert result == "backend.src.database.models"

    def test_with_module(self) -> None:
        assert path_to_import("backend/src/api", "routes") == "backend.src.api.routes"

    def test_root_level(self) -> None:
        assert path_to_import("models") == "models"

    def test_backslash_path(self) -> None:
        assert path_to_import("backend\\src\\models") == "backend.src.models"

    def test_python_root_stripped(self) -> None:
        assert path_to_import("src/api/routes", python_root="src") == "api.routes"

    def test_python_root_with_trailing_slash(self) -> None:
        assert path_to_import("src/api/routes", python_root="src/") == "api.routes"

    def test_python_root_exact_match(self) -> None:
        assert path_to_import("src", python_root="src") == ""

    def test_python_root_no_match_is_noop(self) -> None:
        assert (
            path_to_import("backend/src/models", python_root="other")
            == "backend.src.models"
        )

    def test_python_root_with_module(self) -> None:
        result = path_to_import("src/api", "routes", python_root="src")
        assert result == "api.routes"


class TestPathToImportFilter:
    """Filter registration binds python_root from the config closure."""

    def test_filter_strips_python_root(self) -> None:
        env = get_template_env("python-fastapi", config={"python_root": "src"})
        filter_fn = env.filters["path_to_import"]
        assert filter_fn("src/api/models") == "api.models"

    def test_filter_without_config_behaves_as_before(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["path_to_import"]
        assert filter_fn("backend/src/api/models") == "backend.src.api.models"


class TestSnakeCase:
    """Test CamelCase → snake_case conversion (mirrors to_snake_case macro)."""

    def test_pascal_case(self) -> None:
        assert snake_case("UserSession") == "user_session"

    def test_single_capital(self) -> None:
        assert snake_case("User") == "user"

    def test_acronym_prefix(self) -> None:
        assert snake_case("ApiKey") == "api_key"

    def test_consecutive_capitals_acronym(self) -> None:
        assert snake_case("APIKey") == "api_key"

    def test_all_caps_acronym_mid_word(self) -> None:
        assert snake_case("HTTPSConfig") == "https_config"

    def test_leading_acronym(self) -> None:
        assert snake_case("HTTPRequest") == "http_request"

    def test_already_snake_case(self) -> None:
        assert snake_case("user_session") == "user_session"

    def test_lowercase_passthrough(self) -> None:
        assert snake_case("user") == "user"

    def test_empty_string(self) -> None:
        assert snake_case("") == ""

    def test_single_letter(self) -> None:
        assert snake_case("A") == "a"

    def test_multi_word(self) -> None:
        assert snake_case("PortfolioAsset") == "portfolio_asset"

    def test_filter_registered(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["snake_case"]
        assert filter_fn("UserRole") == "user_role"


class TestCamelCase:
    """Test snake_case → lowerCamelCase conversion (Flutter field names)."""

    def test_multi_segment(self) -> None:
        assert camel_case("last_login_at") == "lastLoginAt"

    def test_two_segments(self) -> None:
        assert camel_case("user_id") == "userId"

    def test_single_word_passthrough(self) -> None:
        assert camel_case("already") == "already"

    def test_empty_string(self) -> None:
        assert camel_case("") == ""

    def test_leading_underscore_preserved(self) -> None:
        # Dart private-member convention; the underscore stays.
        assert camel_case("_private_field") == "_privateField"

    def test_collapses_repeated_underscores(self) -> None:
        assert camel_case("a__b") == "aB"

    def test_trailing_underscore_ignored(self) -> None:
        assert camel_case("name_") == "name"

    def test_all_underscores_returned_unchanged(self) -> None:
        assert camel_case("__") == "__"

    def test_preserves_inner_capitals(self) -> None:
        # First segment keeps its original casing past the first char.
        assert camel_case("api_URL") == "apiURL"

    def test_filter_registered(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["camel_case"]
        assert filter_fn("created_at") == "createdAt"


class TestWrapText:
    """Test text wrapping utility."""

    def test_short_text_unchanged(self) -> None:
        result = wrap_text("Short text", width=88)
        assert result == "Short text"

    def test_long_text_wrapped(self) -> None:
        long = "A " * 60  # ~120 chars
        result = wrap_text(long.strip(), width=88)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 88

    def test_width_parameter_respected(self) -> None:
        # 50 "word"s > 40 chars: with width=40 every line must be ≤ 40
        long = " ".join(["word"] * 50)
        result = wrap_text(long, width=40)
        lines = result.split("\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 40

    def test_custom_indent(self) -> None:
        long = "word " * 30
        result = wrap_text(long.strip(), width=60, indent=8)
        lines = result.split("\n")
        # Continuation lines should be indented
        if len(lines) > 1:
            assert lines[1].startswith(" " * 8)

    def test_prefix_stripped(self) -> None:
        result = wrap_text("hello world", width=88, prefix="    field: ")
        # Prefix should not appear in output; content must be intact
        assert not result.startswith("    field: ")
        assert result == "hello world"

    def test_empty_text(self) -> None:
        assert wrap_text("") == ""

    def test_none_like_empty(self) -> None:
        # The function should handle empty strings
        assert wrap_text("") == ""

    def test_default_width_is_88(self) -> None:
        # 30 two-char words = 89 chars total; wraps at width=88, stays on one line at 89
        text = " ".join(["aa"] * 30)
        result = wrap_text(text)  # default width
        lines = result.split("\n")
        assert all(len(line) <= 88 for line in lines)

    def test_default_indent_is_zero(self) -> None:
        long = " ".join(["word"] * 30)
        result = wrap_text(long, width=40)  # default indent
        lines = result.split("\n")
        assert len(lines) > 1
        assert not lines[1].startswith(" ")

    def test_default_prefix_is_empty(self) -> None:
        # 18 "word"s = 89 chars; fits in width=89 only when no prefix eats into width
        text = " ".join(["word"] * 18)
        result = wrap_text(text, width=89)  # default prefix
        assert "\n" not in result


class TestTemplateEnv:
    """Test Jinja2 template environment setup."""

    def test_creates_environment(self) -> None:
        env = get_template_env("python-fastapi")
        assert env is not None

    def test_default_stack_loads_templates(self) -> None:
        env = get_template_env()  # default stack must be "python-fastapi"
        template = env.get_template("database/model.py.j2")
        assert template is not None

    def test_has_custom_filters(self) -> None:
        env = get_template_env("python-fastapi")
        assert "dict2items" in env.filters
        assert "path_to_import" in env.filters
        assert "wrap" in env.filters
        assert "snake_case" in env.filters
        assert "camel_case" in env.filters

    def test_dict2items_filter(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["dict2items"]
        result = filter_fn({"a": 1, "b": 2})
        assert result == [{"key": "a", "value": 1}, {"key": "b", "value": 2}]

    def test_path_to_import_filter(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["path_to_import"]
        assert filter_fn("src/api/models") == "src.api.models"

    def test_wrap_filter(self) -> None:
        env = get_template_env("python-fastapi")
        filter_fn = env.filters["wrap"]
        result = filter_fn("short text", 88)
        assert result == "short text"

    def test_template_loading(self) -> None:
        env = get_template_env("python-fastapi")
        # Should be able to load key templates
        template = env.get_template("database/model.py.j2")
        assert template is not None

    def test_trim_blocks_and_trailing_newline(self) -> None:
        env = get_template_env("python-fastapi")
        assert env.trim_blocks is True
        assert env.lstrip_blocks is True
        assert env.keep_trailing_newline is True
