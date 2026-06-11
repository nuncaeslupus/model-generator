# Changelog

All notable changes to model-generator are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] — 2026-06-11

### Security

Hardened the generated FastAPI CRUD surface (follow-ups from a downstream
security audit). **Adopters built from generator output (e.g. `oms`,
`ml-engine`) should regenerate to pick these up.** No wire contract changed —
field names, enums, and happy-path status codes are identical; every change
below affects only the malformed-input / error paths.

- **List filters validate at the boundary (no more 500s).** Numeric and date
  `list_*` query params are now emitted with their real types
  (`Decimal | None`, `datetime | None`) instead of `str | None` coerced inside
  the handler. A malformed filter (`?<field>_min=abc`, `?<field>_after=notadate`)
  now returns a structured 422 at the framework boundary instead of an unhandled
  500 with a stack trace. The manual `Decimal(...)` / `datetime.fromisoformat(...)`
  calls are gone; valid filters behave exactly as before.
- **Generic 409 duplicate-value message.** The integrity-error helper
  (`errors.py`, `format_integrity_error`) no longer parses and echoes the
  offending DB column name by default ("A &lt;entity&gt; with these values
  already exists"). Set `app.expose_integrity_error_fields: true` to restore the
  field-named message. The structured error shape is unchanged.
- **Request-body size limit (defense-in-depth).** Generated apps install an
  ASGI middleware (`request_limit.py`) that rejects request bodies larger than
  `app.max_request_body_bytes` (default 10 MiB, generous so normal payloads are
  unaffected) with a 413, before the body is read into memory. Set the value to
  0 to disable; the middleware is then not emitted.
- **Trimmed validation errors.** A `RequestValidationError` handler
  (`errors.py`, `validation_exception_handler`, registered in `main.py`)
  summarizes pydantic errors to a `field` + `message` list instead of returning
  the raw `exc.errors()`, which echoed submitted input values and internal
  locator detail.

### Added

- `app.max_request_body_bytes` and `app.expose_integrity_error_fields` project
  config keys (`.model-generator.yaml` / stack `config.yaml`).

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

[Unreleased]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/nuncaeslupus/model-generator/releases/tag/v0.1.0
