# Next Session Plan

## Current State (2026-04-26, post-§15.4)

PR #10 (§9 owner-scoping) merged to `main` as squash `62a700c`. §15 (one-file-per-entity layout) is in progress on `feat/15-per-entity-layout` — **6 local commits, not pushed**.

### `feat/15-per-entity-layout`

- `18c6531` — `chore: align make lint with CI` — picked up the two `make lint` follow-ups: `ruff format --check .` added to lint target, and `examples/.*/backend/` + `examples/.*/alembic/` added to `[tool.mypy].exclude` so local mypy stops tripping on gitignored 3.12 generated output.
- `72c9ab4` — `feat: thread generation.layout config flag (§15.1)` — `load_config` defaults `generation.layout` to `"per-entity"`; `_validate_generation_config()` rejects unknown values. Plumbing only — no emission change yet.
- `8a7d481` — `feat: add snake_case filter for entity-derived filenames (§15.2)` — Python `snake_case()` in `utils/templates.py` mirroring the existing `to_snake_case` Jinja macro byte-for-byte; registered as a Jinja filter for template-side parity.
- `c5aefd0` — `docs: capture §15 mid-session checkpoint in next-session.md` — captured the §15.3 design before pausing; superseded by `96a3bbc`.
- `be47358` — `feat: split database emission per-entity (§15.3)` — generator + factory.py.j2 + model.py.j2 changes plus the entity_refs gap fix (sibling factory imports for `one_to_many` create_related). Test fixtures pinned to per-domain across `test_generators.py` (`project_env`), `test_integration.py`, and `test_edge_cases.py::test_database_only`; `test_full_generation.py` updated to expect per-entity `user.py` since it copies the example config which intentionally rides on the new default.
- `96a3bbc` — `docs: checkpoint §15.3 done in next-session.md` — captured §15.3 outcome and the §15.4 design question (combined vs two-file).
- `32641ac` — `feat: split api-models emission per-entity (§15.4)` — chose two-file path (no template changes). `generate_api_models` slices `model.entities` per render and emits `{stem}_response.py` + `{stem}_requests.py`; `generate_api_init` adds a layout-aware fallback (mirror of `generate_init` from §15.3). +5 tests (`TestApiModelsGeneratorPerEntity` × 3, `TestGenerateApiInitPerEntity` × 2).

**Verification at checkpoint:** 338 tests passing (was 333 — +5 new). `make lint` clean (ruff check + ruff format check + mypy), working tree clean.

---

## Priority Next Session — Continue §15 (steps 5–6)

The full §15 plan is at `~/.claude/plans/tranquil-shimmying-flute.md`. Steps 1–4 landed.

### §15.5 — api-routes and api-tests per-entity (NEXT UP)

Same layout-aware slicing pattern in `generate_api_routes` and `generate_api_tests` (`generators/api.py:192-220` and `223-255`). Audit `route.py.j2` and `tests/contract.py.j2` for cross-entity references (none expected in current CRUD scaffolding — confirmed during the §15.3 entity_refs analysis, but `route.py.j2` was not directly inspected). Per-entity output should be `routes/{entity_snake}.py` and `tests/api/test_{entity_snake}_api.py`. Both helpers currently return `dict | None`; per-entity bumps them to `list[dict] | None` (callers in `generate.py:80-90` already handle the list shape from §15.3 / §15.4).

**Files to touch:**
- `src/model_generator/generators/api.py` — `generate_api_routes` and `generate_api_tests`, mirror the slicing pattern from `generate_api_models` (lines 68-89).
- `tests/test_generators.py` — `TestApiRoutesGenerator` (line 591) and `TestApiTestsGenerator` (line 788) ride on per-domain-pinned `project_env`. Add `TestApiRoutesGeneratorPerEntity` and `TestApiTestsGeneratorPerEntity` using `multi_entity_model` + `project_env_per_entity`.

**Audit note:** `routes/__init__.py` and `tests/api/__init__.py` aren't currently emitted by any generator (FastAPI route registration is by import in `main.py.j2`, not by package init). Confirm during §15.5 that this stays true — if `main.py.j2` needs to import `routes.{stem}` per entity instead of `routes.{domain}`, that's a §15.5 template change.

### §15.6 — Example regen + docs

Regenerate `examples/user-auth-project/` with `--clean`. Confirm 149 tests still pass. Add commented `generation.layout` section to `.model-generator.yaml`. Update `docs/agent/json-specification-reference.md` and any user-facing config docs. Note the breaking-shape change in this file.

**Pre-regen blocker — `# None` banner bug discovered during §15.4:** Both `database/init.py.j2:22` and `api/init.py.j2:19` use `{{ domain.section | default(...) }}`. Jinja's `default` filter only fires on *undefined*, not `None` — and §15.3 / §15.4 deliberately set `section=None` for per-entity emission to suppress per-file banners. Result: per-entity `__init__.py` will emit literal `# None` banners. **Not yet visible** because the example hasn't been regenerated since §15.3, but will manifest the moment §15.6 runs `--clean`.

