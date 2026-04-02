# JSON Definition Completeness Guide

## Purpose

Ensure JSON model definitions are **complete and correct** without needing reference implementations. This checklist helps you define entities that won't have missing constraints or relationships.

---

## Constraint Selection by Field Semantics

### Numeric Fields - Choose Based on Business Meaning

| Business Meaning | Valid Values | Constraint Type | JSON |
| --- | --- | --- | --- |
| Count, quantity (required) | > 0 | `positive` | `{"type": "positive"}` |
| Count, quantity (optional) | > 0 or NULL | `positive_or_null` | `{"type": "positive_or_null"}` |
| Balance, amount | >= 0 | `non_negative` | `{"type": "non_negative"}` |
| Balance (optional) | >= 0 or NULL | `non_negative_or_null` | `{"type": "non_negative_or_null"}` |
| Price (required) | > 0 | `positive` | `{"type": "positive"}` |
| Price (optional) | > 0 or NULL | `positive_or_null` | `{"type": "positive_or_null"}` |
| Percentage (0-100) | 0-100 | `range` | `{"type": "range", "min": 0, "max": 100}` |
| Ratio (0-1) | 0-1 | `range` | `{"type": "range", "min": 0, "max": 1}` |
| Timeout (seconds) | 1-300 | `range` | `{"type": "range", "min": 1, "max": 300}` |
| Rate limit | >= 0 | `non_negative` | `{"type": "non_negative"}` |

### Decision Flow for Numeric Constraints

```
Is the field nullable (optional)?
├── YES → Can it be zero?
│         ├── YES → non_negative_or_null
│         └── NO  → positive_or_null
└── NO  → Can it be zero?
          ├── YES → non_negative
          └── NO  → positive
```

### String Fields

| Field Type    | Validation Location | Why                           |
| ------------- | ------------------- | ----------------------------- |
| Email         | Pydantic validator  | Regex not portable across DBs |
| URL           | Pydantic validator  | Complex regex                 |
| Custom format | Pydantic validator  | DB-specific syntax            |
| Length limits | DB constraint       | Simple, universal             |

**Rule**: Put regex-based validation in Pydantic, not database constraints.

> **See Also**: [constraints.md](./constraints.md) for detailed guidance on DB vs Pydantic constraint placement.

---

## Relationship Completeness

### Rule 1: Every FK Needs a Relationship (Both Sides)

```json
// Child entity (has the FK)
"user_id": { "type": "reference", "reference_table": "users" },
"relationships": {
  "user": { "type": "many_to_one", "target": "User", "back_populates": "orders" }
}

// Parent entity (User) - MUST add inverse
"relationships": {
  "orders": { "type": "one_to_many", "target": "Order", "back_populates": "user" }
}
```

### Rule 2: Multiple FKs to Same Table Need Disambiguation

When an entity references the same table multiple times:

```json
// Entity with two user references
"created_by": { "type": "reference", "reference_table": "users" },
"approved_by": { "type": "reference", "reference_table": "users" },

"relationships": {
  "creator": {
    "type": "many_to_one",
    "target": "User",
    "foreign_key": "created_by",      // Disambiguate!
    "back_populates": "created_items"
  },
  "approver": {
    "type": "many_to_one",
    "target": "User",
    "foreign_key": "approved_by",     // Disambiguate!
    "back_populates": "approved_items"
  }
}
```

### Rule 3: Cross-Domain Workflow

**Problem**: Entity A in domain X references Entity B in domain Y, but Y doesn't exist yet.

**Solution**: Two-pass approach

1. **Pass 1**: Create all domain JSONs with intra-domain relationships only
2. **Pass 2**: Add cross-domain relationships to all affected JSONs
3. **Regenerate**: All affected domains

---

## Multi-Domain Dependency Resolution

### Identifying Dependencies

Before generating, map which entities reference other domains:

```
users.json:
  User → references nothing external
  ApiKey → references User (same domain)

orders.json:
  Order → references User (users domain), Product (products domain)
```

### Generation Order

1. Generate domains with no external dependencies first
2. Then generate domains that depend on already-generated domains
3. Finally, add back-references to parent domains

---

## Self-Validation Checklist

After writing a JSON definition, verify:

### For Each Entity

- [ ] Every FK field has a corresponding relationship
- [ ] Every relationship has `back_populates` pointing to the other entity
- [ ] Nullable numeric fields use `_or_null` constraint variants
- [ ] Required numeric fields use non-`_or_null` constraint variants
- [ ] Balance/amount fields are `non_negative`
- [ ] Price/rate fields are `positive` or `positive_or_null`
- [ ] Percentage fields have `range` constraint

### For Each Relationship

- [ ] Both sides defined (parent and child)
- [ ] `back_populates` values match on both sides
- [ ] Multiple FKs to same table have `foreign_key` specified
- [ ] Cascade behavior defined (`cascade: "all, delete-orphan"` where appropriate)

