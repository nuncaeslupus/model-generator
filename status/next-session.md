# Next Session Plan

## Current State (2026-04-19)

Stable release with external-review blockers cleared. 290 tests passing, ruff+mypy clean on `src/`, GitHub Actions CI in place.

### Possible Next Steps

1.  **New stacks** — Add stack templates beyond python-fastapi (e.g., python-django, node-express).
2.  **Test Suite Refactor (Architecture Ready)** — Prepare the test suite for multi-stack support:
    *   **Core vs. Stacks**: Split tests into `tests/core/` (engine-agnostic logic) and `tests/stacks/<stack-name>/` (output-specific assertions).
    *   **Snapshot Testing**: Move away from brittle string matching in `test_generators.py` toward golden-file snapshot comparisons.
    *   **Standardized Stack Smoke Test**: Every stack should implement a standard "Contract" test suite (generate, lint, test-run).
3.  **Mutation testing** — Run mutmut to find remaining test gaps, tighten assertions.
4.  **Template improvements** — More constraint types, pagination options, bulk endpoints.
5.  **Wizard enhancements** — Improve interactive mode UX, add model editing workflow.
6.  **Documentation** — Add architecture diagrams, more examples, video walkthrough.
7.  **Deferred review items** — §8 (binary field type), §9 (owner-scoped endpoints), §12–§15 nice-to-haves. Each warrants its own plan; see the completed review batch below for context.

## Recently Completed Fixes

### 1. gen-clean failing to delete all generated files (FIXED)
When MG was invoked with `--clear-only`, several generated files were not deleted.
Cleanup logic was improved in `src/model_generator/generate.py` to cover:
- All infrastructure files (`env.py`, `script.py.mako`, `utils.py`, `types.py`, etc.)
- All `__init__.py` files in generated packages.
- All `__pycache__` directories recursively.
- All explicit file paths defined in the stack configuration.

### 2. Standardize timestamp_after constraint (FIXED)
The `timestamp_after` constraint was previously only supported as a direct field
property in the source schema. Some specs listed it instead as a `field_constraint`
entry, where it failed validation.

MG now supports both in the schema and automatically normalizes the constraint form into the direct field property during loading, ensuring consistent template behavior.

### 3. External Review Follow-Up — Template + Loader Blockers (SHIPPED 2026-04-19)

Second external review landed 15 items (7 blockers, 4 sharp edges, 4 nice-to-haves). The user-approved scope (7 blockers + §10 + §11, keep warn-only validation) shipped across six commits on `chore/skills-subtree`:

| Commit | Summary | Review items |
|---|---|---|
| `c1d3380` | model.py.j2: `remote_side=[pk]` on self-ref many_to_one; stop auto-emitting `default=dict`/`default=list` for required JSON fields; `Mapped[dict[str, Any]]` / `Mapped[list[Any]]` with `from typing import Any` gated on `ns.has_json`. | §1, §10, §11 |
| `98a96be` | factory.py.j2: `create_batch(count, {{ rel.back_populates }}=obj)` replaces the broken `entity_name.lower()=obj`. | §5 |
| `cabe42b` | route.py.j2: gate all five CRUD blocks on `entity.api.endpoints`; fold mutability into the update gate. `_shared/_tests.j2` `get_enum_value` applies `\| upper` to `field_default` so enum defaults match the uppercase-everywhere convention. | §6, §7 |
| `37281a9` | `python_root` config threaded into `path_to_import` via a closure in `get_template_env`; infrastructure direct call sites refactored to use `path_to_import(dir, "module", python_root=...)` instead of `+ "."` string concat (fixes empty-base relative-import edge case); tests cover direct and filter paths. | §3 |
| `b70e6c4` | migrations.py: skip alembic.ini write when it already exists, mirroring pyproject/gitignore protection. | §4 (residual) |
| `bb42083` | loaders.py: `_normalize_indexes` converts all four legacy index shapes to canonical before validation. `json-specification-reference.md` rewritten to show the canonical shape with a proper parameter table and a back-compat note. | §2 |

**Verified via:** `uv run pytest -q` (290 passing, up from 283), `uv run ruff check src tests` clean, live `configure_mappers()` on a generated self-ref Category model, and a `python_root: "src"` probe that produced `from main import app` / `from database.engine import get_session`.

