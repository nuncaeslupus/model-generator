# Next Session Plan

## Current State (2026-04-25, mid-day, mid-§15)

PR #10 (§9 owner-scoping) merged to `main` as squash `62a700c`. §15 (one-file-per-entity layout) is in progress on `feat/15-per-entity-layout` — **3 local commits, not pushed**.

### `feat/15-per-entity-layout` (this session)

- `18c6531` — `chore: align make lint with CI` — picked up the two `make lint` follow-ups: `ruff format --check .` added to lint target, and `examples/.*/backend/` + `examples/.*/alembic/` added to `[tool.mypy].exclude` so local mypy stops tripping on gitignored 3.12 generated output.
- `72c9ab4` — `feat: thread generation.layout config flag (§15.1)` — `load_config` defaults `generation.layout` to `"per-entity"`; `_validate_generation_config()` rejects unknown values. Plumbing only — no emission change yet.
- `8a7d481` — `feat: add snake_case filter for entity-derived filenames (§15.2)` — Python `snake_case()` in `utils/templates.py` mirroring the existing `to_snake_case` Jinja macro byte-for-byte; registered as a Jinja filter for template-side parity.

**Verification at checkpoint:** 323 tests passing (was 308 — +6 from §15.1 validator/load_config defaults, +9 from §15.2 snake_case), `make lint` clean (ruff check + ruff format check + mypy), working tree clean.

---

## Priority Next Session — Continue §15 (steps 3–6)

The full §15 plan is at `~/.claude/plans/tranquil-shimmying-flute.md`. Steps 1–2 landed; step 3 was started this session — partial template edits were reverted to leave a clean checkpoint, but the design analysis is preserved below so it doesn't need redoing.

### §15.3 — database generator: per-entity loop (NEXT UP)

**Files to touch:**
- `src/model_generator/generators/database.py` — rewrite three functions
- `templates/database/factory.py.j2` — layout-aware imports + sibling check
- `templates/database/model.py.j2` — gate section_divider on per-domain
- `tests/test_generators.py` — pin existing fixture to per-domain, add per-entity test classes

**Generator design** (drop into `generators/database.py`, replacing all three functions):

```python
from ..utils.parser import scan_model_files
from ..utils.templates import snake_case


def _layout(config: dict) -> str:
    return config.get("generation", {}).get("layout", "per-entity")


def generate_database_model(model, config, env, project_root):
    template = env.get_template("database/model.py.j2")
    output_dir = project_root / config["paths"]["database_models"]
    sibling_entities = list(model.get("entities", {}).keys())

    if _layout(config) == "per-entity":
        return [
            {
                "path": output_dir / f"{snake_case(name)}.py",
                "content": template.render(
                    model={**model, "entities": {name: e}},
                    config=config,
                    sibling_entities=sibling_entities,
                ),
            }
            for name, e in model.get("entities", {}).items()
        ]
    domain = model.get("domain", "models")
    content = template.render(
        model=model, config=config, sibling_entities=sibling_entities
    )
    return {"path": output_dir / f"{domain}.py", "content": content}


def generate_init(model, config, env, project_root):
    output_dir = project_root / config["paths"]["database_models"]
    domains = scan_model_files(output_dir)

    if _layout(config) == "per-entity":
        existing = {d["file"] for d in domains}
        for name in model.get("entities", {}).keys():
            stem = snake_case(name)
            if stem not in existing:
                domains.append(
                    {"name": stem, "file": stem, "section": None, "entities": [name]}
                )
    else:
        current = model.get("domain", "unknown")
        if current not in {d["name"] for d in domains}:
            domains.append(
                {
                    "name": current,
                    "file": current,
                    "section": model.get("section_header"),
                    "entities": list(model.get("entities", {}).keys()),
                }
            )

    if not domains:
        print(f"  ℹ️  No model files found in {output_dir}")
        return None

    template = env.get_template("database/init.py.j2")
    content = template.render(domains=domains, config=config)
    return {
        "path": output_dir / "__init__.py",
        "content": content,
        "mode": "write",
        "domain_count": len(domains),
        "entity_count": sum(len(d["entities"]) for d in domains),
    }


def generate_factories(model, config, env, project_root):
    template = env.get_template("database/factory.py.j2")
    factories_dir = project_root / config["paths"]["database_models"] / "factories"
    sibling_entities = list(model.get("entities", {}).keys())

    if _layout(config) == "per-entity":
        return [
            {
                "path": factories_dir / f"{snake_case(name)}.py",
                "content": template.render(
                    model={**model, "entities": {name: e}},
                    config=config,
                    sibling_entities=sibling_entities,
                ),
            }
            for name, e in model.get("entities", {}).items()
        ]
    domain = model.get("domain", "models")
    content = template.render(
        model=model, config=config, sibling_entities=sibling_entities
    )
    return {"path": factories_dir / f"{domain}.py", "content": content}
```

**`factory.py.j2` changes (two edits):**

(a) Replace lines 79–84 (the model-import block) with a layout-aware version + new cross-entity factory imports block:

```jinja
{#- Import database models -#}
{% set db_models_import = config.paths.database_models | path_to_import %}
{% if config.generation.layout == 'per-entity' %}
{% for entity_name in model.entities.keys() %}
from {{ db_models_import }}.{{ entity_name | snake_case }} import {{ entity_name }}
{% endfor %}
{% else %}
from {{ db_models_import }}.{{ model.domain}} import (
{% for entity_name in model.entities.keys() %}
    {{ entity_name }},
{% endfor %}
)
{% endif %}
{% if config.generation.layout == 'per-entity' and ns.entity_refs %}
{% for ref in ns.entity_refs %}
from .{{ ref | snake_case }} import {{ ref }}Factory
{% endfor %}
{% endif %}
```

