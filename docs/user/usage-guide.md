# Usage Guide

CLI workflows for model-generator: generation, preview, cleanup, and interactive mode.

---

## CLI Overview

```bash
model-gen [model_dir] [options]
```

**Arguments:**
- `model_dir` — Path to a `.model.json` file or directory containing them (required unless using `--clear-only`)

**Common options:**
- `--target TARGET` — What to generate (default: `all`)
- `--diff` — Show changes without writing files
- `--dry-run` — List files that would be created
- `--clean` — Delete generated files before generating
- `--clear-only` — Delete only, don't generate
- `--no-root-files` — Skip `pyproject.toml`, `alembic.ini`, and `.gitignore` (see [Generating into an existing project](#generating-into-an-existing-project))
- `--interactive` — Launch the interactive wizard

---

## Python Import Root

By default, generated imports use the configured `paths.*` value verbatim. With `paths.database_models: src/hub/database/models`, the database model file emits:

```python
from src.hub.database.types import PortableUuid
```

That's wrong for the standard `src/`-layout, where `src/` is on `sys.path` (not a package) and the correct import is `from hub.database.types import PortableUuid`.

Set the top-level `python_root` key in `.model-generator.yaml` to strip that prefix when forming Python import strings. **Filesystem paths are unchanged — only generated imports differ.**

```yaml
project:
  name: "My App"

stack: python-fastapi

python_root: "src"    # strips "src/" from paths.* when forming imports

paths:
  database_models: src/hub/database/models
  # → generated import: from hub.database.models import X
  # → file written to:  src/hub/database/models/x.py (unchanged)
```

Omit the key (or set it empty) when your `paths.*` values are already importable as-is (e.g. `backend/src/...` flat-layout projects that import from `backend.src.X`).

---

## Base Module Location

`paths.base` **must be located inside `paths.database_models`** and **must be named `base.py`** — the base module is required to be a child of the models directory (and a sibling of the generated model files). Generated model files emit a relative import:

```python
from .base import Base
```

so the file specified by `paths.base` must live inside the `paths.database_models` directory under the filename `base.py`. A mismatch generates without complaint but fails at test-collection time with `ModuleNotFoundError: No module named '<...>.models.base'`.

```yaml
paths:
  database_models: hub/database/models
  base: hub/database/models/base.py   # ✓ child of paths.database_models, named base.py
  # base: hub/database/base.py        # ✗ ModuleNotFoundError (wrong directory)
  # base: hub/database/models/foundation.py   # ✗ filename must be base.py
```

When `paths.base` is omitted, the default derives from `paths.database_models` (`{database_models}/base.py`), so adopters who only customize the models directory don't need to also restate the base path. `model-gen` validates both constraints eagerly and exits with a remediation message on mismatch.

---

## Generation Targets

| Target | Description | Output |
|--------|-------------|--------|
| `all` | Everything in TDD order | All files below |
| `infrastructure` | Base, engine, main, root conftest | One-time setup files |
| `enums` | Enum classes from `_shared/enums.json` | `enums.py` |
| `constraints` | Constants from `_shared/constraints.json` | `constraints.py` |
| `database` | SQLAlchemy models | `{domain}.py` per domain |
| `factories` | FactoryBoy test factories | `factories/{domain}.py` |
| `api-models` | Pydantic request/response schemas | `{domain}_requests.py`, `{domain}_response.py` |
| `api-routes` | FastAPI route handlers | `{domain}.py` per domain |
| `api-tests` | Contract tests | `test_{domain}_api.py` per domain |
| `migration-init` | Alembic infrastructure | `alembic.ini`, `alembic/env.py`, etc. |

---

## Common Workflows

### First Generation (Start Here)

```bash
cd your-project
model-gen models/ --target all
```

This generates everything in TDD order:
1. Infrastructure (base, engine, main)
2. Database models (SQLAlchemy)
3. API models (Pydantic)
4. Tests (contract tests — RED phase)
5. Routes (FastAPI — GREEN phase)
6. Migrations (Alembic setup)

### Preview Before Writing

```bash
# Show what files would be created
model-gen models/ --dry-run

# Show actual file contents/diffs
model-gen models/ --diff
```

### Generate Specific Parts

```bash
model-gen models/ --target database       # Just database models
model-gen models/ --target api-models     # Just Pydantic schemas
model-gen models/ --target api-tests      # Just tests
```

### Clean and Regenerate

```bash
# Remove only files that would be regenerated
model-gen models/ --target all --clean

# Remove everything (including venvs, caches)
model-gen models/ --target all --clean --scope full

# Remove generated files without regenerating
model-gen --clear-only --scope full
```

**Cleanup scopes:**
- `selective` (default) — Only files that would be regenerated
- `full` — Also removes cache dirs (`.pytest_cache`, `.mypy_cache`, `.venv`), generated infrastructure, and `alembic.ini`

### Generating into an existing project

When integrating model-generator output into a project that already has its own `pyproject.toml`, `.gitignore`, or alembic config, use `--no-root-files` to suppress root-level file emission:

```bash
model-gen models/ --target all --no-root-files
```

This skips `pyproject.toml`, `alembic.ini`, and `.gitignore` even when those files don't yet exist in the target directory. The in-tree `alembic/env.py`, `script.py.mako`, and `versions/.gitkeep` still emit, since they live inside the migrations subdirectory rather than at the project root.

Useful for the scratch-and-migrate workflow: generate into a scratch directory, then move the generated `src/` and `tests/` trees into your real repo without clobbering its curated root files.

---

## Generation Order

When using `--target all`, files generate in TDD order:

```
1. Infrastructure (base, engine, main, conftest) — foundation
2. Enums, constraints, database init — shared definitions
3. Database models — SQLAlchemy (source of truth)
4. Factories — test data generation
5. API models — Pydantic request/response
6. API init, pagination — shared API infrastructure
7. API tests — contract tests (RED: tests exist, routes don't yet)
8. Test conftest — test configuration
9. API routes — FastAPI endpoints (GREEN: tests now pass)
10. Migration init — Alembic setup
```

---

## Post-Generation

After generating code:

```bash
# Install dependencies
uv venv && uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Check code quality
uv run ruff check .
uv run mypy . --explicit-package-bases

# Start development — the generated code is yours to maintain
```

### Environment Variables

Generation emits a `.env.example` manifesting every environment variable the
project reads. Copy it and fill in real values:

```bash
cp .env.example .env
```

Commented-out variables are optional (their documented default applies when
unset). The set grows with enabled features — auth adds `SESSION_SECRET_KEY`
and the password pepper; a redis rate-limit backend adds
`RATELIMIT_STORAGE_URI`; encrypted binary fields add `FERNET_KEY`.

Two variables have **production guards** that refuse insecure dev fallbacks
when `APP_ENV=production`: `DATABASE_URL` (otherwise an ephemeral local SQLite
file) and, with auth enabled, `SESSION_SECRET_KEY` (otherwise a baked-in dev
key). Both raise at startup if missing in production, so a misconfigured
deploy fails loudly instead of silently losing data or signing cookies with a
known key.

---

## Interactive Mode

Launch the wizard to avoid memorizing CLI flags:

```bash
model-gen --interactive
```

The wizard provides a menu:

1. **Setup/update project settings** — Create or modify `.model-generator.yaml`
2. **Generate code** — Select domains and targets interactively
3. **Clean generated files** — Preview before deleting
4. **Run tests** — pytest with optional coverage
5. **Exit**

### Install for Rich UI

```bash
pip install -e "model-generator/[interactive]"
```

With `questionary` installed, the wizard uses arrow-key selection menus. Without it, a plain numbered-list fallback works.

---

## Validation

Validate JSON models before generating:

```bash
model-val models/
```

This checks your `.model.json` files against the JSON schema without generating any code.

---

## Database Migrations

The generator creates Alembic infrastructure. After generation:

```bash
# Set database URL
export DATABASE_URL="sqlite:///./app.db"

# Create tables
alembic upgrade head

# After manual model changes, generate migration
alembic revision --autogenerate -m "Add new field"

# Apply
alembic upgrade head
```

---

## Authentication and Route Scoping

When `auth.strategy` is set in `.model-generator.yaml`, the generator scaffolds authentication infrastructure (login, session management, password hashing). However, CRUD endpoints are **unauthenticated by default** — the auth scaffold is only wired into a route when the entity declares `api.scope`.

**Note:** When `auth.strategy` is set, add `api.scope` to owner-bound entities so routes inject `Depends(get_current_user)` and enforce per-row ownership. Entities without `api.scope` remain publicly accessible.

```json
"api": {
    "scope": {"owner_field": "user_id"},
    "endpoints": ["list", "create", "get", "update", "delete"]
}
```

The generator warns at generation time if `auth.strategy` is set but no API-enabled entity declares `api.scope` — this combination results in a fully open API, which is almost always unintentional.

---

## Tips

- **Start with `--diff`** to review what will be generated before writing files
- **Use `--target all`** for initial generation, specific targets for iteration
- **Infrastructure files are create-once** — they won't overwrite if they exist
- **Domain files overwrite** — use `--clean` to start fresh if needed
