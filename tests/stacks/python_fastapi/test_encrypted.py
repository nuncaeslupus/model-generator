"""Tests for encrypted-bytes generator."""

import ast
from typing import Any

from model_generator.generators.infrastructure import (
    generate_encrypted_bytes,
    generate_infrastructure,
)


class TestEncryptedBytesGenerator:
    """Smoke-test the §13 EncryptedBytes TypeDecorator emission helper.

    Closes the latent emission gap: ``model.py.j2`` conditionally imports
    ``from .encrypted_bytes import EncryptedBytes`` when any field declares
    ``type: binary`` + ``encrypt: {...}``, but until this generator landed
    no infrastructure code emitted the imported module.
    """

    def test_returns_none_when_no_encrypted_binary(
        self, project_env_per_entity: Any
    ) -> None:

        project_root, config, env = project_env_per_entity
        # has_encrypted_binary defaults to False — common-case projects with
        # no binary+encrypt fields must not get a stray cryptography import.
        assert generate_encrypted_bytes(config, env, project_root) is None

    def test_emits_when_flag_set(self, project_env_per_entity: Any) -> None:

        project_root, config, env = project_env_per_entity
        result = generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)

        assert result is not None
        # Lives next to the model files so `from .encrypted_bytes import …`
        # in model.py.j2 resolves via the package's relative import.
        assert result["path"] == project_root / "src/database/models/encrypted_bytes.py"
        content = result["content"]
        # Core TypeDecorator surface
        assert "class EncryptedBytes(TypeDecorator):" in content
        assert "impl = LargeBinary" in content
        assert "cache_ok = True" in content
        # Fernet wiring + lazy import (avoids hard cryptography dep at module load)
        assert 'FERNET_KEY = os.environ.get("FERNET_KEY")' in content
        assert "from cryptography.fernet import Fernet" in content
        # Postgres dialect-specific type
        assert "from sqlalchemy.dialects.postgresql import BYTEA" in content
        assert 'dialect.name == "postgresql"' in content
        # Template bug fix: the opener `{#-` must render to nothing, not
        # leak literal text. Catch any regression where the typo `{-#`
        # would surface as raw output.
        assert "{-#" not in content
        assert "{#-" not in content

    def test_signatures_are_fully_annotated(self, project_env_per_entity: Any) -> None:
        """TPL-10: every method/function carries annotations so the file passes
        the strict mypy config the generator also ships.

        Mirrors the ``types.py`` TypeDecorator convention (``dialect: Any``);
        an unannotated ``_get_fernet`` or ``dialect`` param fails
        ``disallow_untyped_defs``. ``_get_fernet`` is typed ``-> Fernet`` (not
        ``Any``) so the bind/result values stay ``bytes``, dodging
        ``warn_return_any``.
        """

        project_root, config, env = project_env_per_entity
        result = generate_encrypted_bytes(
            config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)
        content = result["content"]

        assert "from typing import TYPE_CHECKING, Any" in content
        assert 'def _get_fernet() -> "Fernet":' in content
        assert "from cryptography.fernet import Fernet" in content
        assert "value: bytes | None, dialect: Any" in content
        assert "def load_dialect_impl(self, dialect: Any) -> Any:" in content
        # No bare (unannotated) `dialect` parameter should remain.
        assert "dialect)" not in content

        # The annotated file must parse cleanly.

        ast.parse(content)

    def test_returns_none_when_file_exists(self, project_env_per_entity: Any) -> None:

        project_root, config, env = project_env_per_entity
        # Adopter has customized encrypted_bytes.py; bootstrap helper must skip.
        out = project_root / "src/database/models/encrypted_bytes.py"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("# adopter has customized this\n")

        assert (
            generate_encrypted_bytes(
                config, env, project_root, has_encrypted_binary=True
            )
            is None
        )

    def test_path_follows_custom_database_models(
        self, project_env_per_entity: Any
    ) -> None:

        project_root, _config, env = project_env_per_entity
        # Custom layout: adopter put models elsewhere; emission must follow.
        custom_config = {
            "paths": {"database_models": "backend/lib/db/models"},
        }
        result = generate_encrypted_bytes(
            custom_config, env, project_root, has_encrypted_binary=True
        )
        assert isinstance(result, dict)

        assert result is not None
        assert (
            result["path"] == project_root / "backend/lib/db/models/encrypted_bytes.py"
        )

    def test_emission_wired_into_generate_infrastructure(
        self, project_env_per_entity: Any
    ) -> None:
        """The aggregator must include encrypted_bytes.py when the flag is set."""

        project_root, config, env = project_env_per_entity

        generated = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["users"],
            has_encrypted_binary=True,
        )

        emitted_names = {p.name for p in generated}
        assert "encrypted_bytes.py" in emitted_names

    def test_aggregator_skips_when_flag_unset(
        self, project_env_per_entity: Any
    ) -> None:
        """No binary+encrypt fields anywhere → no encrypted_bytes.py."""

        project_root, config, env = project_env_per_entity

        generated = generate_infrastructure(
            config=config,
            env=env,
            project_root=project_root,
            domains=["users"],
            # has_encrypted_binary omitted — defaults to False
        )

        emitted_names = {p.name for p in generated}
        assert "encrypted_bytes.py" not in emitted_names


class TestHasEncryptedBinaryField:
    """Test the _has_encrypted_binary_field helper (§13 emission gate)."""

    def test_empty_models_returns_false(self) -> None:
        from model_generator.generate import _has_encrypted_binary_field

        assert _has_encrypted_binary_field([]) is False

    def test_model_without_binary_field_returns_false(self) -> None:
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "User": {"fields": {"email": {"type": "text"}}},
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is False

    def test_binary_field_without_encrypt_returns_false(self) -> None:
        """Plain ``binary`` (no encrypt block) goes to LargeBinary directly —
        no EncryptedBytes TypeDecorator needed."""
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "File": {"fields": {"blob": {"type": "binary"}}},
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is False

    def test_binary_with_encrypt_returns_true(self) -> None:
        from model_generator.generate import _has_encrypted_binary_field

        models = [
            {
                "entities": {
                    "Token": {
                        "fields": {
                            "value": {
                                "type": "binary",
                                "encrypt": {"key_env": "FERNET_KEY"},
                            }
                        }
                    }
                }
            }
        ]
        assert _has_encrypted_binary_field(models) is True

    def test_detected_in_later_model_in_list(self) -> None:
        """Mixed-project case: only the second model carries an encrypted field."""
        from model_generator.generate import _has_encrypted_binary_field

        models: list[dict[str, Any]] = [
            {"entities": {"User": {"fields": {"email": {"type": "text"}}}}},
            {
                "entities": {
                    "ApiKey": {
                        "fields": {
                            "secret": {
                                "type": "binary",
                                "encrypt": {"key_env": "FERNET_KEY"},
                            }
                        }
                    }
                }
            },
        ]
        assert _has_encrypted_binary_field(models) is True
