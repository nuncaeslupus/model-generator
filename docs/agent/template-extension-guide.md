# Template Extension Guide

How to add field types, create templates, and register generators in model-generator. Written for autonomous agent work with exact file paths and code patterns.

---

## Architecture Overview

```
src/model_generator/
├── generate.py                     # CLI entry point, GENERATORS dict, TARGETS lists
├── validate.py                     # JSON schema validation
├── generators/
│   ├── __init__.py                 # Re-exports all generator functions
│   ├── api.py                      # API models, routes, tests, pagination
│   ├── database.py                 # Database models, init, factories
│   ├── enums.py                    # Enum generation (create/append)
│   ├── constraints.py              # Constraint generation (create/append)
│   ├── infrastructure.py           # Base, engine, main, errors, validators, etc.
│   └── migrations.py               # Alembic init and autogenerate
├── utils/
│   ├── __init__.py                 # Re-exports: get_template_env, load_config, etc.
│   ├── loaders.py                  # load_model, load_config, load_shared_enums/constraints
│   ├── templates.py                # Jinja2 env, custom filters (wrap, path_to_import, dict2items)
│   ├── parser.py                   # scan_model_files, scan_api_model_files
│   ├── quality.py                  # run_quality_tools (ruff, mypy)
│   ├── constants.py                # GENERATED_MARKER
│   └── conftest_generator.py       # Test conftest generation
└── stacks/
    └── python-fastapi/
        ├── config.yaml             # Type mappings, paths, constraints, naming, quality
        └── templates/
            ├── database/           # model.py.j2, init.py.j2, enums.py.j2, constraints.py.j2, factory.py.j2
            ├── api/                # request.py.j2, response.py.j2, route.py.j2, init.py.j2, pagination.py.j2
            ├── tests/              # contract.py.j2, conftest_root.py.j2
            ├── infrastructure/     # base.py.j2, engine.py.j2, main.py.j2, errors.py.j2, validators.py.j2, utils.py.j2, types.py.j2, database_init.py.j2
            └── migrations/         # ini.j2, env.py.j2, script.py.mako.j2
```

### Data Flow

```
.model-generator.yaml + config.yaml  →  merged config dict
*.model.json + _shared/*.json         →  model dict + enums dict + constraints dict
                                      ↓
                          generate.py: main() → _generate_target() → GENERATORS[target]()
                                      ↓
                          generators/*.py: render Jinja2 template with (model, config, env)
                                      ↓
                          Output: {path, content, mode} dicts → _process_outputs() → files
```

---

## Template System

### Jinja2 Environment

Created in `utils/templates.py:get_template_env()`:

```python
env = Environment(
    loader=FileSystemLoader(template_dir),
    trim_blocks=True,       # Remove first newline after block tag
    lstrip_blocks=True,     # Strip leading whitespace before block tags
    keep_trailing_newline=True,
)
```

### Custom Filters

**`path_to_import`** — Convert file path to Python import path:

```jinja2
{{ config.paths.database_models | path_to_import }}
{# "backend/src/database/models" → "backend.src.database.models" #}

{{ config.paths.database_models | path_to_import("enums") }}
{# → "backend.src.database.models.enums" #}
```

Source: `utils/templates.py:path_to_import(file_path, module_name="")`

**`wrap`** — Wrap text to line width:

```jinja2
{{ description | wrap(88) }}              {# Simple wrap at 88 chars #}
{{ description | wrap(88, 4, "    ") }}   {# 4-space continuation, 4-char prefix #}
```

Parameters: `wrap(width=88, indent=0, prefix="")`. The `prefix` accounts for first-line content already in the template but is NOT included in output.

Source: `utils/templates.py:wrap_text(text, width, indent, prefix)`

**`dict2items`** — Convert dict to list of `{key, value}` pairs:

```jinja2
{% for item in my_dict | dict2items %}
  {{ item.key }}: {{ item.value }}
{% endfor %}
```

### Template Variables

Every template receives at minimum:

| Variable | Type | Description |
|----------|------|-------------|
| `model` | dict | Full model JSON (domain, entities, description) |
| `config` | dict | Merged config (paths, types, constraints, etc.) |

