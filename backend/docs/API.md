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

`manager@demo.com` and `staff@demo.com` belong to **Examination** (department 1). Extra seeded accounts, same password:

| Department | Manager | Staff |
|---|---|---|
| Examination | `manager@demo.com` | `staff@demo.com` (Counter 1), `staff2.exam@demo.com` (Counter 2) |
| Student Affairs | `manager.sa@demo.com` | `staff1.sa@demo.com` (Counter 1), `staff2.sa@demo.com` (Counter 2) |
| Accounts | `manager.acc@demo.com` | `staff1.acc@demo.com` (Counter 1), `staff2.acc@demo.com` (Counter 2) |

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

## Organisation setup (Phase 2)

Live. Seeded data: departments **Examination** (`EXAM`, id 1), **Student Affairs** (`SA`, id 2), **Accounts** (`ACC`, id 3), with services A–F and counters as in brief §6. `manager@demo.com` and `staff@demo.com` belong to Examination.

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
  "created_at": "2026-10-01T08:04:17.146767Z"
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
  "id": 2,
  "department_id": 1,
  "name": "Counter 2",
  "service_ids": [1, 2],
  "assigned_staff_id": 7,
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
| `GET /departments?include_inactive=` | public | | page of departments, ordered by name (active only unless `include_inactive=true`) |
| `GET /departments/{id}` | public | | department |
| `POST /departments` | admin | `name, code, timezone?, working_hours?, break_windows?` | `201` department |
| `PATCH /departments/{id}` | admin (any field) · manager (own: `working_hours`, `break_windows` only) | any department fields, `active` | department |
| `DELETE /departments/{id}` | admin | | `204` (soft delete) |
| `GET /departments/{id}/services?include_inactive=` | public | | page of services, ordered by code (active only unless `include_inactive=true`) |
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

Users aren't deleted; suspend them with `account_status: "suspended"`. When an admin changes a staff member's role or department, that person is taken off their counter and their shifts are removed.

### Example requests and errors

`POST /departments/1/services` as `manager@demo.com`:
```json
{ "name": "Transcript Request", "code": "T", "average_duration_min": 15, "slot_config": { "max_per_slot": 4 } }
```
`201`:
```json
{
  "id": 6,
  "department_id": 1,
  "name": "Transcript Request",
  "code": "T",
  "description": null,
  "average_duration_min": 15,
  "is_priority": false,
  "active_status": true,
  "slot_config": { "slot_length_min": 30, "max_per_slot": 4, "daily_limit": null }
}
```

`PATCH /services/6` (partial `slot_config`; omitted fields keep their values):
```json
{ "description": "Official transcript copies", "slot_config": { "daily_limit": 20 } }
```
`200`: the service, now with `"description": "Official transcript copies"` and `"slot_config": { "slot_length_min": 30, "max_per_slot": 4, "daily_limit": 20 }`.

`POST /departments/1/counters`:
```json
{ "name": "Counter 4", "service_ids": [6] }
```
`201`:
```json
{ "id": 9, "department_id": 1, "name": "Counter 4", "service_ids": [6], "assigned_staff_id": null, "status": "closed" }
```

`PATCH /departments/1` as a manager, setting breaks (the Friday break is longer):
```json
{ "break_windows": [ { "start": "13:00", "end": "14:00" }, { "start": "12:30", "end": "14:30", "days": ["fri"] } ] }
```
`200`: the department, with
```json
"break_windows": [
  { "start": "13:00:00", "end": "14:00:00", "days": null },
  { "start": "12:30:00", "end": "14:30:00", "days": ["fri"] }
]
```

`POST /admin/users`:
```json
{ "name": "Hina Staff", "email": "hina@demo.com", "password": "Secret@123", "role": "staff", "department_id": 3 }
```
`201`:
```json
{ "id": 14, "name": "Hina Staff", "email": "hina@demo.com", "phone": null, "role": "staff", "department_id": 3, "account_status": "active", "created_at": "2026-10-01T08:05:21.015183Z" }
```

