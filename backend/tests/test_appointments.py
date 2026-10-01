from datetime import date, time, timedelta

import pytest

from app.core import time as clock
from app.models import AppointmentStatus as S
from app.models import Role
from app.schemas.org import DEFAULT_BREAKS, DEFAULT_WORKING_HOURS
from app.services.appointment_manager import ALLOWED, slot_times
from app.utils.state_machine import InvalidTransition, check_transition
from tests.conftest import bearer

API = "/api/v1"
MON, TUE, SAT = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 10)
HOURS = DEFAULT_WORKING_HOURS.model_dump(mode="json")
BREAKS = [b.model_dump(mode="json") for b in DEFAULT_BREAKS]


def at(hh: int, mm: int = 0, day: int = 5) -> str:
    """UTC ISO start for a Karachi (UTC+5) local time in October 2026."""
    return f"2026-10-{day:02d}T{hh - 5:02d}:{mm:02d}:00Z"


def assert_error(r, status: int, code: str):
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code


async def book(client, user, service_id, start):
    return await client.post(
        f"{API}/appointments", headers=bearer(user), json={"service_id": service_id, "start": start}
    )


@pytest.fixture
async def customers(make_user):
    return [await make_user(Role.customer, email=f"c{i}@example.com") for i in range(3)]


# --- pure slot math ---


def test_slot_math_across_break():
    slots = slot_times(MON, HOURS, BREAKS, 30)
    starts = [s.strftime("%H:%M") for s, _ in slots]
    assert len(slots) == 14  # 9-13 (8) + 14-17 (6)
    assert starts[7] == "12:30" and starts[8] == "14:00"  # nothing at 13:00 or 13:30
    assert slots[-1] == (time(16, 30), time(17, 0))


def test_slot_math_uneven_length_restarts_after_break():
    starts = [s.strftime("%H:%M") for s, _ in slot_times(MON, HOURS, BREAKS, 45)]
    # 12:00-12:45 is the last morning slot; the afternoon starts fresh at 14:00
    assert starts == [
        "09:00",
        "09:45",
        "10:30",
        "11:15",
        "12:00",
        "14:00",
        "14:45",
        "15:30",
        "16:15",
    ]


def test_slot_math_day_specific_breaks_and_closed_days():
    friday_only = [{"start": "12:00:00", "end": "14:30:00", "days": ["fri"]}]
    assert len(slot_times(MON, HOURS, friday_only, 60)) == 8  # break doesn't apply Monday
    fri = [s.strftime("%H:%M") for s, _ in slot_times(date(2026, 10, 9), HOURS, friday_only, 60)]
    assert fri == ["09:00", "10:00", "11:00", "14:30", "15:30"]
    assert slot_times(SAT, HOURS, BREAKS, 30) == []


def test_appointment_transition_table():
    allowed = [
        (S.booked, S.confirmed),
        (S.confirmed, S.checked_in),
        (S.checked_in, S.waiting),
        (S.waiting, S.in_service),
        (S.in_service, S.completed),
        (S.booked, S.cancelled),
        (S.confirmed, S.cancelled),
        (S.booked, S.rescheduled),
        (S.confirmed, S.rescheduled),
        (S.confirmed, S.missed),
        (S.waiting, S.delayed),
        (S.in_service, S.delayed),
        (S.delayed, S.waiting),
        (S.delayed, S.in_service),
    ]
    for frm, to in allowed:
        check_transition(ALLOWED, "appointment", frm, to)
    allowed_set = set(allowed)
    for frm in S:
        for to in S:
            if (frm, to) not in allowed_set:
                with pytest.raises(InvalidTransition):
                    check_transition(ALLOWED, "appointment", frm, to)


# --- slot grid and available dates ---


async def test_slot_grid(client, frozen, make_service):
    s = await make_service()
    r = await client.get(f"{API}/services/{s.id}/slots?date={MON}")
    assert r.status_code == 200, r.text
    grid = r.json()
    assert grid["timezone"] == "Asia/Karachi" and len(grid["slots"]) == 14
    first = grid["slots"][0]
    assert first == {
        "start": "2026-10-05T04:00:00Z",
        "end": "2026-10-05T04:30:00Z",
        "local_start": "09:00",
        "local_end": "09:30",
        "max": 6,
        "booked": 0,
        "status": "available",
    }

    clock._frozen = frozen + timedelta(hours=5)  # 11:00 local
    statuses = [
        x["status"]
        for x in (await client.get(f"{API}/services/{s.id}/slots?date={MON}")).json()["slots"]
    ]
    assert statuses[:6] == ["past"] * 5 + ["available"]  # 9:00-11:00 have started

    assert_error(
        await client.get(f"{API}/services/{s.id}/slots?date=2026-10-04"),
        422,
        "OUTSIDE_BOOKING_WINDOW",
    )
    assert_error(
        await client.get(f"{API}/services/{s.id}/slots?date=2026-10-30"),
        422,
        "OUTSIDE_BOOKING_WINDOW",
    )


