# Changelog

All notable changes to model-generator are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`encrypt` is now expressible in a valid spec.** A binary field's `encrypt`
  block (which triggers the at-rest `EncryptedBytes` type) was rejected by the
  field schema (`additionalProperties: false` with no `encrypt` property), so
  `model-val` flagged it and `load_model` warned even though `model-gen` honors
  it. Added `encrypt` (`{key_env?}`) to the field schema.
- **Example `.gitignore` no longer hides generated code.** The bundled
  `user-auth-project/.gitignore` excluded the generated `src/`, `tests/`, and
  `alembic/` trees — contradicting the "the generated code is yours, commit it"
  philosophy and diverging from the `.gitignore` the generator actually emits.
  It now mirrors the generated file (ignoring only caches/venvs/secrets/build
  artifacts).
- **Generated contract suite is green for owner-scoped entities.** When
  `auth.strategy` is on and an entity declares `api.scope`, its CRUD endpoints
  require an authenticated `current_user` and inject the owner from it. The
  generated contract fixtures created such entities unauthenticated (401), and
  the `missing_required_fields` test still omitted the (now injected) owner
  field and expected 422 — so the suite was red out of the box. The API
  `conftest.py` now emits an autouse fixture that authenticates every test as a
  persisted owner user (overriding `get_current_user`, coercing the id to the
  owner column's `uuid.UUID` type), and the missing-required test no longer
  treats the scope owner field as a required request field.
- **All generator file I/O is now UTF-8 explicit.** Reading specs/schemas and
  writing generated files passed no `encoding=`, so they used the platform
  default codec (cp1252 on Windows) — risking mojibake or `UnicodeDecodeError`
  on non-ASCII model content. Every read/write now pins `encoding="utf-8"`.
- **`model-val` accepts the same JSON dialect as `model-gen`.** The validator
  parsed specs with a raw `json.load` that bypassed the shared loader, so it
  rejected files the generator happily builds: `//` comments, the `integer`
  alias (normalized to `counter`), and legacy index shapes
  (`{"type": "unique", "field": ...}`). It now reads through the shared
  comment-stripping + normalizing parser, so validation and generation agree.
- **Conftest generation tolerates `//`-commented specs.** The contract-test
  conftest builder also used a raw `json.load` and crashed on commented model
  files; it now uses the same shared parser.
- **`run_quality_tools` no longer swallows failures or uses a shell.** The
  post-generation ruff step ran via `subprocess.run(..., shell=True)` with the
  file list interpolated into a string (breaking on paths with spaces/special
  characters), and ignored the return code — so a missing ruff or a failing
  `ruff format` was silent. It now invokes ruff with an argv list (no shell),
  warns clearly when ruff isn't installed, and surfaces a non-zero `ruff format`
  (a non-zero `ruff check --fix`, expected for freshly generated code, stays
  quiet).

### Changed

- **Internal: ruff lint set broadened** to `B`/`SIM`/`UP`/`PTH`/`RUF` (from
  `E`/`W`/`F`/`I`), matching the project's global standard, with an explanatory
  comment; ~33 real issues fixed across the package.
- **Release notes scoped per version.** The release workflow now publishes only
  the tagged version's CHANGELOG section instead of the entire file, and the
  CHANGELOG no longer names specific downstream projects.

### Added

- **CI runs the generated example end-to-end.** A new `generated-example` CI
  job (and `make smoke-example` / `scripts/smoke_generated_example.sh`)
  regenerates the bundled example into a throwaway tree and runs its emitted
  contract suite under Python 3.12 — catching template changes that ship
  importable-but-broken code, which the mocked/string-matched unit suite cannot.

## [0.1.4] — 2026-06-14

### Fixed

Two generator-template fixes surfaced by the 0.1.3 downstream regen.
**Adopters should regenerate to pick these up.** No wire contract changed.

- **Alembic `env.py`: async driver + custom-type autogenerate.** The generated
  `migrations/env.py` built a synchronous Alembic engine straight from
  `DATABASE_URL`, so an async URL (`postgresql+asyncpg://`, `sqlite+aiosqlite://`,
  `mysql+aiomysql://`, …) broke `alembic upgrade`/autogenerate. `get_url()` now
  coerces a known async driver to its sync equivalent. Separately, autogenerate
  emitted the project's custom column types (`PortableUuid`, `PortableNumeric`)
  into migrations without importing them, so the migration failed with
  `NameError`; a `render_item` hook (wired into both the offline and online
  `context.configure(...)` calls) now renders those types and adds the matching
  import. These were previously carried as hand-edits in downstream repos.
- **Password field OpenAPI example is no longer a secret-like value.** The
  request-model example for any `password`-named field was hardcoded to
  `SecureP@ssw0rd!`, which secret scanners (GitGuardian) flagged in every
  generated repository. It is now the non-secret placeholder
  `your-password-here`.

### Changed

- **Release tooling.** Added `make tag-release`, which tags the current `main`
  HEAD with `v<pyproject-version>` and pushes it (triggering the PyPI publish
  workflow) only when on a clean, in-sync `main` with consistent version
  strings and no pre-existing tag — making it impossible to tag the wrong
  commit. `RELEASE.md` now documents it as the canonical release step.

## [0.1.3] — 2026-06-14

### Fixed

Signed financial fields no longer fail validation on legitimate negative
values. **Adopters built from generator output should regenerate to pick this
up.** No wire contract changed — field names, types, and status codes are
identical.

- **`financial` field validator selection is now constraint-aware.** The API
  response template (`api/response.py.j2`) hardcoded
  `validate_non_negative_decimal` for *every* `financial` field, so any field
  that can legitimately be negative (PnL, realized/unrealized PnL, returns,
  Sharpe ratio, slippage bps, balance deltas) was rejected with HTTP 422 on a
  valid negative value. A `financial` field now maps to
  `validate_non_negative_decimal` only when it declares a `non_negative` /
  `non_negative_or_null` constraint, `validate_positive_decimal` for a
  `positive` / `positive_or_null` constraint, and the new signed
  `validate_decimal` (the safe default) otherwise. The chosen validator is
  imported to match. The same constraint-aware logic now also drives the
  unconstrained-`financial` default in the request template
  (`api/request.py.j2`) for create/update models, so they accept negatives
  where the spec allows them.
- **New `validate_decimal` validator.** `infrastructure/validators.py.j2` now
  emits a sign-agnostic `validate_decimal` that accepts negative, zero, and
  positive well-formed decimals.

## [0.1.2] — 2026-06-11

### Security

Two template fixes surfaced by a downstream PR-review pass over the 0.1.1
adoption. **Adopters built from generator output should regenerate to pick
these up.** No wire contract changed — field names, enums, and happy-path status
codes are identical.

- **Request-body size limit: negative `Content-Length` bypass (defense-in-depth).**
  The `request_limit.py` middleware read `Content-Length` with `int(value)`
  verbatim, so a client sending `Content-Length: -100` produced `-100`, which
  passed the `> max_body_bytes` guard and took the "stream through untouched"
  fast-path — skipping the byte-counting entirely. `_content_length` now treats
  a negative declared length as invalid (returns `None`), so the request falls
  through to the chunked-counting path and is still rejected with a 413 on
  overflow. Compliant servers reject a negative `Content-Length` at the protocol
  layer; the middleware no longer relies on that pre-filtering.
- **List filters: naive vs. tz-aware datetime comparison.** A `datetime | None`
  list filter parses input without an offset (e.g. `2026-06-11T12:00:00`) as a
  naive datetime, then compared it directly against a tz-aware
  `DateTime(timezone=True)` column — which raises `TypeError`/`DataError` on
  strict drivers (asyncpg/psycopg2) at query time. The generated handler now
  localizes a naive value to UTC (`v.replace(tzinfo=timezone.utc)`) before the
  comparison, applied uniformly to every `_after` and `_before` datetime filter.
  Latent (SQLite suites don't enforce tz-awareness), not a regression from 0.1.1.

## [0.1.1] — 2026-06-11

### Security

Hardened the generated FastAPI CRUD surface (follow-ups from a downstream
security audit). **Adopters built from generator output should regenerate to
pick these up.** No wire contract changed — field names, enums, and happy-path
status codes are identical; every change below affects only the malformed-input
/ error paths.

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

[Unreleased]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/nuncaeslupus/model-generator/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/nuncaeslupus/model-generator/releases/tag/v0.1.0
