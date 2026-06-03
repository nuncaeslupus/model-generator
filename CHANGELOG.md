# Changelog

All notable changes to model-generator are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-06-03

First public release on PyPI.

### Added

- `uv tool install model-generator-kit` (or `pip install model-generator-kit`) — the
  `model-gen` and `model-val` CLIs are now installable from PyPI. The PyPI
  distribution is named `model-generator-kit` because `model-generator` was taken;
  the import package, commands, and config file are unchanged.
- `model-gen --version` / `model-val --version` report the installed version.
- Release automation: pushing a `vX.Y.Z` tag builds and publishes to PyPI via
  GitHub Actions trusted publishing (OIDC, no stored token) and cuts a GitHub
  release. See [RELEASE.md](./RELEASE.md).
- `make version-sync` / `make check-version-sync` keep the version string in
  `pyproject.toml`, `src/model_generator/__init__.py`, and the README footer
  consistent; the check is enforced in CI.

### Notes

- Ships the `python-fastapi` stack (SQLAlchemy models, Pydantic API models,
  FastAPI routes, pytest contract tests, Alembic migrations). The generator is
  stack-agnostic by design — FastAPI is the first stack, selected via
  `--stack` (default `python-fastapi`), not a hard dependency of the tool.

[Unreleased]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/nuncaeslupus/model-generator/releases/tag/v0.1.0
