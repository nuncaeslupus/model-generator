# Next Session Plan

## Current State (2026-05-17, on `main`)

`main` is at **`3bafed5`** (PR #19: addendum NEW SHARP EDGE #1 — factory self-import). The consumer-gaps arc closed §3 + §4 via PR #18 (squashed as `4224a56`, 2026-05-13) and the first addendum NEW finding via PR #19 (squashed as `3bafed5`, 2026-05-17 — addressed Gemini's NameError review on the initial commit with a follow-up using `factory.SubFactory("EntityFactory")` string-literal form). 433 model-generator tests pass.

**Active arc next session:** two remaining follow-up PRs from the multi-agent-researcher consumer addendum (lines 176-281 of `status/gaps-from-multi-agent-researcher-2026-05-13.md`, currently untracked-by-design). Both verified real against current source on 2026-05-13; PR A (factory self-import) shipped 2026-05-17.

---

## Active arc: 2 remaining addendum follow-up PRs

Ship in order B → C. Each is independent, small, low-risk. One PR per finding. (PR A shipped 2026-05-17 as PR #19, squashed to main as `3bafed5` — see "Recently Completed Fixes" below for what surfaced during review.)

### PR B — `feat(generate): warn when paths.base is outside paths.database_models`

`templates/database/model.py.j2:151` does `from .base import Base` (relative). The base module MUST live inside `paths.database_models`. Setting `paths.base: hub/database/base.py` (sibling of models/, naturally-feeling) generates working files but `ModuleNotFoundError: No module named 'hub.database.models.base'` at test-collection time. Example yaml already does this correctly (`paths.base: backend/src/database/models/base.py`); no validation or docs callout exists.

**Fix.** Add `_validate_paths_base()` in `generate.py` (sibling of `_validate_generation_config`). Checks `Path(paths.base).parent == Path(paths.database_models)`. Exit with remediation message on mismatch. Call site: after `_validate_generation_config(config)` in `generate()`. Add docs callout in `usage-guide.md` + `quick-reference.md`.

**Tests.** `test_validate_paths_base_inside_database_models_passes` + `test_validate_paths_base_outside_database_models_exits`. Verification: 434 passing.

### PR C — `fix(generator): make generate_main skip-if-exists (bootstrap-only parity)`

`infrastructure.py:228` (`generate_main`) is one of **four** infra generators that emit a single file without `if output_path.exists(): return None`; the others are `generate_validators` (96), `generate_utils` (109), and `generate_test_conftest_root` (450) — flagged by Gemini-bot review on PR #20 (2026-05-17). Most other infra generators skip (base.py, engine.py, types.py, database_init.py, errors.py, gitignore, pyproject.toml, auth_router, csrf, encrypted_bytes, rate_limit). Consumer aliased `paths.main: hub/main_generated.py` to avoid clobber, which propagated into test imports (`contract.py.j2:1701/1717` correctly derives `from {paths.main} import app` at generation time — the bug is upstream of that).

**Scope decision (next session).** Three viable options:

- **C-narrow:** Only `generate_main`. Matches the original consumer-addendum finding; smallest blast radius.
- **C-medium:** `generate_main` + `generate_test_conftest_root`. Both are adopter-customized files (main wires routers; conftest holds fixture overrides). Higher value, still surgical.
- **C-wide:** All four. `generate_validators` + `generate_utils` are project-agnostic templates today (zero render args), so the clobber risk is theoretical — but adopters typically add domain-specific validators / utilities once a project matures. Closes the parity gap cleanly.

**Fix (per generator chosen).** Add `if output_path.exists(): return None` after computing `output_path`. Update `test_infrastructure_skips_existing` to add the relevant filenames to the `skipped_infra` set. Add per-generator `test_generate_X_skips_existing` tests (parity with `test_generate_base_skips_existing`).

**Trade-off (call out in commit msg).** New domains/routes added later won't auto-wire — adopters edit `main.py` (and conftest if covered) manually. Matches the contract of every other "skip-if-exists" file and the project's "one-shot generation, then evolve manually" principle (CLAUDE.md).

**Verification.** Pytest count depends on chosen scope (C-narrow: 435, C-medium: 437, C-wide: 441 — one skip-if-exists test per generator covered, plus the `skipped_infra` set assertion in the shared test). Manual probe: generate, edit the target file, regenerate → edit preserved. Example: delete example's `main.py`, regenerate, `APP_PASSWORD_PEPPER=test_pepper uv run pytest -q` → 130/130.

### Branch + PR strategy

- Branch off the post-#19 `main` (currently `3bafed5`).
- Two feature branches: `feat/validate-paths-base`, `fix/generate-main-skip-if-exists`.
- One PR per branch. Squash-merge on approval.

### After both merge

Re-queue mutmut + test-suite refactor as the active arc (deferred since 2026-05-11; details under "Other Possible Next Steps" below).

---

## Other Possible Next Steps

1. **Mutation testing** *(queued — re-active after addendum PRs)* — run mutmut to surface untested generator behaviors, tighten test assertions.
2. **Test suite refactor** *(queued — scope informed by #1)* — split into `tests/core/` + `tests/stacks/<name>/`, snapshot tests for generators, standardized stack smoke-test contract.
3. **New stacks** — templates beyond python-fastapi (python-django, node-express).
4. **Template improvements** — more constraint types, pagination options, bulk endpoints.
5. **Wizard enhancements** — interactive mode UX, model editing workflow.
6. **Documentation** — architecture diagrams, more examples, video walkthrough.

---

## Recently Completed Fixes

### Addendum NEW SHARP EDGE #1 — factory self-import (2026-05-17, PR #19)

Merged to `main` as **`3bafed5`** (squash of 2 commits on `fix/factory-self-import`). Closes the first of three NEW findings from the multi-agent-researcher consumer integration addendum.

- **`fc32e9b` — `fix(factory): skip self-loop in entity_refs collection`.** `templates/database/factory.py.j2` now filters self-loops in both `ns.entity_refs` collection paths (line 55 reference-field path, line 62 one_to_many sibling-rel path). The per-entity import block at lines 99-103 no longer emits `from .{entity_snake} import {Entity}Factory` for self-referential entities — that self-import is what ruff catches as F811 and mypy strict rejects.
- **`59460f2` — `fix(factory): emit SubFactory string literal for self-ref fields`.** Folded in after Gemini's review on the first commit flagged a real `NameError` regression: removing the self-import (correctly) left a class-body bare reference `factory.SubFactory(EntityFactory)` that raises at module-load time, because the class isn't bound in the module namespace until the `class` statement completes. The pre-fix self-import had been incidentally pre-binding the name. Fix: emit `factory.SubFactory("EntityFactory")` (string form) for self-ref reference fields — factoryboy resolves the name lazily at `.create()` time. Cross-entity refs keep the bare-class form (sibling-factory imports already bind those names). `create_related` is unaffected — its `EntityFactory.create_batch(...)` references live inside an `@factory.post_generation` method body, executed at call time.

**New tests (3) under `TestFactoryGeneratorSelfRef`.** A `self_ref_factory_model` fixture (Category with `parent_id` reference + `children` one_to_many self-loops, covers both filter paths) drives: (1) asserts no `from .category import` self-import line; (2) asserts `factory.SubFactory("CategoryFactory")` string form is present (and the bare form is absent); (3) `exec()`s the generated factory under stubbed `factory` / `faker` / SQLAlchemy modules — the regression test that catches class-body self-references regardless of which macro emits them. TDD red→green verified for the third test: stashing the template fix → NameError reproduced; popping → passes.

**Verified:** `make format` + `make lint` clean (ruff + mypy strict), 433 / 433 tests passing (was 430 pre-PR-A), Gemini follow-up review approved (`"the correct way to handle this in factory_boy"`).

### Consumer gaps §3 + §4 (2026-05-13, PR #18)

Merged to `main` as **`4224a56`** (squash of 2 commits on `feat/consumer-gaps-3-4`). Closes consumer integration findings §3 (`python_root` docs) + §4 (`--no-root-files` flag for scratch-dir workflow).

- **`0f4e65a` — `docs(python_root): document existing config option`.** The top-level `python_root` config key (sibling of `paths:`, `project:`, `stack:`) was fully implemented (`utils/templates.py:path_to_import` threaded through every import site) but undocumented anywhere visible. Adds a "Python Import Root" section to `usage-guide.md`, a row to `quick-reference.md`, a commented example in `examples/user-auth-project/.model-generator.yaml`, and one end-to-end integration test (`TestPythonRootIntegration.test_database_model_strips_python_root_from_types_import`) that guards against future regressions where a new import site forgets to thread `python_root` through the Jinja filter.
- **`e509088` — `feat(generate): --no-root-files flag for scratch-dir workflow`.** New CLI flag suppresses `pyproject.toml`, `alembic.ini`, and `.gitignore` emission at the project root, keeping in-tree alembic/ scaffolding (env.py, script.py.mako, README, versions/.gitkeep) intact. Threaded through `generate_gitignore`, `generate_pyproject`, `generate_infrastructure`, `generate_migration_init`, `generate()`, `_generate_target()`, and `main()` argparse. Wizard callsite unchanged (relies on the default `no_root_files=False`, matching the wizard's first-time-bootstrap intent). 5 new generator tests + 1 CLI flag-propagation test. Also backfilled the two missing skip-if-exists tests (`.gitignore`, `alembic.ini`) for parity with the pre-existing `pyproject.toml` skip-if-exists coverage.

Verified: `make lint` clean (ruff + mypy strict), 430 / 430 tests passing, §3 + §4 manual probes clean, example 130 / 130 with `APP_PASSWORD_PEPPER` set.

### Mypy strict + `py.typed` marker (2026-05-11, PR #16)


Merged to `main` as **`2f33207`** (squash of 2 commits on `feat/strict-typing`). Brings the CLI mypy in line with what the IDE was already showing and publishes the package as typed for downstream consumers (PEP 561).

- Switches `[tool.mypy]` to `strict = true`; drops `tests/` from exclude so the same rules apply to the suite. Adds `mypy_path = "src"` so the Makefile's `--explicit-package-bases` doesn't double-resolve modules under both `src.model_generator.X` and `model_generator.X`.
- Adds `src/model_generator/py.typed` (PEP 561) and registers it in package-data so the wheel ships it.
- Pins Pyright/Pylance to `typeCheckingMode = "standard"` via a new `[tool.pyright]` block. Strict would emit ~322 `reportUnknownXxxType` errors on `dict[str, Any]` JSON-spec code that mypy strict accepts; proper fix would require TypedDict for every spec shape (separate, larger refactor).
- Annotates ~135 bare `dict / list / set` generics across `src/` and `tests/`.
- Adds 107 `isinstance(result, dict | list)` asserts in `tests/test_generators.py` to narrow the `dict | list[dict] | None` Union that generators return based on the runtime layout config.
- Re-exports `load_model` explicitly via `as` so `no_implicit_reexport` (implied by strict) doesn't break test imports.

Gemini-bot review folded in as the second squashed commit (`refactor(typing): tighten generator helper types`): drops the `list[Any]` / `set[Any]` fallbacks the strict pass had introduced when callers already know the concrete shape (`_GeneratorFn` / `_generate_target` return `list[dict[str, Any]]`; `_extract_ref` / `_extract_regex_ref` `refs` / `seen` → `list[dict[str, Any]]` / `set[str]`).

**Verified:** `make lint` clean (ruff check + ruff format --check + mypy strict), 423 tests pass, `uv run pyright` 0 errors.

### Composite-FK `__table_args__` emission (2026-05-11, PR #15)

Merged to `main` as **`7a40831`** (squash of 4 commits on `feat/composite-fk-table-args`). Closes the only concrete known gap that `Future Work` had been tracking.

New entity-level `foreign_keys` array (mirrors `indexes` / `constraints`) lets a composite FK target a composite-PK table; generator emits a single `ForeignKeyConstraint(...)` inside `__table_args__`; member columns stay typed (`uuid` / `text` / …); a live `Base.registry.configure()` probe verifies no `AmbiguousForeignKeysError`. Eager validator rejects length mismatches, unknown field names, `reference`-typed members (mutex with composite FK), and unknown `references_table`.

**Latent gaps surfaced and closed on the same PR:**

- Non-PK plain `uuid` fields previously emitted nothing — `model.py.j2`'s `regular_fields` dispatch had no `uuid` case. Composite-FK members are the first legitimate non-PK plain-uuid use case; added the dispatch.
- The pre-existing `relationship.foreign_keys` schema property is a disambiguation hint for `relationship(...)`, **not** an FK constraint declaration. The new entity-level `foreign_keys` array is the actual schema-level constraint. Both are needed for composite FKs.

**Spec shape:**

```json
"OrderItem": {
  "fields": {
    "tenant_id": {"type": "uuid", "required": true},
    "order_id":  {"type": "uuid", "required": true}
  },
  "foreign_keys": [
    {
      "fields": ["tenant_id", "order_id"],
      "references_table": "orders",
      "references_columns": ["tenant_id", "id"],
      "on_delete": "CASCADE"
    }
  ],
  "relationships": {
    "order": {
      "type": "many_to_one", "target": "Order", "back_populates": "items",
      "foreign_keys": ["tenant_id", "order_id"]
    }
  }
}
```

**Out of scope (deferred):** wizard interactive-mode support for composite FKs (current wizard doesn't cover composite PKs either); cross-domain composite FKs (target entity in a different model file) — works mechanically since `references_table` is a SQL string, but validation rejects them for v1, relax in a follow-up; `ON UPDATE` action on composite FKs (symmetric gap with single-column FKs).

**Verified:** 423 unit tests (was 408; +15: 6 emission, 6 validator, 3 schema), example suite 130 / 130, lint clean.

### §13.1 — Encrypted-bytes emission gap (2026-05-10, PR #14)

Merged to `main` as **`5563731`** (squash of 3 commits on `fix/encrypted-bytes-emission-gap`). Closes the latent §13 `encrypted_bytes.py` emission gap that the §12 status doc had flagged: `generate_encrypted_bytes` mirrors the `generate_csrf` gating pattern, a project-wide `_has_encrypted_binary_field` scanner is threaded through both CLI and wizard orchestrators, and two pre-existing template bugs surface on emission (`{-#` → `{#-` comment opener; `config.paths.utils` → `config.paths.database_models` docstring path). Gemini-bot review folded in via `01af120` (collapsed `_has_encrypted_binary_field` into an `any()` expression). 11 new tests.

### §12 — Auth scaffolding (2026-05-10, PR #13)

Merged to `main` as **`baff572`** (squash of 7 commits on `feat/12-auth-scaffolding`). End-to-end auth opt-in: setting `auth.strategy: bcrypt-session` in `.model-generator.yaml` produces a session-cookie auth router (register / login / logout / forgot-password / reset-password), CSRF middleware (double-submit cookie with `SESSION_COOKIE_NAME`-gated check), per-endpoint rate limiting (slowapi, default-on at 5/min login + 3/hour register/forgot, configurable to redis backend), bcrypt password hashing with HMAC pepper, and an auto-wired `current_user` FastAPI dependency that flows through `api.scope` to enforce owner-scoped endpoints.

Gemini-bot review feedback addressed inline in `401fb3b` before merge — folded into the squash.

See §12.1–§12.6 entries below for per-step technical detail. The largest mid-epic landmark is §12.6 (example rewire + endpoint gates + rate-limit reset + bcrypt swap, surfaced once the example test suite first ran end-to-end with auth on).

### §12.6 — auto-wire + bcrypt swap + endpoint gates + rate-limit reset (2026-05-10)

Branch tip on `feat/12-auth-scaffolding`. Closes §12. Bundles four logically distinct pieces that surfaced once the example test suite was first run end-to-end with auth on:

**1. Drop `passlib`, use `bcrypt` directly.** passlib 1.7.4's internal wrap-bug-detection probe (75-byte password during `set_backend()`) raises against bcrypt 5.0.0's strict 72-byte cap. passlib's last release was 2020-10 — no fix coming. Native `bcrypt.hashpw / checkpw / gensalt` has identical semantics for HMAC-peppered input. Touches `auth_router.py.j2` (4 lines), `generate.py` (drop `passlib[bcrypt]>=1.7.4` from `auth_extra`), `tests/test_generators.py` (flip assertion to `import bcrypt` / `bcrypt.hashpw(`).

**2. Auto-wire + example rewiring** (carried from prior session's working tree). `loaders.py` moves auth.dependency_path inference into `load_config()` so per-model reload picks it up; `csrf.py.j2` skips the CSRF check when `SESSION_COOKIE_NAME not in request.cookies` (standard double-submit semantics — unauthenticated requests have nothing to forge); `conftest_generator.py` reroutes `user_id` / `user_id_alt` fixtures to POST `/api/v1/auth/register` when `config.auth.strategy` is set; example `users.model.json` drops `create` from `User.api.endpoints` (auth router owns user creation now); example `.model-generator.yaml` activates `auth.strategy: bcrypt-session` + `pepper_env: APP_PASSWORD_PEPPER`.

**3. Contract-test endpoint gating expansion.** `4987fa8` (§15) only gated UPDATE/DELETE/`_immutable_fields`. With User dropping `create`, the remaining sections still emitted POST seeding inside list/get/update/delete tests → 405 cascade. Now `contract.py.j2` gates Section 1 (READ list) on `'list' in endpoints`, Section 2 (CREATE) on `'create' in endpoints` (was already partial), Section 3 (INDIVIDUAL READ) on `'get' in endpoints`, Section 6 (FIELD VALIDATION) on `'create' in endpoints`. Plus, every test that internally seeds via POST is gated on `'create' in endpoints` independently of its section gate: `test_get_..._list_filtering`, `test_get_..._by_id_success`, `test_put_..._success`, `test_put_..._partial_update`, `test_delete_..._success`, `test_..._immutable_fields`. The `_not_found` variants stay (negative-path; no seeding).

**4. Rate-limit test isolation.** §12.5's slowapi limiter caps `/auth/register` at 3/hour. Every test using the `user_id` fixture goes through register → after 3 tests the entire suite cascades to 429. Fix: when `auth.strategy` is set and rate-limit is enabled, the api-conftest emits an autouse `_reset_rate_limiter()` fixture that calls `limiter.reset()` before each test. New `_compute_rate_limiter_import` helper in `generate.py` builds the import path via `path_to_import` (mirroring `infrastructure.py:244-250`'s pattern; small duplication accepted to keep blast radius narrow).

New tests: `TestApiTestsEndpointGates` (3 tests covering the create / list / get gates) and `TestConftestGeneratorRateLimitReset` (2 tests: no-emit when import is None, emits autouse fixture + import line when set). Total: 388 unit tests, 130 example tests, 0 fail / 0 error, lint clean.

### Upstream `analyze_mutmut.py` fix → subtree pull (2026-05-03)

Closes the loose end from §13's Gemini-bot review on PR #3. `run_cmd` now raises `subprocess.CalledProcessError` (caught in `main()` and translated to a clean `Error running ...: stderr` message + `sys.exit(1)`) instead of unconditionally exiting on subprocess failure. Lets future callers `try/except` to skip-and-continue per-mutant.

- Upstream PR: `nuncaeslupus/my-skills#1`, merged 2026-05-03 as `ebf2ba3`.
- Pulled into `.claude/skills/mutmut-report/analyze_mutmut.py` via `git subtree pull --prefix=.claude/skills shared-skills main --squash` on `chore/skills-pull-run-cmd-raise`.
- Net diff in `.claude/skills/`: 11 insertions, 2 deletions.

### §15 — One-file-per-entity layout (2026-05-01, PR #11)

Merged to `main` as **`28b787e`** (squash of 13 commits on `feat/15-per-entity-layout`). Adds `generation.layout: per-entity` (default) | `per-domain` (legacy). Splits database, factory, api-models, api-routes, and api-tests emission into one file per entity. New `snake_case` filter drives entity-derived filenames. `factory.py.j2` rewires imports per-layout: per-entity emits `from {db_models}.{entity_snake} import {Entity}` plus cross-factory `SubFactory` imports for both `reference` fields and `one_to_many` siblings. `model.py.j2` suppresses the per-domain banner under per-entity. `__init__.py` emission appends one synthetic domain entry per current-model entity in per-entity mode.

Trailing fixes folded into the same epic:
- `4987fa8` — Contract test sections (UPDATE / DELETE / `_immutable_fields`) now gated by `entity.api.endpoints` membership. Pre-existing bug surfaced by §15.6 regen; 6 user-auth tests that 405'd against missing routes are no longer emitted (149 → 143 example tests).
- `e8e13f9` — Centralized `_layout(config)` helper (was duplicated across `database.py` / `api.py` / `infrastructure.py`); gated `factory_modules` collection by `has_api`.

**Verification at merge:** 348 model-generator tests, 143 / 143 example tests, `make lint` clean.

See §15.3 and §15.4 sections below for per-step technical detail (the largest mid-epic checkpoints).

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
