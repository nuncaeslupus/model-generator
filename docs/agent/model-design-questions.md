# Model Design Questions

Systematic Q&A for agents to walk through with users when designing JSON model specifications. The model-generator is a **one-shot bootstrap tool** — getting the initial model right is critical.

---

## Phase 1: Domain Understanding

**Goal:** Understand the project before writing any JSON.

### Questions

1. **What does this application do?** What problem does it solve, who uses it?
2. **What are the main workflows?** Walk through 2-3 key user journeys (e.g., "user signs up, creates a portfolio, adds assets, places an order").
3. **Are there compliance or audit requirements?** Some domains require immutable records (financial transactions, medical records, legal documents).
4. **What data is sensitive?** Passwords, tokens, SSNs, financial data — these need `api_exclude_response: true` or encryption.
5. **What external systems will this integrate with?** APIs, payment gateways, exchanges — these may influence entity design.

### Output

A short paragraph describing the domain, its users, and 2-3 core workflows.

---

## Phase 2: Entity Discovery

**Goal:** Identify all entities that need database tables.

### Questions

1. **List every noun from the workflows.** User, Order, Product, Transaction, Portfolio, etc.
2. **Which nouns need persistence?** Not everything is an entity — some are computed values, some are transient.
3. **Which entities are mutable vs immutable?**
   - **Mutable:** User profiles, settings, portfolios (can be updated/deleted)
   - **Immutable:** Transactions, audit logs, events (append-only, no updates)
4. **How do entities group into domains?** A domain is a cohesive set of related entities. Good domain boundaries:
   - `users` — User, ApiKey, UserPreference
   - `portfolio` — Portfolio, PortfolioAsset, Transaction
   - `products` — Product, Category, ProductImage
5. **Are there lookup/reference tables?** Status types, categories, currencies — these are often enums, not entities.

### Output

Table of entities with domain assignment and mutability:

| Entity | Domain | Mutable? | Description |
|--------|--------|----------|-------------|
| User | users | Yes | User account |
| Transaction | portfolio | No | Financial transaction record |

---

## Phase 3: Field Design

**Goal:** Define every field for every entity.

### For Each Entity, Ask:

1. **What uniquely identifies it?** Usually a UUID primary key.
2. **What are the required fields?** Fields that must always have a value.
3. **What are the optional fields?** Fields that can be NULL.
4. **What field type is appropriate?** Use this decision tree:

```
Is it a primary key?
  → uuid (with primary_key: true, auto_generate: true)

Is it a foreign key to another table?
  → reference (with reference_table, on_delete)

Is it a yes/no flag?
  → boolean

Is it a status, type, or category from a fixed set?
  → enum (define in _shared/enums.json)

Is it a date or timestamp?
  → datetime

Is it money, price, or a high-precision decimal?
  → financial (Numeric 20,8)

Is it a percentage (0-1 or 0-100)?
  → percentage (Numeric 5,4)

Is it a count or integer quantity?
  → counter

Is it structured data (settings, metadata)?
  → json_object or json_array

Is it a short string (name, email, title)?
  → text (with max_length)

Is it long-form text (description, notes, bio)?
  → longtext
```

5. **Does it need constraints?**

```
Is it a number that can't be negative?
  → non_negative (or non_negative_or_null if optional)

Is it a number that must be positive (> 0)?
  → positive (or positive_or_null if optional)

Is it bounded to a range?
  → range (with min, max)

Is it a string with a minimum length?
  → length (with min)
```

6. **Is it sensitive?** Passwords, tokens → `api_exclude_response: true`
7. **Is it immutable after creation?** Username, email → `api_exclude_update: true`
8. **Does it have a default value?** What should new records default to?
9. **Is it unique?** Usernames, emails, codes → `unique: true`

### Output

Field table per entity:

| Field | Type | Required | Unique | Default | Constraints | Notes |
|-------|------|----------|--------|---------|-------------|-------|
| id | uuid | Yes | Yes | auto | — | PK |
| username | text(50) | Yes | Yes | — | length min 3 | immutable |
| balance | financial | Yes | No | "0.00" | non_negative | — |