Some templates receive additional variables — see individual generator functions.

---

## How to Add a Field Type

### Step 1: Add Type Mapping to `config.yaml`

File: `src/model_generator/stacks/python-fastapi/config.yaml`

Add under `types:`:

```yaml
types:
  my_new_type:
    database:
      column: "Column(MyType({param}), nullable={nullable})"
      imports:
        - "from sqlalchemy import Column"
        - "from my_package import MyType"
    api_response: "str | None"
    api_request: "str"
    # Optional: validators that should be auto-applied
    validators:
      - validate_my_type
    # Optional: imports needed in API models
    api_imports:
      - "from some.module import something"
```

**Required keys:**
- `database.column` — SQLAlchemy column expression with `{placeholders}` for field options
- `database.imports` — Python imports needed for the column
- `api_response` — Pydantic type for response model
- `api_request` — Pydantic type for request model

**Placeholders** available in `database.column`: `{nullable}`, `{unique}`, `{default}`, `{max_length}`, `{precision}`, `{scale}`, and any field option from JSON.

### Step 2: Update Templates (if needed)

Templates that may need changes:

1. **`database/model.py.j2`** — If the type needs special column declaration logic
2. **`api/request.py.j2`** / **`api/response.py.j2`** — If the type needs special Pydantic handling
3. **`tests/contract.py.j2`** — If the type needs special test value generation
4. **`database/factory.py.j2`** — If the type needs special factory data generation

Most types work with the existing template logic via config.yaml mappings alone.

### Step 3: Update JSON Schema (if validating)

File: `schema/model.schema.json` — Add the new type to the enum of valid types.

### Step 4: Test

1. Create a model JSON using the new type
2. Generate: `model-gen models/ --target all`
3. Verify generated code passes ruff, mypy, pytest
4. Test with all three project structures (full-stack, backend-only, monorepo)

---

## How to Create a New Template

### Conventions

- Template files use `.j2` extension
- Organized by category: `database/`, `api/`, `tests/`, `infrastructure/`, `migrations/`
- All paths must come from `config["paths"]` — never hardcode
- All imports must be generated dynamically using `path_to_import` filter

### Available Variables Per Category

**Database templates** (`database/*.j2`):

```python
template.render(model=model, config=config)
# model.domain, model.entities, model.description
# config.paths, config.types, config.constraints
```

**API templates** (`api/*.j2`):

```python
template.render(model=model, config=config)
# Some also receive: enums=enums, constraints=constraints
```

**Test templates** (`tests/*.j2`):

```python
template.render(model=model, config=config, enums=enums, constraints=constraints)
```

**Infrastructure templates** (`infrastructure/*.j2`):

```python
# Varies per template — some receive domains, imports, project config
# Check the specific generator function for exact variables
```

### Template Patterns

**Dynamic imports:**

```jinja2
from {{ config.paths.database_models | path_to_import }}.base import Base
from {{ config.paths.database_models | path_to_import }}.enums import {{ enum_name }}
```

**Iterating entities:**

```jinja2
{% for entity_name, entity in model.entities.items() %}
class {{ entity_name }}(Base):
    __tablename__ = "{{ entity.table }}"
{% endfor %}
```

**Conditional generation:**

```jinja2
{% if entity.get("timestamps", {}).get("created") %}
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
{% endif %}
```

---

## How to Register a Generator

### Step 1: Write the Generator Function

File: Create in `generators/` or add to existing file.

**Function signature:**

```python
def generate_my_thing(
    model: dict,
    config: dict,
    env: Environment,
    project_root: Path,
) -> dict | list[dict] | None:
    """Generate my thing."""
    template = env.get_template("category/my_thing.py.j2")
    content = template.render(model=model, config=config)

    output_dir = project_root / config["paths"]["my_output_path"]
    domain = model.get("domain", "models")
    output_file = output_dir / f"{domain}_my_thing.py"

    return {"path": output_file, "content": content}
```

**Return format:**

