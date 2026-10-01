# API changelog

Newest first. Every breaking change (renamed/removed field, changed type or error code) gets an entry.

## 2026-10-01 — Phase 2 contract (STUB)
- Added the organisation setup contract: departments, services, counters, staff, shifts, rules, admin user management. Not implemented yet. Shapes are final.
- `GET /admin/users` gains optional `role` and `department_id` filters (additive).

## 2026-10-01 — Phase 1
- Initial contract: `/health`, `/auth/register`, `/auth/login`, `/auth/token`, `/auth/refresh`, `GET/PATCH /me`, `GET /admin/users`. Error format and demo accounts. See `API.md`.
