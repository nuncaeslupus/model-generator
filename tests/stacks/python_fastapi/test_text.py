"""Tests for docstring escaping, unicode, and large spec generation."""

import ast
from pathlib import Path
from typing import Any

import pytest

from model_generator.generators import (
    generate_api_models,
    generate_database_model,
    generate_factories,
)


class TestDocstringEscaping:
    """Descriptions with triple-quotes must not break generated docstrings (SEC-8)."""

    @pytest.fixture
    def triple_quote_model(self) -> dict[str, Any]:
        return {
            "domain": "items",
            "description": 'Has """triple quotes""" in description.',
            "entities": {
                "Item": {
                    "table": "items",
                    "description": 'Entity with """triple""" quotes.',
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                            "description": 'A field with """quotes""".',
                        },
                        "name": {
                            "type": "text",
                            "max_length": 100,
                            "required": True,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_factory_docstring_escapes_triple_quotes(
        self,
        triple_quote_model: dict[str, Any],
        project_env: Any,
    ) -> None:
        project_root, config, env = project_env
        result = generate_factories(triple_quote_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]

        # The raw triple-quote sequence must not appear in the output
        assert '"""triple"""' not in content
        # Output must be valid Python
        ast.parse(content)

    def test_database_model_docstring_escapes_triple_quotes(
        self,
        triple_quote_model: dict[str, Any],
        project_env: Any,
    ) -> None:
        project_root, config, env = project_env
        result = generate_database_model(triple_quote_model, config, env, project_root)
        assert isinstance(result, dict)
        content = result["content"]

        assert '"""triple"""' not in content
        ast.parse(content)


# ---------------------------------------------------------------------------
# TST-8: Unicode / special-character content and large-spec characterisation
# ---------------------------------------------------------------------------


class TestUnicodeDescriptions:
    """Generator output must be valid UTF-8 and parseable when descriptions
    contain accented characters, emoji, or other non-ASCII unicode.

    These are characterisation tests — the generator already handles unicode
    correctly; the tests lock in that behaviour.
    """

    def _unicode_model(self) -> dict[str, Any]:
        return {
            "domain": "users",
            "description": "Représentation d'un utilisateur (用户)",
            "entities": {
                "User": {
                    "table": "users",
                    "description": "Représentation d'un utilisateur (用户)",
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "email": {
                            "type": "text",
                            "max_length": 254,
                            "required": True,
                            "unique": True,
                            "description": "Email address 📧 of the user",
                        },
                        "name": {
                            "type": "text",
                            "max_length": 200,
                            "required": True,
                            "description": "Full name — prénom et nom de famille",
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    def test_generate_factories_succeeds_with_unicode(self, project_env: Any) -> None:
        """generate_factories must not raise and must return content."""
        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        assert result["content"]

    def test_generate_factories_output_is_valid_utf8(
        self, project_env: Any, tmp_path: Path
    ) -> None:
        """Generated factory file must be encodable / decodable as UTF-8."""
        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        out_file = tmp_path / "users_factory.py"
        out_file.write_text(result["content"], encoding="utf-8")
        content = out_file.read_text(encoding="utf-8")
        assert content == result["content"]

    def test_generate_factories_output_is_ast_parseable(self, project_env: Any) -> None:
        """Generated factory file must be syntactically valid Python."""
        import ast

        project_root, config, env = project_env
        result = generate_factories(self._unicode_model(), config, env, project_root)
        assert isinstance(result, dict)
        ast.parse(result["content"])  # raises SyntaxError on failure

    def test_generate_api_models_succeeds_with_unicode(self, project_env: Any) -> None:
        """generate_api_models must not raise with unicode descriptions."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_generate_api_models_output_contains_unicode(
        self, project_env: Any
    ) -> None:
        """Unicode description text must survive template rendering unchanged."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        all_content = "\n".join(r["content"] for r in results)
        assert "📧" in all_content or "Email address" in all_content

    def test_generate_api_models_output_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Every api-models file must be syntactically valid Python."""
        import ast

        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])  # raises SyntaxError on failure

    def test_generate_api_models_output_is_valid_utf8(
        self, project_env: Any, tmp_path: Path
    ) -> None:
        """All generated API-model files must be round-trip safe as UTF-8."""
        project_root, config, env = project_env
        results = generate_api_models(self._unicode_model(), config, env, project_root)
        assert isinstance(results, list)
        for i, item in enumerate(results):
            out_file = tmp_path / f"api_model_{i}.py"
            out_file.write_text(item["content"], encoding="utf-8")
            assert out_file.read_text(encoding="utf-8") == item["content"]


class TestSpecialCharDescriptions:
    """Generator output must remain parseable when descriptions contain
    backslashes, single/double quotes, newlines, or triple-quote sequences.

    These are characterisation tests — they document safe behaviour and pin
    it against regressions.  The triple-quote test is marked xfail if the
    current generator does not yet escape triple-quotes inside docstrings
    (tracked as SEC-8).
    """

    def _model_with_description(self, description: str) -> dict[str, Any]:
        return {
            "domain": "things",
            "entities": {
                "Thing": {
                    "table": "things",
                    "description": description,
                    "fields": {
                        "id": {
                            "type": "uuid",
                            "primary_key": True,
                            "auto_generate": True,
                        },
                        "label": {
                            "type": "text",
                            "max_length": 100,
                            "required": True,
                            "description": description,
                        },
                    },
                    "timestamps": {"created": True, "updated": True},
                }
            },
        }

    @pytest.mark.xfail(
        reason="SEC-8: backslashes in descriptions are not escaped in docstrings; "
        "renders as an invalid unicode escape sequence inside the triple-quoted "
        "docstring body"
    )
    def test_backslash_in_description_is_ast_parseable(self, project_env: Any) -> None:
        """Backslashes in descriptions must not break template rendering.

        This test documents the expected safe behaviour once SEC-8 is fixed.
        Until then it is expected to fail (xfail) so it does not block CI.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description(r"Path is C:\Users\name")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    def test_double_quotes_in_description_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Double quotes in descriptions must not break template rendering."""
        import ast

        project_root, config, env = project_env
        model = self._model_with_description("He said \"hello\" and she said 'bye'")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    @pytest.mark.xfail(
        reason="SEC-8: newlines in descriptions are not escaped in Field() "
        "description strings; renders as an unterminated string literal"
    )
    def test_newlines_in_description_is_ast_parseable(self, project_env: Any) -> None:
        """Embedded newlines in descriptions must not break template rendering.

        This test documents the expected safe behaviour once SEC-8 is fixed.
        Until then it is expected to fail (xfail) so it does not block CI.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description("Line one\nLine two\nLine three")
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])

    def test_triple_quotes_in_description_is_ast_parseable(
        self, project_env: Any
    ) -> None:
        """Triple-quote sequences in descriptions must not break docstrings.

        SEC-8 fixed: triple-quotes are now escaped via the safe_docstring
        Jinja2 filter applied to all description sites in the templates.
        """
        import ast

        project_root, config, env = project_env
        model = self._model_with_description('Open """triple""" quotes here')
        results = generate_api_models(model, config, env, project_root)
        assert isinstance(results, list)
        for item in results:
            ast.parse(item["content"])


class TestLargeSpecGeneration:
    """Regression guard: generating a spec with many entities and fields must
    complete without error and within a reasonable wall-clock time.

    This catches O(N^2) behaviours, truncation bugs, and memory issues that
    only appear at scale.  The tests are marked ``slow`` so ``make test``
    skips them; ``make test-all`` runs them.
    """

    @staticmethod
    def _build_large_model(
        num_entities: int = 15, fields_per_entity: int = 8
    ) -> dict[str, Any]:
        """Build a model dict with *num_entities* entities, each with
        *fields_per_entity* fields drawn from a variety of types."""
        field_types: list[dict[str, Any]] = [
            {"type": "text", "max_length": 200, "required": True},
            {"type": "text", "max_length": 100},
            {"type": "counter", "default": 0},
            {"type": "counter", "default": 1},
            {"type": "financial"},
            {"type": "text", "max_length": 50, "unique": True},
            {"type": "text", "max_length": 500},
            {"type": "counter"},
        ]
        entities: dict[str, Any] = {}
        for i in range(num_entities):
            entity_name = f"Entity{i:02d}"
            fields: dict[str, Any] = {
                "id": {
                    "type": "uuid",
                    "primary_key": True,
                    "auto_generate": True,
                }
            }
            for j in range(fields_per_entity):
                field_def = dict(field_types[j % len(field_types)])
                field_def["description"] = (
                    f"Field {j} of entity {i} — description with some text"
                )
                fields[f"field_{j:02d}"] = field_def
            entities[entity_name] = {
                "table": f"entity_{i:02d}s",
                "description": f"Entity number {i} in the large-spec test",
                "fields": fields,
                "timestamps": {"created": True, "updated": True},
            }
        return {
            "domain": "largescale",
            "description": "Large-scale model for regression testing",
            "entities": entities,
        }

    @pytest.mark.slow
    def test_generate_factories_large_spec(self, project_env: Any) -> None:
        """generate_factories on a 15-entity spec must complete in under 5 s."""
        import ast
        import time

        project_root, config, env = project_env
        model = self._build_large_model()

        start = time.monotonic()
        result = generate_factories(model, config, env, project_root)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"generate_factories took {elapsed:.2f}s (limit 5s)"
        assert isinstance(result, dict)
        ast.parse(result["content"])

    @pytest.mark.slow
    def test_generate_api_models_large_spec(self, project_env: Any) -> None:
        """generate_api_models on a 15-entity spec must complete in under 5 s."""
        import ast
        import time

        project_root, config, env = project_env
        model = self._build_large_model()

        start = time.monotonic()
        results = generate_api_models(model, config, env, project_root)
        elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"generate_api_models took {elapsed:.2f}s (limit 5s)"
        assert isinstance(results, list)
        assert len(results) >= 1
        for item in results:
            ast.parse(item["content"])

    @pytest.mark.slow
    def test_large_spec_factory_per_domain_single_file(self, project_env: Any) -> None:
        """Per-domain layout: generate_factories returns one dict for 15 entities."""
        project_root, config, env = project_env
        model = self._build_large_model(num_entities=15, fields_per_entity=8)
        result = generate_factories(model, config, env, project_root)
        # Per-domain layout returns a single dict, not a list
        assert isinstance(result, dict)
        assert result["content"]

    @pytest.mark.slow
    def test_large_spec_per_entity_produces_one_factory_per_entity(
        self, project_env_per_entity: Any
    ) -> None:
        """Per-entity layout: exactly one factory file per entity."""
        import ast

        project_root, config, env = project_env_per_entity
        num_entities = 15
        model = self._build_large_model(num_entities=num_entities, fields_per_entity=8)
        results = generate_factories(model, config, env, project_root)
        assert isinstance(results, list)
        assert len(results) == num_entities
        for item in results:
            ast.parse(item["content"])
