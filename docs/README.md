# Model Generator Documentation

Index of all documentation, organized by audience.

---

## For Users

Getting started, designing models, and using the CLI.

| Document | Description |
|----------|-------------|
| [Installation Guide](./user/installation.md) | Install, configure, create your first project |
| [Model Design Guide](./user/model-design-guide.md) | Step-by-step guide to designing JSON specifications |
| [Usage Guide](./user/usage-guide.md) | CLI workflows: generate, preview, clean, interactive mode |
| [Quick Reference](./user/quick-reference.md) | Lookup tables: field types, constraints, options, CLI flags |
| [Architecture, Troubleshooting & Upgrades](./user/architecture.md) | Pipeline overview, generated layout, common errors, upgrade story |
| [Extending Generated Code](./user/extending-generated-code.md) | Add business logic, custom routes, migrations |

---

## For Agents

Autonomous model design and template extension.

| Document | Description |
|----------|-------------|
| [Model Design Questions](./agent/model-design-questions.md) | Systematic Q&A for eliciting model specs from users |
| [Template Extension Guide](./agent/template-extension-guide.md) | Add field types, templates, and generators |
| [JSON Specification Reference](./agent/json-specification-reference.md) | Every key, every option, every format |

---

## Deep Dives

Detailed treatment of specific features.

| Document | Description |
|----------|-------------|
| [Constraints](./deep-dives/constraints.md) | DB vs API constraint placement, cross-field constraints, naming |
| [Completeness Guide](./deep-dives/completeness-guide.md) | JSON specification checklist, relationship rules, shared resources |
| [Custom Tests](./deep-dives/custom-tests.md) | TDD workflow, test factories, extending the test suite |

---

## For Contributors

Maintaining the tool itself.

| Document | Description |
|----------|-------------|
| [Skill Reusability](./contributor/skill-reusability.md) | Core principle: zero project-specific code |
| [Project-Agnostic Rules](./contributor/project-agnostic-rules.md) | DO/DON'T patterns, three-structure test, coding rules |

---

## Stack Documentation

| Document | Description |
|----------|-------------|
| [Python-FastAPI Stack](../src/model_generator/stacks/python-fastapi/README.md) | Stack overview, template structure, how to add stacks |

---

## Quick Decision: Where to Look

| I want to... | Go to |
|--------------|-------|
| Install and try the example | [Installation Guide](./user/installation.md) |
| Understand how generation works / fix a common error | [Architecture, Troubleshooting & Upgrades](./user/architecture.md) |
| Design a new JSON model | [Model Design Guide](./user/model-design-guide.md) |
| Look up a field type or option | [Quick Reference](./user/quick-reference.md) |
| Understand the exact JSON format | [JSON Specification Reference](./agent/json-specification-reference.md) |
| Add a new field type to the generator | [Template Extension Guide](./agent/template-extension-guide.md) |
| Walk a user through model design | [Model Design Questions](./agent/model-design-questions.md) |
| Understand constraint placement | [Constraints](./deep-dives/constraints.md) |
| Add business logic to generated code | [Extending Generated Code](./user/extending-generated-code.md) |
| Contribute to the generator itself | [Skill Reusability](./contributor/skill-reusability.md) |
