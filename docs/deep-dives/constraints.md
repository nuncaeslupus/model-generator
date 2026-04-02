# Constraint Placement Policy

**Summary:** Guidelines for deciding when to place data validation in the database (SQLAlchemy CheckConstraints) vs. the API layer (Pydantic validators).

---

## Decision Framework

### Place in DATABASE (SQLAlchemy CheckConstraint) When:

| Criteria | Rationale | Example |
| --- | --- | --- |
| **Data integrity is critical** | Database is the last line of defense | `balance >= 0` |
| **Constraint is simple** | Database can enforce efficiently | `quantity > 0` |
| **Multiple writers exist** | API, scripts, migrations all must comply | `status IN ('active', 'inactive')` |
| **Business invariant** | Core domain rules | `available + locked = total` |
| **Range validation** | Simple numeric bounds | `percentage >= 0 AND percentage <= 1` |
| **Non-negative checks** | Financial fields | `price >= 0` |
| **Positive checks** | Quantities, sizes | `size > 0` |
| **Enum validation** | Status, type fields | SQLAlchemy Enum type |

### Place in PYDANTIC (API Validators) When:

| Criteria | Rationale | Example |
| --- | --- | --- |
| **Regex patterns** | SQLite doesn't support `~` operator | Email format, URL format |
| **Complex string formats** | Better error messages | Trading pair format `BTC/USD` |
| **Cross-field validation** | Requires multiple fields | `end_date > start_date` |
| **User-facing errors** | Need readable messages | "Password must be at least 8 characters" |
| **Conditional validation** | Depends on other values | Price required only for limit orders |

### Place in BOTH (Defense in Depth) When:

| Criteria | When to Duplicate |
| --- | --- |
| **Security-critical** | Password min length (API for UX, DB for safety) |
| **Financial data** | Balance checks (API for instant feedback, DB for integrity) |
| **Unique constraints** | User/email uniqueness (handled by DB, reported nicely by API) |

---

## Constraint Types in JSON Model Definition

### Single-Field Constraints

| Type | SQL Expression | Use Case |
| --- | --- | --- |
| `non_negative` | `field >= 0` | Balances, counts |
| `positive` | `field > 0` | Prices, sizes, quantities |
| `non_negative_or_null` | `field >= 0 OR field IS NULL` | Optional non-negative |
| `positive_or_null` | `field > 0 OR field IS NULL` | Optional positive |
| `range` | `field >= min AND field <= max` | Percentages |
| `range_or_null` | `(field >= min AND field <= max) OR field IS NULL` | Optional ranges |
| `length` | `length(field) >= N` | String minimum length |

### Cross-Field Constraints

**New!** Define cross-field constraints using the `cross_field_constraints` array in your entity JSON:

| Type | SQL Expression | Use Case |
| --- | --- | --- |
| `sum_equals` | `field1 + field2 + ... = total` | Balance consistency, shopping cart totals |
| `product_equals` | `field_a * field_b = result` | Area calculations, price \* quantity |
| `field_equal` | `field_a == field_b` | Password confirmation, mirror fields |
| `field_not_equal` | `field_a != field_b` | Currency pair symbols, prevent self-reference |
| `field_less_than` | `field_a < field_b` | Date ranges (strict), price bounds |
| `field_less_than_or_equal` | `field_a <= field_b` | OHLC integrity (low <= open) |
| `field_greater_than` | `field_a > field_b` | Profit margins, performance thresholds |
| `field_greater_than_or_equal` | `field_a >= field_b` | Date ranges, OHLC integrity (high >= low) |

**Example - OHLC Integrity:**

```json
{
  "MarketData": {
    "fields": {
      "open": { "type": "financial", "required": true },
      "high": { "type": "financial", "required": true },
      "low": { "type": "financial", "required": true },
      "close": { "type": "financial", "required": true }
    },
    "cross_field_constraints": [
      {
        "type": "field_greater_than_or_equal",
        "name": "high_greater_equal_low",
        "fields": ["high", "low"],
        "message": "High price must be >= low price"
      },
      {
        "type": "field_less_than_or_equal",
        "name": "low_less_equal_open",
        "fields": ["low", "open"],
        "message": "Low price must be <= open price"
      }
    ]
  }
}
```

