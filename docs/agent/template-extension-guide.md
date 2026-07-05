# Template Extension Guide

How to add field types, create templates, and register generators in model-generator. Written for autonomous agent work with exact file paths and code patterns.

---

## Architecture Overview

`generate.py` is stack-agnostic: it resolves `--stack <name>` to a `StackSpec`
from the shared registry and drives whichever stack the user selects. Each stack
lives entirely in its own directory under `stacks/` and `generators/`.

```
src/model_generator/
├── generate.py                     # CLI entry point; resolves stack via registry
├── validate.py                     # JSON schema validation
├── generators/
│   ├── registry.py                 # StackSpec, register_stack, STACKS dict
│   ├── python_fastapi/             # python-fastapi stack generators
│   │   ├── __init__.py             # PYTHON_FASTAPI_STACK StackSpec + register_stack()
│   │   ├── api.py                  # API models, routes, tests, pagination
│   │   ├── database.py             # Database models, init, factories
│   │   ├── enums.py                # Enum generation (create/append)
│   │   ├── constraints.py          # Constraint generation (create/append)
│   │   ├── infrastructure.py       # Base, engine, main, errors, validators, etc.
│   │   └── migrations.py           # Alembic init and autogenerate
│   └── flutter/                    # flutter stack generators
│       ├── __init__.py             # FLUTTER_STACK StackSpec + register_stack()
│       ├── generators.py           # Models, enums, converters, scaffold
│       ├── api.py                  # Retrofit client, repos, dio setup, auth interceptor
│       ├── fields.py               # Dart field-type resolution helpers
│       └── paths.py                # lib/{pkg}/… path helpers
├── utils/
│   ├── __init__.py                 # Re-exports: get_template_env, load_config, GENERATED_MARKER, etc.
│   ├── loaders.py                  # load_model, load_config, load_shared_enums/constraints
│   ├── templates.py                # Jinja2 env, custom filters (wrap, path_to_import, dict2items, camel_case)
│   ├── parser.py                   # scan_model_files, scan_api_model_files
│   ├── quality.py                  # run_config_quality (stack-driven: ruff, dart format/analyze)
│   └── conftest_generator.py       # Test conftest generation (python-fastapi only)
└── stacks/
    ├── python-fastapi/
    │   ├── config.yaml             # Type mappings, paths, constraints, naming, quality
    │   └── templates/
    │       ├── database/           # model.py.j2, init.py.j2, enums.py.j2, constraints.py.j2, factory.py.j2
    │       ├── api/                # request.py.j2, response.py.j2, route.py.j2, init.py.j2, pagination.py.j2
    │       ├── tests/              # contract.py.j2, conftest_root.py.j2
    │       ├── infrastructure/     # base.py.j2, engine.py.j2, main.py.j2, errors.py.j2, validators.py.j2, utils.py.j2, types.py.j2, database_init.py.j2
    │       └── migrations/         # ini.j2, env.py.j2, script.py.mako.j2
    └── flutter/
        ├── config.yaml             # Dart type mappings, paths, dependencies, naming, quality
        └── templates/
            ├── models/             # model.dart.j2, enums.dart.j2, index.dart.j2
            ├── api/                # retrofit_client.dart.j2, request.dart.j2, index.dart.j2, repository.dart.j2
            └── infrastructure/     # pubspec.yaml.j2, analysis_options.yaml.j2, build.yaml.j2, converters.dart.j2, dio_setup.dart.j2, pagination.dart.j2, auth_interceptor.dart.j2, README.md.j2, gitignore.j2
```

### Stack Registry

Each stack module calls `register_stack(StackSpec(...))` at import time.
`generate.py` imports every stack package on startup so all stacks are
registered, then resolves `--stack <name>` to the matching `StackSpec`.

The `StackSpec` fields that `generate.py` reads:

| Field | Purpose |
|---|---|
| `name` | Registry key (matches `stack:` in `.model-generator.yaml`) |
| `infrastructure_targets` | Targets dispatched to `infra_orchestrator` (skip-if-exists semantics) |
| `domain_targets` | Targets dispatched to `generators[target]` (run per model file) |
| `generators` | `{target: fn}` — domain-target dispatch table |
| `infra_orchestrator` | Function that runs all infrastructure targets in order |
| `quality_runner` | Called after generation; runs formatter + analyzer for the stack |
| `cleanup_spec` | Glob patterns and path keys for `--clean` |
| `validators` | Per-generation validators (e.g. `_validate_paths_base` for python-fastapi) |
| `infra_validators` | Pre-infra validators (e.g. `_validate_auth_strategy`) |
| `extra_deps_fn` | Returns extra pyproject deps to inject (python-fastapi only) |

