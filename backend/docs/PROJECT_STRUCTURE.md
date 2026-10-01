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
| `app/core/deps.py` | Request dependencies: `get_db`, `get_current_user`, `require_role(...)` (role-based access, §2), `check_department_access` (managers/staff limited to their own department). |
| `app/core/errors.py` | Uniform error responses `{"error": {"code", "message"}}`. |
| `app/core/time.py` | `now()`: single source of the current time, so tests can freeze it. |
| `app/models/` | Database tables, one file per entity: users, departments, services + slot_config, counters + counter_services, staff_shifts, rules, activity_logs, appointments, tokens + token_sequences + queue_events. |
| `app/schemas/` | Request/response shapes (validation, §10 input validation). |
| `app/services/auth.py` | Registration, login, token refresh logic. |
| `app/services/org.py` | Organisation setup: departments, services, counters, staff, shifts, user management. |
| `app/services/rules_engine.py` | Organisation rules (§10) with department-over-org-over-default lookup. |
| `app/services/activity.py` | Writes the activity log (§10 staff activity logs). |
| `app/services/appointment_manager.py` | **Appointment logic (§3, §5):** slot generation from working hours minus breaks, booking with row locks so slots are never overbooked, duplicate and per-user limits, cancel, reschedule, and the appointment state machine. |
| `app/services/queue_manager.py` | **Queue logic (§3, §4, §7):** token numbers (`A-027`, daily per service, from `token_sequences`), `ordered_queue()` (the one place queue order is decided), live positions and estimates, the token state machine, joining and leaving. |
| `app/services/wait_time.py` | **Waiting-time estimate (§4):** `people_ahead × average service minutes ÷ active counters`, using the rolling mean of today's last 20 services. |
| `app/api/v1/auth.py` | Auth and profile endpoints (`/auth/*`, `/me`). |
| `app/api/v1/departments.py` | Departments and everything inside one: services, counters, staff, shifts. |
| `app/api/v1/services.py` | Service search (§9), view, update, deactivate. |
| `app/api/v1/counters.py` | Counter update/delete, shift delete. |
| `app/api/v1/tokens.py` | Join the queue, my active tokens, token detail, leave the queue. The staff waiting list is `GET /services/{id}/queue` in `services.py`. |
| `app/api/v1/rules.py` | Read and set organisation/department rules. |
| `app/api/v1/appointments.py` | Book, list, view, cancel and reschedule appointments. Slot grid and available dates are under `/services/{id}/` in `services.py`. |
| `app/utils/state_machine.py` | Shared transition-table check; invalid moves become `409 INVALID_TRANSITION` (CLAUDE.md §6). |
| `app/api/v1/admin.py` | Admin user management. |
| `app/utils/pagination.py` | `{items, total}` list pages. |
| `alembic/` | Database migrations. |
| `scripts/seed.py` | Demo accounts for every role, plus a demo university: 3 departments, 5 services, counters, staff and shifts. |
| `tests/` | Automated tests (pytest) against a separate test database. `tests/test_concurrency.py` fires simultaneous bookings and proves a slot can't be overbooked, 20 simultaneous tokens get 20 unique gap-free numbers, and duplicate token requests give exactly one token. |
| `Dockerfile` | Production image; runs migrations then the API. |

## Features → files

- **Authentication & role-based access (§10):** `core/security.py`, `core/deps.py`, `services/auth.py`, `api/v1/auth.py`.
- **Departments, services, counters, staff, shifts (§2, §5, §6):** `services/org.py`, `api/v1/departments.py`, `api/v1/services.py`, `api/v1/counters.py`.
- **Organisation rules (§10):** `services/rules_engine.py`, `api/v1/rules.py`.
- **Activity logs (§10):** `models/activity_log.py`, `services/activity.py`. Every create/update/delete writes a row in the same transaction.
- **Service search (§9):** `GET /services?q=` in `api/v1/services.py`.
- **Appointments: slots, booking, no overbooking, cancel, reschedule (§3, §5, §10):** `services/appointment_manager.py`, `api/v1/appointments.py`, `models/appointment.py`. A booking locks the customer's row and the service's row (`SELECT … FOR UPDATE`) before counting and inserting, so 20 simultaneous requests for a 6-seat slot give exactly 6 bookings. A partial unique index blocks duplicate active appointments at the database level.
- **Walk-in tokens, queue order, waiting time (§3, §4, §7):** `services/queue_manager.py`, `services/wait_time.py`, `api/v1/tokens.py`, `models/token.py`. Token numbers come from one atomic upsert on `token_sequences` (the row lock makes simultaneous joins take turns). Queue order: priority services, then checked-in appointments due within 5 minutes, then join time. A partial unique index blocks two active tokens for the same customer and service; every token change writes a `queue_events` row.
