# Quick Reference

Lookup tables for model-generator. No prose — just the facts.

---

## Field Types

| Type | Description | SQLAlchemy | Pydantic | Options |
|------|-------------|------------|----------|---------|
| `uuid` | UUID identifier | `Column(String, primary_key=True, default=uuid4)` | `str` | `primary_key`, `auto_generate` |
| `text` | Short string | `Column(String(N))` | `str` | `max_length` (required), `min_length`, `unique` |
| `longtext` | Unlimited text | `Column(Text)` | `str` | — |
| `financial` | High-precision decimal | `Column(Numeric(20, 8))` | `str` | `precision`, `scale`, `default` |
| `percentage` | 0-1 decimal | `Column(Numeric(5, 4))` | `str` | `default` |
| `counter` | Integer | `Column(Integer)` | `int` | `default` |
| `boolean` | True/false | `Column(Boolean)` | `bool` | `default` |
| `datetime` | Timezone-aware timestamp | `Column(DateTime(timezone=True))` | `str` (ISO 8601) | — |
| `enum` | Enumeration | `Column(SQLEnum(Name))` | `EnumName` | `enum_name` (required), `default` |
| `json_object` | JSON dict | `Column(JSON)` | `dict[str, Any]` | — |
| `json_array` | JSON list | `Column(JSON)` | `list[Any]` | — |
| `reference` | Foreign key | `Column(String, ForeignKey(...))` | `str` | `reference_table` (required), `on_delete` |

---

## Field Options

| Option | Applies To | Description | Example |
|--------|-----------|-------------|---------|
| `required` | All | NOT NULL constraint | `true` |
| `unique` | text, uuid | UNIQUE constraint | `true` |
| `default` | All (except reference) | Default value | `"0.00"`, `true`, `0` |
| `description` | All | Docs/API description (keep under ~65 chars) | `"Account balance"` |
| `primary_key` | uuid | Set as PK | `true` |
| `auto_generate` | uuid | Auto-generate UUID | `true` |
| `max_length` | text | VARCHAR size | `50` |
| `min_length` | text | Pydantic min validation | `3` |
| `precision` | financial | Total digits | `20` |
| `scale` | financial | Decimal places | `8` |
| `enum_name` | enum | Enum class name | `"UserStatus"` |
| `reference_table` | reference | Target table | `"users"` |
| `reference_column` | reference | Target column (default: `"id"`) | `"id"` |
| `on_delete` | reference | FK delete behavior | `"CASCADE"` |
| `api_exclude_response` | All | Hide from API response | `true` (for passwords) |
| `api_exclude_update` | All | Exclude from update request | `true` (for username) |
| `api_readonly` | All | Read-only in API | `true` |

---

## Single-Field Constraints

| Type | SQL Expression | Use Case | JSON |
|------|---------------|----------|------|
| `non_negative` | `field >= 0` | Balances, counts | `{"type": "non_negative"}` |
| `positive` | `field > 0` | Prices, quantities | `{"type": "positive"}` |
| `non_negative_or_null` | `field >= 0 OR NULL` | Optional balances | `{"type": "non_negative_or_null"}` |
| `positive_or_null` | `field > 0 OR NULL` | Optional prices | `{"type": "positive_or_null"}` |
| `range` | `field >= min AND <= max` | Bounded values | `{"type": "range", "min": 0, "max": 1}` |
| `range_or_null` | `range OR NULL` | Optional bounded | `{"type": "range_or_null", "min": 0, "max": 100}` |
| `length` | `length(field) >= min` | String minimum | `{"type": "length", "min": 3}` |

**With shared refs:** `{"type": "range", "min_ref": "FEE_MIN", "max_ref": "FEE_MAX"}`

---

## Cross-Field Constraints

| Type | Expression | Example |
|------|-----------|---------|
| `sum_equals` | `a + b = target` | Balance consistency |
| `product_equals` | `a * b = result` | Price * quantity |
| `field_equal` | `a == b` | Confirmation fields |
| `field_not_equal` | `a != b` | Prevent self-reference |
| `field_less_than` | `a < b` | Date ranges (strict) |
| `field_less_than_or_equal` | `a <= b` | OHLC low <= open |
| `field_greater_than` | `a > b` | Profit thresholds |
| `field_greater_than_or_equal` | `a >= b` | OHLC high >= low |

