# Next Session Plan

## Current State (2026-04-19)

Stable release. 9 of 15 items from the 2026-04-19 template-level external review landed on `main`. Plus the `.claude/skills/` subtree was formally re-imported from `shared-skills` (`https://github.com/nuncaeslupus/my-skills`) so future upstream skill updates can be pulled via `git subtree pull`.

- `2bf39c6` — PR #2 `fix: external review follow-up — 9 of 15 items shipped` (squashed; included gemini-bot follow-up for JSON default lambda emission + composite-PK `remote_side`).
- `8a34eb3` — PR #3 `chore(skills): re-import .claude/skills as a git subtree` (squashed).

290 tests passing, `ruff check src tests` clean, `mypy src` clean on `main`.

---

## Priority Next Session — Remaining Review Items (§8, §9, §12–§15)

Six items from the 2026-04-19 review were explicitly deferred with user approval. Each needs its own plan before implementation; sketches below.

### §8 — `binary` field type (blocker)

**What:** `{"type": "binary"}` → SQLAlchemy `LargeBinary`, Pydantic `bytes`, factory `secrets.token_bytes(...)`.
**Why deferred:** new type cuts across config + model + Pydantic + factory + contract tests; wanted a dedicated plan.
**Surface to edit:**
- `stacks/python-fastapi/config.yaml` — add binary to the field-type table.
- `templates/database/model.py.j2` — add `ns.has_binary`, emit `Mapped[bytes{optional}] = mapped_column(LargeBinary{, nullable/unique})`.
- `templates/database/factory.py.j2` — new `binary` branch in `generate_field_factory` macro: `factory.LazyFunction(lambda: secrets.token_bytes(32))`.
- `templates/api/models/*.py.j2` (request/response) — `bytes` field type; Pydantic auto-handles base64 in JSON.
- `templates/tests/contract.py.j2` — round-trip `POST` → `GET` assertion.
**Verify:** SQLite BLOB round-trip + Postgres BYTEA round-trip; contract test confirms `POST` body bytes survive `GET` response decoded.
**Blocks:** §13 (encrypted-at-rest depends on this type existing).
**Estimated scope:** ~1 day, ~6 files, mostly mechanical once the type is registered.

### §9 — Owner-scoped endpoints (sharp edge)

**What:** Per-entity `api.scope: {owner_field, inject_from, miss_status}`. When present, every list/get/update/delete handler depends on `current_user`, filters by `entity.owner_field == current_user.id`, and returns 404 (configurable) on cross-owner access.
**Why deferred:** heavy `route.py.j2` changes + a new contract-test scenario; each generator change compounds.
**Surface to edit:**
- `.model-generator.yaml` gains `auth.dependency_path: "backend.src.auth.get_current_user"` (configurable import path).
- `model.schema.json` — new `entity.api.scope` sub-object with `owner_field`, `inject_from`, `miss_status`.
- `templates/api/route.py.j2` — when `scope` is set, inject `current_user: User = Depends(get_current_user)` into 4 handler signatures; add the `.where(owner_field == current_user.id)` filter to every `select()` and `session.get()`; short-circuit to `format_not_found_error` (or custom status) on mismatch.
- `templates/tests/contract.py.j2` — generate a "user B cannot access user A's row" assertion per scoped entity.
**Non-goals:** generator does NOT emit `get_current_user` itself — adopter writes that function; generator only threads it in.
**Estimated scope:** 1–2 days; `route.py.j2` churn is the biggest risk surface.

### §12 — Auth scaffolding (nice-to-have)

**What:** `auth: {strategy: "bcrypt-session", pepper_env: "APP_PASSWORD_PEPPER"}` → generates a starter auth router (register / login / logout / forgot / reset / change-password) with bcrypt+pepper hashing, itsdangerous session cookies, CSRF middleware, and rate limiting on login/register.
**Depends on:** User entity with `password` field (already present in the user-auth example).
**Surface:** new `templates/infrastructure/auth_router.py.j2` + session middleware hook into `main.py.j2`.
**Estimated scope:** 2–3 days. Biggest item of the batch — substantial new template surface; should be broken into its own multi-commit plan.

