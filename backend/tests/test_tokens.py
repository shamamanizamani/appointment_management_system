from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import time as clock
from app.core.db import SessionLocal
from app.models import (
    Appointment,
    AppointmentStatus,
    Counter,
    CounterStatus,
    QueueEvent,
    Role,
    Token,
    TokenSource,
)
from app.models import TokenStatus as T
from app.services import wait_time
from app.services.queue_manager import ALLOWED
from app.services.wait_time import estimate
from app.utils.state_machine import InvalidTransition, check_transition
from tests.conftest import bearer

API = "/api/v1"
MON = date(2026, 10, 5)
MONDAY_10AM = datetime(2026, 10, 5, 5, 0, tzinfo=UTC)  # 10:00 in Asia/Karachi


def assert_error(r, status: int, code: str):
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code


async def join(client, user, service_id):
    return await client.post(f"{API}/tokens", headers=bearer(user), json={"service_id": service_id})


@pytest.fixture
def open_now():
    clock._frozen = MONDAY_10AM
    return MONDAY_10AM


@pytest.fixture
async def customers(make_user):
    return [await make_user(Role.customer, email=f"c{i}@example.com") for i in range(4)]


async def add_counter(service, status=CounterStatus.available) -> Counter:
    async with SessionLocal() as db:
        counter = Counter(department_id=service.department_id, name="C", status=status)
        counter.services = [await db.get(type(service), service.id)]
        db.add(counter)
        await db.commit()
        return counter


# --- pure logic ---


def test_brief_wait_time_example():
    assert estimate(5, 4, 2) == 10  # brief §4
    assert estimate(0, 4, 2) == 0
    assert estimate(3, 4, 0) == 12  # no open counter: treated as one
    assert estimate(1, 4.5, 2) == 3  # rounds up


def test_token_transition_table():
    allowed = [
        (T.waiting, T.called),
        (T.called, T.in_service),
        (T.in_service, T.completed),
        (T.called, T.no_response),
        (T.no_response, T.recalled),
        (T.recalled, T.called),
        (T.called, T.skipped),
        (T.recalled, T.skipped),
        (T.skipped, T.waiting),
        (T.no_response, T.missed),
        (T.recalled, T.missed),
        (T.waiting, T.cancelled),
    ]
    for frm, to in allowed:
        check_transition(ALLOWED, "token", frm, to)
    for frm in T:
        for to in T:
            if (frm, to) not in allowed:
                with pytest.raises(InvalidTransition):
                    check_transition(ALLOWED, "token", frm, to)


# --- joining the queue ---


async def test_three_customers_get_sequential_tokens(client, open_now, make_service, customers):
    """BUILD_PLAN Phase 4 'done when', with the §3 response fields."""
    s = await make_service()  # average_duration_min = 10, no counters yet
    bodies = [(await join(client, c, s.id)).json() for c in customers[:3]]

    assert [b["token_number"] for b in bodies] == ["A-001", "A-002", "A-003"]
    third = bodies[2]
    assert third["people_ahead"] == 2
    assert third["queue_position"] == 3
    assert third["estimated_wait_min"] == 20  # 2 × 10 min ÷ max(0, 1)
    assert third["current_token"] is None
    assert third["status"] == "waiting" and third["source"] == "walk_in"
    assert third["customer_name"] == "Test customer"

    async with SessionLocal() as db:
        events = (await db.scalars(select(QueueEvent.event))).all()
    assert events == ["created"] * 3


async def test_active_counters_change_the_estimate(client, open_now, make_service, customers):
    s = await make_service()
    tokens = [(await join(client, c, s.id)).json() for c in customers[:3]]
    third = tokens[2]["id"]

    async def wait():
        r = await client.get(f"{API}/tokens/{third}", headers=bearer(customers[2]))
        return r.json()["estimated_wait_min"]

    await add_counter(s)
    assert await wait() == 20  # 2 × 10 ÷ 1
    await add_counter(s, CounterStatus.busy)
    assert await wait() == 10  # 2 × 10 ÷ 2
    await add_counter(s, CounterStatus.closed)  # closed counters don't count
    await add_counter(s, CounterStatus.break_)
    assert await wait() == 10


async def test_rolling_average_replaces_configured_duration(open_now, make_service):
    s = await make_service()  # configured average: 10 min
    start = MONDAY_10AM - timedelta(hours=1)
    async with SessionLocal() as db:
        for i, minutes in enumerate((4, 6)):  # served today: mean 5 min
            db.add(
                Token(
                    token_number=f"A-90{i}",
                    service_id=s.id,
                    queue_date=MON,
                    source=TokenSource.walk_in,
                    status=T.completed,
                    service_started_at=start,
                    completed_at=start + timedelta(minutes=minutes),
                )
            )
        await db.commit()
        assert await wait_time.avg_duration(db, s, MON) == pytest.approx(5)
        assert await wait_time.avg_duration(db, s, MON + timedelta(days=1)) == 10  # fallback


async def test_numbers_reset_daily_and_per_service(client, open_now, make_service, customers):
    a = await make_service("A")
    b = await make_service("B")
    assert (await join(client, customers[0], a.id)).json()["token_number"] == "A-001"
    assert (await join(client, customers[1], a.id)).json()["token_number"] == "A-002"
    assert (await join(client, customers[0], b.id)).json()["token_number"] == "B-001"

    clock._frozen = MONDAY_10AM + timedelta(days=1)  # Tuesday
    r = await join(client, customers[2], a.id)
    assert r.json()["token_number"] == "A-001"
    assert r.json()["people_ahead"] == 0  # yesterday's queue doesn't carry over


