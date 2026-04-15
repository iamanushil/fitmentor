# Phase 3 — Profile Service Design

**Date:** 2026-04-16  
**Status:** Approved  

---

## Context

Phases 1–2 established the FastAPI scaffold, Docker infrastructure, SQLAlchemy ORM models (`User`, `FitnessProfile`), async session factory, Alembic migrations, and Clerk JWT auth with `get_current_user` dependency.

Phase 3 wires `FitnessProfile` into a real REST API.

---

## Architecture

**Pattern:** Service layer (thin router + pure service functions)

- **Router** handles HTTP concerns: request parsing, status codes, auth injection
- **Service** handles domain logic: DB queries, upsert semantics, cascade deletes
- **Schemas** are pure Pydantic — no ORM objects leave the service layer

```
Request + Bearer JWT
  → ClerkJWT middleware (verify RS256 token)
  → get_current_user dep (resolve/create User row)
  → router (parse body → Pydantic schema)
  → profile_service (query/mutate FitnessProfile)
  → router (serialize ORM → response schema)
  → Response
```

---

## File Structure

```
backend/src/fitmentor/
├── api/
│   └── v1/
│       ├── __init__.py
│       ├── router.py          # master APIRouter, includes sub-routers
│       └── profile.py         # profile route handlers
├── schemas/
│   ├── __init__.py
│   └── profile.py             # ProfileIn, ProfileOut Pydantic models
└── services/
    ├── __init__.py
    └── profile_service.py     # get_profile(), upsert_profile(), delete_profile()
```

`main.py` updated to uncomment router include pointing at `api.v1.router`.

---

## Endpoints

| Method   | Path               | Auth | Description                          | Success | Error     |
|----------|--------------------|------|--------------------------------------|---------|-----------|
| `GET`    | `/api/v1/profile`  | ✓    | Return current user's fitness profile | 200     | 404       |
| `PUT`    | `/api/v1/profile`  | ✓    | Upsert fitness profile (all fields)  | 200     | 422       |
| `DELETE` | `/api/v1/profile`  | ✓    | Hard-delete fitness profile          | 204     | 404       |

All endpoints require `Authorization: Bearer <clerk_jwt>` header.

---

## Schemas

### `ProfileIn` (request body for PUT)
```
goals: list[str] | None          # ["lose_fat", "build_strength"]
experience: str | None           # "beginner" | "intermediate" | "advanced"
injuries: list[dict] | None      # [{body_part, notes}]
equipment: list[str] | None      # ["dumbbells", "pullup_bar"]
days_per_week: int | None        # 1–7
session_minutes: int | None
height_cm: int | None
weight_kg: float | None
```

### `ProfileOut` (response for GET and PUT)
All `ProfileIn` fields plus:
```
id: UUID
user_id: UUID
status: str                      # "pending" | "ready"
version: int
created_at: datetime
updated_at: datetime
```

---

## Service Layer

### `get_profile(user: User, db: AsyncSession) -> FitnessProfile | None`
- Simple `SELECT WHERE user_id = user.id`
- Returns `None` if no profile exists (router maps to 404)

### `upsert_profile(user: User, data: ProfileIn, db: AsyncSession) -> FitnessProfile`
- Fetch existing profile by `user_id`
- If exists: update all non-None fields, increment `version`
- If not exists: create new `FitnessProfile` row
- Flush + return updated model
- Router commits transaction via `AsyncSession` context

### `delete_profile(user: User, db: AsyncSession) -> None`
- Fetch profile, raise `404` if not found
- `await db.delete(profile)` — CASCADE on DB handles FK integrity
- Flush

---

## Transaction Ownership

The **router** owns the transaction commit. Each route handler receives `AsyncSession` via `Depends(get_db)`. The service functions call `db.flush()` (write to DB buffer, no commit). The router calls `await db.commit()` after a successful service call. On exception, SQLAlchemy rolls back automatically.

**Why this matters in interviews:** "Who commits the transaction?" is a classic question. Fat routers commit inline — messy. Service-layer commit means you can chain multiple service calls in one transaction. Router-owns-commit is the clean answer.

---

## Doc Updates

| File              | Update                                      |
|-------------------|---------------------------------------------|
| `ROADMAP.md`      | Mark Phase 3 checklist items, add endpoints |
| `ARCHITECTURE.md` | Add Profile Service section + ER note       |

---

## Out of Scope (Phase 3)

- Profile photo upload (Phase 8+, S3)
- Partial PATCH updates (PUT upsert is sufficient for now)
- Profile validation rules (e.g. days_per_week range enforcement) — Phase 4+