**Format:** `"fields": [field_a, field_b]` → comparison is `field_a <op> field_b`.

---

## Relationship Types

| Type | Direction | FK Side | Example |
|------|-----------|---------|---------|
| `one_to_many` | Parent → Children | Child has FK | User → Portfolios |
| `many_to_one` | Child → Parent | This entity has FK | Portfolio → User |
| `one_to_one` | Either | Child has FK + unique | User → UserProfile |

**Required keys:** `type`, `target`, `back_populates`

**Optional:** `foreign_keys` (when ambiguous), `cascade` (parent side)

---

## API Configuration

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `false` | Generate endpoints |
| `prefix` | string | table name | URL prefix: `/api/v1/{prefix}` |
| `endpoints` | array | all 5 | `list`, `create`, `get`, `update`, `delete` |

**Immutable entity:** `"endpoints": ["list", "create", "get"]`

---

## Entity Configuration

| Key | Values | Description |
|-----|--------|-------------|
| `mutability` | `mutable` (default), `immutable` | Controls update/delete availability |
| `timestamps.created` | `true`/`false` | Add `created_at` column |
| `timestamps.updated` | `true`/`false` | Add `updated_at` column |

---

## Project Config (Top-Level YAML Keys)

Top-level keys in `.model-generator.yaml` (siblings of `paths:`, `project:`, `stack:`).

| Key | Type | Description |
|-----|------|-------------|
| `python_root` | string | Prefix stripped from `paths.*` when forming Python imports. Use for `src/`-layout projects. See [Python Import Root](./usage-guide.md#python-import-root). |

---

## CLI Targets

| Target | Description | Scope |
|--------|-------------|-------|
| `all` | Generate everything in TDD order | All |
| `infrastructure` | Base, engine, main, conftest | Once |
| `database` | SQLAlchemy models | Per domain |
| `factories` | FactoryBoy test factories | Per domain |
| `enums` | Enum definitions from `_shared/enums.json` | Shared |
| `constraints` | Constraint constants from `_shared/constraints.json` | Shared |
| `init` | Database models `__init__.py` | Shared |
| `api-models` | Pydantic request/response models | Per domain |
| `api-init` | API models `__init__.py` | Shared |
| `api-pagination` | Pagination models | Once |
| `api-routes` | FastAPI route handlers | Per domain |
| `api-tests` | Contract tests | Per domain |
| `api-tests-config` | Test conftest | Shared |
| `migration-init` | Alembic infrastructure | Once |

---

## CLI Options

| Flag | Description |
|------|-------------|
| `model` | Path to `.model.json` file or directory |
| `--target TARGET` | Generation target (default: `all`) |
| `--diff` | Show what would change without writing |
| `--dry-run` | List files that would be created |
| `--clean` | Delete generated files before regenerating |
| `--scope {selective\|full}` | Cleanup scope |
| `--clear-only` | Delete generated files without regenerating |
| `--stack STACK` | Stack to use (default: `python-fastapi`) |
| `--interactive` | Launch interactive wizard |

---

## File Naming Conventions

| File | Pattern |
|------|---------|
| Domain model | `{domain}.model.json` |
| Shared enums | `_shared/enums.json` |
| Shared constraints | `_shared/constraints.json` |
| Database model | `{domain}.py` |
| Factory | `factories/{domain}.py` |
| API request models | `{domain}_requests.py` |
| API response models | `{domain}_response.py` |
| API routes | `{domain}.py` |
| Contract tests | `test_{domain}_api.py` |

---

## On-Delete Behaviors

| Value | When to Use |
|-------|-------------|
| `CASCADE` | Child meaningless without parent (orders → user) |
| `SET NULL` | Child survives, loses reference (requires nullable FK) |
| `RESTRICT` | Prevent deletion if children exist |
| `NO ACTION` | Database default (usually same as RESTRICT) |
