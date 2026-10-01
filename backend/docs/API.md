# API contract

The Flutter app's source of truth. Every example below was copied from a real response.
Interactive docs: `<base-url>/docs` (Swagger). Changes are listed in `API_CHANGELOG.md`.

- **Base URL:** `https://queue-api-m3n4.onrender.com` (Swagger: `/docs`). Local: `http://localhost:8000`.
- Free hosting sleeps after 15 min idle; the first request after that can take ~1 min. Hit `/health` to wake it.
- All endpoints except `/health` are under **`/api/v1`**.
- JSON in, JSON out. Timestamps are ISO 8601 in **UTC** (`...Z` / `+00:00`); convert to local time in the app.
- Lists: `?limit=&offset=` → `{"items": [...], "total": n}`.

## Demo accounts

Stable. These never change.

| Role | Email | Password |
|---|---|---|
| customer | `customer@demo.com` | `Demo@1234` |
| staff | `staff@demo.com` | `Demo@1234` |
| manager | `manager@demo.com` | `Demo@1234` |
| admin | `admin@demo.com` | `Demo@1234` |

## Authentication

Send the access token on every authenticated request:

```
Authorization: Bearer <access_token>
```

- Access token lives **30 min**, refresh token **7 days**.
- When any request returns `401` with code `TOKEN_EXPIRED`, call `POST /auth/refresh` once with the refresh token and retry. If refresh also fails, send the user to login.
- Route the user to their home screen by `user.role`: `customer` | `staff` | `manager` | `admin`.

## Errors

Every error has this shape. **Show `message` to the user directly**; branch on `code`.

```json
{
  "error": {
    "code": "EMAIL_TAKEN",
    "message": "An account with this email already exists."
  }
}
```

Validation errors (`422`) also carry `fields`, for highlighting form inputs:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "name: String should have at least 1 character",
    "fields": [
      { "field": "name", "message": "String should have at least 1 character" },
      { "field": "email", "message": "value is not a valid email address: An email address must have an @-sign." },
      { "field": "password", "message": "String should have at least 8 characters" }
    ]
  }
}
```

| Code | HTTP | When |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Bad or missing input |
| `NOT_AUTHENTICATED` | 401 | No token sent |
| `INVALID_TOKEN` | 401 | Token malformed, wrong type, or user gone |
| `TOKEN_EXPIRED` | 401 | Token expired. Refresh and retry |
| `INVALID_CREDENTIALS` | 401 | Wrong email or password |
| `ACCOUNT_SUSPENDED` | 403 | Account disabled by an admin |
| `FORBIDDEN` | 403 | Logged in, but this role can't do this |
| `EMAIL_TAKEN` | 409 | Registration with an existing email |
| `NOT_FOUND` | 404 | Unknown path or resource |
| `INTERNAL_ERROR` | 500 | Server bug. Message is generic |

## User object

Returned by `/me`, inside auth responses, and in user lists.

```json
{
  "id": 1,
  "name": "Demo Customer",
  "email": "customer@demo.com",
  "phone": null,
  "role": "customer",
  "department_id": null,
  "account_status": "active",
  "created_at": "2026-10-01T07:15:48.374562Z"
}
```

`role`: `customer` | `staff` | `manager` | `admin`. `account_status`: `active` | `suspended`. `department_id` is set for staff/managers from Phase 2.

---

## Endpoints

### `GET /health`
**Auth:** none. Checks the API and database. Hit it to wake a sleeping free-tier server.

```json
{ "status": "ok", "time": "2026-10-01T07:16:16.112853+00:00" }
```

### `POST /api/v1/auth/register`
**Auth:** none. Creates a **customer** account (other roles are created by admins) and logs in.

Request:
```json
{ "name": "Sara Ahmed", "email": "sara@example.com", "password": "Secret@123", "phone": "+923001234567" }
```
- `name`: 1–100 chars. `email`: valid email, stored lowercase. `password`: 8–72 chars. `phone`: optional, 7–15 digits, optional leading `+`.

Response `201`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 5,
    "name": "Sara Ahmed",
    "email": "sara@example.com",
    "phone": "+923001234567",
    "role": "customer",
    "department_id": null,
    "account_status": "active",
    "created_at": "2026-10-01T07:16:59.117072Z"
  }
}
```
Errors: `409 EMAIL_TAKEN`, `422 VALIDATION_ERROR`.

### `POST /api/v1/auth/login`
**Auth:** none.