### For Cross-Domain

- [ ] All domains that reference this entity have relationships defined
- [ ] This entity has relationships to entities in other domains it references
- [ ] `foreign_key` used when disambiguation needed

---

## Common Mistakes

| Mistake | Result | Prevention |
| --- | --- | --- |
| Missing `_or_null` on optional price | DB rejects valid NULL | Check nullability, use correct constraint |
| Missing `back_populates` | SQLAlchemy warning, broken navigation | Always define both sides |
| Missing `foreign_key` disambiguation | SQLAlchemy error | Add when 2+ FKs point to same table |
| Forgot cross-domain relationship | Can't navigate between domains | Do Pass 2 after all domains exist |
| Regex in DB constraint | Fails on SQLite | Put regex in Pydantic only |

---

## Centralized Enums & Constraints Architecture

**IMPORTANT**: All enums and constraints are centralized in shared files:

```
models/
├── _shared/
│   ├── enums.json          # ALL enum definitions (single source of truth)
│   └── constraints.json    # ALL constraint constants (single source of truth)
├── users.model.json        # Domain models reference enums/constraints by name
├── exchanges.model.json
└── ...

↓ generates ↓

backend/src/database/models/
├── enums.py               # Generated from _shared/enums.json
├── constraints.py         # Generated from _shared/constraints.json
└── ...
```

**Domain model JSONs only reference enums/constraints by name** - they don't define them inline.

---

## Enum Definitions

**All enums are defined in `models/_shared/enums.json`**:

```json
// models/_shared/enums.json
{
  "enums": {
    "UserStatus": {
      "description": "User account status.",
      "values": ["active", "inactive", "suspended"]
    },
    "OrderType": {
      "description": "Order type classification.",
      "values": [
        { "name": "MARKET", "value": "market" },
        { "name": "LIMIT", "value": "limit" },
        {
          "name": "STOP_LOSS",
          "value": "stop_loss",
          "description": "Stop loss order"
        }
      ]
    }
  }
}
```

### Enum Value Formats

| Format | JSON | Generated Code |
| --- | --- | --- |
| Simple string | `"active"` | `ACTIVE = "active"` |
| Object | `{"name": "GTC", "value": "GTC"}` | `GTC = "GTC"` |
| With description | `{"name": "IOC", "value": "IOC", "description": "Immediate or Cancel"}` | `IOC = "IOC"  # Immediate or Cancel` |

### Using Enums in Domain Models

Domain model JSONs reference enums by name only:

```json
// models/users.model.json
"status": {
  "type": "enum",
  "enum_name": "UserStatus",  // References enum in _shared/enums.json
  "default": "active",
  "description": "User account status"
}
```

---

## Constraint Definitions

**All constraints are defined in `models/_shared/constraints.json`**:

```json
// models/_shared/constraints.json
{
  "constraints": {
    "PERCENTAGE": {
      "description": "Percentage values (0.0 to 1.0)",
      "min": { "name": "PERCENTAGE_MIN", "type": "decimal", "value": "0" },
      "max": { "name": "PERCENTAGE_MAX", "type": "decimal", "value": "1" }
    },
    "FEE_RATE": {
      "description": "Fee rate constraints",
      "min": { "name": "FEE_RATE_MIN", "type": "decimal", "value": "0" },
      "max": { "name": "FEE_RATE_MAX", "type": "decimal", "value": "1" }
    },
    "USERNAME": {
      "description": "Username length constraints",
      "min": { "name": "USERNAME_MIN_LENGTH", "type": "integer", "value": "3" },
      "max": { "name": "USERNAME_MAX_LENGTH", "type": "integer", "value": "50" }
    }
  }
}
```

### Constraint Types

| Type      | JSON Value            | Generated Code     |
| --------- | --------------------- | ------------------ |
| `decimal` | `"value": "0.001"`    | `Decimal("0.001")` |
| `integer` | `"value": "3"`        | `3`                |
| `pattern` | `"value": "^[A-Z]+$"` | `r"^[A-Z]+$"`      |

### Using Constraints in Domain Models

Domain model JSONs reference constraints by name:

```json
// models/exchanges.model.json
"fee_rate": {
  "type": "financial",
  "constraints": [
    { "type": "range", "min_ref": "FEE_RATE_MIN", "max_ref": "FEE_RATE_MAX" }
  ]
}

// models/users.model.json
"username": {
  "type": "text",
  "max_length": 50,
  "constraints": [
    { "type": "length", "min_ref": "USERNAME_MIN_LENGTH" }
  ]
}
```

---

## Why Centralize Enums & Constraints?

1. **Single Source of Truth**: Define once, use everywhere
2. **Consistency**: Same values across all domains
3. **Documentation**: Central place to understand all enums/constraints
4. **Discoverability**: Easy to see what's available
5. **No Duplication**: Avoid defining `UserStatus` in multiple JSONs