async def test_available_dates(client, frozen, make_service, customers):
    s = await make_service(daily_limit=1)
    await book(client, customers[0], s.id, at(9, day=6))  # fills Tuesday
    r = await client.get(f"{API}/services/{s.id}/available-dates?from=2026-10-05&to=2026-10-11")
    days = {d["date"]: (d["status"], d["available_slots"]) for d in r.json()["items"]}
    assert days["2026-10-05"] == ("available", 14)
    assert days["2026-10-06"] == ("full", 0)
    assert days["2026-10-10"] == ("closed", 0)
    assert r.json()["total"] == 7


# --- booking ---


async def test_book_and_list_mine(client, frozen, make_service, customers):
    s = await make_service()
    r = await book(client, customers[0], s.id, at(9, 30))
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["status"] == "confirmed"
    assert a["appointment_number"] == f"APT-{a['id']:06d}"
    assert (a["appointment_date"], a["start_time"], a["end_time"]) == (
        "2026-10-05",
        "2026-10-05T04:30:00Z",
        "2026-10-05T05:00:00Z",
    )
    assert (a["service_code"], a["customer_name"]) == ("A", "Test customer")

    mine = (
        await client.get(f"{API}/appointments/me?when=upcoming", headers=bearer(customers[0]))
    ).json()
    assert [x["id"] for x in mine["items"]] == [a["id"]]
    other = (await client.get(f"{API}/appointments/me", headers=bearer(customers[1]))).json()
    assert other["total"] == 0

    grid = (await client.get(f"{API}/services/{s.id}/slots?date={MON}")).json()
    assert grid["slots"][1]["booked"] == 1 and grid["booked_total"] == 1


async def test_duplicate_rejected(client, frozen, make_service, customers):
    s = await make_service()
    assert (await book(client, customers[0], s.id, at(9))).status_code == 201
    assert_error(await book(client, customers[0], s.id, at(15)), 409, "DUPLICATE_APPOINTMENT")
    assert (
        await book(client, customers[0], s.id, at(9, day=6))
    ).status_code == 201  # next day is fine


async def test_slot_full_and_cancel_frees_slot(client, frozen, make_service, customers):
    s = await make_service(max_per_slot=2)
    first = (await book(client, customers[0], s.id, at(10))).json()
    assert (await book(client, customers[1], s.id, at(10))).status_code == 201
    assert_error(await book(client, customers[2], s.id, at(10)), 409, "SLOT_FULL")

    r = await client.post(f"{API}/appointments/{first['id']}/cancel", headers=bearer(customers[0]))
    assert r.json()["status"] == "cancelled" and r.json()["cancelled_at"]
    assert (await book(client, customers[2], s.id, at(10))).status_code == 201

    r = await client.post(f"{API}/appointments/{first['id']}/cancel", headers=bearer(customers[0]))
    assert_error(r, 409, "INVALID_TRANSITION")


async def test_daily_limit(client, frozen, make_service, customers):
    s = await make_service(daily_limit=2)
    await book(client, customers[0], s.id, at(9))
    await book(client, customers[1], s.id, at(14))
    r = await book(client, customers[2], s.id, at(16))
    assert_error(r, 409, "SLOT_FULL")
    assert "fully booked" in r.json()["error"]["message"]


async def test_per_user_daily_limit_rule(client, frozen, make_service, customers, make_user):
    a = await make_service("A")
    b = await make_service("B", department_id=a.department_id)
    c = await make_service("C", department_id=a.department_id)
    await book(client, customers[0], a.id, at(9))
    await book(client, customers[0], b.id, at(10))  # default limit is 2 per day
    assert_error(await book(client, customers[0], c.id, at(11)), 409, "LIMIT_REACHED")