**Example - Date Range:**

```json
{
  "Backtest": {
    "fields": {
      "start_date": { "type": "datetime", "required": true },
      "end_date": { "type": "datetime", "required": true }
    },
    "cross_field_constraints": [
      {
        "type": "field_greater_than_or_equal",
        "name": "end_date_after_start_date",
        "fields": ["end_date", "start_date"],
        "message": "End date must be >= start date"
      }
    ]
  }
}
```

**Example - Balance Consistency:**

```json
{
  "Asset": {
    "fields": {
      "available_balance": { "type": "financial" },
      "locked_balance": { "type": "financial" },
      "total_balance": { "type": "financial" }
    },
    "cross_field_constraints": [
      {
        "type": "sum_equals",
        "name": "balance_consistency",
        "fields": ["available_balance", "locked_balance"],
        "target_field": "total_balance",
        "message": "Total balance must equal available plus locked"
      }
    ]
  }
}
```

### Custom Constraints

For complex expressions not covered by the types above, use `custom_constraints`:

```json
"custom_constraints": [
  {
    "name": "ck_custom_business_rule",
    "expression": "field_a * 0.1 <= field_b AND field_c IS NOT NULL"
  }
]
```

---

## Database Constraint Naming Convention

```
ck_{table_name}_{description}
```

Examples:

- `ck_users_username_length` - Username minimum length
- `ck_assets_balance_non_negative` - Balance >= 0
- `ck_orders_filled_quantity_valid` - filled_quantity <= quantity
- `ck_positions_entry_price_positive` - entry_price > 0

---

## Constraints Intentionally in Pydantic Only

The following constraints are **not** in the database because they use regex patterns that SQLite doesn't support:

| Constraint | Reason | Pydantic Location |
| --- | --- | --- |
| Email format | Regex validation | `validate_email_format()` |
| Symbol format | Pattern like `^[A-Z0-9]+$` | `validate_symbol_format()` |
| Trading pair format | Pattern like `^[A-Z0-9]+/[A-Z0-9]+$` | `validate_trading_pair_format()` |
| URL format | URL pattern validation | `AnyUrl` type |

---

## Examples

### In Database (via JSON model definition)

```json
// portfolio.model.json - Asset entity
"total_balance": {
  "type": "financial",
  "constraints": [{ "type": "non_negative" }],
  "description": "Total asset balance"
}
```

### In Pydantic Only (regex-based)

```python
# backend/src/api/models/requests.py
class CreateUserRequest(BaseModel):
    email: str = Field(...)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        # Regex validation here, not in DB
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError("Invalid email format")
        return v
```

### In Database (commented out with reason)

```python
# backend/src/database/models/users.py
__table_args__ = (
    # Email validation moved to Pydantic (regex ~ not supported in SQLite)
    # CheckConstraint("email ~ '^...$'", name="ck_user_email"),
)
```

---

## ⚠️ Nullable Fields with positive_or_null Constraints

### Rule

**DO NOT** specify `default: "0.0"` for nullable fields with `positive_or_null` constraints.

**Reason:** The constraint requires values to be either positive (> 0) OR NULL. Zero violates this constraint.

### Correct Usage

#### ✅ Nullable positive_or_null without default

```json
"stop_loss": {
  "type": "financial",
  "required": false,
  "constraints": [
    {"type": "positive_or_null"}
  ]
}
```

**Generates:**

```python
stop_loss = Column(Numeric(20, 8), nullable=True)  # Defaults to NULL ✓
```

#### ✅ With explicit positive default

```json
"stop_loss": {
  "type": "financial",
  "required": false,
  "default": "100.0",
  "constraints": [
    {"type": "positive_or_null"}
  ]
}
```

**Generates:**

```python
stop_loss = Column(Numeric(20, 8), nullable=True, default=Decimal("100.0"))  # ✓
```

#### ❌ Wrong: Implicit zero default

```json
"stop_loss": {
  "type": "financial",
  "required": false,
  "default": "0.0",  // ❌ VIOLATES CONSTRAINT
  "constraints": [
    {"type": "positive_or_null"}
  ]
}
```

### Common Use Cases