### §13 — Encrypted-at-rest column modifier (nice-to-have)

**What:** `{"type": "binary", "encrypt": {"key_env": "FERNET_KEY_FILE"}}` → SQLAlchemy `TypeDecorator` wrapping `fernet.encrypt` / `fernet.decrypt`. App code reads/writes raw `bytes`; codec is invisible.
**Hard dependency:** §8. Do not start before the binary type ships.
**Surface:** `templates/infrastructure/encrypted_bytes.py.j2` emits the `TypeDecorator` class; `model.py.j2` emits the decorated column when the field declares `encrypt`.
**Estimated scope:** ~half day on top of §8.

### §14 — Quality-tool defaults per-project (nice-to-have)

**What:** `quality:` section in `.model-generator.yaml` overrides the hardcoded `line-length = 88` (ruff) and `python_version = "3.11"` (mypy) in the generated `pyproject.toml.j2`.
**Why valuable:** adopters on `line-length = 100` / Python 3.12 currently get unnecessary reformat churn on first save.
**Surface:** thread `quality` from config through `generate_pyproject` in `generators/infrastructure.py`; replace the hardcodes in `templates/infrastructure/pyproject.toml.j2` with `{{ quality.line_length | default(88) }}` etc.
**Estimated scope:** ~half day; small surface, high user-value.

### §15 — One-file-per-entity (nice-to-have)

**What:** Optional emit mode where each entity writes to `models/<entity>.py` instead of one file per domain.
**Motivation:** large domains (10+ entities) produce 1000+ line files that IDEs choke on.
**Surface:** config flag `generation.layout: "per-entity" | "per-domain"`; the domain-level loop in `model.py.j2` / `factory.py.j2` / `contract.py.j2` is split to emit N files. Imports in `route.py.j2` and `tests/conftest.py` need updating to match.
**Estimated scope:** 1–2 days — touches many templates, but is mostly a refactor, not new functionality.

### Sequencing recommendation

1. **§14 first** (quality-tool defaults) — quickest, unblocks adopter adoption, no dependencies.
2. **§8** (binary type) — prerequisite for §13.
3. **§13** (encrypted-at-rest) — tacks onto §8.
4. **§9** (owner-scoping) — standalone, largest risk to `route.py.j2`.
5. **§15** (one-file-per-entity) — standalone refactor, don't bundle with other feature work.
6. **§12** (auth scaffolding) — last, most ambitious, benefits from §9 already landing.

### Incidental follow-ups discovered during the 2026-04-19 batch

- **Composite-FK `__table_args__` emission.** Verifying my composite-PK self-ref fix (PR2-c) exposed that `model.py.j2` emits N separate `ForeignKey(...)` columns for a multi-column FK instead of a single `ForeignKeyConstraint` in `__table_args__`. SQLAlchemy's `configure_mappers()` raises `AmbiguousForeignKeysError` when two entities (or one entity, as in self-ref) share multiple FK paths — even when both sides specify `foreign_keys`. Affects any composite-FK relationship, not just self-ref. Scope: new spec shape (`relationships[].composite_fk: true`?) + `__table_args__` emission change. Not blocking any current adopter.
- **Upstream fix in `nuncaeslupus/my-skills`.** Gemini-bot correctly flagged on PR #3 that `.claude/skills/mutmut-report/analyze_mutmut.py`'s `run_cmd` should raise rather than `sys.exit(1)` (otherwise a single failing `mutmut show` terminates the entire analysis). Fix belongs upstream — file a PR against `nuncaeslupus/my-skills`, then pull via `git subtree pull --prefix=.claude/skills shared-skills main --squash`.

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