Errors (all real):
```json
{ "error": { "code": "FORBIDDEN", "message": "You can only manage your own department." } }
{ "error": { "code": "FORBIDDEN", "message": "Managers can only change working hours and breaks." } }
{ "error": { "code": "FORBIDDEN", "message": "Only admins can change organisation-wide rules." } }
{ "error": { "code": "INVALID_REFERENCE", "message": "Every service on a counter must belong to the counter's department." } }
{ "error": { "code": "INVALID_RULE_VALUE", "message": "That isn't a valid value for 'max_recalls'." } }
```

### Rules
`GET /rules?department_id=1` returns the **effective** value of every rule for that department. A department override beats the org-wide value, which beats the default. Omit `department_id` to get org-wide values.
```json
{
  "items": [
    { "key": "max_appointments_per_user_per_day", "value": 2, "source": "default" },
    { "key": "max_tokens_per_user", "value": 2, "source": "default" },
    { "key": "cancellation_limit", "value": 1, "source": "department" },
    { "key": "early_checkin_minutes", "value": 10, "source": "default" },
    { "key": "late_checkin_minutes", "value": 10, "source": "default" },
    { "key": "max_recalls", "value": 2, "source": "default" },
    { "key": "priority_services", "value": [], "source": "default" },
    { "key": "booking_window_days", "value": 14, "source": "default" }
  ],
  "total": 8
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

---

## Appointments (Phase 3)

Live. Every example below is a real response.

### Flow (brief §3)
1. `GET /departments` → `GET /departments/{id}/services` (Phase 2)
2. `GET /services/{id}/available-dates`: which days have free slots
3. `GET /services/{id}/slots?date=`: the slot grid for one day
4. `POST /appointments` with the chosen slot's `start` **exactly as returned** by `/slots`
5. `GET /appointments/me`: upcoming and history; cancel or reschedule from there

Booking needs a **customer** login. Browsing slots is public.

### Slot grid: `GET /services/{id}/slots?date=2026-10-02`
**Auth:** none. `date` is the department's local date (`YYYY-MM-DD`). Real response, first 3 of 14 slots:
```json
{
  "service_id": 1,
  "date": "2026-10-02",
  "timezone": "Asia/Karachi",
  "slot_length_min": 30,
  "daily_limit": null,
  "booked_total": 6,
  "slots": [
    { "start": "2026-10-02T04:00:00Z", "end": "2026-10-02T04:30:00Z", "local_start": "09:00", "local_end": "09:30", "max": 6, "booked": 0, "status": "available" },
    { "start": "2026-10-02T04:30:00Z", "end": "2026-10-02T05:00:00Z", "local_start": "09:30", "local_end": "10:00", "max": 6, "booked": 0, "status": "available" },
    { "start": "2026-10-02T05:00:00Z", "end": "2026-10-02T05:30:00Z", "local_start": "10:00", "local_end": "10:30", "max": 6, "booked": 6, "status": "full" }
  ]
}
```
- `status`: `available` | `full` | `past` (already started).
- `start`/`end` are UTC. `local_start`/`local_end` are ready to display in the department's timezone.
- Slots come from the department's working hours minus its breaks, cut into the service's `slot_length_min` (§5). There are no slots over a break, and a non-working day returns `"slots": []`.
- When the service's `daily_limit` is reached, every slot that day shows `full`.
- Errors: `404`, `409 SERVICE_CLOSED` (service or department inactive), `422 OUTSIDE_BOOKING_WINDOW` (date in the past or more than `booking_window_days` ahead).

### `GET /services/{id}/available-dates?from=2026-10-02&to=2026-10-05`
**Auth:** none. Defaults run from today to the end of the booking window, with at most 31 days per call.
```json
{
  "items": [
    { "date": "2026-10-02", "available_slots": 14, "status": "available" },
    { "date": "2026-10-03", "available_slots": 0, "status": "closed" },
    { "date": "2026-10-04", "available_slots": 0, "status": "closed" },
    { "date": "2026-10-05", "available_slots": 14, "status": "available" }
  ],
  "total": 4
}
```
`status`: `available` | `full` | `closed` (not a working day).

### Appointment object
Response of `POST /appointments` with `{ "service_id": 1, "start": "2026-10-02T06:00:00Z" }` as `customer@demo.com` (`201`):
```json
{
  "id": 7,
  "appointment_number": "APT-000007",
  "user_id": 1,
  "customer_name": "Demo Customer",
  "customer_phone": null,
  "service_id": 1,
  "service_name": "Document Verification",
  "service_code": "A",
  "department_id": 1,
  "department_name": "Examination",
  "appointment_date": "2026-10-02",
  "start_time": "2026-10-02T06:00:00Z",
  "end_time": "2026-10-02T06:30:00Z",
  "status": "confirmed",
  "check_in_time": null,
  "cancelled_at": null,
  "rescheduled_from_id": null,
  "created_at": "2026-10-01T08:34:59.866543Z"
}
```
Rescheduling it with `{ "start": "2026-10-05T04:30:00Z" }` returns the new appointment (`201`): `"id": 8`, `"appointment_number": "APT-000008"`, `"appointment_date": "2026-10-05"`, `"start_time": "2026-10-05T04:30:00Z"`, `"status": "confirmed"`, `"rescheduled_from_id": 7`. Appointment 7 now has `"status": "rescheduled"`. Cancelling returns the appointment with `"status": "cancelled"` and `"cancelled_at": "2026-10-01T08:34:59.968951Z"`.
`status` (brief §3): `booked` → `confirmed` → `checked_in` → `waiting` → `in_service` → `completed`. Other statuses: `cancelled`, `missed`, `rescheduled`, `delayed`. New bookings are confirmed at once. Any other move returns `409 INVALID_TRANSITION`.

### Endpoints

| Method & path | Who | Body / params | Returns |
|---|---|---|---|
| `POST /appointments` | customer | `{ "service_id": 1, "start": "2026-10-05T04:30:00Z" }` | `201` appointment |
| `GET /appointments/me?when=&status=` | customer | `when`: `upcoming` \| `past` \| `all` (default `all`); `status` optional | page of own appointments (upcoming soonest first; otherwise newest first) |
| `GET /appointments/{id}` | the customer who booked it · staff/manager of its department · admin | | appointment |
| `POST /appointments/{id}/cancel` | the customer · manager of its department · admin | | appointment (`cancelled`) |
| `POST /appointments/{id}/reschedule` | the customer · manager of its department · admin | `{ "start": "2026-10-06T05:00:00Z" }` (same service) | `201` the **new** appointment; the old one becomes `rescheduled` and the new one has `rescheduled_from_id` |
| `GET /appointments?department_id=&service_id=&date=&status=` | staff/manager (own department, the default) · admin | all filters optional | page of appointments, by start time |

### Booking rules and errors
| Code | HTTP | When |
|---|---|---|
| `SLOT_FULL` | 409 | Slot has reached `max_per_slot`, or the service hit its `daily_limit` that day |
| `DUPLICATE_APPOINTMENT` | 409 | Customer already has an active appointment for this service that day |
| `LIMIT_REACHED` | 409 | Over `max_appointments_per_user_per_day`, or (on cancel) over `cancellation_limit` in the last 7 days |
| `OUTSIDE_WORKING_HOURS` | 422 | `start` isn't the start of one of that day's slots |
| `OUTSIDE_BOOKING_WINDOW` | 422 | Date is in the past or beyond `booking_window_days` |
| `SLOT_PASSED` | 422 | The slot already started |
| `SERVICE_CLOSED` | 409 | Service or department is inactive |
| `INVALID_TRANSITION` | 409 | e.g. cancelling a completed or already-cancelled appointment |

Cancelling or rescheduling frees the old slot immediately. Cancellations by a manager or admin don't count toward the customer's `cancellation_limit`. `GET /appointments/me` lists every status, including `rescheduled` and `cancelled` ones; filter with `status=` if needed.

Real errors:
```json
{ "error": { "code": "SLOT_FULL", "message": "This slot is full. Please pick another time." } }
{ "error": { "code": "SLOT_FULL", "message": "This service is fully booked that day." } }
{ "error": { "code": "DUPLICATE_APPOINTMENT", "message": "You already have an appointment for this service that day." } }
{ "error": { "code": "OUTSIDE_WORKING_HOURS", "message": "That time isn't one of this service's slots." } }
{ "error": { "code": "INVALID_TRANSITION", "message": "This appointment is already cancelled, so that isn't possible." } }
```

## Walk-in tokens and queue (Phase 4)

Live. Every example below is a real response.

### How the queue works (brief §3, §4)
- There is **one queue per service per day**. Counters serving that service all pull from it (Phase 5).
- Token numbers are `{service code}-{001…}` and restart at `001` every day for each service, e.g. `A-001`, `A-002`.
- Order of the waiting list: priority services first, then checked-in appointments due within 5 minutes, then everyone else by the time they joined.
- `estimated_wait_min = ceil(people_ahead × average service minutes ÷ active counters)`. Average service minutes is the mean of the last 20 completed services today for that service, or the service's `average_duration_min` until there are any. Active counters are counters serving the service with status `available` or `busy` (at least 1).
- The queue is open during the department's working hours for today (breaks included).
- `people_ahead` and `estimated_wait_min` are recalculated on every read. Until live updates arrive (Phase 7), poll `GET /tokens/{id}` every 10 seconds.

### Token object
Response of `POST /tokens` with `{ "service_id": 1 }` for the third customer in the Document Verification queue (`201`; counters 1 and 2 serve it, so 2 × 10 min ÷ 2 = 10):
```json
{
  "id": 6,
  "token_number": "A-006",
  "service_id": 1,
  "service_name": "Document Verification",
  "service_code": "A",
  "department_id": 1,
  "department_name": "Examination",
  "user_id": 24,
  "customer_name": "Queue Tester 2",
  "source": "walk_in",
  "appointment_id": null,
  "status": "waiting",
  "priority": false,
  "recall_count": 0,
  "counter_id": null,
  "queue_date": "2026-10-01",
  "queue_position": 3,
  "people_ahead": 2,
  "estimated_wait_min": 10,
  "current_token": null,
  "created_at": "2026-10-01T08:51:29.623444Z",
  "called_at": null,
  "service_started_at": null,
  "completed_at": null
}
```
Cancelling returns the same object with `"status": "cancelled"` and `queue_position`, `people_ahead` and `estimated_wait_min` all `null`; everyone behind moves up one place.
- `current_token`: the token most recently called for this service today (`null` until staff call someone, Phase 5).
- `queue_position` (1 = next), `people_ahead` and `estimated_wait_min` are set only while `status` is `waiting`; otherwise `null`.
- `source`: `walk_in` or `appointment` (created at check-in, Phase 6). `user_id` and `customer_name` can be `null` for kiosk walk-ins.
- `status`: `waiting` → `called` → `in_service` → `completed`; also `no_response`, `recalled`, `skipped`, `missed`, `cancelled`. Phase 4 only uses `waiting` and `cancelled`; staff actions arrive in Phase 5.

### Endpoints

| Method & path | Who | Body / params | Returns |
|---|---|---|---|
| `POST /tokens` | customer | `{ "service_id": 1 }` | `201` token |
| `GET /tokens/me/active` | customer | | page of own active tokens (`waiting`, `called`, `no_response`, `recalled`, `in_service`) |
| `GET /tokens/{id}` | the customer who owns it · staff/manager of its department · admin | | token, with live position and estimate |
| `POST /tokens/{id}/cancel` | the customer · manager of its department · admin | | token (`cancelled`) |
| `GET /services/{id}/queue` | staff/manager of its department · admin | | page of today's waiting tokens, in the order they will be called |

### Errors
| Code | HTTP | When |
|---|---|---|
| `DUPLICATE_TOKEN` | 409 | Customer already has an active token for this service today |
| `LIMIT_REACHED` | 409 | Customer already holds `max_tokens_per_user` active tokens today (rule, default 2) |
| `SERVICE_CLOSED` | 409 | Service or department inactive, or outside today's working hours |
| `INVALID_TRANSITION` | 409 | e.g. cancelling a token that was already called or cancelled |

Real errors:
```json
{ "error": { "code": "DUPLICATE_TOKEN", "message": "You already have a token for this service." } }
{ "error": { "code": "LIMIT_REACHED", "message": "You can hold at most 2 tokens at once." } }
{ "error": { "code": "SERVICE_CLOSED", "message": "This queue is closed right now. Please come back during opening hours." } }
{ "error": { "code": "INVALID_TRANSITION", "message": "This token is already cancelled, so that isn't possible." } }
```
