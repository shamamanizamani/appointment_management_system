# API changelog

Newest first. Every breaking change (renamed/removed field, changed type or error code) gets an entry.

## 2026-10-01 — Phase 3 contract (STUB)
- Added the appointments contract: slot grid, available dates, book, my appointments, cancel, reschedule, staff/manager list. Not implemented yet.

## 2026-10-01 — Phase 2 live
- All organisation setup endpoints are implemented; the `STUB` marker is removed. Shapes unchanged from the contract.
- Additive: `include_inactive` query param on `GET /departments` and `GET /departments/{id}/services`.
- New generic error `409 CONFLICT` (a rare race on unique data; show the message and let the user retry).
- `manager@demo.com` and `staff@demo.com` now belong to Examination (department 1). More seeded staff/manager accounts are listed in `API.md`.

## 2026-10-01 — Phase 2 contract (STUB)
- Added the organisation setup contract: departments, services, counters, staff, shifts, rules, admin user management. Not implemented yet. Shapes are final.
- `GET /admin/users` gains optional `role` and `department_id` filters (additive).

## 2026-10-01 — Phase 1
- Initial contract: `/health`, `/auth/register`, `/auth/login`, `/auth/token`, `/auth/refresh`, `GET/PATCH /me`, `GET /admin/users`. Error format and demo accounts. See `API.md`.