```python
# Single file:
{"path": Path, "content": str, "mode": "write"}  # mode defaults to "write"

# Append mode:
{"path": Path, "content": str, "mode": "append", "new_count": int, "skipped": int}

# Multiple files:
[{"path": Path, "content": str}, ...]

# Skip (nothing to generate):
None

# Instructions (not a file):
{"info": str, "instructions": str}
```

### Step 2: Export from `generators/__init__.py`

```python
from .my_module import generate_my_thing

__all__ = [
    ...,
    "generate_my_thing",
]
```

### Step 3: Register in `generate.py`

**For simple generators** (standard signature), add to the dispatch table:

```python
GENERATORS = {
    ...,
    "my-thing": lambda m, c, e, p, mp: generate_my_thing(m, c, e, p),
}
```

The lambda signature is `(model, config, env, project_root, model_path)`. Use only the params your generator needs.

**For generators needing extra data** (enums, constraints), add to `_generate_target()`:

```python
def _generate_target(self, target, model, config, env, project_root, model_path, enums, constraints):
    ...
    elif target == "my-thing":
        return generate_my_thing(model, config, env, project_root, enums, constraints)
```

### Step 4: Add to Target Lists

In `generate.py`, add to the appropriate list:

```python
# For infrastructure (run once):
INFRASTRUCTURE_TARGETS = [..., "my-thing"]

# For domain-specific (run per model file):
DOMAIN_TARGETS = [..., "my-thing"]
```

The target appears in `TARGETS` automatically (union of both + `"infrastructure"` + `"all"`).

---

## Existing Generator Reference

| Target | Generator Function | Template | Output |
|--------|-------------------|----------|--------|
| `base` | `generate_base()` | `infrastructure/base.py.j2` | `{paths.base}` |
| `engine` | `generate_engine()` | `infrastructure/engine.py.j2` | `{paths.engine}` |
| `main` | `generate_main()` | `infrastructure/main.py.j2` | `{paths.main}` |
| `test-conftest-root` | `generate_test_conftest_root()` | `tests/conftest_root.py.j2` | `{paths.test_conftest_root}` |
| `enums` | `generate_enums()` | `database/enums.py.j2` | `{paths.enums}` |
| `constraints` | `generate_constraints()` | `database/constraints.py.j2` | `{paths.constraints}` |
| `init` | `generate_init()` | `database/init.py.j2` | `{paths.database_models}/__init__.py` |
| `database` | `generate_database_model()` | `database/model.py.j2` | `{paths.database_models}/{domain}.py` |
| `factories` | `generate_factories()` | `database/factory.py.j2` | `{paths.factories}/{domain}.py` |
| `api-models` | `generate_api_models()` | `api/request.py.j2`, `api/response.py.j2` | `{paths.api_models}/{domain}_requests.py`, `{domain}_response.py` |
| `api-init` | `generate_api_init()` | `api/init.py.j2` | `{paths.api_models}/__init__.py` |
| `api-pagination` | `generate_api_pagination()` | `api/pagination.py.j2` | `{paths.api_models}/pagination.py` |
| `api-tests` | `generate_api_tests()` | `tests/contract.py.j2` | `{paths.api_tests}/test_{domain}_api.py` |
| `api-tests-config` | `generate_conftest()` | — (custom) | `{paths.api_tests}/conftest.py` |
| `api-routes` | `generate_api_routes()` | `api/route.py.j2` | `{paths.api_routes}/{domain}.py` |
| `migration-init` | `generate_migration_init()` | `migrations/*.j2` | `alembic.ini`, `{paths.migrations}/env.py`, etc. |
| `migration-autogen` | `generate_migration_autogen()` | — | Instructions only |

Infrastructure generators (`generate_infrastructure()`) also create: `types.py`, `database/__init__.py`, `errors.py`, `validators.py`, `utils.py`, and `__init__.py` files for all package directories.

---

## Config.yaml Reference

Full annotated reference for `stacks/python-fastapi/config.yaml`:

