# Architecture, Troubleshooting & Upgrades

A high-level map of how model-generator turns JSON specs into a backend, what
the generated project looks like, the errors adopters most commonly hit, and how
to handle the "I generated once — now what?" question.

---

## Architecture Overview

model-generator is a **one-shot scaffolder**, not a runtime framework. The flow:

```
  models/*.model.json  ──┐
  models/_shared/*.json ─┤
  .model-generator.yaml ─┴──▶  load + validate  ──▶  generators  ──▶  Jinja2 templates  ──▶  files on disk
        (specs)              (loaders/parser,      (generators/*.py,    (stacks/<stack>/
                              jsonschema)           one per target)      templates/*.j2)
```

1. **Specs** — `*.model.json` files (one per domain) plus `_shared/enums.json`
   and `_shared/constraints.json` define entities, fields, relationships, API
   config, and test config. `.model-generator.yaml` supplies project-level
   config (paths, layout, auth, stack).
2. **Load + validate** — JSON is comment-stripped and loaded, type aliases are
   normalized (`integer`→`counter`), legacy index shapes are canonicalized, and
   the result is validated against `schema/model.schema.json`. Cross-spec
   checks (auth strategy, `paths.base`, scope coverage) run here.
3. **Generators** — one function per *target* (`database`, `api-models`,
   `api-routes`, `api-tests`, `infrastructure`, …) builds a render context and
   selects templates. `--target all` runs them in TDD order (models → tests →
   routes).
4. **Templates** — project-agnostic Jinja2 templates under
   `stacks/python-fastapi/templates/` emit the actual Python. Templates contain
   **zero** project-specific code; everything is driven by the spec.

The generator is **stack-agnostic** — `python-fastapi` is the first stack
(selected with `--stack`), not a hard dependency.

### Two kinds of generated file

| Kind | Examples | Regeneration behavior |
|------|----------|-----------------------|
| **Domain files** | database models, routes, API models, factories, contract tests | **Overwritten** on every run |
| **Infrastructure files** | `base.py`, `engine.py`, `main.py`, `auth/router.py`, root `conftest.py`, `utils.py`, `alembic.ini`, `pyproject.toml` | **Skip-if-exists** — written once, never clobbered |

This split is the core of the "generate once, then own it" model: you can re-run
generation while iterating on specs (domain files refresh), and your edits to
hand-owned infra survive.

---

## Generated Project Layout (python-fastapi, per-entity default)

```
backend/src/
  database/
    base.py                  # declarative Base + custom column types
    engine.py                # async engine + get_session dependency
    enums.py                 # generated enum classes (UPPER_CASE)
    models/{entity}.py       # SQLAlchemy models, one per entity
  api/
    models/{entity}_requests.py / {entity}_response.py   # Pydantic schemas
    routes/{entity}.py       # FastAPI handlers
    pagination.py
  main.py                    # FastAPI app — mounts routers, middleware
  auth/router.py             # only when auth.strategy is set
tests/
  conftest.py
  contract/test_{entity}_api.py
alembic/                     # migration env, versions/
.env.example                 # every env var the app reads
pyproject.toml
```

The stack is **async** end to end: `AsyncSession`, `async_sessionmaker`,
`await session.execute(select(...))`. See
[Extending Generated Code](./extending-generated-code.md) for the idioms.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named '...models.base'` | `paths.base` is not a `base.py` inside `paths.database_models` | See [Base Module Location](./usage-guide.md#base-module-location) — base must be a child of the models dir, named `base.py` |
| Imports like `from src.hub.database...` are wrong for your `src/` layout | `python_root` not set | Set `python_root: "src"` to strip the prefix from generated imports (see [Python Import Root](./usage-guide.md#python-import-root)) |
| `/api/v1/auth/register` returns 500 and the whole suite cascades | `APP_PASSWORD_PEPPER` (or `SESSION_SECRET_KEY`) unset | `cp .env.example .env` and fill them in, or export them before `pytest` |
| Adopter config silently ignored | `model-gen` run from a directory other than the project root | `load_config` reads `.model-generator.yaml` from **CWD** — `cd` into the project first |
| `RuntimeError: DATABASE_URL ... must be set in production` | `APP_ENV=production` with no `DATABASE_URL` | Set a real `DATABASE_URL` (the dev SQLite fallback is refused in production by design) |
| `alembic upgrade` fails on an async URL | (older output) sync Alembic engine | Already fixed — `get_url()` coerces async drivers to sync; regenerate `alembic/env.py` if your tree predates 0.1.4 |
| `GET /api/v1/<entity>` returns *all* rows despite auth being on | Entity has no `api.scope` | CRUD is unauthenticated **unless** an entity declares `api.scope`; the generator warns when auth is on but nothing is scoped |
| `ruff check .` flags `E402` in `alembic/env.py` | per-file ignore missing (older output) | Already emitted in `pyproject.toml`; regenerate or add `[tool.ruff.lint.per-file-ignores]` for `alembic/env.py` |

---

## Upgrading After a One-Shot Generation

There is **no automatic upgrade channel.** Once you edit generated code, it is
yours. When a new generator version ships a template fix you want, the CHANGELOG
entry names the affected file and whether it is a domain file (normal re-run
picks it up) or an infra file (skip-if-exists — apply manually):

- **Domain files** (models, routes, schemas, tests) are overwritten on a normal
  re-run, so to adopt a fix: re-run generation, then `git diff` and keep what you
  want. Your hand edits to these files are at risk — review the diff.
- **Infrastructure files** are skip-if-exists, so a re-run will **not** touch
  them. To pick up an infra fix (e.g. a security patch to `main.py`'s CORS or
  `errors.py`):
  1. Delete just that file in your project and re-run `model-gen`, **or**
  2. Generate into a throwaway directory (`model-gen models/ --target <infra-target>`
     in an empty tree) and copy the file across, **or**
  3. Read the CHANGELOG entry and port the diff by hand.

A `--force-infra` flag for selective infra-only overwrite without touching domain
code is tracked as a future improvement.

Treat generator upgrades like a careful `git merge`, not a `pip upgrade`. Keep
your specs (`models/`) and `.model-generator.yaml` under version control so a
clean re-generation into a scratch tree is always a `diff` away.
