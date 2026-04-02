# Model Design Guide

How to design comprehensive JSON model specifications for model-generator. This is a one-shot bootstrap tool — the initial model must be solid because regeneration overwrites manual changes.

---

## Why This Matters

Model-generator creates your database models, API endpoints, tests, and migrations from JSON specs. After generation, you own the code and maintain it manually. Getting the model right upfront saves hours of post-generation fixes.

---

## Step 1: Understand Your Domain

Before writing JSON, list:

- **Core concepts:** What are the main "things" in your application?
- **Workflows:** Walk through 2-3 user journeys end-to-end
- **Data rules:** What constraints exist? What can't be negative? What must be unique?

**Example:** A portfolio tracker has Users, Portfolios, Assets, and Transactions. Users create portfolios, add assets, and record transactions. Balances can't be negative. Transactions are append-only.

---

## Step 2: Identify Entities

Every noun from your workflows is a candidate entity. Filter:

- **Needs persistence?** → Entity (User, Order, Transaction)
- **Fixed set of values?** → Enum, not entity (OrderStatus, UserRole)
- **Computed or transient?** → Skip (totals, session data)

Group entities into domains — cohesive sets of related entities:

| Domain | Entities |
|--------|----------|
| `users` | User, ApiKey |
| `portfolio` | Portfolio, PortfolioAsset, Transaction |

One `.model.json` file per domain.

---

## Step 3: Define Fields

For each entity, determine every field. Use the type decision tree:

| Question | Type |
|----------|------|
| Primary key? | `uuid` |
| Foreign key? | `reference` |
| Yes/no flag? | `boolean` |
| Fixed set of values? | `enum` |
| Date or timestamp? | `datetime` |
| Money or high-precision decimal? | `financial` |
| Percentage? | `percentage` |
| Integer count? | `counter` |
| Structured data? | `json_object` or `json_array` |
| Short string? | `text` (with `max_length`) |
| Long-form text? | `longtext` |

For each field, also decide:

- **Required?** Must every record have this value?
- **Unique?** Can two records share this value?
- **Default?** What value for new records if not specified?
- **Sensitive?** Passwords → `api_exclude_response: true`
- **Immutable?** Username → `api_exclude_update: true`

---

## Step 4: Add Constraints

Every numeric field should have a constraint. Use this flow:

```
Is it nullable?
├── Yes → Can it be zero?
│         ├── Yes → non_negative_or_null
│         └── No  → positive_or_null
└── No  → Can it be zero?
          ├── Yes → non_negative
          └── No  → positive
```

Common patterns:

| Field Meaning | Constraint |
|--------------|------------|
| Balance, amount | `non_negative` |
| Price, rate | `positive` |
| Optional price | `positive_or_null` |
| Percentage (0-1) | `range` with min=0, max=1 |
| String with minimum | `length` with min |

**Cross-field constraints** for related fields:

```json
"cross_field_constraints": [
  {
    "type": "field_less_than_or_equal",
    "name": "available_less_equal_total",
    "fields": ["available_balance", "total_balance"],
    "message": "Available cannot exceed total"
  }
]
```

**Shared constants** for values used across entities go in `_shared/constraints.json`:

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

Reference with `"min_ref": "FEE_RATE_MIN"` in field constraints.

---

## Step 5: Define Relationships

For every foreign key, define the relationship **on both sides**:

**Child (has the FK):**
```json
"user_id": {"type": "reference", "reference_table": "users", "on_delete": "CASCADE"},
"relationships": {
  "user": {"type": "many_to_one", "target": "User", "back_populates": "portfolios"}
}
```

**Parent (referenced):**
```json
"relationships": {
  "portfolios": {"type": "one_to_many", "target": "Portfolio", "back_populates": "user"}
}
```

Choose `on_delete` behavior:
- **CASCADE** — Delete children with parent (orders when user deleted)
- **SET NULL** — Keep child, null the reference (requires nullable FK)
- **RESTRICT** — Block parent deletion if children exist

If an entity has multiple FKs to the same table, add `"foreign_key"` to disambiguate.

---

## Step 6: Configure API Exposure

For each entity, decide:

1. **Should it have API endpoints?** Set `"api": {"enabled": true}`
2. **What URL prefix?** Default is the table name: `/api/v1/{prefix}`
3. **Which endpoints?** Default is all five: `list`, `create`, `get`, `update`, `delete`

For immutable entities (transactions, audit logs):
```json
"api": {
  "enabled": true,
  "endpoints": ["list", "create", "get"]
}
```

---

## Step 7: Configure Timestamps

| Entity Type | `created` | `updated` |
|-------------|-----------|-----------|
| Mutable | `true` | `true` |
| Immutable | `true` | `false` |
| No timestamps needed | `false` | `false` |

```json
"timestamps": {"created": true, "updated": true}
```

---

## Step 8: Review Checklist

Before generating, verify each entity:

- [ ] Every FK has a relationship defined (both sides)
- [ ] `back_populates` values match on both sides
- [ ] Every numeric field has an appropriate constraint
- [ ] Nullable fields use `_or_null` constraint variants
- [ ] Sensitive fields (password, token) have `api_exclude_response: true`
- [ ] Identity fields (username) have `api_exclude_update: true`
- [ ] Immutable entities use `mutability: "immutable"`
- [ ] All enums defined in `_shared/enums.json`
- [ ] Descriptions under ~65 characters for clean generated code

---

## Common Patterns

### User with Authentication

```json
{
  "fields": {
    "id": {"type": "uuid", "primary_key": true, "auto_generate": true},
    "username": {"type": "text", "required": true, "unique": true, "max_length": 50, "api_exclude_update": true},
    "email": {"type": "text", "required": true, "unique": true, "max_length": 255},
    "password": {"type": "text", "required": true, "max_length": 255, "api_exclude_response": true, "constraints": [{"type": "length", "min": 8}]},
    "is_active": {"type": "boolean", "default": true, "required": true}
  }
}
```

### Append-Only Record

```json
{
  "mutability": "immutable",
  "timestamps": {"created": true, "updated": false},
  "api": {"endpoints": ["list", "create", "get"]}
}
```

### Entity with Shared Constraints

```json
{
  "fee_rate": {
    "type": "financial",
    "constraints": [{"type": "range", "min_ref": "FEE_RATE_MIN", "max_ref": "FEE_RATE_MAX"}]
  }
}
```

---

## YAGNI vs Comprehensive

**Go minimal when:**
- You're prototyping and will iterate
- The domain is well-understood and simple
- You can easily add fields later with Alembic migrations

**Go comprehensive when:**
- This is a production system with data integrity requirements
- The domain has known constraints (financial, compliance)
- Multiple services will write to the same database
- You want generated tests to catch constraint violations

For a one-shot bootstrap tool, **err on the side of comprehensive**. It's easier to remove an unused field than to add a missing constraint after data exists.
