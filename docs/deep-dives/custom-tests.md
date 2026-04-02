# Custom Tests & TDD Guide

> **Note on Stack Specificity:** This guide uses examples based on the **Python-FastAPI** stack. Technical implementations (like `conftest.py` or `factory_boy`) are specific to this environment. For other stacks, consult the stack-specific documentation in `stacks/{name}/README.md`.

This guide explains how to extend the generated test suite, set up your test environment, and use the generated data factories for Test-Driven Development (TDD).

## What Generated Contract Tests Cover

Contract tests verify the API matches the specification. They are generated per entity and cover:

- **CRUD happy paths** — Create, read (single + list), update, delete
- **Field validation** — Required fields (422), type correctness, min/max lengths
- **Unique constraint violations** — Duplicate unique fields return 409
- **Not found errors** — Non-existent IDs return 404 with structured error format
- **Response format validation** — Field presence, types (str/bool/int), UUID format, ISO 8601 timestamps
- **Pagination** — Page/page_size parameters, metadata structure, invalid pagination rejected
- **Filtering and sorting** — Enum, boolean, datetime range, financial range, counter range filters
- **Timestamp correctness** — `created_at <= updated_at`, timezone-aware ISO 8601
- **Immutable field protection** — Fields marked `api_exclude_update` cannot be changed via PUT
- **Partial updates** — PUT with a single field updates only that field
- **Security** — Fields marked `api_exclude_response` are absent from responses

### What You Need to Add (Integration Tests)

Contract tests validate the API shape, not your business logic. You need to write tests for:

- **Business rules** — e.g., "can't withdraw more than balance", "orders must have valid status transitions"
- **Authentication and authorization** — Who can access what
- **Multi-step workflows** — e.g., create order -> process payment -> update inventory
- **Cross-entity validation** — e.g., "portfolio total must equal sum of positions"
- **Error recovery** — Concurrent writes, database errors, partial failures
- **Custom validators** — Beyond field-level (e.g., "email domain must be whitelisted")
- **Performance** — Load testing, query optimization validation

Place your tests in `tests/integration/` and `tests/unit/`. See sections 3-5 below.

## 1. Test Environment Setup (`conftest.py`)

The generator creates contract tests, but your project needs a `conftest.py` to configure the test runner, database fixtures, and API client.

If `tests/conftest.py` does not exist, create it with the following configuration:

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.src.main import app
from backend.src.database.session import Base, get_db

# Use an in-memory SQLite database for fast tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
    return engine

@pytest.fixture(scope="function")
def db_session(db_engine):
    """
    Creates a fresh database session for each test.
    """
    # Create tables
    Base.metadata.create_all(bind=db_engine)

    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient with database session override.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

## 2. Using Generated Factories

The generator creates `factory_boy` factories for all your entities in `backend/src/database/models/factories/`. These factories allow you to create complex test data with a single line of code.

### Importing Factories

```python
# tests/conftest.py (add these to expose factories as fixtures)
from backend.src.database.models.factories.users import UserFactory
from backend.src.database.models.factories.orders import OrderFactory
from pytest_factoryboy import register

register(UserFactory)
register(OrderFactory)
```

### Using in Tests

If you register them with `pytest_factoryboy` (as above), you can use them as fixtures:

```python
def test_user_can_place_order(client, user_factory, order_factory):
    # Create a user in the DB
    user = user_factory(username="trader_joe")

    # Create an order linked to the user
    order = order_factory(user_id=user.id, amount=100)

    assert user.username == "trader_joe"
    assert order.user_id == user.id
```

Alternatively, import and use them directly:

```python
from backend.src.database.models.factories.users import UserFactory

def test_manual_factory_usage(db_session):
    user = UserFactory(username="manual_user")
    db_session.commit() # Factories might not auto-commit depending on config
```

## 3. TDD Workflow: Adding a Feature

Let's walk through adding a feature using TDD: **"Users cannot withdraw more than their balance."**

### Step 1: Write the Failing Test (Red)

Create `tests/integration/test_withdrawals.py`:

```python
def test_withdraw_insufficient_funds(client, user_factory, wallet_factory):
    # 1. Setup: User with 100 USD
    user = user_factory()
    wallet = wallet_factory(user_id=user.id, balance=100.00)

    # 2. Action: Try to withdraw 200 USD
    response = client.post("/api/v1/withdrawals", json={
        "user_id": user.id,
        "amount": 200.00
    })

    # 3. Assertion: Should fail
    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient funds"
```

Run the test:

```bash
pytest tests/integration/test_withdrawals.py
```

**Result:** `FAILED` (404 Not Found, because the route doesn't exist).

### Step 2: Implement Minimum Code (Green)

1.  **Create Route:** `backend/src/api/routes/withdrawals.py`
2.  **Implement Logic:**

```python
@router.post("/withdrawals")
def create_withdrawal(request: WithdrawalRequest, db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter_by(user_id=request.user_id).first()

    if wallet.balance < request.amount:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    # ... process withdrawal ...
    return {"status": "success"}
```

Run the test again:

```bash
pytest tests/integration/test_withdrawals.py
```

**Result:** `PASSED`.

### Step 3: Refactor

Move the logic to a service layer (`backend/src/services/payment_service.py`) to keep the route clean.

```python
# Route becomes:
@router.post("/withdrawals")
def create_withdrawal(request: WithdrawalRequest, db: Session = Depends(get_db)):
    payment_service.process_withdrawal(db, request.user_id, request.amount)
    return {"status": "success"}
```

Run the test again to ensure no regressions.

## 4. Where to Put Tests

- **`tests/contract/`**: Generated tests. **Do not modify.** These ensure your API matches the specification.
- **`tests/integration/`**: Your custom tests for workflows (TDD goes here).
- **`tests/unit/`**: Tests for isolated service functions or utility classes.

## 5. Running Tests

Run all tests:

```bash
pytest
```

Run only your custom tests:

```bash
pytest tests/integration/
```

Run generated contract tests:

```bash
pytest tests/contract/
```