Fix before §15.6: change both templates to `{% if domain.section %}# {{ domain.section }}{% endif %}` (one-line edit each), or pass `boolean=true` to `default()`. Add a per-entity `__init__.py` content assertion to `TestGenerateInitPerEntity` and `TestGenerateApiInitPerEntity` that grep-rejects `# None` to lock the fix.

**Watch for during regen:** the User entity has 3 `one_to_many` sibling relationships (UserSession, ApiKey, UserRole) — these exercise the entity_refs gap fix from §15.3. If the regen produces a User factory that NameErrors at import time, the fix isn't doing its job.

### Housekeeping

- Branch `feat/15-per-entity-layout` is local-only (6 commits ahead of origin/main). Push for backup: `git push -u origin feat/15-per-entity-layout`.

---

## §12 — Auth scaffolding (after §15)

**What:** `auth: {strategy: "bcrypt-session", pepper_env: "APP_PASSWORD_PEPPER"}` → generates a starter auth router (register / login / logout / forgot / reset / change-password) with bcrypt+pepper hashing, itsdangerous session cookies, CSRF middleware, and rate limiting on login/register.
**Depends on:** User entity with `password` field (already present in the user-auth example).
**Surface:** new `templates/infrastructure/auth_router.py.j2` + session middleware hook into `main.py.j2`.
**Estimated scope:** 2–3 days. Should be broken into its own multi-commit plan.

### Incidental follow-ups still open

- **Composite-FK `__table_args__` emission.** `model.py.j2` emits N separate `ForeignKey(...)` columns for a multi-column FK instead of a single `ForeignKeyConstraint` in `__table_args__`. SQLAlchemy's `configure_mappers()` raises `AmbiguousForeignKeysError` when two entities (or one entity, as in self-ref) share multiple FK paths — even when both sides specify `foreign_keys`. Affects any composite-FK relationship. Scope: new spec shape (`relationships[].composite_fk: true`?) + `__table_args__` emission change. Not blocking any current adopter.
- **Upstream fix in `nuncaeslupus/my-skills`.** Gemini-bot correctly flagged on PR #3 that `.claude/skills/mutmut-report/analyze_mutmut.py`'s `run_cmd` should raise rather than `sys.exit(1)`. Fix belongs upstream — file a PR against `nuncaeslupus/my-skills`, then pull via `git subtree pull --prefix=.claude/skills shared-skills main --squash`.
- **Factory docstring drift in per-entity mode.** `factory.py.j2`'s docstring "Usage" example uses `model.domain` (e.g., `from .factories.users import UserFactory`) but the per-entity file lives at `factories/user.py`. Misleading but not a hard break. Polish in §15.6.

---

## Other Possible Next Steps

1. **New stacks** — templates beyond python-fastapi (python-django, node-express).
2. **Test suite refactor** — split into `tests/core/` + `tests/stacks/<name>/`, snapshot tests for generators, standardized stack smoke-test contract.
3. **Mutation testing** — run mutmut to tighten test-suite assertions.
4. **Template improvements** — more constraint types, pagination options, bulk endpoints.
5. **Wizard enhancements** — interactive mode UX, model editing workflow.
6. **Documentation** — architecture diagrams, more examples, video walkthrough.

---

## Recently Completed Fixes

### §15.3 — database generator: per-entity loop (2026-04-26, `be47358`)

**Generator design landed:**
- `_layout(config)` helper reads `config.generation.layout` with `per-entity` default.
- `generate_database_model` and `generate_factories` return `dict | list[dict]`. Per-entity slices `model.entities` to one entity per render, derives filenames from `snake_case(EntityName)`, and threads `sibling_entities` (the full domain entity list) into the template render context.
- `generate_init` is layout-aware: per-entity appends one synthetic `domain` entry per current-model entity (file=stem, name=stem, section=None, entities=[Entity]); per-domain keeps the legacy single-domain entry.

**Template changes (`factory.py.j2`):**
- Replaced the single `from {db_models}.{model.domain} import (...)` block with a layout-aware version: per-entity emits `from {db_models}.{entity_snake} import {Entity}` per entity. Followed by a per-entity-only block emitting `from .{ref_snake} import {Ref}Factory` for every entry in `ns.entity_refs`.
- Extended `ns.entity_refs` collection to also include `one_to_many` relationship targets that are in `sibling_entities` (the gap not anticipated in the original §15.3 design). Without this, the User factory in user-auth would NameError at import time on `UserSessionFactory` / `ApiKeyFactory` / `UserRoleFactory` since those are referenced in `create_related` blocks but only registered in `ns.entity_refs` from `reference` field types.
- Swapped `rel.target in model.entities` for `rel.target in sibling_entities` at the create_related filter — preserves "is this rel target in our domain scope?" semantic in both modes (in per-entity mode `model.entities` is sliced to 1 entry and would silently drop sibling create_related blocks).

