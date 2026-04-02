# Skill Reusability Principles

**Purpose:** Core principles for maintaining a truly reusable code generation skill.

**Last Updated:** 2026-01-17

---

## 🎯 Core Principle

> **This skill directory contains a standalone, reusable tool.**
>
> It must work for ANY project without modification. It must contain ZERO references to any specific project.

---

## 🧩 What Is This Skill?

A **generic code generator** for FastAPI/SQLAlchemy projects that:

- Reads JSON entity definitions
- Generates database models, API models, routes, and tests
- Adapts to different project structures via configuration

**Not specific to:**

- Trading platforms
- E-commerce
- SaaS applications
- Any particular domain

**Works for:**

- Any Python FastAPI + SQLAlchemy project
- Any project structure (monorepo, backend-only, full-stack)
- Any domain (finance, retail, healthcare, etc.)

---

## 📋 Skill Responsibilities

### What the Skill Provides

✅ **Generic Templates**

- Jinja2 templates for database models, API models, routes, tests
- Work with ANY entity type (User, Product, Order, etc.)
- Use variables for all project-specific content

✅ **Type System**

- Mappings: abstract types → SQLAlchemy/Pydantic types
- Generic: uuid, text, financial, enum, etc.
- No domain-specific types

✅ **Configuration System**

- Projects define their structure in `.model-generator.yaml`
- Skill adapts to project's paths
- Deep merge of project config with stack defaults

✅ **Generation Logic**

- Read JSON entity definitions
- Render templates with project data
- Write to project-specified paths

✅ **Documentation**

- How the skill works
- JSON schema reference
- Configuration options
- Generic examples

### What the Skill Does NOT Provide

❌ **Domain-Specific Logic**

- No trading-specific code
- No e-commerce-specific code
- No authentication implementation
- No business rules

❌ **Project Structure Assumptions**

- No hardcoded paths
- No assumed directory layout
- No required file locations

❌ **Project Metadata**

- No project names
- No copyright statements
- No team information

---

## 🚫 Forbidden References

The skill must NEVER contain:

### 1. Project Names

❌ "Trading Kit" ❌ "MyApp" ❌ "Acme Corp"

### 2. Hardcoded Paths

❌ `backend/src/database/models` ❌ `tests/contract/api` ❌ `services/api/src`

✅ Instead: `config["paths"]["database_models"]`

### 3. Hardcoded Imports

❌ `from backend.src.api.validators import X` ❌ `from myapp.database.models import Y`

✅ Instead: `from {{ db_models_import }} import Y`

### 4. Domain-Specific Entities

❌ User, Exchange, Product, Order (in skill code) ❌ Special cases for specific entity types

✅ Instead: Generic entity handling based on field types/attributes

### 5. Business Logic

❌ How to calculate trade fees ❌ How to validate credit cards ❌ Domain-specific validation rules

✅ Instead: Generic validation patterns (non_negative, length, etc.)

---

## ✅ Allowed Patterns

### Generic Examples in Documentation

**✅ GOOD:**

```markdown
Example: User Authentication

{ "domain": "users", "entities": { "User": { "fields": { "email": { "type": "text", "unique": true }, "password_hash": { "type": "text", "api_exclude_response": true } } } } }
```

This is generic - ANY project might have users.

**❌ BAD:**

```markdown
In Trading Kit, we define exchanges like this...
```

Don't reference specific projects.

### Multiple Structure Examples

**✅ GOOD:**

```yaml
# Example 1: Full-stack project
paths:
  database_models: backend/src/database/models

# Example 2: Backend-only project
paths:
  database_models: src/database/models

# Example 3: Monorepo
paths:
  database_models: services/api/src/database/models
```

Shows flexibility, no specific project.

### Generic Entity Types

**✅ GOOD:**

```python
# In template
{% for entity_name, entity in model.entities.items() %}
    # Works for User, Product, Order, whatever
{% endfor %}
```

**❌ BAD:**

