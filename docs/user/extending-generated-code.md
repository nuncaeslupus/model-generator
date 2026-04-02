# Extending Generated Code

> **Note on Stack Specificity:** This guide uses examples based on the **Python-FastAPI** stack. While the principles of extension apply to all stacks, specific directory structures and code patterns will vary (e.g., Node.js will use `src/` instead of `backend/src/`, and Jest instead of Pytest).

The Model Generator builds the foundation of your application (database models, CRUD APIs, tests). This guide explains how to build upon that foundation to add business logic, custom routes, and complex workflows.

**Philosophy:** The generated code is _yours_. It is not a black box. You are expected to modify, extend, and maintain it. The generator is a bootstrap tool, not a runtime framework.

## 1. Project Structure Review

(Assuming Python-FastAPI stack)

- `backend/src/database/models/` - SQLAlchemy models (Table definitions)
- `backend/src/api/models/` - Pydantic models (Request/Response schemas)
- `backend/src/api/routes/` - FastAPI route handlers
- `tests/contract/` - Generated API tests

## 2. Workflow: Test-Driven Development (Recommended)

We strongly recommend a **Test-Driven Development (TDD)** workflow when extending the application. Since the generator has already provided a working baseline with tests, TDD helps maintain that stability while adding complex logic.

### The Cycle (Red -> Green -> Refactor)

1.  **Red:** Write a test for your new feature (e.g., "User registration should fail if age < 18"). Run it, and watch it fail.
2.  **Green:** Write the minimum code necessary in your Service or Route to make the test pass.
3.  **Refactor:** Clean up the code while keeping the test passing.

### Example: Adding a "Reset Password" Feature

**1. Create the Test First** Create `tests/integration/test_password_reset.py`:

```python
def test_reset_password_success(client, user_factory):
    user = user_factory(password="old_pass")

    # We expect this endpoint to exist and work
    response = client.post(
        "/api/auth/reset-password",
        json={"user_id": user.id, "new_password": "new_secure_pass"}
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify DB change (pseudo-code)
    db_user = get_user_from_db(user.id)
    assert db_user.password != "old_pass"
```

**2. Watch it Fail** Run your test runner (e.g., `pytest`). It will fail because the route `/api/auth/reset-password` does not exist yet.

**3. Implement the Logic** Now, implement the route and service logic (see sections below) until the test passes.

## 3. Adding Business Logic (Service Layer)

Generated routes contain basic CRUD logic. For complex rules, move logic to a "Service Layer".

**Recommended Approach:**

1.  Create a `services` directory: `backend/src/services/`
2.  Create a service file, e.g., `user_service.py`
3.  Inject the service or call it from your route handlers.

**Example Implementation:**

```python
# backend/src/services/user_service.py
from sqlalchemy.orm import Session
from ..database.models.user import User

def reset_user_password(db: Session, user_id: str, new_password: str):
    user = db.query(User).get(user_id)
    if not user:
        raise ValueError("User not found")

    # Add complex logic (hashing, notification, etc.)
    user.password_hash = hash_secret(new_password)
    db.commit()
    return user
```

## 4. Customizing Routes

### Modifying Generated Routes

You can directly edit files in `backend/src/api/routes/`.

- **Add input validation:** Add more Pydantic validators to models in `api/models/`.
- **Add side effects:** Send emails, trigger background tasks within the route function.
- **Change authorization:** Add `Depends(get_current_user)` to route decorators.

### Adding New Custom Routes

For endpoints that don't map 1:1 to a database entity (e.g., `/login`, `/reports`, `/actions/reset-password`):

1.  **Create a new file:** `backend/src/api/routes/auth.py` (or `reports.py`).
2.  **Define the Router:**

    ```python
    from fastapi import APIRouter, Depends
    from sqlalchemy.orm import Session
    from ...database.session import get_db

    router = APIRouter(prefix="/auth", tags=["Auth"])

    @router.post("/reset-password")
    def reset_password(payload: ResetPayload, db: Session = Depends(get_db)):
        # Call the service we designed
        service.reset_user_password(db, payload.user_id, payload.new_password)
        return {"status": "success"}
    ```

3.  **Register the Router:** Update `backend/src/api/routes/__init__.py` or `backend/src/main.py` (depending on your project's entry point) to include the new router.

## 5. Customizing Models & Migrations

### Modifying Database Models

1.  Edit the model file: `backend/src/database/models/user.py`.
2.  Add/Remove fields or methods.
3.  **Create a Migration:**
    ```bash
    alembic revision --autogenerate -m "Added phone number to user"
    ```
4.  **Apply Migration:**
    ```bash
    alembic upgrade head
    ```

### Modifying API Schemas

Edit `backend/src/api/models/user.py` to change validation rules, add fields to requests/responses, or create new specific schemas (e.g., `UserUpdatePasswordRequest`).

## Summary Checklist

- [ ] **TDD:** Write a failing test for the new behavior first.
- [ ] **Logic:** Move complex logic to `src/services/`.
- [ ] **Routes:** Create new route files for non-CRUD endpoints.
- [ ] **DB:** Use Alembic for all schema changes after initial generation.
- [ ] **Verification:** Ensure all tests (generated + new) pass.