**Explicitly deferred** (need their own plans before tackling):
- **§8 binary field type** — new type mapping across config.yaml + model.py.j2 + Pydantic + factory.
- **§9 owner-scoped endpoints** — `api.scope` block, heavy `route.py.j2` changes.
- **§12–§15 nice-to-haves** (auth scaffolding, encrypted-at-rest modifier, quality-tool drift, one-file-per-entity) — low priority.

---

## Queued Upstream Gaps (from External Review, 2026-04-19)

Documentation-only audit by a downstream adopter. Items are framed in MG-internal terms; severity reflects the adopter's assessment.

### Blockers (cannot generate target schema correctly without these)

- **`bytes` / `binary` field type.** The 12 current field types have nothing that maps to SQLAlchemy `LargeBinary`. Any spec with a ciphertext / raw-bytes column has to work around via `longtext` + base64 (two transforms per read/write) or post-edit the SQLAlchemy model — both defeat the one-shot generation promise. Proposed surface: `{"type": "binary"}` → `Column(LargeBinary, nullable=...)` (SQLAlchemy) + `bytes` (Pydantic) + `factory.LazyFunction(lambda: secrets.token_bytes(32))` (factory default). Verify: round-trip on SQLite (BLOB) and Postgres (BYTEA), contract test confirms `bytes` column survives `POST` → `GET`.
- **Self-referential foreign key.** Docs only show cross-entity `reference` (e.g., `users ← audit_logs`). A self-ref (`Entity.parent_id → Entity.id`) is undocumented, and template iteration in `database/model.py.j2` is likely written assuming `rel.target != self`. Needed: a confirmed-working self-ref example in `examples/`, a regression test in `tests/test_generators.py` that generates a self-ref entity and runs its contract tests green, and — if `foreign_keys` must be specified explicitly for same-target relations — docs guidance for that case.

### Sharp Edges (generation works but produces code adopters immediately rewrite)

- **Owner-scoped endpoints.** Generated CRUD emits unscoped queries (`db.query(Project).filter_by(id=...)`) — a logged-in user can fetch/edit/delete another user's row by guessing an id. Every regeneration undoes any post-edit. Proposed surface: per-entity `api.scope: {owner_field, inject_from, miss_status}`; when present the generator wires `current_user: User = Depends(get_current_user)` into route signatures (dependency path configurable in `.model-generator.yaml`), filters every list/get/update/delete by `owner_field == current_user.id`, returns 404 (configurable) on cross-owner access, and emits a "user B cannot access user A's row" contract test. The dependency function itself stays user-written; the generator just knows to call it.
- **`json_object` / `json_array` default when `required: true`.** Docs say the SQLAlchemy default for `json_object` is `default=dict`. If generator still emits `Column(JSON, nullable=False, default=dict)` under `required: true`, any code path that forgets to set the field silently inserts an empty `{}` — a data-integrity landmine. Need either docs clarification that `required: true` suppresses the default, OR a `default: null` option to force "no server-side default, every insert must set the field."

### Nice-to-haves (not blocking any current adopter; longer-term)

- **Auth scaffolding.** The `User` example already has a `password` field with `api_exclude_response: true`, which reads as "auth support is coming." A future `auth: {strategy: "bcrypt-session", pepper_env: "APP_PASSWORD_PEPPER"}` block emitting a starter auth router (register/login/logout/forgot/reset, bcrypt+pepper hashing, itsdangerous session cookies, CSRF middleware, rate limiting on login/register) would be a natural extension. Flag for post-v0.2.
- **Encrypted-at-rest column modifier.** Builds on the `binary` type: `{"type": "binary", "encrypt": {"key_env": "FERNET_KEY_FILE"}}` → emits a SQLAlchemy `TypeDecorator` that `fernet.encrypt()` on write and `fernet.decrypt()` on read. App code writes/reads raw `bytes`; the codec is invisible.
- **Quality-tool defaults per-project.** Generated code hardcodes `line-length = 88` (ruff) and `python_version = "3.11"` (mypy). Adopters with different conventions (`line-length = 100`, Python 3.12, etc.) get unnecessary reformat churn on first save. A `quality:` section in `.model-generator.yaml` that lets the consumer override these before generation would prevent the noise diff.

### Audit scope notes

The review above was documentation-only against `docs/`. A templates-level second pass — generate a draft spec with several entities and inspect the produced SQLAlchemy models, API routes, contract tests, and Alembic env — would likely surface additional gaps not visible in docs alone. Worth scheduling before declaring any of the above "done."
