# JSON Specification Reference

Machine-precise reference for model-generator JSON specifications. Every key, every option, every format.

---

## Top-Level Structure

```json
{
  "$schema": "./schema/model.schema.json",
  "domain": "string (required)",
  "description": "string (optional, for module docstring)",
  "entities": { ... }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `$schema` | string | No | Path to JSON schema for editor validation |
| `domain` | string | Yes | Domain name (snake_case). Used for file naming: `{domain}.py`, `{domain}_requests.py`, etc. |
| `description` | string | No | Module-level docstring for generated files |
| `entities` | object | Yes | Map of entity names (PascalCase) to entity definitions |

---

## Entity Structure

```json
{
  "EntityName": {
    "table": "string (required)",
    "description": "string (optional)",
    "mutability": "mutable | immutable",
    "fields": { ... },
    "timestamps": { ... },
    "relationships": { ... },
    "indexes": [ ... ],
    "cross_field_constraints": [ ... ],
    "custom_constraints": [ ... ],
    "api": { ... },
    "tests": { ... }
  }
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `table` | string | **required** | Database table name (snake_case) |
| `description` | string | `""` | Entity description. Under ~65 chars for clean `Field()` output; full text goes in docstrings |
| `mutability` | string | `"mutable"` | `"mutable"` (full CRUD) or `"immutable"` (create + read only) |
| `fields` | object | **required** | Map of field names to field definitions |
| `timestamps` | object | `{}` | Timestamp configuration |
| `relationships` | object | `{}` | ORM relationship definitions |
| `indexes` | array | `[]` | Index definitions |
| `cross_field_constraints` | array | `[]` | Multi-field database constraints |
| `custom_constraints` | array | `[]` | Raw SQL constraint expressions |
| `api` | object | `{}` | API generation configuration |
| `tests` | object | `{}` | Test generation configuration |

---

## Field Types

All 12 supported field types with their applicable options:

### `uuid`

```json
{
  "type": "uuid",
  "primary_key": true,
  "auto_generate": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `primary_key` | bool | `false` | Set as table primary key |
| `auto_generate` | bool | `false` | Auto-generate UUID on creation |

**SQLAlchemy:** `Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))`
**Pydantic:** `str | None` (response), `str` (request)

### `text`

```json
{
  "type": "text",
  "max_length": 50,
  "min_length": 3,
  "required": true,
  "unique": true,
  "default": "guest",
  "description": "Username for login"
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_length` | int | **required** | Maximum string length (VARCHAR size) |
| `min_length` | int | — | Minimum length (Pydantic validation) |
| `required` | bool | `false` | NOT NULL constraint |
| `unique` | bool | `false` | UNIQUE constraint |
| `default` | string | — | Default value |
| `description` | string | — | Field description |
| `api_exclude_response` | bool | `false` | Exclude from API response (e.g., passwords) |
| `api_exclude_update` | bool | `false` | Exclude from update request (immutable fields) |
| `api_readonly` | bool | `false` | Read-only in API |
| `constraints` | array | `[]` | Validation constraints |

**SQLAlchemy:** `Column(String(50), nullable=False, unique=True)`
**Pydantic:** `str` (request), `str | None` (response)

### `longtext`

```json
{
  "type": "longtext",
  "required": false,
  "description": "Extended notes"
}
```

Same options as `text` except no `max_length` (unlimited).

**SQLAlchemy:** `Column(Text, nullable=True)`

### `financial`

```json
{
  "type": "financial",
  "precision": 18,
  "scale": 8,
  "default": "0.00",
  "required": true,
  "constraints": [{"type": "non_negative"}]
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `precision` | int | `20` | Total digits |
| `scale` | int | `8` | Decimal places |
| `default` | string | — | Default value (as string: `"0.00"`) |
| `required` | bool | `false` | NOT NULL |
| `constraints` | array | `[]` | Typically `non_negative` or `positive` |

**SQLAlchemy:** `Column(Numeric(20, 8), nullable=False, default=Decimal("0.00"))`
**Pydantic:** `str` (request/response — string representation for precision)

### `percentage`

```json
{
  "type": "percentage",
  "default": "0.0",
  "constraints": [{"type": "range", "min": 0, "max": 1}]
}
```

Same numeric options as `financial`. Fixed precision: `Numeric(5, 4)`.

**SQLAlchemy:** `Column(Numeric(5, 4), nullable=True, default=Decimal("0.0"))`

### `counter`

```json
{
  "type": "counter",
  "default": 0,
  "required": true,
  "constraints": [{"type": "non_negative"}]
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default` | int | — | Default value |
| `required` | bool | `false` | NOT NULL |
| `constraints` | array | `[]` | Typically `non_negative` or `positive` |

**SQLAlchemy:** `Column(Integer, nullable=False, default=0)`
**Pydantic:** `int`

### `boolean`

```json
{
  "type": "boolean",
  "default": true,
  "required": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `default` | bool | — | Default value |
| `required` | bool | `false` | NOT NULL |

**SQLAlchemy:** `Column(Boolean, nullable=False, default=True)`
**Pydantic:** `bool`

### `datetime`

```json
{
  "type": "datetime",
  "required": false
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `required` | bool | `false` | NOT NULL |

**SQLAlchemy:** `Column(DateTime(timezone=True), nullable=True)`
**Pydantic:** `str` (ISO 8601 format)

### `enum`

```json
{
  "type": "enum",
  "enum_name": "UserStatus",
  "default": "active",
  "required": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enum_name` | string | **required** | Enum class name (must exist in `_shared/enums.json`) |
| `default` | string | — | Default enum value |
| `required` | bool | `false` | NOT NULL |

**SQLAlchemy:** `Column(SQLEnum(UserStatus, native_enum=False), nullable=False, default=UserStatus.active)`
**Pydantic:** `UserStatus` (enum type)

### `json_object`

```json
{
  "type": "json_object",
  "required": false
}
```

**SQLAlchemy:** `Column(JSON, nullable=True, default=dict)`
**Pydantic:** `dict[str, Any] | None`

### `json_array`

```json
{
  "type": "json_array",
  "required": false
}
```

**SQLAlchemy:** `Column(JSON, nullable=True, default=list)`
**Pydantic:** `list[Any] | None`

### `reference`

```json
{
  "type": "reference",
  "reference_table": "users",
  "reference_column": "id",
  "on_delete": "CASCADE",
  "required": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `reference_table` | string | **required** | Target table name |
| `reference_column` | string | `"id"` | Target column name |
| `on_delete` | string | `"CASCADE"` | `CASCADE`, `SET NULL`, `RESTRICT`, `NO ACTION` |
| `required` | bool | `false` | NOT NULL |

**SQLAlchemy:** `Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)`

---

## Common Field Options (All Types)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `type` | string | **required** | One of the 12 field types above |
| `required` | bool | `false` | NOT NULL constraint |
| `unique` | bool | `false` | UNIQUE constraint (text, uuid) |
| `default` | varies | — | Default value (type-appropriate) |
| `description` | string | — | Field description for docs/API |
| `api_exclude_response` | bool | `false` | Hide from API response |
| `api_exclude_update` | bool | `false` | Exclude from update request |
| `api_readonly` | bool | `false` | Read-only in API |
| `constraints` | array | `[]` | Validation constraints (see below) |

---

## Constraints

### Single-Field Constraints

```json
"constraints": [
  {"type": "non_negative"},
  {"type": "positive"},
  {"type": "range", "min": 0, "max": 100},
  {"type": "length", "min": 3},
  {"type": "non_negative_or_null"},
  {"type": "positive_or_null"},
  {"type": "range_or_null", "min": 0, "max": 1}
]
```

| Type | SQL Expression | Applies To |
|------|---------------|------------|
| `non_negative` | `field >= 0` | financial, counter, percentage |
| `positive` | `field > 0` | financial, counter |
| `non_negative_or_null` | `field >= 0 OR field IS NULL` | nullable financial/counter |
| `positive_or_null` | `field > 0 OR field IS NULL` | nullable financial/counter |
| `range` | `field >= min AND field <= max` | financial, counter, percentage |
| `range_or_null` | `(range check) OR field IS NULL` | nullable numeric |
| `length` | `length(field) >= min` | text |

**With shared constraint references:**

```json
"constraints": [
  {"type": "range", "min_ref": "FEE_RATE_MIN", "max_ref": "FEE_RATE_MAX"},
  {"type": "length", "min_ref": "USERNAME_MIN_LENGTH"}
]
```

`min_ref` / `max_ref` reference constants from `_shared/constraints.json`.

### Cross-Field Constraints

Defined at entity level in `cross_field_constraints` array:

```json
"cross_field_constraints": [
  {
    "type": "field_less_than_or_equal",
    "name": "available_less_equal_balance",
    "fields": ["available_balance", "balance"],
    "message": "Available balance cannot exceed total balance"
  }
]
```

| Type | SQL Expression |
|------|---------------|
| `sum_equals` | `field1 + field2 + ... = target_field` |
| `product_equals` | `field_a * field_b = result` |
| `field_equal` | `field_a == field_b` |
| `field_not_equal` | `field_a != field_b` |
| `field_less_than` | `field_a < field_b` |
| `field_less_than_or_equal` | `field_a <= field_b` |
| `field_greater_than` | `field_a > field_b` |
| `field_greater_than_or_equal` | `field_a >= field_b` |

**Fields:** `"fields"` is a 2-element array `[field_a, field_b]` where the comparison is `field_a <op> field_b`.

**For `sum_equals`:** `"fields"` lists summands, `"target_field"` is the expected total.

### Custom Constraints

```json
"custom_constraints": [
  {
    "name": "ck_custom_business_rule",
    "expression": "field_a * 0.1 <= field_b AND field_c IS NOT NULL"
  }
]
```

---

## Timestamps

```json
"timestamps": {
  "created": true,
  "updated": true
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `created` | bool | `false` | Add `created_at` column with `server_default=func.now()` |
| `updated` | bool | `false` | Add `updated_at` column with `server_default=func.now(), onupdate=func.now()` |

For immutable entities, typically set `"created": true, "updated": false`.

---

## Relationships

```json
"relationships": {
  "relationship_name": {
    "type": "one_to_many | many_to_one | one_to_one",
    "target": "TargetEntity",
    "foreign_keys": ["field_name"],
    "back_populates": "inverse_relationship_name",
    "cascade": "all, delete-orphan"
  }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `type` | string | Yes | `one_to_many`, `many_to_one`, `one_to_one` |
| `target` | string | Yes | Target entity name (PascalCase) |
| `foreign_keys` | array | No | FK field names (required when ambiguous) |
| `back_populates` | string | Yes | Inverse relationship name on target entity |
| `cascade` | string | No | SQLAlchemy cascade option (for parent side) |

**Both sides must be defined.** If entity A has a `many_to_one` to B, entity B must have a `one_to_many` back to A.

---

## API Configuration

```json
"api": {
  "enabled": true,
  "prefix": "users",
  "endpoints": ["list", "create", "get", "update", "delete"]
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Generate API endpoints for this entity |
| `prefix` | string | table name | URL prefix: `/api/v1/{prefix}` |
| `endpoints` | array | all 5 | Which CRUD endpoints to generate |

**Available endpoints:** `list`, `create`, `get`, `update`, `delete`

For immutable entities, use `["list", "create", "get"]`.

---

## Tests Configuration

```json
"tests": {
  "enabled": true
}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Generate contract tests for this entity |

---

## Indexes

```json
"indexes": [
  {"fields": ["email"]},
  {"fields": ["user_id", "created_at"]},
  {"fields": ["user_id", "exchange_id"], "unique": true}
]
```

Each entry declares a database index over one or more fields. Set `unique: true` to also enforce a unique constraint on the tuple.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `fields` | `string[]` | yes | Columns the index covers (one entry = single-column, multiple = composite) |
| `unique` | `bool` | no | Emit a `UniqueConstraint` instead of a plain `Index` (default `false`) |
| `name` | `string` | no | Override the default auto-generated index name |

Legacy shapes `{"type": "single"\|"composite"\|"unique", "field"\|"fields": ...}` are accepted for backward compatibility and normalized to the canonical form at load time, but new specs should use the form above.

---

## Shared Resources

### `_shared/enums.json`

```json
{
  "enums": {
    "EnumName": {
      "description": "Enum description",
      "values": [
        "simple_string_value",
        {"name": "EXPLICIT_NAME", "value": "explicit_value"},
        {"name": "WITH_DESC", "value": "val", "description": "Documented value"}
      ]
    }
  }
}
```

### `_shared/constraints.json`

```json
{
  "constraints": {
    "CONSTRAINT_GROUP": {
      "description": "Group description",
      "min": {"name": "CONST_MIN", "type": "decimal|integer|pattern", "value": "0"},
      "max": {"name": "CONST_MAX", "type": "decimal|integer|pattern", "value": "1"}
    }
  }
}
```

**Constraint value types:**

| Type | JSON Value | Generated Python |
|------|-----------|-----------------|
| `decimal` | `"0.001"` | `Decimal("0.001")` |
| `integer` | `"3"` | `3` |
| `pattern` | `"^[A-Z]+$"` | `r"^[A-Z]+$"` |

---

## File Organization

```
models/
├── _shared/
│   ├── enums.json              # All enum definitions
│   └── constraints.json        # All constraint constants
├── users.model.json            # Domain: users
├── portfolio.model.json        # Domain: portfolio
└── {domain}.model.json         # Convention: {domain}.model.json
```

- One file per domain
- Domain name matches file name (without `.model.json`)
- Shared resources in `_shared/` directory
- Domain JSONs reference enums/constraints by name only

---

## Complete Annotated Example

```json
{
  "$schema": "./schema/model.schema.json",
  "domain": "users",
  "description": "User management domain with authentication.",
  "entities": {
    "User": {
      "table": "users",
      "description": "User account for the application",
      "mutability": "mutable",
      "fields": {
        "id": {
          "type": "uuid",
          "primary_key": true,
          "auto_generate": true
        },
        "username": {
          "type": "text",
          "required": true,
          "unique": true,
          "max_length": 50,
          "min_length": 3,
          "api_exclude_update": true,
          "description": "Unique login identifier",
          "constraints": [
            {"type": "length", "min_ref": "USERNAME_MIN_LENGTH"}
          ]
        },
        "email": {
          "type": "text",
          "required": true,
          "unique": true,
          "max_length": 255,
          "description": "Contact email address"
        },
        "password": {
          "type": "text",
          "required": true,
          "max_length": 255,
          "api_exclude_response": true,
          "description": "Bcrypt hashed password",
          "constraints": [
            {"type": "length", "min": 8}
          ]
        },
        "status": {
          "type": "enum",
          "enum_name": "UserStatus",
          "required": true,
          "default": "active",
          "description": "Account status"
        },
        "is_active": {
          "type": "boolean",
          "default": true,
          "required": true,
          "description": "Whether account is enabled"
        },
        "balance": {
          "type": "financial",
          "precision": 20,
          "scale": 8,
          "default": "0.00",
          "description": "Account balance",
          "constraints": [
            {"type": "non_negative"}
          ]
        },
        "login_count": {
          "type": "counter",
          "default": 0,
          "description": "Total login count",
          "constraints": [
            {"type": "non_negative"}
          ]
        },
        "bio": {
          "type": "longtext",
          "required": false,
          "description": "User biography"
        },
        "settings": {
          "type": "json_object",
          "required": false,
          "description": "User preferences"
        },
        "tags": {
          "type": "json_array",
          "required": false,
          "description": "User tags"
        }
      },
      "timestamps": {
        "created": true,
        "updated": true
      },
      "relationships": {
        "portfolios": {
          "type": "one_to_many",
          "target": "Portfolio",
          "back_populates": "user",
          "cascade": "all, delete-orphan"
        }
      },
      "indexes": [
        {"fields": ["email"]}
      ],
      "api": {
        "enabled": true,
        "prefix": "users",
        "endpoints": ["list", "create", "get", "update", "delete"]
      },
      "tests": {
        "enabled": true
      }
    },
    "AuditLog": {
      "table": "audit_logs",
      "description": "Immutable record of user actions",
      "mutability": "immutable",
      "fields": {
        "id": {
          "type": "uuid",
          "primary_key": true,
          "auto_generate": true
        },
        "user_id": {
          "type": "reference",
          "reference_table": "users",
          "on_delete": "CASCADE",
          "required": true
        },
        "action": {
          "type": "text",
          "required": true,
          "max_length": 100,
          "description": "Action performed"
        },
        "details": {
          "type": "json_object",
          "description": "Action metadata"
        }
      },
      "timestamps": {
        "created": true,
        "updated": false
      },
      "relationships": {
        "user": {
          "type": "many_to_one",
          "target": "User",
          "back_populates": "audit_logs"
        }
      },
      "api": {
        "enabled": true,
        "prefix": "audit-logs",
        "endpoints": ["list", "create", "get"]
      },
      "tests": {
        "enabled": true
      }
    }
  }
}
```
