# Next Session Plan

## Current State (2026-04-25, end of day)

Review batch §8, §13, §14 merged to `main`. §9 is on `feat/9-owner-scoping` (PR #10), opened today.

- `e3a390f` — PR #7 `feat(infrastructure): surface opt-in style overrides` (§14)
- `cc1cb42` — PR #8 `feat: add binary field type support` (§8)
- `da30d84` — PR #9 `feat: add encrypted binary field support` (§13)
- `78f2ff4` — PR #10 `feat: add owner-scoped endpoints (api.scope) (§9)` — **open**, awaiting merge

308 tests passing on `feat/9-owner-scoping`, `ruff check .` + `ruff format --check .` clean, `mypy src` clean.

---

## Priority Next Session — Remaining Review Items (§12, §15) + §9 follow-ups

### §9 follow-ups (from PR #10 review)

Gemini-code-assist left 5 inline comments on PR #10. Disposition (user-approved 2026-04-25):

| # | Severity | Disposition | Note |
|---|----------|-------------|------|
| 1 | HIGH | **False positive — replied** | Claimed `auth_dep_func` `{% set %}` inside `{% if %}` is unreachable. Jinja2 `{% if %}` does not introduce a scope barrier; only `{% for %}` / `{% block %}` / `{% macro %}` do. The 9 scope-rendering tests pass, which directly disproves the claim. |
| 2 | HIGH | **False positive — replied** | Same scoping claim, additional locations. Same disposition. |
| 3 | MEDIUM | **Skipped** | `{{ inject_from }}.id` hardcodes the PK attr name. A configurability knob conflicts with simplicity-first; current shape assumes the dependency returns an object with `.id` (the conventional shape for User-returning auth deps). Revisit only if an adopter actually needs it. |
| 4 | MEDIUM | **Skipped** | Raw `HTTPException` for `miss_status != 404` skips the project's `format_*` helpers. Default 404 already uses the helper; non-404 is opt-in. Adding `format_forbidden_error` would be feature creep. |
| 5 | MEDIUM | **Fixed in PR #10** | `contract.py.j2` hardcoded `.main` won't work for adopters whose entry-point file isn't `main.py`. Fixed by deriving the module name from `config.paths.main.rsplit('/', 1)[1] | replace('.py', '')`; regression test added (`TestApiTestsGeneratorScope`). |

### §12 — Auth scaffolding (nice-to-have)

**What:** `auth: {strategy: "bcrypt-session", pepper_env: "APP_PASSWORD_PEPPER"}` → generates a starter auth router (register / login / logout / forgot / reset / change-password) with bcrypt+pepper hashing, itsdangerous session cookies, CSRF middleware, and rate limiting on login/register.
**Depends on:** User entity with `password` field (already present in the user-auth example).
**Surface:** new `templates/infrastructure/auth_router.py.j2` + session middleware hook into `main.py.j2`.
**Estimated scope:** 2–3 days. Biggest item of the batch — substantial new template surface; should be broken into its own multi-commit plan.

### §15 — One-file-per-entity (nice-to-have)

**What:** Optional emit mode where each entity writes to `models/<entity>.py` instead of one file per domain.
**Motivation:** large domains (10+ entities) produce 1000+ line files that IDEs choke on.
**Surface:** config flag `generation.layout: "per-entity" | "per-domain"`; the domain-level loop in `model.py.j2` / `factory.py.j2` / `contract.py.j2` is split to emit N files. Imports in `route.py.j2` and `tests/conftest.py` need updating to match.
**Estimated scope:** 1–2 days — touches many templates, but is mostly a refactor, not new functionality.

### Sequencing recommendation

1. **Merge PR #10** (§9 owner-scoping) once review settles.
2. **§15** (one-file-per-entity) — standalone refactor; lower risk than §12 and unblocks better IDE ergonomics for large domains.
3. **§12** (auth scaffolding) — last, most ambitious; benefits from §9 already landing.

### Incidental follow-ups still open

- **Composite-FK `__table_args__` emission.** `model.py.j2` emits N separate `ForeignKey(...)` columns for a multi-column FK instead of a single `ForeignKeyConstraint` in `__table_args__`. SQLAlchemy's `configure_mappers()` raises `AmbiguousForeignKeysError` when two entities (or one entity, as in self-ref) share multiple FK paths — even when both sides specify `foreign_keys`. Affects any composite-FK relationship. Scope: new spec shape (`relationships[].composite_fk: true`?) + `__table_args__` emission change. Not blocking any current adopter.
- **Upstream fix in `nuncaeslupus/my-skills`.** Gemini-bot correctly flagged on PR #3 that `.claude/skills/mutmut-report/analyze_mutmut.py`'s `run_cmd` should raise rather than `sys.exit(1)`. Fix belongs upstream — file a PR against `nuncaeslupus/my-skills`, then pull via `git subtree pull --prefix=.claude/skills shared-skills main --squash`.
- **`make lint` runs mypy across the whole tree.** `make lint` invokes `mypy . --explicit-package-bases`, which trips on gitignored generated output in `examples/*/backend/` (3.12 generic syntax under a 3.11 mypy pin). CI doesn't see this because the files aren't checked in. Options: (a) add `examples/*/backend` to mypy `exclude` in root `pyproject.toml`; (b) tighten `make lint` to `mypy src`. Not blocking any feature.
- **`make lint` does not run `ruff format --check`.** Discovered while shipping PR #10 — CI runs both `ruff check` and `ruff format --check`, but `make lint` runs only the former. PR #10's first CI run failed because `tests/test_generators.py` wasn't formatted to canonical style. Add `ruff format --check .` to the `lint` target so the local pre-commit checklist matches CI.

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

### §9 — Owner-scoped endpoints (2026-04-25, PR #10 open)

Branch `feat/9-owner-scoping`, commits:
- `78f2ff4` — feat: add owner-scoped endpoints (api.scope) (§9)
- *(pending)* — fix: address PR #10 review (formatter + contract import + regression test)

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
