"""CLAUDE.md §12: fire simultaneous requests and check the database never overbooks.

Run after ANY change to booking or token logic: pytest -q tests/test_concurrency.py
"""

import asyncio

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import Appointment, Role
from tests.conftest import bearer

API = "/api/v1"
SLOT = "2026-10-05T05:00:00Z"  # Monday 10:00 Karachi


async def test_20_simultaneous_bookings_on_6_seat_slot(client, frozen, make_service, make_user):
    s = await make_service(max_per_slot=6)
    users = [await make_user(Role.customer, email=f"c{i}@example.com") for i in range(20)]

    responses = await asyncio.gather(
        *(
            client.post(
                f"{API}/appointments", headers=bearer(u), json={"service_id": s.id, "start": SLOT}
            )
            for u in users
        )
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [201] * 6 + [409] * 14, [r.text for r in responses if r.status_code >= 500]
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {"SLOT_FULL"}
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Appointment)) == 6


async def test_simultaneous_duplicate_bookings_by_one_user(client, frozen, make_service, make_user):
    s = await make_service(max_per_slot=50)
    user = await make_user(Role.customer)
    starts = [f"2026-10-05T{h:02d}:{m:02d}:00Z" for h in (4, 5, 6) for m in (0, 30)]  # 6 slots

    responses = await asyncio.gather(
        *(
            client.post(
                f"{API}/appointments", headers=bearer(user), json={"service_id": s.id, "start": st}
            )
            for st in starts
        )
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [201] + [409] * 5
    assert {r.json()["error"]["code"] for r in responses if r.status_code == 409} == {
        "DUPLICATE_APPOINTMENT"
    }