Request:
```json
{ "email": "customer@demo.com", "password": "Demo@1234" }
```
Response `200`: same shape as register.
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "Demo Customer",
    "email": "customer@demo.com",
    "phone": null,
    "role": "customer",
    "department_id": null,
    "account_status": "active",
    "created_at": "2026-10-01T07:15:48.374562Z"
  }
}
```
Errors: `401 INVALID_CREDENTIALS`, `403 ACCOUNT_SUSPENDED`, `422 VALIDATION_ERROR`.

### `POST /api/v1/auth/token`
Same as login but takes a form (`username`=email, `password`). It exists for the **Authorize** button in `/docs`. **The app should use `/auth/login`.**

### `POST /api/v1/auth/refresh`
**Auth:** none (the refresh token is in the body).

Request:
```json
{ "refresh_token": "eyJhbGciOiJIUzI1NiIs..." }
```
Response `200`: same shape as login, with a **new** access *and* refresh token. Store both.
Errors: `401 INVALID_TOKEN` (also when an access token is sent instead), `401 TOKEN_EXPIRED`, `403 ACCOUNT_SUSPENDED`.

### `GET /api/v1/me`
**Auth:** any role. Response `200`: the user object.
```json
{
  "id": 1,
  "name": "Demo Customer",
  "email": "customer@demo.com",
  "phone": null,
  "role": "customer",
  "department_id": null,
  "account_status": "active",
  "created_at": "2026-10-01T07:15:48.374562Z"
}
```
Errors: `401 NOT_AUTHENTICATED` / `INVALID_TOKEN` / `TOKEN_EXPIRED`, `403 ACCOUNT_SUSPENDED`.

### `PATCH /api/v1/me`
**Auth:** any role. Update own `name` and/or `phone`. Omitted fields are unchanged; `"phone": null` clears the phone.

Request:
```json
{ "phone": "03001234567" }
```
Response `200`: the updated user object.
```json
{
  "id": 1,
  "name": "Demo Customer",
  "email": "customer@demo.com",
  "phone": "03001234567",
  "role": "customer",
  "department_id": null,
  "account_status": "active",
  "created_at": "2026-10-01T07:15:48.374562Z"
}
```
Errors: `401`, `422 VALIDATION_ERROR`.

### `GET /api/v1/admin/users?limit=50&offset=0`
**Auth:** admin. All users, ordered by id. `limit` 1–200 (default 50).

Response `200` (`?limit=2`):
```json
{
  "items": [
    {
      "id": 1,
      "name": "Demo Customer",
      "email": "customer@demo.com",
      "phone": null,
      "role": "customer",
      "department_id": null,
      "account_status": "active",
      "created_at": "2026-10-01T07:15:48.374562Z"
    },
    {
      "id": 2,
      "name": "Demo Staff",
      "email": "staff@demo.com",
      "phone": null,
      "role": "staff",
      "department_id": null,
      "account_status": "active",
      "created_at": "2026-10-01T07:15:48.374569Z"
    }
  ],
  "total": 5
}
```
Errors: `401`, `403 FORBIDDEN` (any non-admin):
```json
{ "error": { "code": "FORBIDDEN", "message": "You don't have permission to do this." } }
```

---

## Organisation setup (Phase 2) — `STUB`

> **`STUB`:** this contract is final in shape but **not implemented yet**. Examples are hand-written until the endpoints go live; then they get replaced with real responses and this marker is removed.

### Access rules
- **Public (no login):** browsing departments and services. Customers can browse before logging in.
- **Manager:** only their own department (`user.department_id`). Touching another department → `403 FORBIDDEN`.
- **Admin:** everything, every department.
- Deleting departments and services is a **soft delete**: they become inactive and vanish from public lists, but history keeps pointing at them.
- New error codes: `CODE_TAKEN` (409), `INVALID_REFERENCE` (422, e.g. a counter given a service from another department), `STAFF_ALREADY_ASSIGNED` (409), `UNKNOWN_RULE` (404), `INVALID_RULE_VALUE` (422).

### Weekdays and times
Weekdays are `"mon" "tue" "wed" "thu" "fri" "sat" "sun"`. Times of day are local department time, `"HH:MM:SS"`. Requests may send `"HH:MM"`.

### Department object
```json
{
  "id": 1,
  "name": "Examination",
  "code": "EXAM",
  "timezone": "Asia/Karachi",
  "working_hours": {
    "mon": { "start": "09:00:00", "end": "17:00:00" },
    "tue": { "start": "09:00:00", "end": "17:00:00" },
    "wed": { "start": "09:00:00", "end": "17:00:00" },
    "thu": { "start": "09:00:00", "end": "17:00:00" },
    "fri": { "start": "09:00:00", "end": "17:00:00" },
    "sat": null,
    "sun": null
  },
  "break_windows": [
    { "start": "13:00:00", "end": "14:00:00", "days": null }
  ],
  "active": true,
  "created_at": "2026-10-01T08:00:00Z"
}
```
`working_hours.<day> = null` means closed that day. A break with `"days": null` applies every working day; `"days": ["fri"]` applies on Fridays only.

### Service object
```json
{
  "id": 1,
  "department_id": 1,
  "name": "Document Verification",
  "code": "A",
  "description": null,
  "average_duration_min": 10,
  "is_priority": false,
  "active_status": true,
  "slot_config": { "slot_length_min": 30, "max_per_slot": 6, "daily_limit": null }
}
```
`code` is the token prefix (`A` → `A-027`), 1–3 capital letters, unique within a department. `slot_config`: appointment slot length, bookings allowed per slot, and an optional cap per day (`null` = no cap).

### Counter object
```json
{
  "id": 1,
  "department_id": 1,
  "name": "Counter 1",
  "service_ids": [1, 2],
  "assigned_staff_id": 2,
  "status": "available"
}
```
`status`: `available` | `busy` | `break` | `closed`. New counters start `closed`; changing status is a staff action in Phase 5.

### Shift object
```json
{ "id": 1, "staff_id": 2, "counter_id": 1, "weekday": "mon", "start_time": "09:00:00", "end_time": "17:00:00" }
```

### Endpoints

| Method & path | Who | Body | Returns |
|---|---|---|---|
| `GET /departments` | public | | page of departments (active only) |
| `GET /departments/{id}` | public | | department |
| `POST /departments` | admin | `name, code, timezone?, working_hours?, break_windows?` | `201` department |
| `PATCH /departments/{id}` | admin (any field) · manager (own: `working_hours`, `break_windows` only) | any department fields, `active` | department |
| `DELETE /departments/{id}` | admin | | `204` (soft delete) |
| `GET /departments/{id}/services` | public | | page of services (active only) |
| `POST /departments/{id}/services` | manager (own) · admin | `name, code, average_duration_min, description?, is_priority?, slot_config?` | `201` service |
| `GET /services?q=&department_id=` | public | | page of active services; `q` matches name, case-insensitive (§9 search) |
| `GET /services/{id}` | public | | service |
| `PATCH /services/{id}` | manager (own) · admin | any service fields, `active_status`, partial `slot_config` | service |
| `DELETE /services/{id}` | manager (own) · admin | | `204` (soft delete) |
| `GET /departments/{id}/counters` | staff/manager (own) · admin | | page of counters |
| `POST /departments/{id}/counters` | manager (own) · admin | `name, service_ids?, assigned_staff_id?` | `201` counter |
| `PATCH /counters/{id}` | manager (own) · admin | `name?, service_ids?, assigned_staff_id?` | counter |
| `DELETE /counters/{id}` | manager (own) · admin | | `204` |
| `GET /departments/{id}/staff` | manager (own) · admin | | page of users with role `staff` |
| `POST /departments/{id}/staff` | manager (own) · admin | `name, email, password, phone?` | `201` user (role `staff`) |
| `PATCH /departments/{id}/staff/{user_id}` | manager (own) · admin | `name?, phone?, account_status?` | user |
| `GET /departments/{id}/shifts?staff_id=` | manager (own) · admin | | page of shifts |
| `POST /departments/{id}/shifts` | manager (own) · admin | `staff_id, counter_id, weekday, start_time, end_time` | `201` shift |
| `DELETE /shifts/{id}` | manager (own) · admin | | `204` |
| `GET /rules?department_id=` | manager (own) · admin | | effective rules, see below |
| `PUT /rules/{key}` | admin (org-wide: `department_id: null`) · manager (own department) | `{ "department_id": 1, "value": 3 }` | the rule |
| `DELETE /rules/{key}?department_id=` | same as PUT | | `204` (back to org/default value) |
| `GET /admin/users?role=&department_id=` | admin | | page of users (filters optional) |
| `POST /admin/users` | admin | `name, email, password, role, phone?, department_id?` | `201` user |
| `GET /admin/users/{id}` | admin | | user |
| `PATCH /admin/users/{id}` | admin | `name?, phone?, role?, department_id?, account_status?, password?` | user |

Users aren't deleted; suspend them with `account_status: "suspended"`.

### Rules
`GET /rules?department_id=1` returns the **effective** value of every rule for that department. A department override beats the org-wide value, which beats the default. Omit `department_id` to get org-wide values.
```json
{
  "items": [
    { "key": "max_appointments_per_user_per_day", "value": 2, "source": "default" },
    { "key": "max_tokens_per_user", "value": 2, "source": "org" },
    { "key": "cancellation_limit", "value": 1, "source": "department" }
  ],
  "total": 3
}
```

| Key | Type | Default | Meaning |
|---|---|---|---|
| `max_appointments_per_user_per_day` | int ≥ 1 | 2 | Active appointments one customer can hold on one day |
| `max_tokens_per_user` | int ≥ 1 | 2 | Active walk-in tokens one customer can hold at once (across services) |
| `cancellation_limit` | int ≥ 0 | 3 | Cancellations a customer may make in 7 days |
| `early_checkin_minutes` | int ≥ 0 | 10 | Check-in opens this many minutes before the slot |
| `late_checkin_minutes` | int ≥ 0 | 10 | Check-in closes this many minutes after the slot starts |
| `max_recalls` | int ≥ 0 | 2 | Recalls allowed before a no-show becomes `missed` |
| `priority_services` | list of service ids | `[]` | These services' tokens are served first |
| `booking_window_days` | int ≥ 1 | 14 | How many days ahead customers can book |