| Field Pattern | Constraint | Default Behavior |
| --- | --- | --- |
| Optional stop loss/take profit | `positive_or_null` | No default (NULL) |
| Optional withdrawal limits | `positive_or_null` | No default (NULL) |
| Required entry price | `positive` | `default: "0.0"` OK |
| Optional balance | `non_negative_or_null` | `default: "0.0"` OK |

### Error Symptoms

```
CHECK constraint failed: ck_table_field_positive_or_null
```

**Fix:** Remove `default: "0.0"` from the field definition and regenerate.

---

## Migration Notes

When moving constraints:

1. **DB → Pydantic**: Comment out in DB with reason, add to Pydantic
2. **Pydantic → DB**: Add `custom_constraints` to JSON, regenerate model
3. **Both**: Ensure error messages are consistent

---

## Constraint Helper Architecture

**Two-File Pattern:** Generic + Domain-Specific

The generator creates a clean separation between project-agnostic and domain-specific constraints:

```
backend/src/database/models/
├── constraints.py          # AUTO-GENERATED - Generic helpers (project-agnostic)
│   ├── check_positive(), check_non_negative(), check_range()
│   ├── check_percentage(), check_datetime_order()
│   ├── check_greater_than_field()
│   └── Generic constants (PERCENTAGE_MIN/MAX, file sizes, etc.)
│
└── constraints_custom.py   # MANUAL - Domain-specific (trading/finance)
    ├── MIN_LEVERAGE, MAX_LEVERAGE, FEE_RATE_MIN/MAX
    ├── check_leverage(), check_fee_rate(), check_confidence()
    └── USERNAME_MIN_LENGTH, EMAIL_PATTERN
```

### Why Two Files?

**constraints.py** (AUTO-GENERATED)

- ✅ Generic SQL helper functions
- ✅ Project-agnostic constants
- ✅ Regenerated from template
- ✅ Never manually edited
- ✅ Portable across any project (e-commerce, healthcare, finance, etc.)

**constraints_custom.py** (MANUAL)

- ✅ Domain-specific business constants
- ✅ Industry-specific validation wrappers
- ✅ Manually curated and maintained
- ✅ Contains business knowledge
- ✅ Consistent with `_custom.py` pattern (routes, tests)

### Usage in Database Models

Generated database models import from **both** files:

```python
# Generated code in backend/src/database/models/financial.py
from .constraints import PERCENTAGE_MIN, PERCENTAGE_MAX, check_positive
from .constraints_custom import MIN_LEVERAGE, MAX_LEVERAGE, check_fee_rate

class Position(Base):
    __tablename__ = "positions"

    leverage = Column(Numeric(20, 8), default=Decimal("1.0"))
    entry_price = Column(Numeric(20, 8), nullable=False)

    __table_args__ = (
        # Generic helper from constraints.py
        CheckConstraint(check_positive("entry_price"), name="ck_positions_entry_price_positive"),

        # Domain constant from constraints_custom.py
        CheckConstraint(
            f"CAST(leverage AS NUMERIC) >= {MIN_LEVERAGE} AND CAST(leverage AS NUMERIC) <= {MAX_LEVERAGE}",
            name="ck_positions_leverage_range"
        ),
    )
```

### Helper Functions Available

**Generic SQL Builders** (in constraints.py):

| Function | SQL Output | Use Case |
| --- | --- | --- |
| `check_positive(field)` | `CAST(field AS NUMERIC) > 0` | Prices, quantities |
| `check_non_negative(field)` | `CAST(field AS NUMERIC) >= 0` | Balances, counts |
| `check_range(field, min, max)` | `CAST(field AS NUMERIC) >= min AND ...` | Bounded values |
| `check_percentage(field)` | `check_range(field, 0, 1)` | Percentage fields |
| `check_datetime_order(start, end)` | `end >= start` | Date/time ranges |
| `check_greater_than_field(a, b)` | `CAST(a AS NUMERIC) > CAST(b AS NUMERIC)` | Field comparisons |

All helpers support optional `allow_null` parameter for nullable fields.

### Generic Constants Available

**Built into constraints.py:**

