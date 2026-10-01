# Project structure (backend)

Feeds the submission explanation document (brief §12).

## How the parts connect

Flutter app (Android APK) → HTTPS JSON API (`app/api/v1/*`) → business logic (`app/services/*`) → PostgreSQL (via SQLAlchemy models in `app/models/*`).

## Folders and files

| Path | Purpose |
|---|---|
| `app/main.py` | Creates the FastAPI app, registers routers, error handlers, CORS, `/health`. |
| `app/core/config.py` | Settings loaded from `.env` / environment variables. |
| `app/core/db.py` | Async database engine and session factory. |
| `app/core/security.py` | Password hashing (bcrypt) and JWT access/refresh tokens. |
| `app/core/deps.py` | Request dependencies: `get_db`, `get_current_user`, `require_role(...)` (role-based access, §2). |
| `app/core/errors.py` | Uniform error responses `{"error": {"code", "message"}}`. |
| `app/core/time.py` | `now()`: single source of the current time, so tests can freeze it. |
| `app/models/` | Database tables, one file per entity (`user.py`). |
| `app/schemas/` | Request/response shapes (validation, §10 input validation). |
| `app/services/auth.py` | Registration, login, token refresh logic. |
| `app/api/v1/auth.py` | Auth and profile endpoints (`/auth/*`, `/me`). |
| `app/api/v1/admin.py` | Admin-only endpoints. |
| `alembic/` | Database migrations. |
| `scripts/seed.py` | Demo accounts, one per role. |
| `tests/` | Automated tests (pytest) against a separate test database. |
| `Dockerfile` | Production image; runs migrations then the API. |

## Features → files

- **Authentication & role-based access (§10):** `core/security.py`, `core/deps.py`, `services/auth.py`, `api/v1/auth.py`.
