# Next Session Plan

## Current State (2026-06-03, on `claude/wizardly-goodall-ftNAF`)

Filter-test coverage merged to `main` as **`eec462f`** (#24). On top of it, a follow-up branch applies a consumer factory/seeding patch (financial+counter constraint fix, factory-seeded read-only get-by-id test, layout-aware factory import) plus the PR #25 Gemini-review responses (min_ref/max_ref resolved at generation time, safe config access) — see "Recently Completed Fixes". 457 model-generator tests pass; example suite 131/131 on Python 3.12.

**Active arc next session:** mutmut + test-suite refactor (re-queued, see "Other Possible Next Steps" below).

---

## Active arc: re-queue mutmut + test-suite refactor

The consumer-addendum arc is closed. Next session picks up the two long-deferred items (since 2026-05-11): mutation testing (#1) then the test-suite refactor (#2), both detailed under "Other Possible Next Steps".

---

## Other Possible Next Steps

1. **Mutation testing** *(queued — re-active after PR C)* — run mutmut to surface untested generator behaviors, tighten test assertions.
2. **Test suite refactor** *(queued — scope informed by #1)* — split into `tests/core/` + `tests/stacks/<name>/`, snapshot tests for generators, standardized stack smoke-test contract.
3. **New stacks** — templates beyond python-fastapi (python-django, node-express).
4. **Template improvements** — more constraint types, pagination options, bulk endpoints.
5. **Wizard enhancements** — interactive mode UX, model editing workflow.
6. **Documentation** — architecture diagrams, more examples, video walkthrough.

---

## Recently Completed Fixes

### Generated CRUD hardening — P1–P4 from downstream audit (2026-06-11)

Branch `claude/gallant-heisenberg-86x7iq`. Four security follow-ups from a
`trading.kit` audit (services `oms`, `ml-engine`), all fixed in TEMPLATES so
adopters regenerate rather than hand-patch. No wire contract changed (field
names / enums / happy-path status codes identical); behavior changes are
malformed-input / error-path only. New `app:` config section in the stack
`config.yaml`.

- **P1 — `route.py.j2` typed list filters.** Numeric/date filter params were
  `str | None` then coerced unguarded in the handler (`Decimal(...)` /
  `datetime.fromisoformat(...)`), so `?<field>_min=abc` / `?<field>_after=notadate`
  raised an unhandled 500. Now emitted as `Decimal | None` / `datetime | None`
  so FastAPI validates at the boundary → 422; the manual coercion is dropped.
  Counter filters were already `int | None` (unchanged). `Decimal`/`datetime`
  imports remain (now used in the signatures, not the body).
- **P2 — `errors.py.j2` generic 409.** `format_integrity_error` no longer
  echoes the parsed DB column name by default ("…with these values already
  exists"). Opt back in via `app.expose_integrity_error_fields: true` (threaded
  through `generate_errors`). Structured shape unchanged.
- **P3 — request-body size limit.** New `infrastructure/request_limit.py.j2`
  (pure-ASGI `RequestBodySizeLimitMiddleware`: Content-Length fast-path +
  buffer-and-replay for chunked bodies, 413 on overflow) + `generate_request_limit`
  (bootstrap-only, gated on `app.max_request_body_bytes > 0`, default 10 MiB).
  Wired into `generate_infrastructure`; `main.py.j2` installs it innermost so
  CORS stays outermost. Disabled (0) → not emitted, not wired.
- **P4 — `errors.py.j2` trimmed validation errors.** New
  `validation_exception_handler` summarizes `exc.errors()` to a `field` +
  `message` list (drops submitted values + internal locators); registered in
  `main.py.j2` via `app.add_exception_handler(RequestValidationError, …)`. Uses
  a literal `422` to dodge the Starlette `HTTP_422_UNPROCESSABLE_ENTITY` →
  `_CONTENT` rename DeprecationWarning.

**Tests (+15 → 476).** `TestApiRoutesFilterCoercion` (5); errors P2/P4 (3) +
main P3/P4 (4) in `TestInfrastructureGenerators`; `TestRequestLimitGenerator`
(3); `test_generate_infrastructure_creates_all` / `test_infrastructure_skips_existing`
updated for `request_limit.py`. RED→GREEN verified (8 fail with the three
templates reverted, all pass restored).

**Verified:** `make lint` clean (ruff + mypy strict), 476/476 unit tests.
Example regenerated end-to-end **from inside the example dir** (so the project
`.model-generator.yaml` auth config is picked up — `load_config` reads
`.model-generator.yaml` from CWD, so a repo-root invocation silently drops the
project config) → 131/131 on Python 3.12 (`APP_PASSWORD_PEPPER=test_pepper`).
Generated tree is ruff-clean after the standard `--fix` (only the pre-existing
pagination PEP695-vs-3.11-target quirk remains); my generated files add zero
new mypy errors vs a stashed-changes baseline. Live TestClient probe confirms
the repros: `?balance_min=abc` → 422 (input value not echoed),
`?last_login_at_after=notadate` → 422, valid filters → 200, 11 MiB body → 413,
small invalid body → 422.

### CORS scaffold hardening — drop wildcard+credentials default (2026-06-10)

Branch `claude/funny-brahmagupta-dpjh6j`. Out-of-band security fix from a downstream review (Finding F2): the generated `main.py` shipped the textbook CORS hole — `allow_origins=os.getenv("CORS_ORIGINS", "*")` paired with `allow_credentials=True`. With a wildcard + credentials, Starlette reflects the caller's `Origin` and returns `Access-Control-Allow-Credentials: true`. Two downstream projects (oms, ml-engine) carried the byte-identical generated block.

- **`templates/infrastructure/main.py.j2`.** CORS default is now a concrete localhost dev origin (`http://localhost:3000`), never `*`. `CORS_ORIGINS` is parsed into a stripped, non-empty list. `allow_credentials` is computed as `"*" not in cors_origins` — credentials switch **off** automatically if any deployment sets a wildcard, so the dangerous pairing can't recur. `allow_methods` narrowed from `["*"]` to the CRUD verbs the generated routes use (`GET/POST/PUT/DELETE/OPTIONS`); `allow_headers` narrowed from `["*"]` to `Content-Type` plus `X-CSRF-Token` (the latter emitted only when `csrf_module_import` is set, i.e. auth/CSRF is wired). A comment explains the credentials gating so adopters don't "simplify" it back to `True`.

**Tests:** 4 new in `TestInfrastructureGenerators` — no wildcard default + credentials decoupled; methods/headers narrowed; `X-CSRF-Token` present iff auth/CSRF is wired (per-entity auth config) and absent otherwise. 457 → 461.

**Verified:** `make lint` clean (ruff + mypy strict), 461/461 unit tests, generated `main.py` `ast.parse`s and ruff-checks clean (only the pre-existing I001 import-sort quirk). Example regenerated end-to-end with auth on → 131/131 on Python 3.12 (`APP_PASSWORD_PEPPER=test_pepper`); confirmed in generated output: `allow_credentials="*" not in cors_origins`, `allow_headers` carries `X-CSRF-Token`, CSRF still added before CORS.

### Factory constraint fix + factory-seeded read-only get-by-id (2026-06-03)

Branch `claude/wizardly-goodall-ftNAF`, off `main` at `eec462f` (post-PR #24). Consumer patch (factory + seeding) plus one correctness fix I added on top.

- **`factory.py.j2` financial/counter constraints.** The old `min_ref`/`max_ref` handling set loop-local `min_val`/`max_val` inside a `{% for constraint %}` loop — a Jinja scoping bug: `{% set %}` inside a `for` does not persist outside it, so the values silently stayed at the `0`/`999999` defaults (dead code). Rewritten with `namespace(min=…, max=…)` (the standard Jinja workaround), and extended to honor `type: positive` (min→1), inline `type: range` `min`/`max`, plus the existing `min_ref`/`max_ref`. The financial faker call drops `left_digits=12` + `positive=True` when min/max are set (faker rejects `left_digits` combined with `min_value`/`max_value`); the no-constraints branch keeps `left_digits`.
- **`contract.py.j2` + `conftest_root.py.j2` read-only get-by-id.** Read-only entities (no `create`) previously had no `test_get_X_by_id_success` — there was no endpoint to seed a row. Now, when an entity has `get` but no `create`, no required FK, and no `one_to_many` (factory cascade would pull in child rows with their own FKs), the test seeds a row directly via `{Entity}Factory.create()` (the writer path) and reads it back. `conftest_root.py.j2` binds every factory to a sync `seed_session` on the same SQLite file the async app reads (`sqlalchemy_session_persistence = "commit"` makes the row visible across connections).
- **Layout-aware factory import (added on top of the patch).** The patch hardcoded `from {factories}.{model.domain} import {Entity}Factory`, which only works in **per-domain** layout. The default is **per-entity**, where factories live at `{factories}/{entity_snake}.py`. Fixed to derive the module from `snake_case(entity_name)` in per-entity layout, `model.domain` in per-domain. Without this, a per-entity read-only entity matching the guard would emit a broken import (ModuleNotFoundError at collection).

**Gemini review responses (PR #25).**
- **min_ref/max_ref NameError (high) — fixed by resolving at generation time (user-chosen).** The revived `min_ref`/`max_ref` handling emitted the bare constant name (`min_value=PRICE_MAX`), which would `NameError` at `create()` (the factory never imports the constraints module). `generate_factories` now loads the flattened shared-constraint dict (`load_shared_constraints`, threaded via a new `model_path`/`constraints` param + the `factories` dispatcher passing `mp`) and the template resolves `constraints[ref].value` to a literal; unresolved refs fall back to default bounds. Verified end-to-end: a probe with `range` `min_ref`/`max_ref` on financial+counter fields emits `min_value=10.00, max_value=5000.00` / `max_value=100`, compiles, zero bare names.
- **Safe config access (medium) — applied.** Read-only factory import switched from `config.generation.layout | default(...)` to `config.get('generation', {}).get('layout', 'per-entity')`. The `| default` form does **not** protect a missing `generation` key — the `UndefinedError` fires during attribute access, before the filter (confirmed: `factory.py.j2:88` raises the same way on a bare config).
- **pkgutil factory discovery (high) — declined (incorrect premise).** Gemini assumed `_get_factory_classes()` imports `{domain}` and so breaks in per-entity layout. But the conftest's `domains` var is `factory_modules` in per-entity mode (`infrastructure.py:520`), i.e. the entity snakes — so it already imports `factories/{entity_snake}.py`. Proven by the per-entity probe (imported `country`, get-by-id passed). Replied on the PR.

**Folded in: `_shared/_tests.j2` counter range refs.** A counter `range` constraint using `min_ref`/`max_ref` (no inline `min`/`max`) tripped `constraint.min | int` on an Undefined → generation crash (pre-existing; no example/pre-PR input exercised counter-range-with-refs). The counter branch now resolves inline-or-ref bounds via a namespace, computes the midpoint from whichever bounds are present (`(min+max)//2`, else `min`, else `max//2`, else `10`), and falls back cleanly when refs are unresolved. The financial/percentage builders already resolved `max_ref` and never touched `min`, so they didn't crash — left as-is. Added `TestApiTestsCounterRangeRefs` (2 tests: refs→midpoint 50; unresolved→fallback 10).

**Folded in: `model.py.j2` one-sided range CHECK.** A `range` / `range_or_null` constraint with only one bound (e.g. `max_ref` and no min) emitted a broken `CheckConstraint(f"x >= {} AND x <= {MAX}")` (empty `{}` → `SyntaxError` at import). Both branches now emit a one-sided CHECK when only one bound is defined (`x >= {MIN}` or `x <= {MAX}`, plus the `OR x IS NULL` tail for `range_or_null`); two-bound ranges are unchanged. Added `TestDatabaseGeneratorRangeCheck` (4 tests: both bounds, max-only, min-only, range_or_null max-only — each asserts no empty `{}`).

**Tests:** patch updated `test_skips_create_tests_when_create_endpoint_excluded` (get-by-id now emitted, factory-seeded, still no `client.post(`). Added `test_read_only_factory_import_is_layout_aware` (per-entity import targets `factories.country`, not `factories.geo`), `test_ref_constraints_resolve_to_literals`, `test_ref_constraints_fall_back_when_unresolved`, and `TestApiTestsCounterRangeRefs` (2). 448 → 457.

**Verified:** `make lint` clean (ruff + mypy strict), 457/457 unit tests. Example regenerated end-to-end → 131/131 (financial/counter fields exercise the factory branch); generated-project ruff identical to the no-patch baseline (4 pre-existing quirks: alembic E402, pagination PEP695 under ruff's 3.11 target, 2× main/auth I001 — patch adds zero new). Built a throwaway per-entity project with a read-only `Country` entity (list+get, unique text, `counter` `positive`) → import resolves to `factories.country`, `population` factory emits `min_value=1`, `test_get_country_by_id_success` **passes** end-to-end on Python 3.12 (validates seeding + commit visibility).

### Filter-test coverage for reference + unique-text fields (2026-06-03)

Branch `claude/wizardly-goodall-ftNAF`, off `main` at `eeff908` (post-PR #23). Follow-up to the consumer read-only filtering fix: `route.py.j2` generates exact-match filter params for `reference` and unique-`text` fields, but **neither** contract-test branch asserted them (both only handled enum/boolean/datetime/financial/percentage/counter). Closed the gap in both branches.

- **`contract.py.j2` create-mode branch.** Added `reference` and unique-`text` cases that assert the **created** row's value filters correctly (`all(item[field] == val for item in items)`), mirroring the enum/boolean pattern. Both are gated `(field.required or (field.default is defined and field.default is not none))` — a nullable reference's created value can be `None`, which would render `?field=None` and 500 on the UUID column (caught during the example probe: `UserRole.granted_by`). The `is not none` half closes a Gemini-flagged edge: `field.default is defined` is **true** for an explicit `default: null`, so the looser guard would still emit a broken filter. The `ns_needs_created` flag uses the **same** guard so `created_X` is emitted iff at least one case consumes it (otherwise ruff F841 in the generated project) — the enum/boolean emission guards were tightened to the same form to keep all five in sync.
- **`contract.py.j2` read-only branch.** Added `reference` (literal `00000000-…-0` UUID) and unique-`text` (literal `test_value`) cases asserting HTTP 200 acceptance. No created value needed, so no required-guard — covers nullable references too.

**Tests:** new `TestApiTestsReferenceTextFiltering` (3): create-mode required-reference uses created value; read-only reference+text use data-free literals (no `created_gadget`); nullable reference (with explicit `default: None`) is skipped in create-mode. 445 → 448.

**Verified:** `make lint` clean (ruff + mypy strict), 448/448 unit tests. Example regenerated end-to-end → 131/131 (Python 3.12, `APP_PASSWORD_PEPPER=test_pepper`); generated test suite `ruff check` clean (no unused `created_X`). Confirmed in generated output: `UserSession.user_id` (required ref) gets a created-value assertion, `User` (read-only) gets `?username=` / `?email=` text-filter assertions, `UserRole.granted_by` (nullable ref) is correctly absent.

### Consumer template fixes — alembic URL, unique-index fixtures, read-only filtering (2026-06-03)

Branch `claude/wizardly-goodall-ftNAF`, off `main` at `786293d` (post-PR #22). Three template/generator fixes surfaced by a downstream project that consumes MG, delivered as one patch:

- **`migrations/env.py.j2` — `ALEMBIC_DATABASE_URL` priority.** `get_url()` now checks `ALEMBIC_DATABASE_URL` first, then `DATABASE_URL`, then `alembic.ini`. Lets adopters point migrations at a sync driver while the app runs an async one (the common asyncpg/psycopg split). Error message updated to list all three sources.
- **`utils/conftest_generator.py` — unique-index/constraint detection.** New `_field_in_unique_index()` helper: text fields participating in a unique index or unique constraint (including composite ones, e.g. `(model_name, version)`) now get a per-test `unique_suffix` in the shared session-scoped fixtures, instead of a constant. Without this, repeated inserts collided with HTTP 409. `extract_entities()` now carries `indexes`/`constraints` metadata so the helper can see them. Wired into both `generate_minimal_create_data` and `needs_unique_suffix`.
- **`tests/contract.py.j2` — read-only filtering test.** Entities with filterable fields and a `list` endpoint but no `create` (e.g. `User`, whose creation is owned by the auth router) now get a data-free `test_get_X_list_filtering` that asserts each filter parameter is accepted (HTTP 200) for a valid literal value, rather than POSTing seed data. Covers enum/boolean/datetime/financial/percentage/counter filters.

**Verified:** `make lint` clean (ruff + mypy strict), 445/445 unit tests (test_generators.py assertion updated: read-only filtering is now emitted in data-free form). Example regenerated end-to-end → 131/131 (was 130; +1 = the new `User` read-only filtering test, which now exercises `status` / `last_login_at` / `email_verified` filters that previously had no coverage), Python 3.12, `APP_PASSWORD_PEPPER=test_pepper`.

### PR C — skip-if-exists parity for all single-file infra generators (2026-06-02)

Branch `claude/wizardly-goodall-ftNAF`, off `main` at `f2f3cbc`. Closes the last consumer-addendum follow-up. **Scope: C-wide** (all four generators).

Four single-file infra generators emitted unconditionally, clobbering adopter edits on every regeneration: `generate_main`, `generate_test_conftest_root`, `generate_validators`, `generate_utils`. Each now does `if output_path.exists(): return None` after computing `output_path` — matching the contract of every other bootstrap-only infra file (base, engine, types, errors, auth_router, csrf, …) and the project's "generate once, then evolve manually" principle.

**Trade-off:** new domains/routes/factories added later no longer auto-wire into `main.py` / `conftest.py` — adopters edit those (and add domain validators/utilities) manually. This is the intended bootstrap-only contract.

**Tests:** `test_infrastructure_skips_existing` `skipped_infra` set expanded to include `main.py`, `conftest.py`, `validators.py`, `utils.py`. Added 5 tests: `test_generate_validators_skips_existing`, `test_generate_utils` + `test_generate_utils_skips_existing` (utils had no standalone test), `test_generate_main_skips_existing`, `test_generate_test_conftest_root_skips_existing`. 440 → 445.

**Verified:** `make lint` clean (ruff + mypy strict), 445/445 unit tests. Manual probe: generate example → append custom middleware to `main.py` → regenerate → edit preserved. Example suite 130/130 (`APP_PASSWORD_PEPPER=test_pepper`, Python 3.12).

### Addendum NEW SHARP EDGE #2 — paths.base validator + loader derivation (2026-05-17, PR #21)

Branch tip on `feat/validate-paths-base` (2 commits, squash on merge). Closes the second of three NEW findings from the multi-agent-researcher consumer integration addendum. PR B in the active arc.

- **First commit — `feat(generate): validate paths.base sibling of paths.database_models`.** New `_validate_paths_base()` helper in `generate.py` (sibling of `_validate_generation_config`), wired into `generate()` after `_validate_generation_config(config)`. Generated database model files emit `from .base import Base` (relative), so the base module MUST live inside `paths.database_models`. A mismatch generates successfully but raises `ModuleNotFoundError` at import / test-collection time — silent at generation, loud at runtime. Validator catches it eagerly with a remediation message echoing both paths and the fix shape. Three initial tests under `TestValidatePathsBase`: default-passes, sibling-passes, outside-exits. `tests/test_integration.py::project_setup` had been relying on the silent broken behavior (custom `paths.database_models: lib/db/models` + default `paths.base: backend/src/database/models/base.py`); fixture corrected.
- **Second commit — `refactor: address Gemini-bot review feedback on PR #21`.** Three changes from gemini-code-assist's review:
  1. **Default `paths.base` now derives from `paths.database_models`.** Done at the loader (`utils/loaders.py:load_config`) rather than at each reader, so the merged config is internally consistent — the stack `config.yaml`'s `base: backend/src/database/models/base.py` no longer wins on deep-merge when the project only overrides `paths.database_models`. Lets adopters customize `database_models` without having to also restate `paths.base`. Also lets the `test_integration.py` fixture revert to its pre-PR shape (no explicit `paths.base`).
  2. **Filename enforcement.** `_validate_paths_base` now also rejects `paths.base` with a name other than `base.py`. The template's `from .base import Base` is hardcoded, so `paths.base: src/db/models/foundation.py` would generate fine but fail at runtime. Caught eagerly with a dedicated error message.
  3. **Docs wording cleanup.** `usage-guide.md` and `quick-reference.md` clarified: `base.py` is a *child* of `paths.database_models` (and a sibling of the generated model files), not a sibling of the directory itself. Fixed the "live one directory below itself" typo. Added the filename constraint to both docs.
- **Not addressed: Gemini's `.resolve()` suggestion.** `Path()` already normalizes `./` prefixes and trailing slashes; `.resolve()` would make errors show absolute paths anchored to CWD — worse for the user.

**Verification:** `make format` + `make lint` clean (ruff + mypy strict), 440 / 440 tests passing (was 433 pre-PR-B; +7: 5 in `TestValidatePathsBase`, 2 in `TestLoadConfigEdgeCases` guarding the loader-level derivation).

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
