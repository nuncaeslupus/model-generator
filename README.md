# Model Generator

A **one-shot bootstrap code generator** that turns JSON specifications into production-ready API backends — database models, API endpoints, tests, and migrations. The generator is stack-agnostic by design; it currently ships the **`python-fastapi`** stack (chosen with `--stack`, the default).

## What It Does

- **Database models** — SQLAlchemy ORM with constraints, relationships, and indexes
- **API models** — Pydantic request/response schemas with validators
- **API routes** — FastAPI CRUD endpoints
- **Tests** — pytest contract tests with FactoryBoy factories (a full contract suite in the example project)
- **Migrations** — Alembic infrastructure

## Install

`model-generator` is a build-time scaffolding tool, not a runtime dependency of
the backends it generates. Install it as an isolated global CLI:

```bash
uv tool install model-generator-kit     # or: pipx install model-generator-kit
```

This puts `model-gen` and `model-val` on your PATH. For the interactive wizard,
add the extra: `uv tool install "model-generator-kit[interactive]"`.

> The PyPI package is `model-generator-kit` (the name `model-generator` was already
> taken); the commands it installs are `model-gen` and `model-val`.

## Quick Start

```bash
# In any project directory, scaffold from your JSON specs
model-gen models/ --target all

model-gen --version    # confirm the install
```

To try the bundled example from a clone of this repo:

```bash
git clone https://github.com/nuncaeslupus/model-generator && cd model-generator
uv sync --extra dev
cd examples/user-auth-project
uv run model-gen models/ --target all
uv venv && uv sync --extra dev
uv run pytest  # the generated contract suite passes
```

For your own project, see the [Installation Guide](./docs/user/installation.md).

## Documentation

### For Users

- **[Installation Guide](./docs/user/installation.md)** — Install, configure, first project
- **[Model Design Guide](./docs/user/model-design-guide.md)** — How to design comprehensive JSON specifications
- **[Usage Guide](./docs/user/usage-guide.md)** — CLI workflows, generation, cleanup, interactive mode
- **[Quick Reference](./docs/user/quick-reference.md)** — Lookup tables: field types, constraints, options
- **[Extending Generated Code](./docs/user/extending-generated-code.md)** — Business logic, custom routes, migrations

### For Agents

- **[Model Design Questions](./docs/agent/model-design-questions.md)** — Systematic Q&A for eliciting model specs from users
- **[Template Extension Guide](./docs/agent/template-extension-guide.md)** — Add types, templates, generators
- **[JSON Specification Reference](./docs/agent/json-specification-reference.md)** — Exact format, every key, every option

### Deep Dives

- **[Constraints](./docs/deep-dives/constraints.md)** — DB vs API constraint placement, cross-field constraints
- **[Completeness Guide](./docs/deep-dives/completeness-guide.md)** — JSON specification checklist
- **[Custom Tests](./docs/deep-dives/custom-tests.md)** — Extending the generated test suite

### For Contributors

- **[Skill Reusability](./docs/contributor/skill-reusability.md)** — Core principles for reusable generation
- **[Project-Agnostic Rules](./docs/contributor/project-agnostic-rules.md)** — Coding rules for templates and scripts

## Development

```bash
# Install in editable mode with dev dependencies
uv sync --extra dev

# Run the test suite
uv run pytest tests/ -v
```

### Test Suite

| File | What It Covers |
|------|---------------|
| `test_generators.py` | Each generator (database, API models, routes, tests, enums, constraints, infrastructure), immutable entities |
| `test_edge_cases.py` | JSON comments, invalid input, config loading, deep merge, shared enums/constraints, file scanners, partial generation |
| `test_wizard.py` | Wizard imports, prompt fallbacks, menu flow, project setup, clean and test runner actions |
| `test_template_utils.py` | `path_to_import`, `wrap_text`, template environment, custom Jinja2 filters |
| `test_cli.py` | CLI flags: `--interactive`, `--clear-only`, `--dry-run`, `--diff`, missing model |
| `test_full_generation.py` | End-to-end generation from example project |
| `test_integration.py` | Full generation pipeline |
| `test_validation.py` | JSON schema validation |
| `test_utils.py` | Utility functions |

## Philosophy

Define specifications once in JSON. Generate production-ready scaffolds. Then maintain and evolve manually. The generated code is yours — no lock-in, no regeneration, full control.

---

**Model Generator** | Bootstrap Tool for API Backends | v0.1.2
