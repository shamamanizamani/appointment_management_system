# API contract

The Flutter app's source of truth. Every example below was copied from a real response.
Interactive docs: `<base-url>/docs` (Swagger). Changes are listed in `API_CHANGELOG.md`.

- **Base URL:** `https://<deployed-url>` (TBD after first deploy). Local: `http://localhost:8000`.
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