```python
# In template
{% if entity_name == "Exchange" %}
    # Special handling for exchanges
{% endif %}
```

---

## 🔍 Self-Test Questions

Before committing changes, ask:

### 1. The Rename Test

> "If someone renamed their project, would the skill break?"

- ✅ NO → Good (skill doesn't reference project)
- ❌ YES → Coupled (fix it)

### 2. The Domain Test

> "Could a e-commerce site use this skill without changes?"

- ✅ YES → Good (truly generic)
- ❌ NO → Domain-specific (make it generic or document as limitation)

### 3. The Path Test

> "If someone uses `src/models/` instead of `backend/src/database/models/`, does it work?"

- ✅ YES → Good (configurable paths)
- ❌ NO → Hardcoded (use config)

### 4. The Import Test

> "Are all imports generated from config paths?"

- ✅ YES → Good (dynamic imports)
- ❌ NO → Hardcoded (use path_to_import filter)

### 5. The Documentation Test

> "Does the skill documentation explain how it works, not how a specific project uses it?"

- ✅ YES → Good (skill-focused docs)
- ❌ NO → Project-specific (move to project docs)

---

## 📚 Documentation Scope

### What Skill Docs Should Explain

✅ How to configure paths ✅ JSON schema options ✅ Available field types ✅ Template structure ✅ How to add custom logic (generic pattern) ✅ Multiple project structure examples

### What Skill Docs Should NOT Explain

❌ How to use this in Project X ❌ Project X's architecture ❌ Project X's entities ❌ Project X's business rules ❌ Why Project X chose certain patterns

**Reason:** Projects using the skill should document their own usage.

---

## 🔄 Configuration Design

### Stack Config (In Skill)

**File:** `stacks/python-fastapi/config.yaml`

**Contains:**

```yaml
# Technical mappings only
types:
  uuid:
    database:
      column: "Column(String, primary_key=True)"
  financial:
    database:
      column: "Column(Numeric(20, 8))"

# Default paths (can be overridden)
paths:
  database_models: backend/src/database/models
  api_models: backend/src/api/models
```

**Rules:**

- ✅ Type mappings (technical)
- ✅ Default paths (sensible defaults)
- ✅ Pattern definitions (constraints, indexes)
- ❌ Project metadata (name, description)
- ❌ Specific entity definitions
- ❌ Business logic

### Project Config (In Project Using Skill)

**File:** `.model-generator.yaml` (in project root, NOT in skill)

**Contains:**

```yaml
# Project-specific configuration
project:
  name: "Your Project Name"
  description: "Your project description"

# Override paths for your structure
paths:
  database_models: src/database/models
```

**Rules:**

- ✅ Project metadata
- ✅ Path overrides for project structure
- ✅ References to specific entities (in entity JSON files)

---

## 🎯 File Boundaries

### Files in Skill Directory

**Location:** `.agents/model-generator/` or wherever skill is installed

**Contents:**

- `scripts/generate.py` - Generation logic
- `stacks/{stack}/config.yaml` - Stack technical config
- `stacks/{stack}/templates/*.j2` - Generic templates
- `docs/` - How the skill works
- `SKILL.md` - Main skill documentation

**Rules:**

- ✅ Zero hardcoded paths
- ✅ Zero hardcoded imports
- ✅ Zero project references
- ✅ Only generic examples
- ✅ Documentation about the skill itself

### Files in Project Using Skill

**Location:** Project root (where `.model-generator.yaml` lives)

**Contents:**

- `.model-generator.yaml` - Project's config
- `models/*.model.json` - Project's entities
- Generated code (wherever project configured)
- Custom code (project-specific)

**Rules:**

- ✅ Can reference specific entities
- ✅ Can hardcode paths (in non-generated files)
- ✅ Can include business logic
- ✅ Can document project-specific usage

---

## 🧪 Testing Reusability

### Minimum Viable Test

Create three test projects with different structures:

**Project 1: Full-stack**

```
test-fullstack/
├── .model-generator.yaml
├── backend/src/database/models/
└── backend/src/api/models/
```

**Project 2: Backend-only**

```
test-backend/
├── .model-generator.yaml
├── src/database/models/
└── src/api/models/
```

**Project 3: Monorepo**

```
test-monorepo/
├── .model-generator.yaml
├── services/
│   └── api/
│       ├── src/database/models/
│       └── src/api/models/
```

**Test:**

1. Copy skill to each project
2. Create `.model-generator.yaml` with appropriate paths
3. Create identical entity JSON
4. Run generator
5. Verify all three generate valid code

**Success:** All three work without modifying skill files

---

## 📊 Checklist for Skill Changes

Before committing changes to skill:

- [ ] No hardcoded file paths
- [ ] No hardcoded import statements
- [ ] No project names or references
- [ ] No domain-specific entity names in logic
- [ ] All paths from `config["paths"]`
- [ ] All imports generated dynamically
- [ ] Documentation is skill-focused (not project-focused)
- [ ] Examples are generic or show multiple domains
- [ ] Passed mental three-structure test
- [ ] Could be copied to different domain project unchanged

---

## 🚨 Red Flags

If you see these in the skill, stop and refactor:

### In Code

```python
# ❌ Project reference
if project_name == "Trading Kit":

# ❌ Domain-specific logic
if entity.table == "exchanges":

# ❌ Hardcoded path
output_dir = Path("backend/src/database/models")

# ❌ Hardcoded import
from backend.src.api.validators import X
```

### In Templates

```jinja2
{# ❌ Project reference #}
Copyright © Trading Kit Team

{# ❌ Hardcoded import #}
from backend.src.database.models.enums import X

{# ❌ Domain-specific logic #}
{% if entity.domain == "trading" %}
```

### In Config

```yaml
# ❌ Project metadata in stack config
project:
  name: "Specific Project"

# ❌ Hardcoded imports
import: "from backend.src.api import X"
```

### In Documentation

```markdown
<!-- ❌ Project-specific usage -->

In Trading Kit, we use this to...

<!-- ❌ Domain-specific examples only -->

Example: How to create a cryptocurrency exchange
```

---

## 💡 Making Changes Generic

When you need to add a feature:

### Step 1: Identify the Pattern

**Specific:** "I need to add websocket support for exchanges" **Generic:** "I need to add optional async operations for entities"

### Step 2: Make It Configurable

```json
// ❌ Hardcoded in template
{% if entity.table == "exchanges" %}
    async def connect_websocket():
{% endif %}

// ✅ Configurable field
{
  "Exchange": {
    "supports_async_operations": true  // ← Generic flag
  }
}

// ✅ Generic template logic
{% if entity.supports_async_operations | default(false) %}
    async def connect():
{% endif %}
```

### Step 3: Document Generically

```markdown
# ❌ Domain-specific docs

## Websocket Support for Exchanges

# ✅ Generic docs

## Async Operations Support

Set `supports_async_operations: true` on any entity to generate async methods.
```

---

## 🎓 Summary

| Principle      | Skill (Generic)     | Project (Specific)   |
| -------------- | ------------------- | -------------------- |
| **References** | None to any project | Can reference skill  |
| **Paths**      | From config         | In config            |
| **Imports**    | Dynamic from paths  | Can be hardcoded     |
| **Entities**   | Generic templates   | Specific definitions |
| **Logic**      | Patterns, not rules | Business rules       |
| **Docs**       | How it works        | How we use it        |
| **Examples**   | Multiple domains    | Our domain           |

**The Golden Rule:**

> The skill should be **copy-paste reusable** across ANY domain without touching a single file.
>
> If someone needs to edit skill files to use it, we failed at reusability.

---

## 📖 Related Documentation

- [Project-Agnostic Rules](./project-agnostic-rules.md) - Detailed coding rules
- [stacks/python-fastapi/README.md](../../src/model_generator/stacks/python-fastapi/README.md) - Stack documentation

**Note:** These docs are all in the skill directory and contain NO project-specific references.