```python
# Percentage constraints (0% to 100% as decimal 0.0-1.0)
PERCENTAGE_MIN = Decimal("0")
PERCENTAGE_MAX = Decimal("1")

# File size constraints
MIN_FILE_SIZE = 0  # bytes
MAX_FILE_SIZE = 1024 * 1024 * 100  # 100 MB

# Session duration constraints (in seconds)
MIN_SESSION_DURATION = 60  # 1 minute
MAX_SESSION_DURATION = 86400  # 24 hours

# Token expiry constraints (in seconds)
MIN_TOKEN_EXPIRY = 300  # 5 minutes
MAX_TOKEN_EXPIRY = 31536000  # 1 year

# Counter/quantity constraints
MIN_POSITIVE_COUNT = 1
MIN_RETRY_ATTEMPTS = 0
MAX_RETRY_ATTEMPTS = 10
```

### Adding Domain-Specific Constants

**Manual process** (intentionally not generated):

1. Identify domain-specific business rules
2. Add constants to `constraints_custom.py`
3. Create wrapper functions if needed
4. Use in database models or validators

**Example:**

```python
# backend/src/database/models/constraints_custom.py

from decimal import Decimal

# Trading domain constants
MIN_LEVERAGE = Decimal("1.0")    # 1x = spot equivalent
MAX_LEVERAGE = Decimal("100.0")  # 100x maximum

FEE_RATE_MIN = Decimal("0")      # 0% min fee
FEE_RATE_MAX = Decimal("1")      # 100% max fee

# String constraints
USERNAME_MIN_LENGTH = 3
EMAIL_PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
TRADING_PAIR_PATTERN = r"^[A-Z0-9]{2,10}/[A-Z0-9]{2,10}$"

def check_leverage(field_name: str) -> str:
    """Generate SQL CHECK for valid leverage range."""
    from .constraints import check_range
    return check_range(field_name, MIN_LEVERAGE, MAX_LEVERAGE)

def check_fee_rate(field_name: str) -> str:
    """Generate SQL CHECK for valid fee rate."""
    from .constraints import check_percentage
    return check_percentage(field_name)
```

### Regenerating constraints.py

To regenerate the generic helpers file:

```bash
# Generate constraints.py from template
python .agents/model-generator/scripts/generate.py models/{any-domain}.model.json --target constraints

# This creates/overwrites constraints.py with:
# - All generic helper functions
# - All constants referenced in JSON models
# - Generic project-agnostic constants
```

**Note:** You only need to regenerate when:

- Adding your first model (creates the file)
- Template updates add new helpers
- You want to update generic constants

The file is **idempotent** - safe to regenerate any time.

---

## Best Practices

### When to Use Cross-Field Constraints

✅ **Use for:**

- OHLC integrity (high ≥ low, high ≥ open/close)
- Date/time ordering (end_date ≥ start_date)
- Fee bounds (maximum_fee ≥ minimum_fee)
- Balance consistency (total = available + locked)
- Price bounds (take_profit > entry_price > stop_loss)

❌ **Don't use for:**

- Complex conditional logic (use Pydantic or triggers)
- Calculations requiring multiple tables (use application logic)
- User-facing validation that needs custom messages (use Pydantic)

### Testing Cross-Field Constraints

The generator automatically creates coordinated test data that satisfies all constraints:

```python
# Auto-generated factory in tests/factories.py
class MarketDataFactory(factory.Factory):
    class Meta:
        model = MarketData

    # Factory ensures: high >= low, high >= open, high >= close, etc.
    low = factory.Faker("pydecimal", min_value=100, max_value=200)
    high = factory.LazyAttribute(lambda o: o.low + Decimal("50"))
    open = factory.LazyAttribute(lambda o: fake.pydecimal(
        left_digits=10,
        right_digits=2,
        min_value=float(o.low),
        max_value=float(o.high)
    ))
```

### Constraint Naming Guidelines

Follow the convention: `ck_{table}_{descriptive_name}`

**Good names:**

- `ck_market_data_high_greater_equal_low` (descriptive)
- `ck_backtests_end_date_after_start_date` (clear intent)
- `ck_assets_balance_consistency` (business meaning)

**Avoid:**

- `ck_market_data_constraint1` (not descriptive)
- `ck_check_high_low` (missing table name)
- `high_low_check` (doesn't follow convention)
