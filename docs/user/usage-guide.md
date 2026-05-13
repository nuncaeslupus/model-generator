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

## Tips

- **Start with `--diff`** to review what will be generated before writing files
- **Use `--target all`** for initial generation, specific targets for iteration
- **Infrastructure files are create-once** — they won't overwrite if they exist
- **Domain files overwrite** — use `--clean` to start fresh if needed