The cross-entity factory imports are the key piece — they make `factory.SubFactory({Ref}Factory)` resolve in per-entity mode where sibling factories live in separate files.

(b) Line 241: change `rel.target in model.entities` → `rel.target in sibling_entities`.

> **Subtle gotcha worth understanding before editing**: in per-entity mode `model.entities` has only 1 entry, so the existing `rel.target in model.entities` check silently suppresses sibling-target `create_related` blocks (a regression). Plumbing `sibling_entities` (the full domain entity list) from the generator preserves the semantic "is this rel target in our domain scope?" in both modes.

**`model.py.j2` change (one edit):**

Line 158 — gate `section_divider` on per-domain so per-entity files don't each emit the same `# USERS MODELS` header (which would produce N redundant comments in the generated `__init__.py`):

```jinja
{% if config.generation.layout != 'per-entity' %}
{{ section_divider(model.section_header | default(model.domain | upper + ' MODELS')) }}
{% endif %}
```

The model.py.j2 docstring block (lines 12–21) doesn't need changes — it accurately describes a single-entity file.

**Test changes (`tests/test_generators.py`):**

1. Pin existing `project_env` fixture to per-domain so existing assertions about file shape stay precise:

   ```python
   config_data = {
       ...,
       "generation": {"layout": "per-domain"},
   }
   ```

2. Add `project_env_per_entity` fixture with `"generation": {"layout": "per-entity"}`.

3. Add new test classes:
   - `TestDatabaseGeneratorPerEntity` — assert returns a list, one entry per entity, paths end in `{entity_snake}.py`, content contains the entity class.
   - `TestGenerateInitPerEntity` — patch `scan_model_files` to return per-entity-shaped data; assert init emits `from .user import User` per file.
   - `TestFactoryGeneratorPerEntity` — assert per-entity factory file emits the new cross-entity factory imports for sibling refs (and that `create_related` is preserved via `sibling_entities`).

**Architectural notes already verified this session:**

- `scan_model_files` is naturally layout-polymorphic — reads what's on disk and returns `[{"file": stem, "entities": [classes]}]`. Per-entity files have one entity per stem; per-domain files have many. **No scanner changes needed for §15.3.**
- `_generate_target` already handles `dict | list | None` returns; the `GENERATORS` dispatch table needs no changes.
- SQLAlchemy `relationship()` and `ForeignKey()` use string identifiers — model.py.j2 itself needs no cross-entity imports beyond the section-divider gate.

### §15.4 — api-models per-entity

Write new combined `templates/api/entity.py.j2` (Request + Response in one file, per the user-approved plan decision). Refactor `generate_api_models` to use it in per-entity mode. Update `scan_api_model_files` — current detection is suffix-based (`*_response.py` / `*_requests.py`) and needs a per-entity branch detecting `{entity_snake}.py`. Update `generate_api_init`. Tests.

### §15.5 — api-routes and api-tests per-entity

Same per-entity loop pattern in `generate_api_routes` and `generate_api_tests`. Audit `route.py.j2` for cross-entity references (none expected in current CRUD scaffolding). Tests.

### §15.6 — Example regen + docs

Regenerate `examples/user-auth-project/` with `--clean`. Confirm 149 tests still pass. Add commented `generation.layout` section to `.model-generator.yaml`. Update `docs/agent/json-specification-reference.md` and any user-facing config docs. Note the breaking-shape change in this file.

### Housekeeping

- Branch `feat/15-per-entity-layout` is local-only. Push for backup: `git push -u origin feat/15-per-entity-layout`.

---

## §12 — Auth scaffolding (after §15)

**What:** `auth: {strategy: "bcrypt-session", pepper_env: "APP_PASSWORD_PEPPER"}` → generates a starter auth router (register / login / logout / forgot / reset / change-password) with bcrypt+pepper hashing, itsdangerous session cookies, CSRF middleware, and rate limiting on login/register.
**Depends on:** User entity with `password` field (already present in the user-auth example).
**Surface:** new `templates/infrastructure/auth_router.py.j2` + session middleware hook into `main.py.j2`.
**Estimated scope:** 2–3 days. Should be broken into its own multi-commit plan.

### Incidental follow-ups still open

- **Composite-FK `__table_args__` emission.** `model.py.j2` emits N separate `ForeignKey(...)` columns for a multi-column FK instead of a single `ForeignKeyConstraint` in `__table_args__`. SQLAlchemy's `configure_mappers()` raises `AmbiguousForeignKeysError` when two entities (or one entity, as in self-ref) share multiple FK paths — even when both sides specify `foreign_keys`. Affects any composite-FK relationship. Scope: new spec shape (`relationships[].composite_fk: true`?) + `__table_args__` emission change. Not blocking any current adopter.
- **Upstream fix in `nuncaeslupus/my-skills`.** Gemini-bot correctly flagged on PR #3 that `.claude/skills/mutmut-report/analyze_mutmut.py`'s `run_cmd` should raise rather than `sys.exit(1)`. Fix belongs upstream — file a PR against `nuncaeslupus/my-skills`, then pull via `git subtree pull --prefix=.claude/skills shared-skills main --squash`.

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

### §15.1 + §15.2 — Per-entity layout plumbing (2026-04-25, in progress)

Branch `feat/15-per-entity-layout`, 3 local commits (not pushed). See "Priority Next Session" block above for §15.3+ design. 323 tests passing at the §15.2 tip.

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
