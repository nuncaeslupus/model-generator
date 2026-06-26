"""Shared fixtures for python-fastapi stack tests."""

import os
from pathlib import Path
from typing import Any

import pytest
import yaml

from model_generator.utils import get_template_env, load_config

_PATHS: dict[str, str] = {
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
    "enums": "src/database/models/enums.py",
    "constraints": "src/database/models/constraints.py",
    "migrations": "alembic",
}


def _make_project_env(
    tmp_path: Path, extra_config: dict[str, Any] | None = None
) -> tuple[Path, dict[str, Any], Any]:
    config_data: dict[str, Any] = {
        "project": {"name": "Test Project", "version": "0.1.0"},
        "stack": "python-fastapi",
        "generation": {"layout": "per-domain"},
        "paths": _PATHS,
    }
    if extra_config:
        config_data.update(extra_config)

    (tmp_path / ".model-generator.yaml").write_text(yaml.dump(config_data))

    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    config = load_config("python-fastapi")
    env = get_template_env("python-fastapi")
    os.chdir(original_cwd)

    return tmp_path, config, env


@pytest.fixture
def project_env(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
    """Temporary project with config and template env, pinned to per-domain layout.

    Pinned so existing assertions about file shape (e.g., `items.py`, not
    `item.py`) stay precise as the default flips.
    """
    return _make_project_env(tmp_path)


@pytest.fixture
def project_env_per_entity(tmp_path: Path) -> tuple[Path, dict[str, Any], Any]:
    """Same as project_env but with generation.layout pinned to per-entity."""
    return _make_project_env(tmp_path, {"generation": {"layout": "per-entity"}})


@pytest.fixture
def minimal_model() -> dict[str, Any]:
    """Minimal model for testing individual generators."""
    return {
        "domain": "items",
        "description": "Test items domain",
        "entities": {
            "Item": {
                "table": "items",
                "description": "A test item",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "name": {
                        "type": "text",
                        "max_length": 100,
                        "required": True,
                        "unique": True,
                    },
                    "count": {
                        "type": "counter",
                        "default": 0,
                    },
                },
                "timestamps": {"created": True, "updated": True},
            }
        },
    }


@pytest.fixture
def multi_entity_model() -> dict[str, Any]:
    """Two-entity model exercising reference fields and one_to_many siblings.

    Post → Author via reference field (drives SubFactory imports).
    Author → Post via one_to_many (drives create_related sibling-factory imports).
    """
    return {
        "domain": "blog",
        "description": "Blog domain with authored posts",
        "entities": {
            "Author": {
                "table": "authors",
                "description": "Post author",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "name": {
                        "type": "text",
                        "max_length": 100,
                        "required": True,
                    },
                },
                "relationships": {
                    "posts": {
                        "type": "one_to_many",
                        "target": "Post",
                        "back_populates": "author",
                    },
                },
                "timestamps": {"created": True, "updated": True},
            },
            "Post": {
                "table": "posts",
                "description": "Authored post",
                "fields": {
                    "id": {
                        "type": "uuid",
                        "primary_key": True,
                        "auto_generate": True,
                    },
                    "title": {
                        "type": "text",
                        "max_length": 200,
                        "required": True,
                    },
                    "author_id": {
                        "type": "reference",
                        "reference_entity": "Author",
                        "reference_table": "authors",
                        "required": True,
                    },
                },
                "relationships": {
                    "author": {
                        "type": "many_to_one",
                        "target": "Author",
                        "back_populates": "posts",
                    },
                },
                "timestamps": {"created": True, "updated": True},
            },
        },
    }


@pytest.fixture
def cross_domain_models() -> list[dict[str, Any]]:
    """Two SEPARATE domain specs whose relationships cross the domain boundary.

    blog.Post --one_to_many--> engagement.Comment (and back). In a real
    generated project each domain is its own module; SQLAlchemy only sees one
    registry once every module is imported.
    """
    blog: dict[str, Any] = {
        "domain": "blog",
        "entities": {
            "Author": {
                "table": "authors",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "name": {"type": "text", "max_length": 100, "required": True},
                },
                "relationships": {
                    "posts": {
                        "type": "one_to_many",
                        "target": "Post",
                        "back_populates": "author",
                    },
                },
            },
            "Post": {
                "table": "posts",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "title": {"type": "text", "max_length": 200, "required": True},
                    "author_id": {
                        "type": "reference",
                        "reference_entity": "Author",
                        "reference_table": "authors",
                        "required": True,
                    },
                },
                "relationships": {
                    "author": {
                        "type": "many_to_one",
                        "target": "Author",
                        "back_populates": "posts",
                    },
                    "comments": {
                        "type": "one_to_many",
                        "target": "Comment",
                        "back_populates": "post",
                    },
                },
            },
        },
    }
    engagement: dict[str, Any] = {
        "domain": "engagement",
        "entities": {
            "Comment": {
                "table": "comments",
                "fields": {
                    "id": {"type": "uuid", "primary_key": True, "auto_generate": True},
                    "body": {"type": "text", "max_length": 500, "required": True},
                    "post_id": {
                        "type": "reference",
                        "reference_entity": "Post",
                        "reference_table": "posts",
                        "required": True,
                    },
                },
                "relationships": {
                    "post": {
                        "type": "many_to_one",
                        "target": "Post",
                        "back_populates": "comments",
                    },
                },
            },
        },
    }
    return [blog, engagement]