**Template change (`model.py.j2`):**
- Gated the full-width `section_divider` call on `config.generation.layout != 'per-entity'`. Per-entity files don't each emit a redundant `# BLOG MODELS` banner.

**Test fixture changes:**
- `project_env` (test_generators.py): pinned `generation.layout: per-domain` so the existing 98 assertions about `items.py`-shape paths stay precise.
- `test_integration.py::project_setup`: same pin (test verifies custom paths, not layout).
- `test_edge_cases.py::TestPartialGeneration::test_database_only`: same pin (test verifies partial generation, not layout).
- `test_full_generation.py`: updated assertions from `users.py` to `user.py` since the test copies the example config which intentionally adopts the new per-entity default. The class assertion `class User(Base):` and content checks are unchanged.

**New test classes:**
- `TestDatabaseGeneratorPerEntity` — list return shape, snake_case paths, single-entity content per file, section_divider banner absent.
- `TestGenerateInitPerEntity` — patched `scan_model_files` baseline, asserts `from .author import` / `from .post import` appear, existing per-entity files don't get redeclared.
- `TestFactoryGeneratorPerEntity` — list return shape, per-entity model imports (`from src.database.models.author import Author`), cross-entity SubFactory imports (`from .author import AuthorFactory` in `post.py`), and **create_related preserved via sibling_entities** (`from .post import PostFactory` + `PostFactory.create_batch(count, author=obj)` in `author.py`).
- `multi_entity_model` fixture (Author + Post with both a `reference` field and a `one_to_many` sibling rel) drives all three classes.

**Verification:** 333 passing (was 323; +10 new), `make lint` clean, working tree clean.

### §15.4 — api-models generator: per-entity loop (2026-04-26, `32641ac`)

**Generator design landed (two-file path chosen over combined-template path):**
- `_layout(config)` helper duplicated locally in `generators/api.py` (3 lines, mirror of `database.py:14-16`). DRY trade accepted to keep §15.4's blast radius contained to one module.
- `generate_api_models` returns `list[dict] | None` in both modes. Per-entity slices `model.entities` to one entity per render and emits two files per entity (`{snake_case(EntityName)}_response.py` + `{snake_case(EntityName)}_requests.py`); per-domain still emits one combined response + one combined request file.
- `generate_api_init` is layout-aware: per-entity appends one synthetic domain entry per current-model entity (`name=stem`, `section=None`, `response_models=[EntityResponse]`, `request_models=[Create/UpdateEntityRequest]`); per-domain keeps the legacy single-domain entry. Mutability check still drops `Update*Request` for `mutability: immutable` entities.

**No template changes.** `request.py.j2` and `response.py.j2` already iterate `for name, entity in model.entities.items()` — feeding sliced inputs Just Works. The existing `scan_api_model_files` (`utils/parser.py:69-129`) already groups by stripping `_response` / `_requests` suffixes, so it handles per-entity files transparently.

**New test classes:**
- `TestApiModelsGeneratorPerEntity` (3 tests) — four-file return shape (one Response + one Requests per entity), snake_case paths (`author_response.py`, etc.), content isolation (`author_response.py` contains `AuthorResponse` and not `PostResponse`).
- `TestGenerateApiInitPerEntity` (2 tests) — patched `scan_api_model_files` baseline, asserts `from .author_response import` / `from .post_response import` appear; existing per-entity files don't get redeclared (dedup case).

**Verification:** 338 passing (was 333; +5 new), `make lint` clean, working tree clean.

### §15.1 + §15.2 — Per-entity layout plumbing (2026-04-25)

Already on branch as `72c9ab4` and `8a7d481`. See commits in the branch list above.

### §9 — Owner-scoped endpoints (2026-04-25, merged)

Merged to `main` as **`62a700c`** (squash of 2 commits on `feat/9-owner-scoping`).

Per-entity `api.scope: {owner_field, inject_from, miss_status}` gates CRUD on a per-row owner check. Adopter sets `auth.dependency_path` in `.model-generator.yaml`; the generator threads that callable through FastAPI `Depends()`. Scoped behavior: `list` filters by `owner_field == current_user.id`; `get`/`update`/`delete` reject cross-owner access (404 default, configurable); `create` injects current user and force-assigns `owner_field`; `owner_field` is excluded from `Create`/`Update` request schemas. `generate.py` validates the spec/config pair eagerly: `api.scope` without dotted `auth.dependency_path` exits with a remediation message.

Schema fix bundled in: PR #8 omitted `binary` from the `type` enum, so `model-val` rejected specs using the binary type. Added.