---

## Phase 4: Relationship Mapping

**Goal:** Define how entities connect.

### Questions

1. **Draw the relationship graph.** For each pair of connected entities:
   - What is the cardinality? (one-to-many, many-to-one, one-to-one)
   - Which side has the foreign key?
   - What happens on delete? (CASCADE, SET NULL, RESTRICT)

2. **Both sides must be defined.** If Portfolio has `user_id` → users table:
   - Portfolio needs: `relationships.user` (many_to_one → User, back_populates: "portfolios")
   - User needs: `relationships.portfolios` (one_to_many → Portfolio, back_populates: "user")

3. **Multiple FKs to same table need disambiguation.**
   If an entity has `created_by` and `approved_by` both referencing users:
   - Each relationship needs explicit `foreign_key` specification

4. **Cross-domain references are fine** but both domains must define their side.

### On-Delete Decision Tree

```
Is the child meaningless without the parent?
  → CASCADE (delete children when parent deleted)

Should the child survive but lose the reference?
  → SET NULL (requires nullable FK)

Should deletion be blocked if children exist?
  → RESTRICT (prevent parent deletion)
```

### Output

Relationship table:

| From | Field | To | Type | on_delete | back_populates |
|------|-------|----|------|-----------|----------------|
| Portfolio | user_id | User | many_to_one | CASCADE | portfolios |
| User | — | Portfolio | one_to_many | — | user |

---

## Phase 5: Constraint Definition

**Goal:** Ensure data integrity at the database level.

### Questions

1. **For every numeric field:** Does it need a constraint?

```
Balance, amount, total → non_negative
Price, rate, fee → positive (or positive_or_null if optional)
Percentage → range (0 to 1, or 0 to 100)
Count, quantity → non_negative or positive
```

2. **For every pair of related numeric fields:** Do they have a cross-field constraint?

```
available_balance <= total_balance → field_less_than_or_equal
start_date < end_date → field_less_than
high >= low (OHLC data) → field_greater_than_or_equal
available + locked = total → sum_equals
```

3. **Are there shared constants?** Values used across multiple entities belong in `_shared/constraints.json`:

```json
{
  "constraints": {
    "FEE_RATE": {
      "min": {"name": "FEE_RATE_MIN", "type": "decimal", "value": "0"},
      "max": {"name": "FEE_RATE_MAX", "type": "decimal", "value": "1"}
    }
  }
}
```

Reference with `min_ref` / `max_ref` in field constraints.

4. **Nullable fields with positive constraints:** Never set `default: "0.0"` on a field with `positive_or_null` — zero violates the constraint.

### Output

Constraint summary per entity, plus `_shared/constraints.json` content.

---

## Phase 6: Best Practices Research

**Goal:** Validate the design against domain-specific standards and patterns.

### Questions

1. **Are there industry standards for this domain?** Search for:
   - Financial: OHLC data patterns, balance consistency, audit trails
   - E-commerce: Order state machines, inventory tracking, pricing
   - Healthcare: HIPAA compliance, patient record immutability
   - SaaS: Multi-tenancy, subscription states, usage tracking

2. **What entities do similar applications typically have?** Missing something obvious is worse than having too many entities.

3. **Are the enum values comprehensive?** Status enums should cover the full lifecycle:
   - User: active, inactive, suspended, deleted
   - Order: pending, confirmed, processing, completed, cancelled, failed

4. **Are there edge cases in the constraints?** Test mentally:
   - What if a numeric field is zero? Does that make sense?
   - What if a referenced entity is deleted?
   - What if two unique fields collide?

---

## Phase 7: Validation

**Goal:** Final check before generation.

### Completeness Checklist

