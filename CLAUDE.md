# Claude Agent Instructions — Model Generator

## Overview

One-shot bootstrap code generator for FastAPI backends. Produces database models, API endpoints, tests, and migrations from JSON specifications. Generate once, then evolve manually.

---

## Reading Protocol

### Every Session (Required)
1. **This file** (CLAUDE.md) — you're reading it now
2. **[status/next-session.md](./status/next-session.md)** — current progress and next steps

### Development Sessions
3. **[docs/contributor/](./docs/contributor/)** — reusability rules, project-agnostic coding rules
4. **[docs/agent/template-extension-guide.md](./docs/agent/template-extension-guide.md)** — adding types, templates, generators

### As Needed
- **[docs/README.md](./docs/README.md)** — full documentation index
- **[docs/agent/json-specification-reference.md](./docs/agent/json-specification-reference.md)** — every key, every option
- **[docs/deep-dives/](./docs/deep-dives/)** — constraints, completeness, custom tests

---

## Project Structure

```
model-generator/
├── CLAUDE.md                           # This file
├── README.md                           # User-facing project overview
├── pyproject.toml                      # uv/setuptools config
├── Makefile                            # Dev shortcuts
├── LICENSE                             # MIT
├── status/
│   └── next-session.md                 # Session tracking
├── src/model_generator/                # Main package
│   ├── generate.py                     # CLI entry point (model-gen)
│   ├── validate.py                     # CLI entry point (model-val)
│   ├── generators/                     # Code generators (api, database, enums, etc.)
│   ├── utils/                          # Parsing, loading, templates, quality
│   ├── wizard/                         # Interactive CLI mode
│   ├── schema/model.schema.json        # JSON Schema for model definitions
│   └── stacks/python-fastapi/          # Jinja2 templates for FastAPI stack
├── tests/                              # 273 tests
├── docs/                               # 14 documentation files
│   ├── user/                           # Installation, usage, model design
│   ├── agent/                          # JSON reference, template extension
│   ├── contributor/                    # Reusability, coding rules
│   └── deep-dives/                     # Constraints, completeness, custom tests
├── examples/user-auth-project/         # Example project (generates 143 tests)
│   ├── models/                         # Input specifications
│   └── .model-generator.yaml           # Generator config
└── tmp/                                # Ephemeral files (gitignored)
```

---

## Key Principles

1. **One-shot generation** — Generate all boilerplate once from JSON specs, then maintain manually. No regeneration workflow.
2. **JSON specs are source of truth** — `models/*.model.json` defines everything: fields, constraints, relationships, API config, test config.
3. **Project-agnostic** — Templates must contain zero project-specific code. Everything is driven by the specification.
4. **Quality templates** — Generated code is exemplary: typed, tested, linted, with proper constraints and validators.

---

## Development

```bash
make sync       # uv sync --extra dev
make test       # pytest (skip slow tests)
make test-all   # pytest (all tests)
make lint       # ruff check + mypy
make format     # ruff auto-fix + format
make clean      # remove caches
make update-skills  # pull latest shared Claude skills from the my-skills repo
```

### CLI Entry Points

```bash
uv run model-gen --help          # Code generator
uv run model-val --help          # Spec validator
uv run model-gen --interactive   # Interactive wizard
```

### Running the Example

```bash
uv run model-gen examples/user-auth-project/models --target all
cd examples/user-auth-project
uv venv && uv sync --extra dev
uv run pytest                    # 143 tests
```

---

## Important Notes

- All enum values are UPPERCASE everywhere
- `normalize_decimal` strips trailing zeros: `"100.00000000"` → `"100"`
- `pyproject.toml.j2` only generates if no pyproject.toml exists (bootstrap-only)
- `main.py` needs `ruff check --fix` after regeneration (I001 workaround)
- **NEVER use sed on Jinja2 templates** — shell brace expansion destroys `{{ }}` syntax
- mutmut: pin to `<3.5.0` (3.5.0 is broken), use `also_copy = ["examples/"]`
- `.claude/skills/` is imported from a shared repo via `git subtree` from
  `https://github.com/nuncaeslupus/my-skills.git`. `make update-skills` pulls
  the latest. Project-specific skills can be dropped alongside the shared
  ones — subtree won't touch them.

---

**Last Updated:** 2026-04-02