async def test_reschedule_links_old_to_new(client, frozen, make_service, customers):
    s = await make_service(max_per_slot=1)
    old = (await book(client, customers[0], s.id, at(9))).json()
    r = await client.post(
        f"{API}/appointments/{old['id']}/reschedule",
        headers=bearer(customers[0]),
        json={"start": at(11)},
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["rescheduled_from_id"] == old["id"] and new["status"] == "confirmed"
    assert new["start_time"] == "2026-10-05T06:00:00Z"
    old_now = (
        await client.get(f"{API}/appointments/{old['id']}", headers=bearer(customers[0]))
    ).json()
    assert old_now["status"] == "rescheduled"

    # old slot is free again (max_per_slot=1), and the old appointment can't move twice
    assert (await book(client, customers[1], s.id, at(9))).status_code == 201
    r = await client.post(
        f"{API}/appointments/{old['id']}/reschedule",
        headers=bearer(customers[0]),
        json={"start": at(12)},
    )
    assert_error(r, 409, "INVALID_TRANSITION")


async def test_failed_reschedule_keeps_original(client, frozen, make_service, customers):
    s = await make_service(max_per_slot=1)
    old = (await book(client, customers[0], s.id, at(9))).json()
    await book(client, customers[1], s.id, at(10))
    r = await client.post(
        f"{API}/appointments/{old['id']}/reschedule",
        headers=bearer(customers[0]),
        json={"start": at(10)},
    )
    assert_error(r, 409, "SLOT_FULL")
    still = (
        await client.get(f"{API}/appointments/{old['id']}", headers=bearer(customers[0]))
    ).json()
    assert still["status"] == "confirmed"  # whole reschedule rolled back


async def test_cancellation_limit(client, frozen, make_service, customers, make_user, login):
    s = await make_service()
    await make_user(Role.admin)
    await client.put(
        f"{API}/rules/cancellation_limit",
        headers=await login("admin@example.com"),
        json={"department_id": s.department_id, "value": 1},
    )
    c = customers[0]
    a1 = (await book(client, c, s.id, at(9))).json()
    assert (
        await client.post(f"{API}/appointments/{a1['id']}/cancel", headers=bearer(c))
    ).status_code == 200
    a2 = (await book(client, c, s.id, at(10))).json()
    assert_error(
        await client.post(f"{API}/appointments/{a2['id']}/cancel", headers=bearer(c)),
        409,
        "LIMIT_REACHED",
    )


async def test_booking_validation(client, frozen, make_service, customers, make_user, login):
    s = await make_service()
    c = customers[0]
    assert_error(await book(client, c, s.id, at(9, 10)), 422, "OUTSIDE_WORKING_HOURS")
    assert_error(await book(client, c, s.id, at(13)), 422, "OUTSIDE_WORKING_HOURS")  # break
    assert_error(
        await book(client, c, s.id, at(10, day=10)), 422, "OUTSIDE_WORKING_HOURS"
    )  # Saturday
    assert_error(await book(client, c, s.id, at(10, day=30)), 422, "OUTSIDE_BOOKING_WINDOW")
    assert_error(await book(client, c, 999, at(10)), 404, "NOT_FOUND")
    r = await client.post(
        f"{API}/appointments",
        headers=bearer(c),
        json={"service_id": s.id, "start": "2026-10-05T09:00:00"},
    )
    assert_error(r, 422, "VALIDATION_ERROR")  # start must carry a timezone

    clock._frozen = frozen + timedelta(hours=4)  # 10:00 local
    assert_error(await book(client, c, s.id, at(9, 30)), 422, "SLOT_PASSED")

    await make_user(Role.admin)
    await client.delete(f"{API}/services/{s.id}", headers=await login("admin@example.com"))
    assert_error(await book(client, c, s.id, at(15)), 409, "SERVICE_CLOSED")


async def test_access_rules(client, frozen, make_service, customers, make_user):
    s = await make_service()
    other = await make_service("B")  # different department
    a = (await book(client, customers[0], s.id, at(9))).json()
    url = f"{API}/appointments/{a['id']}"

    assert_error(await client.get(url, headers=bearer(customers[1])), 404, "NOT_FOUND")
    staff = await make_user(Role.staff, department_id=s.department_id)
    assert (await client.get(url, headers=bearer(staff))).status_code == 200
    assert_error(await client.post(f"{url}/cancel", headers=bearer(staff)), 403, "FORBIDDEN")
    outsider = await make_user(Role.manager, department_id=other.department_id)
    assert_error(await client.get(url, headers=bearer(outsider)), 403, "FORBIDDEN")
    assert_error(await book(client, staff, s.id, at(10)), 403, "FORBIDDEN")  # customers only

    listed = (await client.get(f"{API}/appointments?date={MON}", headers=bearer(staff))).json()
    assert [x["id"] for x in listed["items"]] == [a["id"]]
    assert (await client.get(f"{API}/appointments", headers=bearer(outsider))).json()["total"] == 0
    r = await client.get(
        f"{API}/appointments?department_id={s.department_id}", headers=bearer(outsider)
    )
    assert_error(r, 403, "FORBIDDEN")

    manager = await make_user(Role.manager, email="m2@example.com", department_id=s.department_id)
    r = await client.post(f"{url}/cancel", headers=bearer(manager))
    assert r.json()["status"] == "cancelled"