For each entity:
- [ ] Every FK field has a corresponding relationship (both sides defined)
- [ ] `back_populates` values match on both sides
- [ ] Nullable numeric fields use `_or_null` constraint variants
- [ ] Required numeric fields use non-`_or_null` constraint variants
- [ ] Balance/amount fields are `non_negative`
- [ ] Price/rate fields are `positive` or `positive_or_null`
- [ ] Percentage fields have `range` constraint
- [ ] Sensitive fields have `api_exclude_response: true`
- [ ] Identity fields have `api_exclude_update: true`
- [ ] Immutable entities have `mutability: "immutable"` and appropriate timestamps/endpoints
- [ ] Password fields enforce minimum length
- [ ] All enums are defined in `_shared/enums.json`
- [ ] All shared constants are in `_shared/constraints.json`
- [ ] Descriptions are under ~65 characters

### Technical Validation

```bash
# Validate JSON against schema
model-val models/

# Preview generation without writing
model-gen models/ --diff

# Generate and test
model-gen models/ --target all
```

---

## Output Format

The final deliverable is a set of files:

```
models/
├── _shared/
│   ├── enums.json              # All enum definitions
│   └── constraints.json        # All shared constraint constants
├── {domain1}.model.json        # First domain
├── {domain2}.model.json        # Second domain
└── ...
```

Plus a `.model-generator.yaml` in the project root:

```yaml
project:
  name: "Project Name"
  description: "Project description"
  version: "0.1.0"

stack: python-fastapi

# Override paths if not using default layout
# paths:
#   database_models: src/database/models
```

---

## Quick Reference: Common Patterns

### User Entity

```json
{
  "User": {
    "table": "users",
    "fields": {
      "id": {"type": "uuid", "primary_key": true, "auto_generate": true},
      "username": {"type": "text", "required": true, "unique": true, "max_length": 50, "api_exclude_update": true, "constraints": [{"type": "length", "min": 3}]},
      "email": {"type": "text", "required": true, "unique": true, "max_length": 255},
      "password": {"type": "text", "required": true, "max_length": 255, "api_exclude_response": true, "constraints": [{"type": "length", "min": 8}]},
      "is_active": {"type": "boolean", "default": true, "required": true}
    },
    "timestamps": {"created": true, "updated": true},
    "api": {"enabled": true, "prefix": "users", "endpoints": ["list", "create", "get", "update", "delete"]},
    "tests": {"enabled": true}
  }
}
```

### Immutable Audit Log

```json
{
  "AuditLog": {
    "table": "audit_logs",
    "mutability": "immutable",
    "fields": {
      "id": {"type": "uuid", "primary_key": true, "auto_generate": true},
      "user_id": {"type": "reference", "reference_table": "users", "on_delete": "CASCADE", "required": true},
      "action": {"type": "text", "required": true, "max_length": 100},
      "details": {"type": "json_object"}
    },
    "timestamps": {"created": true, "updated": false},
    "api": {"enabled": true, "endpoints": ["list", "create", "get"]},
    "tests": {"enabled": true}
  }
}
```

### Lookup Table (Enum Instead)

Don't create an entity for static lookup data. Use enums:

```json
// _shared/enums.json
{
  "enums": {
    "OrderStatus": {
      "values": ["pending", "confirmed", "processing", "completed", "cancelled", "failed"]
    }
  }
}
```

Then reference in entity: `{"type": "enum", "enum_name": "OrderStatus"}`.

### Entity with Cross-Field Constraints

```json
{
  "Portfolio": {
    "fields": {
      "available_balance": {"type": "financial", "constraints": [{"type": "non_negative"}]},
      "locked_balance": {"type": "financial", "constraints": [{"type": "non_negative"}]},
      "total_balance": {"type": "financial", "constraints": [{"type": "non_negative"}]}
    },
    "cross_field_constraints": [
      {
        "type": "sum_equals",
        "name": "balance_consistency",
        "fields": ["available_balance", "locked_balance"],
        "target_field": "total_balance",
        "message": "Total must equal available plus locked"
      }
    ]
  }
}
```
