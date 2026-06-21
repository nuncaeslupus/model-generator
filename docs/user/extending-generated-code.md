# Extending Generated Code

> **Note on Stack Specificity:** This guide uses examples based on the **Python-FastAPI** stack. While the principles of extension apply to all stacks, specific directory structures and code patterns will vary (e.g., Node.js will use `src/` instead of `backend/src/`, and Jest instead of Pytest).

The Model Generator builds the foundation of your application (database models, CRUD APIs, tests). This guide explains how to build upon that foundation to add business logic, custom routes, and complex workflows.

**Philosophy:** The generated code is _yours_. It is not a black box. You are expected to modify, extend, and maintain it. The generator is a bootstrap tool, not a runtime framework.

> **The generated stack is async.** Sessions are `AsyncSession`, the FastAPI
> dependency is `get_session` (from `database/engine.py`), and queries use
> `await session.execute(select(...))` — **not** the legacy sync
> `Session` / `db.query(...)` / `get_db` API. Every example below uses the
> async API the generator actually emits.

## 1. Project Structure Review

(Assuming Python-FastAPI stack, default per-entity layout)

- `backend/src/database/models/{entity}.py` — SQLAlchemy models (one file per entity)
- `backend/src/database/engine.py` — async engine + `get_session` dependency
- `backend/src/api/models/{entity}_requests.py` / `{entity}_response.py` — Pydantic request/response schemas
- `backend/src/api/routes/{entity}.py` — FastAPI route handlers (one file per entity)
- `tests/contract/test_{entity}_api.py` — Generated contract tests

> Per-domain layout instead groups every entity of a domain into a single
> `{domain}.py` / `{domain}_requests.py` / etc. The principles below are
> identical; only the filenames differ.

## 2. Workflow: Test-Driven Development (Recommended)

We strongly recommend a **Test-Driven Development (TDD)** workflow when extending the application. Since the generator has already provided a working baseline with tests, TDD helps maintain that stability while adding complex logic.

### The Cycle (Red -> Green -> Refactor)

1.  **Red:** Write a test for your new feature (e.g., "Deactivating a user should reject already-inactive accounts"). Run it, and watch it fail.
2.  **Green:** Write the minimum code necessary in your Service or Route to make the test pass.
3.  **Refactor:** Clean up the code while keeping the test passing.

> **Already have auth turned on?** If `auth.strategy` is set in
> `.model-generator.yaml`, the generator already emits a full auth router
> (register / login / logout / forgot-password / reset-password /
> change-password). Don't re-implement those — extend or wrap them. The example
> below adds a *new* business action that the generator does not provide.

### Example: Adding a "Deactivate Account" Action

**1. Create the Test First** Create `tests/integration/test_deactivate.py`:

```python
def test_deactivate_user_success(client, user_id):
    # We expect this endpoint to exist and work
    response = client.post(f"/api/v1/users/{user_id}/deactivate")

    assert response.status_code == 200
    assert response.json()["status"] == "INACTIVE"
```

**2. Watch it Fail** Run your test runner (e.g., `pytest`). It will fail because the route `/api/v1/users/{user_id}/deactivate` does not exist yet.

**3. Implement the Logic** Now, implement the route and service logic (see sections below) until the test passes.

## 3. Adding Business Logic (Service Layer)

Generated routes contain basic CRUD logic. For complex rules, move logic to a "Service Layer".

**Recommended Approach:**

1.  Create a `services` directory: `backend/src/services/`
2.  Create a service file, e.g., `user_service.py`
3.  Inject the session and call the service from your route handlers.

**Example Implementation:**

```python
# backend/src/services/user_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models.user import User
from ..database.enums import UserStatus


async def deactivate_user(session: AsyncSession, user_id: str) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("User not found")

    # Add complex logic (audit log, notification, revoke sessions, etc.)
    user.status = UserStatus.INACTIVE
    await session.commit()
    await session.refresh(user)
    return user
```

Note the async idioms: `select(...)` + `await session.execute(...)` +
`.scalar_one_or_none()` to fetch, `await session.commit()` to persist. There is
no `db.query(...)` and no synchronous `Session`.

## 4. Customizing Routes

### Modifying Generated Routes

You can directly edit files in `backend/src/api/routes/`.

- **Add input validation:** Add more Pydantic validators to models in `api/models/{entity}_requests.py`.
- **Add side effects:** Send emails, trigger background tasks within the route function.
- **Change authorization:** Add `Depends(get_current_user)` to handlers (with `auth.strategy` on, `api.scope` wires this for you — see the [JSON Specification Reference](../agent/json-specification-reference.md#owner-scoping-apiscope)).

### Adding New Custom Routes

For endpoints that don't map 1:1 to a database entity (e.g., `/reports`, `/users/{id}/deactivate`):

1.  **Create a new file:** `backend/src/api/routes/reports.py` (or extend an existing entity route file).
2.  **Define the Router** (note the async handler and `get_session` dependency):

    ```python
    from fastapi import APIRouter, Depends, HTTPException
    from sqlalchemy.ext.asyncio import AsyncSession

    from ...database.engine import get_session
    from ...services import user_service

    router = APIRouter(prefix="/api/v1/users", tags=["users"])

    @router.post("/{user_id}/deactivate")
    async def deactivate(
        user_id: str,
        session: AsyncSession = Depends(get_session),
    ):
        try:
            user = await user_service.deactivate_user(session, user_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"status": user.status.value}
    ```

    `get_session` is imported from `database/engine.py` — the same dependency
    every generated route uses. It yields an `AsyncSession` and is the canonical
    way to obtain a session.

3.  **Register the Router:** Add `app.include_router(router)` to `backend/src/main.py`. (`main.py` is generated once and is yours to edit — new routers do not auto-wire after the first generation.)

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

Edit `backend/src/api/models/user_requests.py` / `user_response.py` to change validation rules, add fields to requests/responses, or create new specific schemas (e.g., `UserUpdatePasswordRequest`).

## Summary Checklist

- [ ] **TDD:** Write a failing test for the new behavior first.
- [ ] **Async:** Use `AsyncSession` + `await session.execute(select(...))`; obtain the session via `Depends(get_session)`.
- [ ] **Logic:** Move complex logic to `src/services/`.
- [ ] **Routes:** Create new route files for non-CRUD endpoints; register them in `main.py`.
- [ ] **DB:** Use Alembic for all schema changes after initial generation.
- [ ] **Verification:** Ensure all tests (generated + new) pass.