### §13 — Encrypted-at-rest binary fields (2026-04-24, PR #9)

Merged to `main` as **`da30d84`**. `{"type": "binary", "encrypt": {"key_env": "FERNET_KEY_FILE"}}` → SQLAlchemy `TypeDecorator` wrapping `fernet.encrypt` / `fernet.decrypt`. App code reads/writes raw `bytes`; codec is invisible. `templates/infrastructure/encrypted_bytes.py.j2` emits the `TypeDecorator`; `model.py.j2` emits the decorated column when the field declares `encrypt`.

### §8 — Binary field type (2026-04-24, PR #8)

Merged to `main` as **`cc1cb42`**. `{"type": "binary"}` → SQLAlchemy `LargeBinary`, Pydantic `bytes` (auto base64 in JSON), factory `secrets.token_bytes(...)`. Round-trips on SQLite BLOB and Postgres BYTEA. Prerequisite for §13.

### §14 — Quality tool defaults (2026-04-23, PR #7)

Merged to `main` as **`e3a390f`**. Generator now emits only non-default ruff/mypy config so adopters pick up tool defaults automatically; project-level style overrides win over stack-level. Established the principle (now in memory: `feedback_generator_tool_defaults.md`) that absence in emitted config means "use tool default".

### External Review Follow-Up — 9 items shipped (2026-04-19)

Merged to `main` as **`2bf39c6`** (squash of 9 commits on `fix/review-followup-2026-04-19`). User-approved scope: 7 blockers + §10 + §11, keep warn-only validation.

| Touched file                                | Summary                                                                                                                             | Review items |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| `templates/database/model.py.j2`            | self-ref `remote_side=[pk1, pk2, ...]` (all PK fields, not just first); `default=lambda: <spec-value>` for `json_object` / `json_array` when spec declares a default; `Mapped[dict[str, Any]]` / `Mapped[list[Any]]` + `typing.Any` import gated on `ns.has_json`. | §1, §10, §11 |
| `templates/database/factory.py.j2`          | `create_batch(count, {{ rel.back_populates }}=obj)` replaces the broken `entity_name.lower()=obj`.                                   | §5           |
| `templates/api/route.py.j2` + `_shared/_tests.j2` | 5 CRUD blocks gated on `entity.api.endpoints`; `_shared/_tests.j2` `get_enum_value` macro uppercases `field_default`.          | §6, §7       |
| `utils/templates.py` + `generators/infrastructure.py` + `generate.py` + `wizard/actions/generate.py` | `python_root` threaded into `path_to_import` via a closure in `get_template_env`; call sites use `path_to_import(dir, "module", python_root=...)` to avoid empty-base relative imports. | §3           |
| `generators/migrations.py`                  | Skip `alembic.ini` write when it already exists (mirrors pyproject / gitignore protection).                                          | §4 residual  |
| `utils/loaders.py` + `docs/agent/json-specification-reference.md` | `_normalize_indexes` converts 4 legacy index shapes before validation; reference docs rewritten to canonical form + back-compat note. | §2           |

**Verified:** `uv run pytest -q` (290 passing, up from 283), `ruff check src tests` clean, `mypy src` clean, live `configure_mappers()` on single-PK + composite-PK self-ref probes, and a `python_root: "src"` adopter-shaped probe producing `from main import app` / `from database.engine import get_session`.

**Gemini-code-assist review addressed inline (a463a52 → folded into merge):**
- JSON field `default` values now honored via `default=lambda: <value>` lambda wrappers (was emitting `default=dict` / `default=list` ignoring spec value).
- Composite-PK self-ref now emits all PK columns in `remote_side` (was emitting only `pk_fields[0]`).

### Skills subtree re-imported (2026-04-19)

Merged to `main` as **`8a34eb3`** (squash of 3 commits on `chore/skills-subtree`). `.claude/skills/` is now a `git subtree` of `https://github.com/nuncaeslupus/my-skills` branch `main`. To pull future upstream skill updates:

```bash
git remote add shared-skills https://github.com/nuncaeslupus/my-skills.git  # one-time
git subtree pull --prefix=.claude/skills shared-skills main --squash
```

Net content diff vs prior: `.claude/skills/mutmut-report/analyze_mutmut.py` now `sys.exit(1)` on `run_cmd` / `find_mutmut` failure. (Gemini-bot correctly flagged that terminating the whole script on one failed mutmut-show is too aggressive — **fix belongs upstream** in `nuncaeslupus/my-skills`, not in this repo.)

### Earlier fixes (historical)

- **gen-clean cleanup gap** — `--clear-only` now covers all infrastructure files, `__init__.py`, `__pycache__` directories, and explicit paths from the stack config.
- **timestamp_after normalization** — accepted as both a direct field property and a `field_constraint` entry; normalized at load time.
