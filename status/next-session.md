# Next Session Plan

## Current State (2026-06-27) — Flutter Phase 4 shipped; all PRs merged

On `main` (`3bd7537`, synced with `origin/main`). **836 tests** (+ 2 xfailed),
`make lint` clean, all CI jobs green.

### What was shipped (PR #78 — feat/flutter-phase4-cache)

Flutter Phase 4: Drift/SQLite offline cache layer, with Gemini comment fixes and
three CI bug-fixes discovered post-merge of PR #71:

| Change | File | What it does |
|--------|------|--------------|
| Gemini fix: `super.db` → `super(db)` in doc example | `docs/user/flutter.md` | Dart compile error: `this._db` is positional-private |
| Gemini fix: `{}` → `{"local_cache": False}` in test | `test_models.py` | More explicit test for absent flag |
| `generate_pubspec` adds Drift deps when `local_cache: true` | `generators/flutter/generators.py` | Was missing from pubspec generation |
| `local_cache: true` added to flutter-app example | `examples/flutter-app/.model-generator.yaml` | Exercises Phase 4 in CI smoke job |
| **CI fix**: `needs_pagination` + `pagination_uri` in `generate_cached_repositories` | `generators/flutter/cache.py` | `Paginated<T>` not a type — missing import |
| **CI fix**: `column_nullable` param in `_to_companion_expr` | `generators/flutter/cache.py` | `String?` assigned to `String` for PK fields |
| **CI fix**: guard `package:decimal/decimal.dart` on `needs_decimal` | `cached_repository.dart.j2` | Unused import → `dart analyze` exit 2 |
| 5 new tests for the three CI fixes | `test_cache.py` | pagination import, pk null assertion, no-decimal import |

### What was shipped (PR #77 — docs/batch5-revalidation)

batch-5 re-validation: 120 survivors re-run → **15 newly killed** (344 → 359).
`mutmut-progress.json` updated.

### Mutmut arc: active

Batches 1, 2, and 5 are fully triaged (see `status/mutmut-survivors-report.md`),
with no actionable survivors remaining. Batches 3, 4, 6, and 7 are complete but
await triage.

### Next steps

1. **Mutmut survivor triage** — batches 3/4/6/7 are complete but untriaged; run
   `/mutmut-report` skill or manually inspect surviving mutants for real gaps
2. **New feature work** — new field type, new stack, or product call

---

## Previous State (2026-06-26) — code-review backlog closed; on `main`

On `main` (`89f6652`, synced with `origin/main`). **827 tests collected**,
working tree clean. PR #73 (Flutter cache class-name fix + mutmut kills) is
**merged**; the prior feature branch `fix/p3-examples-ex6-ex7-rebased` is deleted.

### The `code-review-2026-06-21.md` backlog is effectively closed

Every P0→P3 item from the 2026-04→06 review arc has been shipped across PRs
#34–#73. The per-row **Status** column in `status/code-review-2026-06-21.md` is
*original-triage state* ("verified" = a finder confirmed the issue), **not** a
live status board — it was never re-marked as items shipped. A 2026-06-26
verification pass cross-referenced all 85 P2/P3 table IDs against the shipped-PR
log (84/85 referenced) and spot-checked the few unaccounted rows directly against
the code; all were resolved:

| Item | Claimed open | Reality (verified in code) |
|------|--------------|----------------------------|
| TPL-16 | scalar-with-default typed nullable | `model.py.j2:240-247` `has_default` logic fixes it |
| TPL-14 | `reference` filter `str` → 500 on bad UUID | `route.py.j2:211` types it `UUID \| None` → 422 |
| GEN-2 | conftest uses raw `json.load` | `utils/conftest_generator.py:34` uses `strip_json_comments` |
| GEN-3 | `validate.py` skips index normalization | parses via shared `parse_model_file` (normalizes) |
| GEN-4 | `shell=True` in ruff call | `utils/quality.py` uses `subprocess.run([...], check=False)` |
| GEN-8 | file I/O omits `encoding="utf-8"` | all reads/writes (incl. wizard) pass `encoding="utf-8"` |
| EX-9 | example `.gitignore` excludes `src/tests/alembic` | now explicitly preserves them (banner comment) |
| TST-11 | CI 3.11/3.12 matrix unexplained | `ci.yml:28-33` documents it |
| PROD-2 | no auth-without-owner-scoping | delivered by `api.require_auth` (api-key strategy) |

A definitive open-vs-closed audit of every remaining row was **not** run — if a
future session wants certainty per ID, that's the "Audit backlog truth" option.

### mutmut status — all 7 batches complete

All batches are `complete` in `status/mutmut-progress.json` (verified 2026-06-26):

| Batch | Total | Killed | Survived |
|-------|------:|-------:|---------:|
| batch-1-utils | 1 610 | 1 183 | 427 |
| batch-2-generators | 1 872 | 1 346 | 526 |
| batch-3-conftest | 1 233 | 473 | 760 |
| batch-4-flutter-api | 1 546 | 965 | 581 |
| batch-5-flutter-gen | 464 | 344 | 120 |
| batch-6-generate | 1 631 | 1 149 | 482 |
| batch-7-infrastructure | 1 559 | 1 061 | 498 |

Survivor triage for batches 3/4/6/7 has not been done. To analyse: run
`/mutmut-report` skill once the survivors are categorised, or use
`uv run python scripts/mutmut_batch.py --list` to see current state.

There is no pending *feature*, *correctness*, or *mutation-testing* work; the
generator is at a stable, shippable point. Next direction is a product call
(new field type, new stack, mutmut survivor triage, or a definitive backlog
audit).

---

## Previous State (2026-06-26) — P3 examples batch (merged, PR #70/#73)

