# Python FastAPI Stack

Code generation stack for FastAPI + SQLAlchemy + Pydantic applications.

---

## Overview

This stack generates production-ready code from JSON model definitions following Test-Driven Development (TDD) principles. All code is generated from a single source of truth: your JSON model files.

**What Gets Generated:**

- **Database Models** (SQLAlchemy ORM)
- **API Models** (Pydantic request/response)
- **API Routes** (FastAPI endpoints)
- **API Tests** (pytest contract tests)
- **Test Factories** (FactoryBoy fixtures)
- **Infrastructure** (base, engine, validators, errors, utils, migrations)

---

## Design Principles

1. **TDD:** Tests generate before implementation (RED, then GREEN)
2. **Database as Source of Truth:** JSON → Database → API → Tests → Routes
3. **Contract Testing:** Tests validate API-database alignment, not framework internals
4. **Fixture-Based Tests:** Each test starts with a clean database, no seed data
5. **Topological Sorting:** Fixtures generated in dependency order
6. **Type Safety:** All code is fully typed (mypy compliant)

For details on these principles, see the [Model Design Guide](../../docs/user/model-design-guide.md) and [Quick Reference](../../docs/user/quick-reference.md).

---

## Template Directory Structure

```
templates/
├── database/
│   ├── model.py.j2             # SQLAlchemy models (per domain)
│   ├── init.py.j2              # Database models __init__.py
│   ├── enums.py.j2             # Enum definitions
│   ├── constraints.py.j2       # Constraint constants and helpers
│   └── factory.py.j2           # FactoryBoy test factories
├── api/
│   ├── request.py.j2           # Pydantic request models
│   ├── response.py.j2          # Pydantic response models
│   ├── route.py.j2             # FastAPI CRUD routes
│   ├── init.py.j2              # API models __init__.py
│   └── pagination.py.j2        # Pagination models
├── tests/
│   ├── contract.py.j2          # Contract tests (8-section per entity)
│   └── conftest_root.py.j2     # Root conftest with DB/client fixtures
├── infrastructure/
│   ├── base.py.j2              # SQLAlchemy Base class
│   ├── engine.py.j2            # Database engine and session
│   ├── main.py.j2              # FastAPI app entry point
│   ├── errors.py.j2            # API error formatting
│   ├── validators.py.j2        # Pydantic validation utilities
│   ├── utils.py.j2             # Formatting helpers (financial, percentage)
│   ├── types.py.j2             # Custom SQLAlchemy types (SqliteNumeric)
│   └── database_init.py.j2     # Database package __init__.py
└── migrations/
    ├── ini.j2                  # alembic.ini
    ├── env.py.j2               # Alembic env.py
    └── script.py.mako.j2       # Migration script template
```

---

## Configuration (`config.yaml`)

All paths and type mappings are configurable. See the [Template Extension Guide](../../docs/agent/template-extension-guide.md) for a complete annotated reference.

Key sections:
- `paths:` — Output paths relative to project root (overridable in `.model-generator.yaml`)
- `types:` — Abstract type → SQLAlchemy/Pydantic mappings
- `constraints:` — Constraint patterns
- `relationships:` — Relationship patterns
- `api:` — API model patterns
- `factory:` — Test data generation (Faker field inference)
- `quality:` — Post-generation tool configuration (ruff, mypy)

---

## Conditional Code Generation

Templates use conditional logic to avoid unused code:

- **Unique suffix** in test fixtures: Only declared when entity has unique text or email fields
- **Cross-domain factories:** `_post_generation` hooks skip relationships targeting entities outside the current domain (`rel.target in model.entities`)
- **Enum/constraint imports:** Only generated when the domain uses them
- **Infrastructure files:** Created once, not overwritten on subsequent runs

---

## Code Quality

All generated code passes:
- **ruff** (0 errors) — linting and formatting at 88-char line width
- **mypy** (0 errors) — full type checking
- **pytest** — all contract tests

Notable patterns for mypy compliance:
- Financial/percentage columns use `Column[Decimal]` type annotation
- Validator functions return `str | None` (not bare `str`) for nullable inputs
- Alembic `env.py` uses assertion to narrow `config.get_section()` return type

---

## Adding a New Stack

To create a new stack (e.g., `node-express`):

1. Create directory: `stacks/node-express/`
2. Create `config.yaml` with type mappings, paths, and patterns
3. Create `templates/` with all required templates
4. Register in `generate.py` if needed (currently stack is a CLI arg)
5. Test with `model-gen models/ --stack node-express --target all`

Each stack is self-contained with its own config and templates. The generation logic is stack-agnostic.

---

## Related Documentation

- **[Template Extension Guide](../../docs/agent/template-extension-guide.md)** — How templates work, how to add types and generators
- **[JSON Specification Reference](../../docs/agent/json-specification-reference.md)** — Input format reference
- **[Quick Reference](../../docs/user/quick-reference.md)** — Type mappings, constraints, options tables