async def test_duplicate_and_limit(client, open_now, make_service, customers):
    a = await make_service("A")
    b = await make_service("B", department_id=a.department_id)
    c = await make_service("C", department_id=a.department_id)
    me = customers[0]

    first = (await join(client, me, a.id)).json()
    assert_error(await join(client, me, a.id), 409, "DUPLICATE_TOKEN")
    assert (await join(client, me, b.id)).status_code == 201
    assert_error(await join(client, me, c.id), 409, "LIMIT_REACHED")  # default max 2

    r = await client.post(f"{API}/tokens/{first['id']}/cancel", headers=bearer(me))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert r.json()["people_ahead"] is None and r.json()["queue_position"] is None
    assert (await join(client, me, a.id)).json()["token_number"] == "A-002"


async def test_service_closed(client, frozen, make_service, customers):
    s = await make_service()
    assert_error(await join(client, customers[0], s.id), 409, "SERVICE_CLOSED")  # 06:00
    clock._frozen = MONDAY_10AM + timedelta(days=5)  # Saturday
    assert_error(await join(client, customers[0], s.id), 409, "SERVICE_CLOSED")
    clock._frozen = MONDAY_10AM.replace(hour=11, minute=59)  # 16:59, still open
    assert (await join(client, customers[0], s.id)).status_code == 201
    clock._frozen = MONDAY_10AM.replace(hour=12)  # 17:00, closed
    assert_error(await join(client, customers[1], s.id), 409, "SERVICE_CLOSED")
    assert_error(await join(client, customers[1], 999), 404, "NOT_FOUND")


# --- ordering (§7) ---


async def test_queue_order(client, open_now, make_service, customers, make_user):
    """priority > checked-in appointments due within 5 min > time joined."""
    s = await make_service()

    def appt(minutes_from_now, who):
        st = MONDAY_10AM + timedelta(minutes=minutes_from_now)
        return Appointment(
            user_id=customers[who].id,
            service_id=s.id,
            appointment_date=MON,
            start_time=st,
            end_time=st + timedelta(minutes=30),
            status=AppointmentStatus.waiting,
        )

    def token(n, joined_min_ago, **kw):
        kw.setdefault("source", TokenSource.walk_in)
        kw.setdefault("status", T.waiting)
        return Token(
            token_number=f"A-{n:03d}",
            service_id=s.id,
            queue_date=MON,
            created_at=MONDAY_10AM - timedelta(minutes=joined_min_ago),
            **kw,
        )

    async with SessionLocal() as db:
        db.add_all(
            [
                token(1, 30),  # walk-in, joined first
                token(2, 20, source=TokenSource.appointment, appointment=appt(30, 0)),  # not due
                token(3, 10, source=TokenSource.appointment, appointment=appt(5, 1)),  # due
                token(4, 5),  # walk-in
                token(5, 1, priority=True),  # priority, joined last
                token(6, 40, status=T.cancelled),  # not waiting
            ]
        )
        await db.commit()

    staff = await make_user(Role.staff, department_id=s.department_id)
    r = await client.get(f"{API}/services/{s.id}/queue", headers=bearer(staff))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [t["token_number"] for t in items] == ["A-005", "A-003", "A-001", "A-002", "A-004"]
    assert [t["people_ahead"] for t in items] == [0, 1, 2, 3, 4]
    assert [t["estimated_wait_min"] for t in items] == [0, 10, 20, 30, 40]


async def test_cancel_moves_people_up(client, open_now, make_service, customers):
    s = await make_service()
    ids = [(await join(client, c, s.id)).json()["id"] for c in customers[:3]]
    await client.post(f"{API}/tokens/{ids[0]}/cancel", headers=bearer(customers[0]))

    r = await client.get(f"{API}/tokens/{ids[2]}", headers=bearer(customers[2]))
    assert r.json()["people_ahead"] == 1
    r = await client.get(f"{API}/tokens/me/active", headers=bearer(customers[2]))
    assert r.json()["total"] == 1 and r.json()["items"][0]["people_ahead"] == 1
    r = await client.get(f"{API}/tokens/me/active", headers=bearer(customers[0]))
    assert r.json() == {"items": [], "total": 0}

    again = await client.post(f"{API}/tokens/{ids[0]}/cancel", headers=bearer(customers[0]))
    assert_error(again, 409, "INVALID_TRANSITION")
    async with SessionLocal() as db:
        events = (await db.scalars(select(QueueEvent.event).order_by(QueueEvent.id))).all()
    assert events == ["created"] * 3 + ["cancelled"]


async def test_access_rules(client, open_now, make_service, customers, make_user):
    s = await make_service()
    other = await make_service("B")
    tid = (await join(client, customers[0], s.id)).json()["id"]
    staff = await make_user(Role.staff, department_id=s.department_id)
    outsider = await make_user(
        Role.manager, email="m@example.com", department_id=other.department_id
    )

    async def get(user):
        return await client.get(f"{API}/tokens/{tid}", headers=bearer(user))

    async def cancel(user):
        return await client.post(f"{API}/tokens/{tid}/cancel", headers=bearer(user))

    async def queue(user):
        return await client.get(f"{API}/services/{s.id}/queue", headers=bearer(user))

    assert_error(await get(customers[1]), 404, "NOT_FOUND")
    assert (await get(staff)).status_code == 200
    assert_error(await get(outsider), 403, "FORBIDDEN")
    assert_error(await cancel(staff), 403, "FORBIDDEN")
    assert_error(await cancel(customers[1]), 404, "NOT_FOUND")
    assert_error(await queue(outsider), 403, "FORBIDDEN")
    assert_error(await queue(customers[0]), 403, "FORBIDDEN")
    assert_error(await join(client, staff, s.id), 403, "FORBIDDEN")
