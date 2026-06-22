# Code Review & Issue Backlog — model-generator

**Date:** 2026-06-21 · **Reviewed at:** `main` @ `690e492` (v0.1.4) · **Reviewer:** Claude (Opus 4.8)

## How this was produced

A 10-lens multi-agent review (architecture/product, generator engine, wizard,
data/API templates, infra templates, security, tests, examples, docs,
typing/tooling) fanned out over **both** codebases a generator owns: the
generator itself (`src/`, ~14k LOC) and the **actual generated output**
(the example was generated fresh into `tmp/genout/`, ~11.5k LOC, so reviewers
diffed *intent* against *emitted Python*). Every bug/security/correctness claim
was then handed to an independent skeptic agent that tried to **refute** it
against the real code. 47 agents, ~1.96M tokens.

- **2 findings were rejected** by verification and dropped (see *Verified-Clean*).
- Severities below are the **verifier-adjusted** values, not the finders' first guess.
- IDs are stable and queue-ready (see *Working this backlog* at the end).
- Effort: **S** = <30 min · **M** = hours · **L** = day+.

---

## Part A — Direct answers to your 10 questions

**1. Is the main idea useful & realistic?** Yes. A spec-driven, one-shot FastAPI
scaffolder is coherent, and you've proven it in real projects. The central
tension is the **one-shot / no-upgrade model**: it's sold as "generate once, own
forever," but `--clean` (docs) and the CHANGELOG ("adopters should regenerate to
pick these up", ×4) keep implying a regeneration *upgrade* path that doesn't
really exist — and because infra templates are skip-if-exists, the security
fixes you shipped in 0.1.x (the CORS hole, the errors leak) **never reach an
already-generated project**. Pick a lane: either commit to one-shot in the docs,
or document a safe re-adopt workflow. (PROD-1, DOC-7)

**2. Are the scripts correct / simplifiable?** Mostly correct and unusually
well-validated. Real bugs: config is read from `cwd` while the project root is
resolved separately (GEN-1); `conftest_generator` bypasses your comment-stripping
loader and crashes on `//`-commented specs (GEN-2); `model-val` and `model-gen`
disagree on legacy index shapes (GEN-3); the post-gen lint step swallows failures
*and* uses `shell=True` (GEN-4); `--dry-run` still creates dirs on disk (GEN-7);
no file I/O sets `encoding="utf-8"` (GEN-8, Windows). Simplification: `_find_project_root`
is copy-pasted 5× with two behaviors (GEN-5), plus a no-op `config/project_config`
double-param and a duplicated write-loop (TOOL-7/8).