### Data Flow

```
.model-generator.yaml + stacks/<name>/config.yaml  →  merged config dict
*.model.json + _shared/*.json                       →  model dict + enums dict + constraints dict
                                                    ↓
                          generate.py: main() → STACKS[stack_name] → StackSpec
                                                    ↓
                          infra_orchestrator(config, env, project_root)    (once)
                          generators[target](GenContext)                    (per model file)
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

This section covers adding a target to an **existing stack**. To add a new stack
entirely, see [Adding a New Stack](#adding-a-new-stack) below.

### Step 1: Write the Generator Function

File: Create in `generators/<stack>/` or add to an existing module there.

**Function signature:**

```python
def generate_my_thing(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | list[dict[str, Any]] | None:
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
```

### Step 2: Add to the stack's `StackSpec`

In `generators/<stack>/__init__.py`, add the target to the dispatch table and
the appropriate target list:

```python
# Domain target (run per model file):
_MY_GENERATORS: dict[str, TargetGenerator] = {
    ...,
    "my-thing": lambda c: generate_my_thing(c.model, c.config, c.env, c.project_root),
}

MY_STACK = StackSpec(
    ...,
    domain_targets=[..., "my-thing"],   # or infrastructure_targets for infra
    generators=_MY_GENERATORS,
    ...
)
```

`GenContext` (the `c` argument) carries `model`, `config`, `env`,
`project_root`, and `model_path`. Use only the fields your generator reads.

For infrastructure targets, call the generator from `infra_orchestrator`
instead (infrastructure runs once, not per model file).

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

## Adding a New Stack

The stack registry makes adding a third or fourth stack purely additive — no
changes to `generate.py` or any shared code are required.

### Step 1: Create the stack config

```
src/model_generator/stacks/<name>/config.yaml
```

At minimum, include `stack.name`, `paths`, `types` (abstract → target-language
mappings), `naming`, and `quality`. Model the file on
`stacks/python-fastapi/config.yaml` (Python) or `stacks/flutter/config.yaml`
(Dart). The config is deep-merged with `.model-generator.yaml` at load time;
any key the project sets overrides the stack default.

### Step 2: Create the generator package

```
src/model_generator/generators/<name>/
    __init__.py          # StackSpec definition + register_stack()
    generators.py        # infrastructure and domain generator functions
    ...                  # additional modules as needed
```

Generator functions follow the existing contract:

```python
def generate_my_thing(
    model: dict[str, Any],
    config: dict[str, Any],
    env: Environment,
    project_root: Path,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    template = env.get_template("category/my_thing.ext.j2")
    content = template.render(model=model, config=config)
    output_file = project_root / config["paths"]["my_output_path"] / f"{model['domain']}.ext"
    return {"path": output_file, "content": content}
```

### Step 3: Register the stack

In `generators/<name>/__init__.py`, build and register a `StackSpec`:

```python
from ..registry import StackSpec, register_stack

MY_STACK = StackSpec(
    name="my-stack",                    # must match stack: in .model-generator.yaml
    infrastructure_targets=[...],       # labels for --target; dispatched to infra_orchestrator
    domain_targets=[...],               # dispatched to generators[target] per model file
    generators={"target": fn, ...},     # domain-target dispatch table
    infra_orchestrator=my_infra_fn,     # runs all infra targets in order
    quality_runner=run_config_quality,  # formatter + analyzer (or a custom callable)
    cleanup_spec=MY_CLEANUP,            # CleanupSpec with path keys + glob patterns
    validators=[],                      # per-generation validators (or stack-specific ones)
    infra_validators=[],                # pre-infra validators
    extra_deps_fn=None,                 # returns extra runtime deps to inject (or None)
)

register_stack(MY_STACK)
```

Import the package from `generate.py`'s stack-import block so it is registered
at startup. The Flutter stack is the canonical reference implementation.

### Step 4: Add templates

```
src/model_generator/stacks/<name>/templates/
    ...                 # one subdirectory per category; .j2 extension
```

Template variables are whatever the generator function passes to
`template.render(...)`. Use the `camel_case` Jinja filter for camelCase
identifiers (Dart/JS stacks) alongside the existing `snake_case` and
`path_to_import` filters.

### Step 5: Test

Add `tests/stacks/<name>/` with:

- Unit tests that render templates against fixture specs and assert correct
  output (no SDK required).
- A smoke script `scripts/smoke_generated_<name>.sh` that regenerates the
  bundled example, runs the target SDK's tool chain, and exits non-zero on
  any error.
- A CI job that runs the smoke script in an environment with the SDK
  installed (see `.github/workflows/ci.yml`'s `generated-flutter` job).

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
