# Installation Guide

## Prerequisites

- Python 3.11 or later
- uv

## Install from Source

```bash
# Clone and navigate to the model-generator directory
cd model-generator

# Install with uv
uv sync

# Or with dev dependencies
uv sync --extra dev
```

## Verify Installation

```bash
model-gen --help
```

You should see the help output with available options and targets.

## Optional: Interactive Mode

The interactive wizard requires `questionary`. Install with the optional dependency:

```bash
uv sync --extra interactive
```

Without it, `model-gen --interactive` still works using a plain-text fallback.

## Try the Example

```bash
cd examples/user-auth-project

# Generate all code
model-gen models/ --target all

# Install generated project dependencies and run tests
uv venv && uv sync --extra dev
uv run pytest

# Result: 149 tests pass, ruff clean, mypy clean
```

---

## Create Your First Project

### 1. Create Project Structure

```bash
mkdir -p my-project/models
cd my-project
```

### 2. Create Config File

Create `.model-generator.yaml` in your project root:

```yaml
project:
  name: "My Project"
  description: "A short description"
  version: "0.1.0"

stack: python-fastapi

# Default paths (override for your layout):
# paths:
#   database_models: backend/src/database/models
#   api_models: backend/src/api/models
#   api_routes: backend/src/api/routes
#   api_tests: tests/contract/api
```

### 3. Create Shared Resources (Optional)

If you use enums or shared constraints:

```bash
mkdir models/_shared
```

`models/_shared/enums.json`:
```json
{
  "enums": {
    "UserStatus": {
      "description": "Account status",
      "values": ["active", "inactive", "suspended"]
    }
  }
}
```

### 4. Create Your First Model

`models/users.model.json`:
```json
{
  "domain": "users",
  "description": "User management domain.",
  "entities": {
    "User": {
      "table": "users",
      "description": "Application user account",
      "fields": {
        "id": {"type": "uuid", "primary_key": true, "auto_generate": true},
        "username": {"type": "text", "required": true, "unique": true, "max_length": 50},
        "email": {"type": "text", "required": true, "unique": true, "max_length": 255}
      },
      "timestamps": {"created": true, "updated": true},
      "api": {"enabled": true, "prefix": "users"},
      "tests": {"enabled": true}
    }
  }
}
```

### 5. Generate

```bash
model-gen models/ --target all
```

### 6. Install and Test

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest
```

---

## Config Reference

All `paths:` keys with defaults (relative to project root):

| Key | Default | Description |
|-----|---------|-------------|
| `database_models` | `backend/src/database/models` | SQLAlchemy models |
| `factories` | `backend/src/database/models/factories` | Test factories |
| `api_models` | `backend/src/api/models` | Pydantic models |
| `api_routes` | `backend/src/api/routes` | FastAPI routes |
| `api_tests` | `tests/contract/api` | Contract tests |
| `base` | `backend/src/database/models/base.py` | SQLAlchemy Base |
| `engine` | `backend/src/database/engine.py` | DB engine/session |
| `main` | `backend/src/main.py` | FastAPI app |
| `errors` | `backend/src/api/errors.py` | Error formatting |
| `validators` | `backend/src/api/validators.py` | Pydantic validators |
| `test_conftest_root` | `tests/conftest.py` | Root conftest |
| `enums` | `backend/src/database/models/enums.py` | Enum definitions |
| `constraints` | `backend/src/database/models/constraints.py` | Constraint constants |
| `migrations` | `alembic` | Alembic directory |

### Layout Examples

**Backend-only:**
```yaml
paths:
  database_models: src/database/models
  factories: src/database/models/factories
  api_models: src/api/models
  api_routes: src/api/routes
  api_tests: tests/api
  base: src/database/models/base.py
  engine: src/database/engine.py
  main: src/main.py
  errors: src/api/errors.py
  validators: src/api/validators.py
  test_conftest_root: tests/conftest.py
  enums: src/database/models/enums.py
  constraints: src/database/models/constraints.py
```

**Monorepo:**
```yaml
paths:
  database_models: services/api/src/database/models
  api_models: services/api/src/api/models
  api_routes: services/api/src/api/routes
  api_tests: services/api/tests/api
```

---

## File Naming Convention

| File | Pattern | Location |
|------|---------|----------|
| Domain model | `{domain}.model.json` | `models/` |
| Shared enums | `enums.json` | `models/_shared/` |
| Shared constraints | `constraints.json` | `models/_shared/` |