```yaml
# Stack metadata
stack:
  name: python-fastapi          # Stack identifier
  description: "..."            # Human description
  version: "1.0"                # Stack version

# Output paths (relative to project root, overridable in .model-generator.yaml)
paths:
  base: backend/src/database/models/base.py        # SQLAlchemy Base class
  engine: backend/src/database/engine.py            # Database engine/session
  main: backend/src/main.py                         # FastAPI app entry point
  errors: backend/src/api/errors.py                 # Error formatting
  validators: backend/src/api/validators.py         # Pydantic validators
  test_conftest_root: tests/conftest.py             # Root test configuration
  database_models: backend/src/database/models      # Per-domain SQLAlchemy models
  factories: backend/src/database/models/factories  # FactoryBoy test factories
  api_models: backend/src/api/models                # Per-domain Pydantic models
  api_routes: backend/src/api/routes                # Per-domain FastAPI routes
  api_tests: tests/contract/api                     # Per-domain contract tests
  enums: backend/src/database/models/enums.py       # Shared enum definitions
  constraints: backend/src/database/models/constraints.py  # Shared constraints
  migrations: alembic                               # Alembic migration directory

# Type mappings: abstract type → concrete implementations
types:
  type_name:
    database:
      column: "Column(...)"       # SQLAlchemy column with {placeholders}
      imports: [...]              # Required Python imports
    api_response: "type | None"   # Pydantic response type
    api_request: "type"           # Pydantic request type
    validators: [...]             # Optional: auto-applied validators
    api_imports: [...]            # Optional: extra API model imports

# Timestamp column patterns
timestamps:
  created_at:
    column: "..."                 # Full column declaration
    imports: [...]
  updated_at:
    column: "..."
    imports: [...]

# Database constraint patterns
constraints:
  non_negative:
    check: 'CheckConstraint("...")'
    imports: [...]
  positive: { ... }
  range: { ... }
  length: { ... }
  pattern: { api_validator: true }   # API-only, no DB constraint
  depends: { ... }

# Index patterns
indexes:
  single: { pattern: "...", imports: [...] }
  composite: { ... }
  unique: { ... }

# Relationship patterns
relationships:
  one_to_many: { parent: "...", child_fk: "...", child_rel: "..." }
  many_to_one: { fk: "...", rel: "..." }
  one_to_one: { parent: "...", child_fk: "...", child_rel: "..." }

# API model patterns
api:
  response_model: { suffix, base_class, config, imports }
  create_request: { prefix, suffix, base_class, imports }
  update_request: { prefix, suffix, base_class, imports }
  validators:
    validator_name: { import: "...", usage: "..." }

# Naming conventions
naming:
  table: snake_case
  model: PascalCase
  field: snake_case
  enum: PascalCase
  # ... naming patterns for constraints, indexes, etc.

# Code style
style:
  line_length: 88
  quotes: double
  indent: 4

# Quality tools (run after generation)
quality:
  linter: "ruff check --fix ."
  formatter: "ruff format ."
  type_checker: "mypy . --explicit-package-bases"

# Factory configuration for test data
factory:
  field_name_inference:
    email: "email()"              # Field name → Faker method
    username: "user_name()"
    # ... many more patterns
  default_text_length: 50
```

---

## Common Pitfalls

### Hardcoded Paths

```python
# WRONG
output_dir = project_root / "backend/src/database/models"

# RIGHT
output_dir = project_root / config["paths"]["database_models"]
```

### Hardcoded Imports in Templates

```jinja2
{# WRONG #}
from backend.src.database.models.enums import {{ enum_name }}

{# RIGHT #}
from {{ config.paths.database_models | path_to_import }}.enums import {{ enum_name }}
```

### Missing Nullable Handling

When adding a field type, ensure the column template handles `nullable={nullable}`. The generator passes `nullable=True` for non-required fields and `nullable=False` for required fields.

### Forgetting Create-Once Semantics

Infrastructure generators check `if output_path.exists(): return None` to avoid overwriting. Per-domain generators overwrite by default. Choose the right behavior for your generator.

### Not Testing Three Structures

Every change must work for:
1. Full-stack: `backend/src/database/models`
2. Backend-only: `src/database/models`
3. Monorepo: `services/api/src/database/models`

All paths come from config, so this works automatically if you avoid hardcoding.