**3. Do the templates do what's expected — too much / too little / simplifiable?**
Faithful overall, but all three problems exist. **Too much:** `constraints.py`
emits ~16 helper functions + generic constants nothing imports (the "single
source of truth" actually inlines its SQL — TPL-7); two `_shared/` macro files
are dead (TPL-8); every response model carries dead `from_attributes=True`
(TPL-11). **Wrong:** datetimes serialize as `isoformat()+"Z"` → invalid on
Postgres (TPL-1); factories omit required FK columns (TPL-2); relationships lack
`Mapped[...]` (TPL-5). **Simplify:** gate constraint/helper emission on actual use.

**4. Does it work right — files in the right place, flexible enough, forcing too
much?** The config-driven layout (paths, `python_root`, per-entity/per-domain)
is genuinely flexible. It *forces*: async SQLAlchemy + FastAPI, and bcrypt-session
as the **only** auth. Fragile bits: project-root heuristics (PROD-3) and the
cwd↔config coupling (GEN-1). One file is misplaced — factories ship **inside the
production package** but import dev-only `factory`/`faker` (TPL-15).

**5. Are the examples complete enough?** No — one kitchen-sink example with large
blind spots. The headline owner-scoping feature (`api.scope`) is used by **zero**
entities even though auth is on (EX-1). Never exercised: composite FK,
one_to_one/many_to_many, `integer`/`binary` types, most constraint kinds,
per-domain layout, `tests.scenarios`/`field_validations` (EX-2…7). Add a **minimal
no-auth example** and extend coverage. The example's own `.gitignore` excludes
the generated code — contradicting "you own it" (EX-8).

**6. Are the tests enough?** The generator suite is large and better than average
(it really exec()s factories, runs `registry.configure()`, drives the ASGI
middleware). But the single highest-value check is missing: **nothing regenerates
the example and runs its contract suite in CI** (TST-1) — and that suite can't
even pass, because `APP_PASSWORD_PEPPER` is never set in the harness (TST-2). The
auth router/CSRF (your most security-sensitive output) is only string-matched
(TST-3); the full tree is never `ast.parse`d (TST-4).

**7. Resulting files — missing or excess?** *Missing:* `.env.example` (the app
needs ~9 env vars — TPL-9), a per-file `E402` ignore so `ruff check .` is green
out of the box (TPL-3), a production `DATABASE_URL` guard (TPL-4). *Excess:* the
constraints helpers, dead macros, `from_attributes`, `asyncio_mode` with no
pytest-asyncio plugin (TPL-13), and factories in the prod wheel (TPL-15).

**8. Users/login — add more, or are you going too far?** You've already gone far
(full bcrypt-session stack: register/login/logout/reset, CSRF, rate-limit, HMAC
pepper). My recommendation: **stop expanding, finish or demote.** Today it's a
half-measure — one strategy, per-entity-layout-only, no "authenticated but not
owner-scoped" option (PROD-2), undocumented (DOC-1), untested (TST-3), and the
flagship example wires it to **nothing** (SEC-1/EX-1). Do **not** add JWT/OAuth or
RBAC/admin surface — that's the adopter's project. Either make the existing stack
first-class (tested, documented, wired in the example) or split it into a clearly
optional add-on (PROD-4).

**9. Documentation — enough / missing / excessive?** Broad but drifted. *Missing:*
auth scaffolding (DOC-1), architecture overview, troubleshooting, upgrade guidance
(DOC-9), `binary`/`encrypt` (DOC-5). *Wrong:* `extending-generated-code.md` uses
the **sync** API and symbols you never emit (DOC-2); the enum-casing lie persists
in schema + reference (DOC-4); `api.scope` auto-wiring is mis-documented (DOC-3);
the sqlite URL in usage-guide breaks the async engine (DOC-6). *Excessive/leaky:*
the CHANGELOG names downstream projects **and is published verbatim to every
GitHub release** (TOOL-1).

**10. Senior-engineer catch-all.** Tooling drifts from your own global standard
(ruff set narrowed to `E/W/F/I`, line-length 88, py311) **with no comment**, and
the broader set surfaces ~33 real lints incl. `B007`/`UP035`/`PTH123` (TOOL-3);
no `utf-8` encoding anywhere (GEN-8); a project-agnostic violation in a published
artifact (TOOL-1); mass-assignment on `ApiKey` create (SEC-6); type-inference
regressions from missing `Mapped[...]` (TPL-5).

---

## Part B — Issue backlog (prioritized)

### P0 — Ships broken/insecure code to every adopter (fix first)

#### SEC-1 · Generated CRUD is unauthenticated by default; the flagship "auth" example ships a fully-open API
*Security · effort M · Q5/Q8 · verified (critical→high)*
The route template only injects `Depends(get_current_user)` + the ownership
filter inside `{% if scope %}` (`templates/api/route.py.j2:159-213`). The example
turns on the full auth stack (`.model-generator.yaml:71`) but **no entity declares
`api.scope`**, so `GET /api/v1/users` enumerates all users, and anyone can
`POST`/`DELETE` sessions, api-keys and portfolios for any `user_id`. The generated
`get_current_user` is imported by **no** route. Nothing warns.
**Fix:** (a) warn/fail at generation when `auth.strategy` is set but an entity is
neither scoped nor explicitly `api.public`; (b) add `api.scope` to the owner-bound
example entities; (c) document that CRUD is open unless scoped. (Pairs with PROD-2.)

#### TPL-1 · Datetimes serialize as `isoformat() + "Z"` → invalid on Postgres (tests can't catch it)
*Bug · effort S · Q3/Q7 · verified high · (also found in direct review)*
`templates/api/route.py.j2:486,501,504` emit `...isoformat() + "Z"`. Columns are
`DateTime(timezone=True)`; on asyncpg/psycopg (Postgres) `isoformat()` already
yields `+00:00`, so output becomes the malformed `...+00:00Z`. SQLite (the test
backend) returns naive datetimes, so the suite is green while production is broken.
**Fix:** drop the manual `"Z"` (or normalize to UTC: `dt.astimezone(UTC).isoformat().replace("+00:00","Z")`). Update the contract tests' `.replace("Z","+00:00")` normalization too.

#### TPL-2 · FactoryBoy factories omit required FK columns (SubFactory keys on a field that never exists)
*Bug · effort M · Q3/Q7 · verified high*
The factory template emits/imports references only when `field.reference_entity is
defined` (`factory.py.j2:55-57,214-219`), but the schema/specs use
**`reference_table`** — `reference_entity` is set nowhere. So required FK columns
get no factory value and the SubFactory import block is dead → `EntityFactory.create()`
raises `IntegrityError` for any entity with a required reference (PortfolioAsset,
UserRole, …). Hidden because no generated test calls the factories.
**Fix:** resolve the target from `reference_table` and emit `SubFactory` for required
refs, or drop the dead `reference_entity` machinery and document explicit FK passing.

#### WIZ-1 · Wizard generates an *uninstallable* `pyproject.toml` (and skips auth validation)
*Bug · effort M · Q2 · verified (critical→high)*
`wizard/actions/generate.py:143-152` re-implements `main()`'s infra-prep but omits
`extra_deps` (`_compute_auth_extra` + model `dependencies`) **and**
`_validate_auth_strategy`. A wizard-generated auth project gets a `pyproject.toml`
missing bcrypt/itsdangerous/email-validator/slowapi — and since `pyproject.toml`
is skip-if-exists, the adopter **cannot recover by re-running.**
**Fix:** extract `main()`'s infra-prep into one shared helper called by both paths
(also closes TOOL-9, the drift).

#### TST-2 · Generated contract suite is red out of the box — `APP_PASSWORD_PEPPER` never set
*Test-gap · effort S · Q6 · verified high (completeness critic)*
With auth on, `_peppered()` raises unless `APP_PASSWORD_PEPPER` is set
(`auth/router.py:80-87`). The fixtures register via `/auth/register`; the generated
root conftest sets **no** env vars, and no doc tells the adopter to export it →
`/auth/register` 500s → the whole suite cascades. (You hit this manually by
exporting the var; a fresh `pytest` does not.)
**Fix:** `os.environ.setdefault(pepper_env, ...)` + a dev `SESSION_SECRET_KEY` in
`conftest_root.py.j2`, or document the required env vars in a generated README.

#### SEC-2 · Password reset/change does not revoke existing sessions
*Security · effort S · Q8 · verified high*
`reset_password`/`change_password` only rewrite `password_hash`
(`auth/router.py:387-411`). `get_current_user` never re-checks the hash, so after a
victim resets their password to evict an attacker, the attacker's DB session stays
valid for the full 7-day TTL.
**Fix:** `UPDATE user_session SET is_active=False WHERE user_id=...` after rotating
the hash (optionally keep the caller's current session on change-password).

#### SEC-3 · Password-reset token is replayable for its full TTL (no single-use)
*Security · effort M · Q8 · verified high*
The reset token is a stateless `itsdangerous` `{"user_id": ...}`; `reset_password`
validates signature+age only and invalidates nothing (`auth/router.py:352,370-395`).
A leaked link (logs, history, forwarded email) is re-usable for up to an hour, even
after the legitimate reset.
**Fix:** bind the token to mutable state (a per-user nonce, or a hash of the current
`password_hash`) so it self-invalidates on first use.

### P1 — High-impact correctness / quality (fix soon)

#### TST-1 · The generated example's contract suite is never run in CI
*Test-gap · effort M · Q6 · verified high*
CI only runs `pytest tests/`. No job regenerates the example and runs its emitted
suite; `test_full_generation.py` only does substring checks. A template change that
emits importable-but-broken code ships green. **This is the single highest-value
missing test.** **Fix:** add a CI job that generates into a tmp tree, `uv sync`es
it, and runs `pytest --collect-only` + a smoke subset.

#### DOC-2 · `extending-generated-code.md` teaches the sync API and symbols you never emit
*Docs · effort M · Q9 · verified high*
The generated stack is async (`get_session() -> AsyncGenerator[AsyncSession]`), but
the guide uses `from sqlalchemy.orm import Session`, `db.query(...)`,
`from ...database.session import get_db`, and `api/models/user.py` — none of which
exist. An adopter copy-pasting it gets `ImportError` on line 1.
**Fix:** rewrite for async (`AsyncSession`, `await session.execute(select(...))`,
`Depends(get_session)` from `database.engine`); fix the per-entity file names; drop
the hand-rolled reset-password (the auth router already has it).

| ID | Title | Sev | Eff | Q | Status |
|----|-------|-----|-----|---|--------|
| PROD-2 | No way to require auth **without** owner-scoping (`scope.owner_field` is required) — add `api.require_auth`/`auth_level` | med | M | Q8 | verified (high→med) |
| TPL-5 | Relationships emitted without `Mapped[...]` → `obj.user`/`obj.assets` lose typing under py.typed/mypy-strict | med | M | Q10 | verified |
| TPL-7 | `constraints.py` over-generates ~16 unused helpers + generic constants; model inlines SQL so "single source of truth" is false | med | M | Q7 | verified |
| TPL-3 | Generated `alembic/env.py` violates `E402` but emitted `pyproject` has no per-file-ignore → `ruff check .` red out of the box | med | S | Q7 | verified |
| TPL-4 | Engine silently falls back to ephemeral SQLite in production (no `APP_ENV=production` guard, unlike the session secret) | med | S | Q7 | verified |
| TPL-9 | No `.env.example` / env-var manifest despite ~9 required env vars | med | M | Q7 | verified |
| GEN-1 | `load_config` reads `.model-generator.yaml` from `cwd` only; if root is resolved elsewhere, adopter config is silently ignored | med | S | Q2 | verified (high→med) |
| GEN-8 | All file I/O omits `encoding="utf-8"` → Windows mojibake/UnicodeError; also violates your PTH standard | med | S | Q2 | verified (critic) |
| WIZ-2 | `questionary` imported unconditionally though it's an optional extra → `--interactive` crashes on base install; the "plain input" fallback is dead code & the docstring lies | med | S | Q2 | verified (high→med) |
| WIZ-3 | No Ctrl-C/ESC handling: `.ask()` returns `None` → silent infinite re-prompt / `TypeError` in checkbox | med | S | Q10 | verified |
| TST-3 | Auth router + CSRF (highest-stakes output) only string-matched, never `ast.parse`/exec'd | med | S→M | Q6 | verified (high→med) |
| SEC-9 | Infra security fixes (CORS `*`+credentials, error column-name leak) are skip-if-exists → never reach existing adopters; example's local infra is stale | med | S | Q5 | verified |
| DOC-1 | §12 auth scaffolding (`auth.strategy`, `pepper_env`, auto-wired `dependency_path`) is entirely undocumented | med | M | Q9 | verified (high→med) |
| TOOL-1 | CHANGELOG names downstream projects (`oms`, `ml-engine`) **and** is published verbatim as every GitHub release body (`release.yml --notes-file CHANGELOG.md`) | med | S | Q9/Q10 | verified (critic) |
| TOOL-3 | ruff lint set narrowed to `E/W/F/I` (drops `B/SIM/UP/PTH/RUF`), line-length 88, py311 — no explanatory comment; broader set finds ~33 real issues | med | M | Q10 | verified |

### P2 — Medium (worth doing)

| ID | Title | Sev | Eff | Q | Status |
|----|-------|-----|-----|---|--------|
| TPL-6 | `percentage` is a 0–1 fraction but descriptions say "0-100%" and column is `Numeric(5,4)` — mismatch baked into the type | med | S | Q3 | verified |
| TPL-10 | `_get_fernet`/TypeDecorator methods in `encrypted_bytes.py` are unannotated → fail the strict mypy config you also ship | med | S | Q3 | verified |
| TPL-12 | Generated fixtures hardcode a **past** `2025-01-01` for all datetimes incl. `expires_at`; inconsistent with the `2099` update payloads (time-bomb) | med | S | Q6 | verified (critic) |
| TPL-14 | UUID/`reference` filters typed `str \| None` → `?ref=notauuid` raises on asyncpg (500, not 422) — same class as the datetime P1 fix, left open for refs | med | S | Q7 | *direct review (unverified by workflow)* |
| GEN-2 | `conftest_generator` uses raw `json.load` → crashes on `//`-commented specs the rest of the pipeline supports | med | S | Q2 | verified |
| GEN-3 | `validate.py` skips `_normalize_indexes` → `model-val` rejects legacy index shapes that `model-gen` accepts | med | S | Q2 | verified |
| GEN-4 | `quality.py` swallows ruff failures + no-ops when ruff absent (ships unformatted/col-0 auth code) + `shell=True` string interpolation | med→low | S | Q2/Q7 | verified (downscoped) |
| GEN-6 | `migration-autogen` instructions hardcode TimescaleDB/docker-compose (project-specific) + print a misleading "Running alembic…" line | med | S | Q4 | verified (critic) |
| WIZ-4 | Wizard can't set `--no-root-files`; loses parity with the CLI scratch-and-migrate workflow | med | S | Q2 | verified |
| WIZ-5 | `run_generate` core logic untested (only a mocked-dispatch test) — the exact path with WIZ-1's bug | med | M | Q6 | verified |
| TST-5 | Cross-domain relationship/mapper config never probed end-to-end (`registry.configure()` only runs on one composite-FK model) | med | M | Q6 | verified |
| TST-6 | Generators never tested against schema-invalid-but-plausible specs (load_model only warns, then generates) | med | M | Q6 | verified |
| TST-7 | Generated output never type-checked/linted in tests despite the "mypy-strict, exemplary" claim | med | M | Q10 | verified |
| EX-2 | No example exercises `api.scope` / `api.validators` / `api.filters` | med | M | Q5 | verified |
| EX-3 | Composite FK and one_to_one/many_to_many never exercised (UserRole is a hand-split join, not many_to_many) | med | M | Q5 | **closed** — composite-FK exercised in `examples/catalog-api` (Warehouse+StockEntry, `api.enabled:false`); one_to_one shipped PR #49 |
| EX-4 | `integer`/`binary` field types and `pattern`/`range`/`positive` constraints have zero example coverage | med | M | Q5 | verified |
| EX-5 | `encrypt` is **absent from the field schema** (`additionalProperties:false`) → encrypted-binary can't be expressed in a valid spec; only "works" because load_model is warn-only | med | S | Q5/Q9 | verified |
| EX-8 | No minimal no-auth example; per-domain layout undemonstrated by any bundled config | med | M | Q10 | **closed** — `examples/catalog-api` is the minimal api-key/per-domain example; `make smoke-catalog-api` + CI `generated-catalog-api` job added |
| EX-9 | Example's `.gitignore` excludes `src/`, `tests/`, `alembic/` from VCS — contradicts "you own the code" and hides the generator's own gitignore template | high | S | Q5 | verified (critic) |
| DOC-3 | json-spec-ref says `api.scope` needs a manually-written `dependency_path` ("the generator does not emit it") — false when `auth.strategy` is set (loaders auto-wire it) | med | S | Q9 | verified |
| DOC-4 | Enum-casing lie: schema + reference say values are lowercase; generator UPPERCASEs everything | med | S | Q9 | verified |
| DOC-5 | `binary` type + `encrypt` missing from every field-type table/reference; `integer` alias undocumented | med | S | Q9 | verified |
| DOC-6 | usage-guide tells users to set a **sync** sqlite URL that breaks the async engine | med | S | Q9 | verified |
| DOC-7 | "No regeneration" philosophy vs documented `--clean` regenerate + CHANGELOG "should regenerate" (×4) — reconcile the upgrade story | med | S | Q9 | verified |
| DOC-8 | CLAUDE.md "Running the Example" runs from repo root → silently drops project config (README gets it right) | med | S | Q9 | verified |
| DOC-9 | No architecture overview / troubleshooting / upgrade-after-one-shot guidance | med | M | Q10 | verified |
| PROD-4 | Bundled auth is scope-creep-as-half-measure (single strategy, single layout, untested, unwired) — decide: first-class vs optional add-on | med | L | Q1 | **closed (first-class)** — two strategies (bcrypt-session + api-key), CI smoke tests (TST-1 + new `generated-catalog-api`), SEC/TPL P0s shipped, full docs; no further architectural change needed |
| SEC-5 | `forgot-password` returns 501 only when the user exists → account-enumeration oracle (contradicts its own docstring) | med | S | Q8 | verified *(also direct review)* |

### P3 — Low / polish (batch these)

| ID | Title | Sev | Eff | Q | Status |
|----|-------|-----|-----|---|--------|
| TPL-8 | Dead template macros: `_shared/_examples.j2`, `_shared/_fields.j2` (imported by nothing) | low | M | Q3 | verified |
| TPL-11 | Response models set `from_attributes=True` but are always dict-constructed (dead/misleading config) | low | S | Q7 | verified |
| TPL-13 | Generated `pyproject` sets `asyncio_mode="auto"` but no pytest-asyncio dep and only sync tests | low | S | Q7 | verified (critic) |
| TPL-15 | Factories live in the production package but import dev-only `factory`/`faker` → unsatisfiable in a prod install | low | M | Q7 | verified (critic) |
| TPL-16 | Boolean (and all scalar) fields with a `default` emitted as nullable `Mapped[T \| None]` | low | S | Q10 | verified |
| TPL-17 | Glued `}  # ==== Field Validators ====` line in every create-request model | low | S | Q7 | verified |
| TPL-18 | `sort_by` whitelist includes `api_exclude_response` columns (password_hash, key_hash) — sortable secrets | low | S | Q7 | verified |
| TPL-19 | Invalid `sort_by` value is silently ignored (no order applied) instead of 422 | low | S | Q7 | *direct review* |
| TPL-20 | Factory docstring glues "Usage:" onto the first import line | low | S | Q7 | verified |
| TPL-21 | alembic `env.py` hardcodes `PortableNumeric`/`PortableUuid` names (must stay in sync with `types.py`) | low | S | Q3 | verified |
| TPL-22 | Generated `requires-python`/`python_version` lags your own 3.12 default | low | S | Q7 | verified |
| TPL-23 | auth-router `request`/`payload` parameter ordering inconsistent across endpoints | low | S | Q3 | verified |
| SEC-4 | Session cookie + reset token share one serializer, no `salt=` separation (defense-in-depth) | low | S | Q8 | verified (med→low) |
| SEC-6 | `CreateApiKeyRequest` allows mass-assignment of `user_id`/`key_hash`/`permissions`/`is_active` (harden the example spec) | low | S | Q7 | verified (med→low) |
| SEC-7 | Rate-limit keys on socket peer IP → useless behind a reverse proxy; undocumented | low | S | Q8 | verified |
| SEC-8 | Entity-name keys & free-text descriptions unvalidated/unescaped → codegen injection / broken docstrings | low | M | Q2 | verified |
| GEN-5 | `_find_project_root` duplicated 5× with two divergent behaviors | low | S | Q10 | verified |
| GEN-7 | `generate_migration_init` creates dirs on disk even in `--dry-run`/`--diff` | low | S | Q2 | verified |
| GEN-9 | `// comment` stripper corrupts JSON string values containing ` //` (clean `sys.exit`, not a crash) | low | S | Q2 | verified |
| GEN-10 | `_validate_paths_base`/loaders can `AttributeError` when `paths`/`auth` overridden as a non-dict | low | S | Q2 | verified |
| GEN-11 | `snake_case` mangles consecutive capitals (`APIKey`→`a_p_i_key`) — Python & Jinja agree, but ugly | low | M | Q10 | verified |
| GEN-12 | `generate_migration_autogen` returns a `dict` with no `path`/`content`, intercepted by a fragile `instructions` check | low | S | Q10 | verified |
| EX-6 | Entity-level table constraints (`check`/`unique`/`depends`) never used by any example | low | S | Q5 | verified |
| EX-7 | `tests.scenarios`/`field_validations` never demonstrated (custom-tests deep-dive has no backing example) | low | S | Q5 | verified |
| TST-8 | No unicode/special-char field-content tests; no large-spec test | low | S | Q6 | verified |
| TST-9 | `slow` marker registered but applied to nothing → `make test` == `make test-all` | low | S | Q2 | verified |
| TST-10 | Model-spec dicts duplicated inline across CLI/integration tests | low | S | Q6 | verified |
| TST-11 | CI test matrix runs 3.11 but lint/mypy target 3.12 — unexplained | low | S | Q2 | verified |
| DOC-10 | CLI Targets/Options tables omit real targets (`base`/`engine`/`main`/`migration-autogen`) & flags (`--no-root-files`/`--version`) | low | S | Q9 | verified |
| DOC-11 | `status/next-session.md` header/test-count stale vs CHANGELOG | low | S | Q9 | verified |
| DOC-12 | CHANGELOG compare-links stop at 0.1.1 though entries reach 0.1.4 | low | S | Q9 | verified |
| DOC-13 | README test-suite table omits `test_cleanup`/`test_enum_examples`/`test_validate` | low | S | Q9 | verified |
| DOC-14 | usage-guide wizard install uses a stale `pip install -e "model-generator/[interactive]"` path | low | S | Q9 | verified |
| TOOL-2 | `_find_project_root` heuristics make "where do files land" non-obvious for nested/monorepo layouts | low | M | Q4 | verified |
| TOOL-4 | Half-applied dispatch table (8 identity-lambda wrappers + parallel if/elif); `env` typed `Any` | low | M | Q10 | verified |
| TOOL-5 | Vestigial `config`/`project_config` double-param (no-op self-merge in `generate_pyproject`) | low | S | Q2 | verified |
| TOOL-6 | Loaders use bare `jsonschema.validate` while `validate.py` pins `Draft7Validator` | low | S | Q2 | verified |
| TOOL-7 | Output-writing loop duplicated in `generate.py` and `infrastructure.py` | low | M | Q10 | verified |
| TOOL-8 | `*_response.py` (singular) vs `*_requests.py` (plural) — permanent naming inconsistency for adopters | low | S | Q7 | verified |
| TOOL-9 | No-op `if` branch + redundant `as load_model` self-alias in `generate.py` | low | S | Q10 | verified |
| TOOL-10 | Duplicate dev-dependency declarations (`optional-dependencies.dev` + `dependency-groups.dev`) | low | S | Q10 | verified |
| TOOL-11 | CI runs only the narrowed `ruff check .`; lint never runs on the min supported Python | low | S | Q2 | verified |

---

## Part C — Verified-Clean (checked and cleared)

- **`--target all` is NOT broken.** A finder claimed it emits auth-dependent
  conftest/main without the auth subsystem (→ red suite); verification refuted it
  with static evidence and my own fresh generation confirms `all` emits `auth/`
  and `main.py` mounts it. (The real red-suite cause is the missing
  `APP_PASSWORD_PEPPER` — TST-2.)
- **`_extract_ref` shared `seen` set is NOT a bug.** Refs are constant *definitions*
  keyed by name, not per-bound usages; deduping is correct, and the proposed
  "fix" would emit duplicate top-level assignments.
- **Generator security surface is sound:** `yaml.safe_load` everywhere, no
  `eval`/`exec`, output paths derived from adopter-trusted config. (The codegen
  injection vector SEC-8 is robustness, not remote exploit.)
- **Packaging is correct:** `py.typed`, schema JSON, and templates are included in
  wheel+sdist; Alembic `target_metadata` wiring verified.

---

## Part D — Working this backlog

**Suggested order:** P0 (7 items) → P1 → then batch P3 by file (most are
one-liners in `route.py.j2`, `pyproject.toml`, the docs). Natural groupings that
fix several at once:

- **One auth PR:** SEC-1, SEC-2, SEC-3, SEC-5, PROD-2, EX-1, DOC-1, DOC-3.
- **One template-correctness PR:** TPL-1, TPL-2, TPL-5, TPL-14, TPL-16.
- **One "generated project is green out of the box" PR:** TPL-3, TPL-4, TPL-9,
  TST-1, TST-2.
- **One wizard PR:** WIZ-1 + TOOL-9 (shared infra-prep helper) closes WIZ-1/5 +
  TOOL-9 drift; add WIZ-2/3/4.
- **One docs sweep:** DOC-2,4,5,6,7,8,9,10,11,12,13,14.
- **One tooling/hygiene PR:** TOOL-1 (+ scrub release notes), TOOL-3, GEN-8.

**Queue-ready:** each ID can become a `claude-arsenal` task — e.g.
`queue-add --title "TPL-1: drop manual Z from datetime serialization" --priority 90 --tag templates`,
then a payload `.md` pointing at the cited file:line and the acceptance gate
("generated routes round-trip a tz-aware datetime through `datetime.fromisoformat`").
`claude-arsenal` is **not** initialized in this repo (no `claude-arsenal/`), so
seeding the queue first needs `/init`. Say the word and I'll scaffold it and seed
the P0/P1 rows, or just knock out the handful of one-line P0/P3 fixes directly.