Shipped on `fix/p3-examples-ex6-ex7` (later rebased, merged via #73). **756 tests**
at the time, `make lint` clean, `make smoke-example` → 128/128.

### All P3 code-review items are now closed

PRs #63 and #64 had already fixed TPL-7, TPL-15, TPL-21, SEC-8, GEN-5, GEN-11, TST-8 before this session; the previous next-session.md incorrectly listed them as open. This PR closes the final two: **EX-6** and **EX-7**.

### What was shipped this session

| ID | Change | File |
|----|--------|------|
| EX-6 | Entity-level table constraints demonstrated: `check` (`ck_transactions_amount_non_negative`) and `unique` (`portfolio_id, reference_id`) on `Transaction` in `portfolio.model.json`. Template fix: `entity.constraints` of `type: "unique"` now triggers the `UniqueConstraint` import (was only triggered by `indexes[].unique`). | `examples/…/portfolio.model.json`, `templates/database/model.py.j2`, `tests/test_generators.py` (+4 tests in `TestDatabaseGeneratorEntityConstraints`) |
| EX-7 | `tests.scenarios` demonstrated on `UserProfile` in `users.model.json`; `json-specification-reference.md` updated to document `tests.scenarios` (with all valid values) and to replace the stale `custom_constraints` section with the correct `entity.constraints` reference (`check`/`unique`/`depends` types, including the `depends` template format). | `examples/…/users.model.json`, `docs/agent/json-specification-reference.md` |

Tests: 752 → 756 (+4 `TestDatabaseGeneratorEntityConstraints`).

### Next steps

1. **Flutter Phase 4** — offline cache via Drift/SQLite behind the repository
   `_custom.dart` seam from Phase 2.
2. **Optional: mutmut re-validation** — re-run `batch-2-generators` and
   `batch-5-flutter-gen` to confirm the `database.py` + `package_name#9` kills
   (1–2 h each, uninterrupted). Commands:
   ```bash
   uv run python scripts/mutmut_batch.py --run batch-2-generators
   uv run python scripts/mutmut_batch.py --run batch-5-flutter-gen
   ```

---

## Previous State (2026-06-26) — P3 batch (PR #69, merged)

On `main`. **752 tests**, `make lint` clean.

### What was shipped (PR #69)

| ID | Change | File |
|----|--------|------|
| TPL-17 | Extra blank before Field Validators section header in `request.py.j2` | `api/request.py.j2` |
| TPL-20 | Blank line between docstring `"""` and first import in `factory.py.j2` | `database/factory.py.j2` |
| TPL-23 | `request: Request,` on its own indented line in rate-limited endpoints | `infrastructure/auth_router.py.j2` |
| GEN-7 | `generate_migration_init` now accepts `diff=False`; skips `mkdir` under `--diff` | `generators/migrations.py`, `generators/registry.py`, `generate.py` |
| GEN-10 | `load_config` normalises `null` → `{}` for paths/auth/generation/style in-place; `_validate_paths_base` also guards with `or {}` | `utils/loaders.py`, `generate.py` |
| TOOL-6 | Already resolved (`loaders.py` and `validate.py` both use `Draft7Validator`) | — |

---

## Previous State (2026-06-25) — mutmut survivor arc (PR #68, merged)

On `main`. Mutmut arc summary:
- **Full run:** 9,915 mutants, 6,518 killed / 3,397 survived (66%). Triage in
  **[`status/mutmut-survivors-report.md`](./mutmut-survivors-report.md)**.
- **745 tests** (started at 740 before this arc).

### What was shipped (PR #68)

| Cluster | Mutants killed | Tests added | File |
|---------|---------------|-------------|------|
| `wizard.actions._common.find_project_root` #3/4/7/8 | 4 | 3 (`TestFindProjectRoot`) | `test_wizard.py` |
| `flutter.paths.resolve_path` default param #1/4/6 | 3 | 1 | `test_flutter_generators.py` |
| `pyproject.toml` mypy exclude | — | — | `pyproject.toml` (pre-existing `make lint` failure fixed) |

### What was confirmed as noise (do not chase)

- **Encoding mutations** (`"utf-8"` → `None`/`"UTF-8"`) in `parser`, `validate`,
  `enums`, `constraints` — EQUIVALENT: same codec on Linux.
- **`mode="append"` mutations** in `enums.py` / `constraints.py` `template.render()`
  — EQUIVALENT: Jinja2 template only checks `mode == 'create'`; any other value is identical.
- **`config=config` → `None`** in `enums.py` / `constraints.py` — EQUIVALENT: template doesn't reference `config`.
- **`skip_files = {"__init__.py"}` mutations** in `scan_api_model_files` — EQUIVALENT: dead code.
- **`is_model = False` → `None`** in `scan_model_files` — EQUIVALENT: both falsy.
- **`versions_dir.mkdir(parents=True)` mutations** in `migrations.py` — EQUIVALENT: `migrations_dir` already created above.
- **`database.py` / `flutter/paths.py::package_name#9`** (49+1 survivors) — likely
  **batch artifacts**: targeted tests were added AFTER the batch ran. Needs re-validation.

---

## Previous State (2026-06-24) — mutmut batch runner (PR #66, merged)

Branch `claude/mutmut-cc-web-modules-f1goys` merged into `main`. Adds
`scripts/mutmut_batch.py` for per-module mutation testing with cross-session progress
tracking. **Batch 1 is the only fully committed result; batches 2–7 need local runs.**

### What was built

- **`scripts/mutmut_batch.py`** — 7-batch runner; `--setup` creates workspace and
  commits mutant name lists; `--run BATCH` tests pending mutants for one batch;
  `--list`/`--update` show/refresh progress; `--cmd BATCH` prints the raw command.
- **`status/mutmut-names.json`** — all 9,915 mutant names organised by batch, committed
  so any machine can regenerate `mutants/` (~20 s) and run without prior state.
- **`status/mutmut-progress.json`** — durable per-batch progress record; `.meta` files
  are ephemeral and reset on every `mutmut run` call.

### Batch progress (as of last commit)

| Batch                   | Total | Killed | Survived | Status   |
|-------------------------|------:|-------:|---------:|----------|
| batch-1-utils           | 1 610 |  1 166 |      444 | complete |
| batch-2-generators      | 1 872 |      — |        — | pending  |
| batch-3-conftest        | 1 233 |      — |        — | pending  |
| batch-4-flutter-api     | 1 546 |      — |        — | pending  |
| batch-5-flutter-gen     |   464 |      — |        — | pending  |
| batch-6-generate        | 1 631 |      — |        — | pending  |
| batch-7-infrastructure  | 1 559 |      — |        — | pending  |

### Local run — full sequence (run uninterrupted per batch)

**Key insight:** mutmut 3.x resets all `.meta` exit_codes on every invocation. Each
batch must run to completion without interruption, or the partial work is lost. Run
one batch per sitting; commit progress between batches.

```bash
# Prerequisites (run once after cloning / on a fresh machine)
make sync                            # uv sync --extra dev
uv run python scripts/mutmut_batch.py --setup   # generate mutants/ workspace (~20s)
                                     # only needed if mutants/ doesn't exist

# For each batch (2 through 7), run uninterrupted:
uv run python scripts/mutmut_batch.py --run batch-2-generators   # ~1-2h at 4 workers
uv run python scripts/mutmut_batch.py --update
git add status/mutmut-progress.json
git commit -m "test(mutmut): batch-2-generators complete — X/Y killed"
git push

uv run python scripts/mutmut_batch.py --run batch-3-conftest
uv run python scripts/mutmut_batch.py --update
git add status/mutmut-progress.json
git commit -m "test(mutmut): batch-3-conftest complete — X/Y killed"
git push

# ... repeat for batches 4-7 ...

# After all 7 batches done:
uv run python scripts/mutmut_batch.py --list     # confirm all complete
# Then run /mutmut-report skill to analyse surviving mutants
```

**Tuning `--max-children`:** default is 4; increase on machines with more cores
(e.g. `--max-children 8`). Batch sizes: batch-3-conftest is the largest (1,233 single
file); batch-5-flutter-gen is the smallest (464 mutants).

### Failures encountered — lessons for future sessions

**1. ruff format changes must be committed, not just applied locally.**
`ruff format` was run in the previous context window and the file was reformatted, but
the result was never staged/committed before `git push`. CI failed with
"Would reformat: scripts/mutmut_batch.py" on the pushed commit. Fix: always run
`git status` after `ruff format` and commit the changed file immediately.

**2. mutmut 3.x resets ALL `.meta` exit_codes when `mutmut run` is called again.**
Every `mutmut run` call (even with a subset of names) regenerates the workspace and
sets every exit_code back to `null`. The `.meta` files therefore only reflect the
*current* session's batch. `status/mutmut-progress.json` is the only durable record;
commit it after every completed or interrupted batch before ending a session.

**3. `--update` (reading from `.meta`) would overwrite completed batches.**
Because `.meta` files were reset, calling `--update` after starting batch 2 showed
batch 1 as pending again. Fixed: `_update_progress()` now skips any batch whose
`status` is already `"complete"` in `progress.json`. Do not call `--update` mid-run
unless you intend to capture a partial snapshot.

**4. Background process (nohup) can be killed by the container.**
The first batch-2 run (PID 8133) died at 1,049/1,872 with no exit message in the log
— the container likely OOM-killed it or the session timed out. After launching a
background job, verify it is still running before trusting progress:
```bash
ps -p <PID>           # check alive
tail -5 /tmp/mutmut-batchN.log   # check last counter line
```
If the process is gone, re-run `--run BATCH` — it picks up from `.meta` pending entries.

**6. Re-running an interrupted batch re-tests previously-completed mutants.**
When `--run BATCH` is called after a crash, it passes only the pending names to
`mutmut run`. However, mutmut regenerates the workspace on every invocation, resetting
ALL `.meta` exit_codes (including already-completed ones in that batch) to null. The
previously-done work is lost from `.meta` and will be re-done. This is unavoidable
with mutmut 3.x's current behaviour — just accept the extra work. The practical rule:
each batch should ideally run uninterrupted in a single session. There is no
incremental resume within a batch; only across batches (via `progress.json`).

**5. Uncommitted `progress.json` triggers the stop hook.**
After `--update`, `status/mutmut-progress.json` is modified but not staged. The
`~/.claude/stop-hook-git-check.sh` requires a clean working tree. Always commit
`progress.json` before ending a session:
```bash
git add status/mutmut-progress.json
git commit -m "test(mutmut): batch-N-... complete — X/Y killed"
git push -u origin <branch>
```

---

## Previous State (2026-06-23) — P3 tooling batch TST-10/TOOL-2/4/5/7/8 (PR #65, pending)

Branch `claude/beautiful-shannon-foxzyy`. Six P3 backlog items from the 2026-06-21
code review, all closed. 738 unit tests + `make lint` clean. PR #64 merged; PR #65
being opened for this batch.

- **TST-10** — Added `minimal_user_model` fixture to `TestValidateModel`; refactored
  three tests to use `copy.deepcopy(minimal_user_model)` instead of repeating the
  full dict literal.
- **TOOL-2** — Fixed `_find_project_root` in `generate.py`: removed the no-op `if`
  branch; resolution now walks CWD → CWD's parent → model's parent (monorepo-aware).
- **TOOL-4** — Changed `env: Any` → `env: Environment` in `GenContext` dataclass
  (`generators/registry.py`); added `from jinja2 import Environment`.
- **TOOL-5** — Removed vestigial `project_config: dict[str, Any]` parameter from
  `generate_env_example`, `generate_pyproject`, `generate_main`, `generate_auth_router`,
  `generate_api_key_auth`, `generate_infrastructure`. Updated all call sites and tests.
- **TOOL-7** — Extracted inline output-writing loop to `utils/output.py:write_outputs()`.
  Both `generate.py` and `infrastructure.py` (and the Flutter orchestrator) now delegate.
- **TOOL-8** — Renamed `*_requests.py` → `*_request.py` throughout: `generators/api.py`,
  `utils/parser.py`, `api/init.py.j2`, `api/route.py.j2`, `test_generators.py`,
  `test_integration.py`, `test_edge_cases.py`.

**Tests:** 735 → 738, ruff + mypy strict clean.

**All code-review-2026-06-21 items now closed** (confirmed or by-design):
- GEN-9 (has passing test `test_strip_json_comments_preserves_slashes_in_strings`)
- TOOL-11 (CI comment explains why lint runs on 3.12 with py311 target — intentional)
- TOOL-4 also fixed in GenContext for completeness

---

### P3 template/tooling batch shipped — TPL-8/11/13/18/19/22 + TOOL-10 (PR #61)

Branch `claude/fervent-babbage-ye4iri`. Seven P3 backlog items from the
2026-06-21 code review, verified clean with 706 unit tests + smoke-example
128/128.

- **TPL-8** — Deleted dead `_shared/_examples.j2` and `_shared/_fields.j2`
  template macros (imported by nothing).
- **TPL-11** — Dropped `from_attributes=True` from response-model `ConfigDict`;
  response models are always dict-constructed via `EntityResponse(**data)`.
- **TPL-13** — Removed `asyncio_mode = "auto"` from generated `pyproject.toml`;
  `pytest-asyncio` is not in the generated dev deps and all contract tests are
  synchronous.
- **TPL-18** — Excluded `api_exclude_response` fields (e.g. `password_hash`,
  `key_hash`) from the `sort_by` valid-fields whitelist; sorting by a secret
  column leaks information even if the value is never returned.
- **TPL-19** — Raises `HTTPException(422)` when `sort_by` is not in
  `valid_fields` instead of silently applying no ordering.
- **TPL-22** — Default `python_version` changed from `"3.11"` → `"3.12"`;
  the stack already uses PEP 695 generics requiring 3.12.
- **TOOL-10** — Removed duplicate `[dependency-groups]` PEP-735 section from
  this repo's `pyproject.toml`.

**Verified:** 706 unit tests (+6), `make lint` clean (ruff + mypy strict),
`make smoke-example` → 128/128.

**Audit result (pre-session):** GEN-1/2/3/4/8, EX-5/9, TST-9, TOOL-1/3 were
already closed in earlier PRs. Remaining open items: lower-priority P3
(TPL-7/15/17/20/21/23, GEN-5/7/9/10/11, SEC-8, TST-8/10/11, TOOL-2/4/5/6/7/8/9/11).

---

### Flutter Phase 3 shipped — flutter-app example + CI (PR pending)

Branch `claude/epic-clarke-bshl6k`. Closes Phase 3 of the Flutter stack plan
(`flutter-stack-plan.md`). Phases 0/1/2 shipped in PRs #57–#59.

- **`examples/flutter-app/`** — the "one spec, two stacks" proof: the same
  catalog-api spec (`catalog.model.json` + `_shared/enums.json`) fed to
  `stack: flutter` (package_name: catalog_api, api-key auth). Exercises:
  `@freezed` models, `ProductStatus` enum with `@JsonValue`, `@RestApi`
  clients for Category (public) and Product (auth-gated), `DecimalConverter`
  (price field), `AuthInterceptor` (X-Catalog-Key), repositories, Dio setup,
  pagination.
- **`scripts/smoke_generated_flutter.sh`** + **`make smoke-flutter`** —
  regenerates the example into a temp tree, runs `dart pub get` →
  `dart run build_runner build --delete-conflicting-outputs` → `dart analyze`
  (zero errors). Mirrors the existing `smoke_generated_example.sh` pattern.
- **`generated-flutter` CI job** — uses `subosito/flutter-action@v2` (stable
  channel); guards the Flutter templates and any shared-engine changes
  (Phase-0 registry).
- **`generate.py` stack-resolution fix** — `--stack` default changed to `None`;
  `main()` now reads `stack:` from `.model-generator.yaml` when not explicitly
  passed; `generate()` likewise resolves the actual stack from the merged config.
  This was the critical bug that caused the flutter example to generate
  python-fastapi output instead of Dart.
- **Docs** — `docs/user/flutter.md` (usage guide); `template-extension-guide.md`
  updated with Flutter stack in architecture overview + "Adding a new stack"
  section; `docs/README.md` Flutter rows added.

**Verified:** 698 unit tests; `make lint` clean. Dart smoke verified by CI
(`generated-flutter` job); no Dart SDK in the Python test environment.

---

A full multi-lens code review landed in **[`status/code-review-2026-06-21.md`](./code-review-2026-06-21.md)**:
~70 prioritized, stable-ID, queue-ready issues (P0→P3) plus direct answers to the
owner's 10 review questions and a fix-sequencing plan. **Read that file — it is the
backlog and the source of truth for this arc.**

**Active arc: remaining P2/P3 Python items + optional Flutter Phase 4.** Flutter
Phase 3 is shipped. Next: work the remaining lower-priority P2/P3 items from the
review backlog (`status/code-review-2026-06-21.md`, Part B/D), or optionally advance
Flutter Phase 4 (offline cache via Drift/SQLite behind the repository `_custom.dart`
seam from Phase 2).

### All 7 P0 items shipped (PRs #34, #35, #36, #37)

- **TPL-1** — `isoformat_utc()` helper in `utils.py.j2`; route datetime fields +
  `created_at`/`updated_at` use it instead of `isoformat() + "Z"` (fixes the
  invalid `...+00:00Z` on Postgres).
- **SEC-2** — `auth_router.py.j2`: `reset_password`/`change_password` revoke the
  user's `UserSession` rows.
- **SEC-3** — `auth_router.py.j2`: `_token_fingerprint()` makes reset tokens
  single-use (bound to the current password hash; no schema change).
- **TST-2** — `conftest_root.py.j2`: defaults the pepper + `SESSION_SECRET_KEY`
  env vars so the generated suite is green without a manual `export`.
- **SEC-1** — warn at generation when `auth.strategy` is set but no API-enabled
  entity declares `api.scope`; scope example owner entities (Portfolio/ApiKey/
  UserSession/UserRole via `user_id`); add usage-guide note.
- **TPL-2** — FactoryBoy factories now emit correct `SubFactory` calls by
  resolving `reference_table` → entity name via a `table_to_entity` dict computed
  in the generator and threaded into the template. Fixes `IntegrityError` on
  `Factory.create()` for FK fields.
- **WIZ-1** — `_prepare_infra_modules()` shared helper extracted from `main()`;
  both `main()` and wizard's `run_generate()` call it. Closes uninstallable
  `pyproject.toml` (missing bcrypt/itsdangerous) for auth projects generated via
  the wizard.

### P1 in progress — TST-1 + scoped-example regression (PR pending)

**Discovery:** the SEC-1 P0 (PR #35) added `api.scope` to four example entities
but did **not** make the generated contract tests auth-aware — so the flagship
example suite has been **silently red since SEC-1** (scoped CRUD → 401; the
`missing_required_fields` test omitted the now-injected owner field and expected
422). Exactly what TST-1 exists to catch.

**Shipped this PR (branch `claude/continuation-bg9kvu`):**
- **Scoped contract suite green.** `conftest_generator.py` emits an autouse
  `_default_authenticated_user` fixture (gated on auth + any `api.scope` entity +
  a `User` entity) that registers a persisted owner via the existing `user_id`
  fixture and overrides `get_current_user`, coercing the id to `uuid.UUID` so the
  route's Python-level owner check (`row.owner != current_user.id`) matches.
  `generate.py` computes the `auth.router` / `main` import paths
  (`_compute_auth_router_import` / `_compute_main_import`). `contract.py.j2`'s
  missing-required loop now skips the scope owner field.
- **TST-1 — CI runs the emitted suite.** New `generated-example` CI job +
  `make smoke-example` + `scripts/smoke_generated_example.sh`: regenerates the
  example into a temp tree and runs its contract suite under Python 3.12 (the
  generated PEP 695 generics need 3.12).
- **Verified:** 519 unit tests (+7), `make lint` clean, `make smoke-example` →
  **135/135** generated contract tests pass.

### P1 green-out-of-box trio shipped — TPL-3 + TPL-4 + TPL-9 (PR pending)

Branch `claude/elegant-dirac-kq7l73`. Completes the "generated project is green
out of the box" cluster (TST-1/TST-2 already shipped in #38).

- **TPL-3 — alembic `env.py` E402 silenced.** `pyproject.toml.j2` emits a
  `[tool.ruff.lint.per-file-ignores]` block ignoring `E402` for
  `{{ migrations_path }}/env.py` (the standard alembic layout configures logging
  before importing model metadata). `generate_pyproject` threads
  `migrations_path` (default `alembic`). Verified: generated `alembic/env.py`
  now passes `ruff check`. (The remaining main/auth I001 + pagination-PEP695
  quirks are auto-fixed by `ruff check --fix` — separate TPL-22 territory.)
- **TPL-4 — production `DATABASE_URL` guard.** `engine.py.j2` wraps the URL
  resolution in `_resolve_database_url()`: keeps the SQLite dev fallback
  normally, but raises `RuntimeError` when `DATABASE_URL` is unset under
  `APP_ENV=production` (mirrors the `SESSION_SECRET_KEY` guard in
  `auth_router.py.j2`).
- **TPL-9 — `.env.example` manifest.** New `infrastructure/env.example.j2` +
  `generate_env_example` (root-file, bootstrap-only, gated on `no_root_files`).
  Always lists `APP_ENV`/`DATABASE_URL`/`ALEMBIC_DATABASE_URL`/`SQL_ECHO`/
  `CORS_ORIGINS`; adds `SESSION_SECRET_KEY` + pepper when auth is on,
  `RATELIMIT_STORAGE_URI` for a redis rate-limit backend, `FERNET_KEY` for
  encrypted binary fields. Usage-guide "Environment Variables" subsection added.

**Verified:** 534 unit tests (+6), `make lint` clean, `make smoke-example` →
135/135. Generated `.env.example` inspected (correct var set + trailing newline);
`ruff check alembic/env.py` clean.

### P1 docs sweep shipped — DOC-2,3,4,5,6,7,8,9,10,11,12,13,14 (PR pending)

Branch `claude/compassionate-dijkstra-d3dgn4`. Closes the docs-sweep cluster.
Docs/schema-description only — no generator logic changed; 534 tests + lint
unchanged-green.

- **DOC-2** — `extending-generated-code.md` rewritten for the **async** API
  (`AsyncSession`, `await session.execute(select(...))`, `Depends(get_session)`
  from `database/engine.py`); per-entity file names corrected
  (`{entity}_requests.py`/`_response.py`); the hand-rolled reset-password worked
  example (the auth router already provides it) swapped for a neutral
  "deactivate account" action; new top banner stating the stack is async.
- **DOC-4** — enum-casing corrected to **UPPER_CASE** in the reference (`default:
  "ACTIVE"`, `UserStatus.ACTIVE`, uppercased `enums.json` value examples + a
  normalization note) and the schema descriptions (`value` "UPPER_CASE;
  auto-uppercased", list "auto-uppercased").
- **DOC-5** — `binary` field type documented (reference section + quick-ref row,
  LargeBinary/`bytes`/`encrypt`); `integer`→`counter` alias noted; "12 field
  types" → "13".
- **DOC-3** — `api.scope` `dependency_path` is **auto-wired** when `auth.strategy`
  is set (only hand-set when bringing your own auth) — reference corrected.
- **DOC-6** — usage-guide migration step uses the async driver
  `sqlite+aiosqlite:///./app.db`.
- **DOC-7** — usage-guide "Clean and Regenerate" gains a one-shot/upgrade note
  (domain files overwrite, infra is skip-if-exists, how "should regenerate"
  actually works).
- **DOC-8** — CLAUDE.md "Running the Example" `cd`s into the example first
  (`load_config` reads CWD).
- **DOC-9** — new `docs/user/architecture.md` (pipeline overview, generated
  layout, troubleshooting table, upgrade-after-one-shot); linked from README +
  `docs/README.md`.
- **DOC-10** — quick-ref CLI tables gain `base`/`engine`/`main`/
  `test-conftest-root`/`migration-autogen` targets and `--no-root-files`/
  `--version` flags.
- **DOC-11** — this status entry; **DOC-12** — CHANGELOG compare-links extended
  to 0.1.2/0.1.3/0.1.4 + Unreleased rebased on v0.1.4; **DOC-13** — README
  test-suite table gains `test_cleanup`/`test_enum_examples`/`test_validate`;
  **DOC-14** — usage-guide wizard install → `uv tool install
  "model-generator-kit[interactive]"`.

### P1/P2 wizard PR shipped — WIZ-2 + WIZ-3 + WIZ-4 + WIZ-5 (PR pending)

Branch `claude/modest-davinci-iu0mhb`. Closes the wizard cluster (WIZ-1 + TOOL-9
already shipped in #37). Wizard runtime only — no templates/generated output
touched, so the smoke-example suite is unaffected.

- **WIZ-2 — `questionary` import guarded.** `prompts.py` wrapped the
  `import questionary as _questionary` in `try/except ImportError` (it ships in
  the optional `[interactive]` extra). On a base install `_questionary` is now
  `None` and the plain-`input()` fallback is *live* code, not dead — previously
  the unconditional import crashed `--interactive` at module load and the
  fallback branches were unreachable despite the docstring's promise.
- **WIZ-3 — Ctrl-C / ESC / Ctrl-D handled.** New `PromptCancelled` exception.
  Every helper raises it when questionary's `.ask()` returns `None` (abort)
  instead of casting `None` to `str`/`list` (silent re-prompt loops / `TypeError`
  on the checkbox result); the fallback maps `EOFError` to the same. `menu.py`'s
  loop catches `PromptCancelled`/`KeyboardInterrupt`: a cancelled *top-level*
  prompt exits the wizard, a cancelled prompt *inside an action* aborts that
  action and returns to the menu (dispatch extracted to `_dispatch`).
- **WIZ-4 — wizard can set `--no-root-files`.** `actions/generate.py` asks
  "Generate root project files (pyproject.toml/alembic.ini/.gitignore)?" when the
  target emits infrastructure, and threads `no_root_files` into both
  `generate_infrastructure(...)` and `generate(...)` — CLI scratch-and-migrate
  parity.
- **WIZ-5 — `run_generate` core path tested.** New `TestRunGenerateAction` drives
  the real function over a tmp project (config + one model): a non-infra target
  scans files and calls `generate(...)` per file; declining root files threads
  `no_root_files=True` into both the infra and per-domain calls. Plus
  `TestPromptsOptionalImport`, `TestPromptsCancellation`, `TestMenuCancellation`.

**Verified:** 559 unit tests (+25), `make lint` clean (ruff + mypy strict).

### P2 template-correctness trio shipped — TPL-6 + TPL-10 + TPL-12 (PR pending)

Branch `claude/keen-ptolemy-4dlslp`. Closes the P2 template-correctness cluster.

- **TPL-10 — `encrypted_bytes.py` is mypy-clean under the shipped config.**
  `encrypted_bytes.py.j2`: `_get_fernet()` was unannotated and `process_bind_param`/
  `process_result_value`/`load_dialect_impl` had a bare `dialect` param →
  `disallow_untyped_defs` failures. Now `from typing import TYPE_CHECKING, Any`,
  `dialect: Any` everywhere (mirrors `types.py`), and `_get_fernet() -> "Fernet"`
  (via a `TYPE_CHECKING` import of `cryptography.fernet.Fernet`) so the bind/result
  values stay `bytes` and don't trip `warn_return_any`. Verified end-to-end:
  rendered file is clean under the generated project's exact mypy flags
  (`disallow_untyped_defs`/`disallow_incomplete_defs`/`check_untyped_defs`/
  `warn_return_any`/…). The only residual — `[type-arg]` on the bare
  `TypeDecorator` base — comes from `disallow_any_generics` (NOT in the shipped
  config) and is shared verbatim with the existing `types.py`, so this is exact
  parity, not a new gap.
- **TPL-12 — datetime fixtures use a far-future literal.**
  `conftest_generator.py:generate_minimal_create_data` emitted `2025-01-01` for
  every datetime create field — a time-bomb: a session `expires_at` seeded in
  the past is already expired, and the literal ages further out of range as real
  time advances. Now `2099-01-01T00:00:00Z`, matching the `2099` convention the
  contract update payloads already use.
- **TPL-6 — `percentage` is documented as a 0–1 fraction.** The type stores a
  0.0–1.0 fraction (`Numeric(5,4)`, `validate_percentage` enforces `0 ≤ v ≤ 1`),
  but the example's `allocation_percentage` description said "(0-100%)". Fixed the
  example description to "0.0-1.0 fraction (e.g. 0.25 = 25%)" and added a
  clarifying note to the `percentage` section of the JSON-spec reference.

**Verified:** 562 unit tests (+2: `TestEncryptedBytesGenerator::
test_signatures_are_fully_annotated`, `TestConftestGeneratorDatetimeFixture`),
RED→GREEN confirmed (both fail with the template/source changes stashed).
`make lint` clean (ruff + mypy strict), `make smoke-example` → 135/135.

### P2 migration-autogen cleanup shipped — GEN-6 + GEN-12 (PR pending)

Branch `claude/keen-ptolemy-4dlslp` (reset onto main after #46 merged). Both
issues live in the same `migration-autogen` code path.

- **GEN-6 — honest + project-agnostic instructions.** `generate_migration_autogen`
  dropped the misleading `print("  Running alembic revision --autogenerate...")`
  (nothing is actually run — the docstring even says so) and the hardcoded
  `docker-compose up -d timescaledb` orchestration line (project-specific, violates
  the project-agnostic principle). The guidance is now a module-level
  `_AUTOGEN_INSTRUCTIONS` constant: "start your database and make sure it is
  reachable", a generic `DATABASE_URL` export (async-driver example), and the
  `alembic revision --autogenerate` / `alembic upgrade head` steps.
- **GEN-12 — no sentinel return dict.** The function returned a `{"info", "instructions"}`
  dict with no `path`/`content`, intercepted by a fragile
  `isinstance(result, dict) and "instructions" in result` branch in `generate.py`'s
  output dispatch. It now **prints** the instructions and returns `None` (typed
  `-> None`); the special-case dispatch branch is removed, so the loop only handles
  real file-emitting results. The `-> None` signature (mypy-enforced in CI) is the
  guard against a sentinel dict being reintroduced.

**Verified:** 560 unit tests, RED→GREEN confirmed (the two `TestMigrationAutogen`
behavioural tests fail with the source changes stashed). `make lint` clean
(ruff + mypy strict), `make smoke-example` → 135/135.

### P2 test-depth cluster shipped — TST-5 + TST-6 + TST-7 (PR pending)

Branch `claude/peaceful-feynman-g0k3kn`. Closes the test-depth cluster. **Pure
test additions — no `src/` or template changes**, so the generated output and the
`make smoke-example` gate are unaffected. These are coverage/characterization
tests (expected GREEN against current code), not bug-fix RED→GREEN: they lock in
correct current behavior the suite never exercised.

- **TST-5 — cross-domain mapper config probed end-to-end.** The only live
  `registry.configure()` probe was on a single composite-FK model
  (`TestCompositeForeignKey`). New `TestCrossDomainMapperConfig` +
  `cross_domain_models` fixture generate **two separate domain specs**
  (`blog.{Author,Post}` + `engagement.Comment`, with `Post`↔`Comment` crossing
  the boundary), merge every emitted per-entity file into one shared
  `DeclarativeBase` registry (what import time does in a real project), and call
  `registry.configure()` — the step that raises on a misconfigured cross-domain
  `back_populates`/join. Second test asserts the relationship resolves as
  inverses on both ends via `sqlalchemy.inspect`.
- **TST-6 — schema-invalid-but-plausible specs characterized.**
  `TestSchemaInvalidSpecHandling` pins both halves of the load/validate contract:
  `load_model` is **warn-only** (returns the spec intact, no `sys.exit`) on an
  unknown field type + a missing PK, while `validate_model` (the `model-val`
  gate) **flags** both. Catches a regression where load_model starts exiting or
  the validator goes silent.
- **TST-7 — generated output is lint-clean after the quality pass.**
  `TestGeneratedOutputLintClean` writes the emitted DB-model + API-model files,
  runs the generator's own `ruff --fix`/`ruff format` pass with the **exact
  select/ignore set** the generated `pyproject.toml` ships (`E,W,F,I,B,C4,UP` /
  `E501,B008,B904,W191`), then asserts `ruff check` finds **no residual** — i.e.
  no *non-auto-fixable* lint (B007/F841/UP…) slipped into a template. (Routes are
  excluded: they carry the known pagination-PEP695-on-py311 quirk, TPL-22.)
  Skips cleanly if `ruff` is absent.

**Verified:** 567 unit tests (+7), `make lint` clean (ruff + mypy strict). No
templates touched → smoke-example unaffected (still 135/135 from the prior PR).

### P2 example-coverage cluster shipped (in-place) — EX-3/EX-4 + part of EX-2 (PR pending)

Branch `claude/peaceful-feynman-g0k3kn`. Extends the **flagship example in place**
(no new bundled example) so the `make smoke-example` job exercises the
previously-uncovered field types, constraints, and relationship kinds. Generator
templates untouched — `examples/user-auth-project/models/users.model.json` only.

- **New `UserProfile` entity** demonstrates **`one_to_one`** (EX-3: `User.profile`
  `one_to_one` ↔ `UserProfile.user` `one_to_one_inverse`, unique `user_id` FK
  enforcing 1:1), the **`binary`** type (`avatar` → `LargeBinary`/`bytes`, EX-4),
  and the **`integer`→`counter` alias** (`profile_views`, EX-4). It's `list`/`get`
  only (no `create`): a *unique* owner FK collides with the contract suite's
  shared session fixtures on repeated creates, and a scoped entity without a
  `create` endpoint trips the auto-generated scope-access-denied test (which
  POSTs) → 405. Left **unscoped** for the same reason (scope is already
  demonstrated by Portfolio/UserSession/ApiKey/UserRole).
- **`ApiKey` gains three constraint demos** (EX-4), all on create-flow fields so
  the request validators + DB CHECKs are actually exercised: `max_calls_per_day`
  (**`integer`** alias + **`range`** 1–100000 → `CheckConstraint(... >= 1 AND ...
  <= 100000)`), `priority` (**`positive`** → `CheckConstraint("priority > 0")`),
  and `label` (**`pattern`** `^[a-z][a-z0-9_]*$` → a `@field_validator` with
  `re.compile`; pattern emits **no** DB CHECK, so factories that bypass Pydantic
  are unaffected, and the create/update literals `test_value`/`updatetest_value`
  match the regex).
- **Deliberately skipped:** `many_to_many` (schema-enum only — the model template
  has no `many_to_many`/`secondary` branch, so it would emit nothing/broken) and
  entity-level **`api.validators`/`api.filters`** (consumed by **no** template —
  validators/filters are auto-derived from field types/constraints, so adding the
  config blocks would demonstrate dead knobs). `api.scope` (EX-2) was already
  wired by SEC-1. Composite-FK-in-example (EX-3) and a minimal no-auth/per-domain
  example (EX-8) remain open — the user chose "extend in place," not a new example.

**Verified:** `make smoke-example` → **141/141** (was 135; +6 = UserProfile
list/get + filter tests). 567 unit tests still green, `make lint` clean. Fresh
generation spot-checked: `profile` `Mapped["UserProfile | None"]` relationship,
`avatar: Mapped[bytes | None]` `LargeBinary`, range/positive CHECKs, and the
`validate_label_format` regex validator all emit.

### Feature: static `api-key` auth strategy shipped (PR pending)

Branch `claude/practical-babbage-k2yj34`. Owner-requested follow-up to the SEC-6
discussion: rather than build a complex server-minted-secret capability (wrong
altitude for this tool), add a **lightweight second `auth.strategy: api-key`** —
a single shared secret read from an env var, checked by one generated dependency.
For service-to-service / internal APIs that don't need the bcrypt-session
user/session/CSRF stack.

- **New `infrastructure/api_key_auth.py.j2` + `generate_api_key_auth`.** Emits a
  `require_api_key` FastAPI dependency: constant-time (`secrets.compare_digest`)
  comparison of a `Header(alias=...)` value against `os.environ[key_env]`,
  fail-closed under `APP_ENV=production` (mirrors the SESSION_SECRET_KEY guard),
  dev fallback otherwise. Config: `auth.key_env` (default `API_KEY`),
  `auth.header_name` (default `X-API-Key`). Bootstrap-only (skip-if-exists).
- **Opt-in: entity `api.require_auth: true`** (new schema property). The route
  template gates every endpoint of that entity with
  `dependencies=[Depends(require_api_key)]` (decorator-level — no owner injection,
  orthogonal to `api.scope`). New `ns.has_auth_gate` scan flag drives the import;
  the auth-dep import block was hoisted/generalized to serve both strategies.
- **Strategy isolation.** Session-only generators (`generate_auth_router`,
  `generate_csrf`, `generate_rate_limit`) and the main.py router/CSRF/rate-limit
  wiring now gate on `strategy == "bcrypt-session"` (were truthy) so api-key emits
  none of them. `_compute_rate_limiter_import`/`_compute_auth_router_import`
  likewise. **smoke-example still 128/128** confirms the bcrypt-session path is
  unregressed.
- **Loader** infers `auth.dependency_path` per strategy: `…api_key.require_api_key`
  for api-key, `…router.get_current_user` for session (explicit values preserved).
- **Validation** (`_validate_auth_strategy`): `api-key` added to valid strategies,
  with its own branch (no User/pepper/layout prerequisites; validates `key_env` is
  non-empty). `_validate_auth_scope_coverage` warns on the right opt-in key per
  strategy (`require_auth` vs `scope`).
- **Contract suite stays green.** The api conftest emits an autouse
  `_bypass_api_key` fixture (overrides `require_api_key` → no-op) when
  api-key + any `require_auth` entity, since CRUD tests don't carry the header.
  `conftest_root` gates the session env-defaults/deferred-import on bcrypt-session
  (api-key reads its env at call time). `.env.example` lists `key_env` (not the
  session secrets) under api-key.

**Verified:** 590 unit tests (+19), `make lint` clean (ruff + mypy strict),
`make smoke-example` → 128/128. **End-to-end probe** (throwaway api-key project,
Python 3.12): generated `api_key.py` + 5 gated routes + no session files +
`.env.example` `API_KEY` + conftest bypass; live TestClient confirmed **no key →
401, bad key → 401, valid key → 200**, and the generated contract suite passes
(16/16) under the bypass. Docs: usage-guide "Authentication" rewritten to cover
both strategies. The flagship example stays bcrypt-session (a bundled api-key
example + smoke wiring is a possible follow-up, overlaps EX-8).

### P2/P3 auth-security cluster shipped — SEC-5 + SEC-4 + SEC-7 (merged, #50)

Branch `claude/practical-babbage-k2yj34`. Template-only auth-router/rate-limit
hardening — no example spec or generated CRUD touched, so the smoke-example gate
is unaffected (still 141/141; the contract suite imports the auth router via its
`/auth/register` fixture, so the new paths load at import time).

- **SEC-5 — forgot-password account-enumeration oracle closed.** The endpoint
  raised `501` only when the email *existed* (the hook is invoked solely in the
  `user is not None` branch), while a missing email returned `200` — directly
  contradicting its own docstring and leaking which addresses have accounts.
  `forgot_password` now returns the uniform `200` regardless; a missing
  `_send_password_reset_email` hook is surfaced via a module-level
  `logger.warning(...)` (new `import logging` + `logger = logging.getLogger(...)`)
  instead of an HTTP status. Docstring rewritten to state the no-oracle contract.
- **SEC-4 — session-cookie / reset-token serializer salt separation.** The single
  `_serializer` signed both session cookies and reset tokens off the same key.
  Split into `_session_serializer` (`salt="session-cookie"`) and
  `_reset_serializer` (`salt="password-reset"`); login/logout/`get_current_user`
  use the session one, forgot/reset use the reset one. A token minted in one
  context can no longer be replayed in the other (defense in depth).
- **SEC-7 — reverse-proxy client-IP caveat documented.** `rate_limit.py.j2`'s
  `get_remote_address` keys on the socket peer — behind a proxy that's the
  *proxy's* IP, collapsing all clients into one bucket. Added a "Client IP /
  reverse proxies" docstring section + inline comment explaining the footgun and
  how to safely read `X-Forwarded-For` from a trusted proxy (doc/comment only — a
  safe forwarded-IP keyfunc needs the deployment's trusted-proxy count).

**Verified:** 570 unit tests (+3: salt separation, no-oracle, proxy caveat — all
RED→GREEN confirmed against reverted templates), `make lint` clean (ruff + mypy
strict), `make smoke-example` → 141/141. The existing
`test_resolves_session_secret_via_helper` assertion was updated for the new
salted serializer construction.

### P2 SEC-6 shipped — ApiKey creation out of generic CRUD + scope-test gating fix (merged, #51)

Branch `claude/practical-babbage-k2yj34` (rebased onto main after #50 merged).
Owner chose **option 1**: move ApiKey creation out of generic CRUD, mirroring the
`User` precedent (user creation is owned by the auth router; ApiKey creation
belongs in a custom key-minting route that the generic CRUD generator can't
produce — the secret must be server-minted and shown once).

- **Generator fix (the enabler).** `contract.py.j2`'s `test_{entity}_scope_access_denied`
  was gated only on `scope`, but it POSTs to seed a row and asserts `201`. A scoped
  entity *without* a `create` endpoint therefore emitted a guaranteed-failing test
  (POST → 405). Gated it on `'create' in endpoints` too — consistent with how the
  other POST-seeding tests (`put`/`delete`/`list_filtering`/`get_by_id`) are
  already gated (§12.6). This is what previously blocked making any scoped entity
  read-only (the UserProfile note in the EX-3/EX-4 entry called this out).
- **Example: ApiKey is now `list`/`get`/`delete` (no `create`).** Dropping `create`
  removes the POST route entirely, so the mass-assignment surface
  (`key_hash`/`permissions`/`is_active` settable by the caller, esp. the
  server-secret `key_hash`) is **unreachable** — verified: the generated
  `api_key.py` route has only list/get/delete handlers and does not import
  `CreateApiKeyRequest`. (The `CreateApiKeyRequest` *model* is still emitted but
  dead — identical to the pre-existing `CreateUserRequest`, since `User` is also
  create-less; api-models emit Create/Update independent of endpoints. Not a
  regression, shared precedent.) Kept `delete` so an owner can still revoke a key
  (safe generic-CRUD op). ApiKey stays `scope`d (keys are per-user); the gating
  fix is what lets scoped+create-less coexist.
- **EX-4 coverage preserved (relocated, not lost).** ApiKey's three create-flow
  constraint demos moved to **UserSession** (which keeps `create`+`scope`, so they
  stay exercised on create *and* in its scope-denial test): `max_duration_minutes`
  (`integer` alias + `range` 1–100000), `connection_priority` (`counter` +
  `positive`), `device_label` (`text` + `pattern` `^[a-z][a-z0-9_]*$`). ApiKey
  keeps `rate_limit_per_minute` (`counter` + `non_negative`).

**Verified:** 571 unit tests (+1: `test_scope_access_denied_gated_on_create`,
RED→GREEN confirmed), `make lint` clean (ruff + mypy strict), `make smoke-example`
→ **128/128** (was 141: ApiKey shed its create/update/scope-denied cases; the
relocated UserSession fields add no new cases). `model-val` valid. Fresh
generation spot-checked: ApiKey route = list/get/delete only, no POST; UserSession
`CreateUserSessionRequest` carries the relocated fields + `validate_device_label_format`.

**Still open (owner decisions):** a *first-class* server-minted-secret capability
(a `server_generated`/`server_default_factory` field flag so the generator could
emit ApiKey-style create routes itself) is the larger feature this defers — left
for a future arc. **PROD-4** (auth: first-class vs optional add-on) also remains
an owner decision.

### EX-8 + EX-3 composite-FK + PROD-4 closed — new `examples/catalog-api` (PR pending)

Branch `claude/laughing-mendel-mytrba`. Adds the second bundled example, closing
the three remaining open backlog items from the P2 cluster.

- **EX-8 closed — `examples/catalog-api/`** is the minimal per-domain + api-key
  demo. Two model files: `catalog.model.json` (Category + Product, both with full
  CRUD; Product has `require_auth: true`) and `inventory.model.json` (Warehouse +
  StockEntry with `api.enabled: false` — DB models + factories only, no routes).
  Shared `_shared/enums.json` provides `ProductStatus` (DRAFT/ACTIVE/DISCONTINUED,
  `enum_existing: true`). Config: `python_root: src`, `generation.layout:
  per-domain`, `auth.strategy: api-key`, `auth.key_env: CATALOG_API_KEY`,
  `auth.header_name: X-Catalog-Key`, `api_tests: tests/contract` (avoids the
  root-conftest overwrite that would occur if `api_tests` shared a directory with
  `test_conftest_root`). Validated: `model-val models` clean; 39/39 generated
  contract tests pass on Python 3.12.
- **EX-3 composite-FK half closed** — `inventory.model.json` exercises the
  entity-level `foreign_keys` array (Warehouse composite PK `(region, id)` +
  StockEntry composite FK `(region, warehouse_id) → warehouses(region, id)`,
  `ForeignKeyConstraint` emitted). `api.enabled: false` keeps the smoke suite
  tractable: the composite-FK factory can't auto-setup FK constraints without a
  live Warehouse row, so only the DB-model/factory generation is verified (no
  contract tests for inventory entities). This is the documented known limitation.
- **PROD-4 closed as "first-class"** — Auth is already first-class: two tested
  strategies, CI smoke coverage, full documentation, SEC P0s shipped. No code
  change needed; resolved in the review doc.
- **New smoke wiring:** `scripts/smoke_generated_catalog_api.sh` mirrors
  `scripts/smoke_generated_example.sh`; `make smoke-catalog-api` target added to
  `Makefile`; `generated-catalog-api` CI job added to `.github/workflows/ci.yml`
  (runs in parallel with `generated-example`).

**Verified:** 591 unit tests (unchanged), `make smoke-catalog-api` → **39/39**
generated contract tests pass, `model-val` clean.

### P1 docs fix shipped — SEC-9 (PR pending)

Branch `claude/vibrant-cannon-3oj0ra`. Docs-only change — no generator logic,
templates, or tests touched.

- **SEC-9 — Infra upgrade path documented.** The four past CHANGELOG entries
  that said "adopters should regenerate" have been replaced with specific
  domain-vs-infra breakdowns. For each security/correctness fix that touched a
  skip-if-exists infra file (`main.py`, `errors.py`, `request_limit.py`,
  `validators.py`, `migrations/env.py`), the entry now names the file and gives
  the exact manual apply steps (delete + re-run, or inline diff). The CORS
  wildcard+credentials fix was previously undocumented in the CHANGELOG; it has
  been added to 0.1.1 as a new security bullet. `architecture.md` updated to
  clarify that CHANGELOG entries now flag domain vs. infra explicitly and notes
  a future `--force-infra` selective-overwrite flag. `usage-guide.md` updated to
  remove the cross-reference to the old CHANGELOG phrasing.

### Next: remaining P2 cluster

Consult the review doc (`status/code-review-2026-06-21.md`, Part B/D). All P0/P1
and most P2 items are now closed. Remaining open items are lower-priority P2/P3.
If `api.filters`/`api.validators` should be real features rather than dead config,
that's a template-wiring task (not example coverage). Note: the generated tree
still has the pre-existing main/auth I001 + pagination-PEP695-on-py311 lint quirks
(auto-fixed by `ruff check --fix`) — TPL-22 territory, not gated by the smoke job.

### P1 template-correctness trio shipped — TPL-5 + TPL-14 + TPL-16 (PR pending)

Branch `claude/nifty-franklin-33emxr`. Completes the template-correctness cluster
that TPL-1/TPL-2 (P0) started.

- **TPL-5 — relationships emit `Mapped[...]`.** `model.py.j2` annotates each
  relationship: `one_to_many` → `Mapped[list["Target"]]`, scalar rels
  (`many_to_one`/`one_to_one`/`one_to_one_inverse`) → `Mapped["Target | None"]`.
  Gated on `rel.target in sibling_entities` so only same-module targets are
  annotated (cross-domain targets aren't importable here → stay unannotated to
  avoid an undefined name under mypy). In per-entity layout, sibling targets get
  an `if TYPE_CHECKING:` import block (combined `from typing import …` with the
  pre-existing `Any` import). `Mapped` was already imported unconditionally.
- **TPL-14 — UUID/`reference` filters typed `UUID`.** `route.py.j2` types a
  reference filter param as `UUID | None` when its `reference_column` is `id`
  (the uuid PK), so `?ref=notauuid` → FastAPI 422 instead of an asyncpg 500. Non-
  `id` (string FK) refs stay `str | None`. New `ns.needs_uuid_filter` scan flag
  drives `from uuid import UUID` (was gated only on a uuid PK).
- **TPL-16 — scalar-with-default is NOT NULL.** `model.py.j2`'s `optional`
  computation now treats a field with a default (explicit, or the implicit
  `False` the boolean branch always emits) as non-Optional `Mapped[T]`. Fixes
  booleans/scalars that had a Python default but were typed `Mapped[T | None]`.

**Verified:** 527 unit tests (+8: `TestDatabaseGeneratorTypedRelationships`,
`TestDatabaseGeneratorNullability`, `TestApiRoutesUuidReferenceFilter`), RED→GREEN
confirmed (5 fail with templates stashed). `make lint` clean,
`make smoke-example` → 135/135. Generated tree ast-parses + `ruff check` clean;
`mypy` on a generated model file shows no `name-defined` errors for the typed
forward refs.

### Working method (apply to every fix)

1. **RED→GREEN**: add/adjust a test that fails before the fix, passes after.
2. **Regenerate into a CLEAN tree** (inputs only — `models/` + `.model-generator.yaml`),
   never over the stale `tmp/genout`: infra files (`utils.py`, `auth_router.py`,
   root `conftest.py`, `main.py`) are **skip-if-exists**, so they only re-emit
   into a fresh dir, and the regenerated routes import from them.
3. `make test` (full suite, ~481 + new) and `make lint` (ruff + mypy strict) clean.
4. `ast.parse` the emitted tree; the only accepted lint quirk is `E402` in
   generated `alembic/env.py` (see TPL-3 to fix that too).
5. One PR per cluster; conventional-commit messages.

Note: this repo's stale-doc/test-count issues (DOC-11) are themselves backlog
items — this header supersedes the older "457 tests / mutmut arc" state below.

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

### Review backlog P0 arc — SEC-1, TPL-2, WIZ-1 (2026-06-21, PRs #35–#37)

Three remaining P0 items from the 2026-06-21 multi-lens code review, each in its
own PR. 512 tests, `make lint` clean after each merge.

- **SEC-1 (PR #35)** — `_validate_auth_scope_coverage()` added to `generate.py`.
  Warns at generation time when `auth.strategy` is set but zero API-enabled
  entities declare `api.scope`. Example spec updated: Portfolio, ApiKey, UserSession,
  and UserRole gain `"scope": {"owner_field": "user_id"}`. Usage-guide section
  added explaining that CRUD is unauthenticated by default and `api.scope` is the
  opt-in. 5 new tests in `TestValidateAuthScopeCoverage`.
- **TPL-2 (PR #36)** — `generate_factories()` in `generators/database.py` computes
  a `table_to_entity` dict (`table_name → EntityName`) and passes it to every
  `template.render()` call. `factory.py.j2` now resolves `reference_table` via
  this dict (instead of the nonexistent `field.reference_entity` key) in both the
  import-scan loop and the `generate_field_factory` macro. Fixes `IntegrityError`
  at `Factory.create()` for any FK reference field. 1 new test:
  `test_required_reference_emits_subfactory_without_reference_entity`.
- **WIZ-1 (PR #37)** — `_prepare_infra_modules()` helper extracted from `main()`.
  Collects domains/route_modules/factory_modules/extra_deps, calls
  `_validate_auth_strategy` + `_validate_auth_scope_coverage`, and returns all
  five values. `main()` and `wizard/actions/generate.py:run_generate()` both call
  it. Closes two bugs: wizard generated `pyproject.toml` missing auth deps
  (bcrypt/itsdangerous/email-validator/slowapi), and wizard skipped the auth-
  strategy cross-model validation. 2 new tests in `TestPrepareInfraModules`.

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

**Gemini review (PR #29) — all 7 comments applied.** `request_limit.py.j2`:
`deque` + `popleft` for O(1) replay (a list's `pop(0)` is O(N), so replaying
many small chunks was O(N²) — a DoS footgun in the DoS-defense middleware);
`return` immediately on `http.disconnect` instead of replaying a half-body
downstream. `errors.py.j2`: strip only the leading `loc` source marker
(`body`/`query`/…), not every occurrence, so a field legitimately named "body"
isn't mangled. `infrastructure.py`: `_app_config()` helper resolves `app` to
`{}` when misconfigured as a non-dict (avoids `AttributeError`). +5 tests
(→ 481); a runtime ASGI probe confirms the chunked deque-replay, disconnect,
and Content-Length paths. CI green (lint + test 3.11/3.12).

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
