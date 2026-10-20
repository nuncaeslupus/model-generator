# Model Generator

[![PyPI](https://img.shields.io/pypi/v/model-generator-kit.svg)](https://pypi.org/project/model-generator-kit/)
[![CI](https://github.com/nuncaeslupus/model-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/nuncaeslupus/model-generator/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

<p align="center">
  <img src="https://raw.githubusercontent.com/nuncaeslupus/model-generator/main/docs/hero.png" width="100%" alt="model-generator: a JSON model spec, run once through model-gen, writes the SQLAlchemy models, Pydantic schemas, FastAPI routes, pytest contract tests and Alembic migrations of a backend">
</p>

**Generate a FastAPI backend from JSON model specs, once, then own the code.**

Every new API backend starts with the same boilerplate: ORM models, request and
response schemas, CRUD routes, tests and migrations, all kept consistent by hand.
`model-gen` writes all of it from one `*.model.json` spec per domain: typed,
linted and with a contract test suite that passes. Then you edit the generated code
like any other code. There is no regeneration loop and no runtime dependency.

## Quick start

```bash
uv tool install model-generator-kit      # or: pipx install model-generator-kit
model-gen --version                      # model-gen 0.1.4
```

This puts `model-gen` (generator) and `model-val` (spec validator) on your PATH.
The PyPI name is `model-generator-kit`. For the interactive wizard, install
`"model-generator-kit[interactive]"`. The tool's Python floor is `requires-python`
in `pyproject.toml`; the generated backend uses PEP 695 generics, so it needs a newer
Python, stated in its own `pyproject.toml`.

In a project directory with a `.model-generator.yaml` and a `models/` folder:

```bash
model-val models/                 # validate the specs
model-gen models/ --target all    # write the backend
```

## Example

`.model-generator.yaml`:

```yaml
project:
  name: "Notes"
  version: "0.1.0"
stack: python-fastapi
```

`models/notes.model.json`:

```json
{
  "domain": "notes",
  "entities": {
    "Note": {
      "table": "notes",
      "fields": {
        "id": { "type": "uuid", "primary_key": true, "auto_generate": true },
        "title": { "type": "text", "max_length": 120, "required": true },
        "body": { "type": "text" },
        "pinned": { "type": "boolean", "default": false }
      },
      "timestamps": { "created": true, "updated": true },
      "api": { "enabled": true, "prefix": "notes", "endpoints": ["list", "get", "create", "update", "delete"], "pagination": true }
    }
  }
}
```

```
$ model-val models/
✅ notes.model.json: Valid (1 entities)

✅ All 1 model(s) valid
$ model-gen models/ --target all
...
✅ Generated 15 file(s)
```

The files written for `Note`, next to the shared infrastructure (`main.py`, engine,
base, errors, `pyproject.toml`, `alembic/`, test conftests):

```
backend/src/database/models/note.py       SQLAlchemy model
backend/src/api/models/note_request.py    CreateNoteRequest, UpdateNoteRequest
backend/src/api/models/note_response.py   NoteResponse
backend/src/api/routes/note.py            GET/POST /notes, GET/PUT/DELETE /notes/{id}
backend/tests/factories/note.py           FactoryBoy factory
tests/contract/api/test_note_api.py       contract tests
```

`backend/src/database/models/note.py` (excerpt):

```python
class Note(Base):
    __tablename__ = "notes"

    # ====== Primary Key ======
    id: Mapped[uuid.UUID] = mapped_column(
        PortableUuid, primary_key=True, default=uuid.uuid4
    )

    # ====== Core Fields ======
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str | None] = mapped_column(String())
    pinned: Mapped[bool | None] = mapped_column(Boolean, default=False)
```

The generated project's own suite runs straight away:

```
$ uv sync --extra dev && uv run pytest -q
17 passed, 1 warning in 0.41s
```

The bundled `examples/user-auth-project` (users, roles, sessions, owner-scoped
portfolio, auth) produces a passing test suite the same way:

```bash
git clone https://github.com/nuncaeslupus/model-generator && cd model-generator
uv sync --extra dev
cd examples/user-auth-project
uv run model-gen models/ --target all
uv venv && uv sync --extra dev
uv run pytest
```

## Use with AI agents

There is no MCP server; an agent drives the CLI and the docs written for it.

- **Spec writing:** [Model Design Questions](./docs/agent/model-design-questions.md)
  is a question list for eliciting a spec from a user, and the
  [JSON Specification Reference](./docs/agent/json-specification-reference.md)
  documents every key.
- **Validation loop:** `model-val <file-or-dir>` exits 1 on an invalid spec and
  prints the error per file. Specs can point `"$schema"` at
  `src/model_generator/schema/model.schema.json` for editor validation.
- **Preview before writing:** `model-gen models/ --dry-run` lists the files, and
  `--diff` shows the changes, without writing anything.
- **Extending the generator:** [Template Extension Guide](./docs/agent/template-extension-guide.md).

## Features

- **Database:** SQLAlchemy models with constraints, indexes, relationships,
  enums and cross-field check constraints.
- **API:** Pydantic request/response models with validators, FastAPI CRUD routes,
  pagination, optional owner scoping and auth scaffolding (`auth.strategy: bcrypt-session`).
- **Tests:** pytest contract tests with FactoryBoy factories.
- **Migrations:** Alembic infrastructure.
- **Layout:** per-entity (default) or per-domain files; all paths set in `.model-generator.yaml`.
- **Stacks:** `python-fastapi` (default). A `flutter` stack that generates a typed
  Dart client from the same spec is on `main`, not yet released; see
  [Flutter Stack](./docs/user/flutter.md).

## Usage

```
model-gen [--target TARGET] [--stack STACK] [--dry-run] [--diff]
          [--clean [--scope selective|full]] [--clear-only]
          [--no-root-files] [--interactive] [model]
```

| Option | Does |
|---|---|
| `--target` | What to generate (default `all`); e.g. `database`, `api-routes`, `api-tests`, `migration-init` |
| `--dry-run` / `--diff` | List files / show changes without writing |
| `--clean`, `--scope` | Delete generated files before generating |
| `--clear-only` | Delete generated files only |
| `--no-root-files` | Skip `pyproject.toml`, `alembic.ini` and `.gitignore` |
| `--stack` | Stack to use (default: from `.model-generator.yaml`, else `python-fastapi`) |
| `--interactive` | Wizard (needs the `interactive` extra) |

Run it from the project root: the config is read from the current directory. The
full target list and spec options are in the [Quick Reference](./docs/user/quick-reference.md).

## Documentation

- **Users:** [Installation](./docs/user/installation.md),
  [Model Design Guide](./docs/user/model-design-guide.md),
  [Usage Guide](./docs/user/usage-guide.md),
  [Quick Reference](./docs/user/quick-reference.md),
  [Architecture, Troubleshooting & Upgrades](./docs/user/architecture.md),
  [Extending Generated Code](./docs/user/extending-generated-code.md),
  [Flutter Stack](./docs/user/flutter.md)
- **Agents:** [Model Design Questions](./docs/agent/model-design-questions.md),
  [JSON Specification Reference](./docs/agent/json-specification-reference.md),
  [Template Extension Guide](./docs/agent/template-extension-guide.md)
- **Deep dives:** [Constraints](./docs/deep-dives/constraints.md),
  [Completeness Guide](./docs/deep-dives/completeness-guide.md),
  [Custom Tests](./docs/deep-dives/custom-tests.md)
- **Contributors:** [Skill Reusability](./docs/contributor/skill-reusability.md),
  [Project-Agnostic Rules](./docs/contributor/project-agnostic-rules.md)
- [Changelog](./CHANGELOG.md), [full docs index](./docs/README.md)

## Development

```bash
make sync        # uv sync --extra dev
make test        # pytest, skipping slow tests
make test-all    # pytest, all tests
make lint        # ruff check + mypy
make smoke-example   # regenerate the bundled example in a temp tree and run its suite
```

## Related projects

- [claude-arsenal](https://github.com/nuncaeslupus/claude-arsenal) — spec-driven Claude Code workflow and gated task queue.
- [drawspec](https://github.com/nuncaeslupus/drawspec) — declarative diagram spec → clean SVG/PNG/text, writable by LLMs; MCP server included.
- [doc-control](https://github.com/nuncaeslupus/doc-control) — lets AI agents edit Word documents as tracked changes.
- [literary-critic](https://github.com/nuncaeslupus/literary-critic) — LLM manuscript analysis the way a professional editor would.
- [integral-job-search](https://github.com/nuncaeslupus/integral-job-search) — candidate-centred job search run in Claude Code.

## License

[MIT](LICENSE)
