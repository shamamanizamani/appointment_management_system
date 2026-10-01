from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import ActivityLog, Role
from app.services import rules_engine

API = "/api/v1"


def assert_error(r, status: int, code: str):
    assert r.status_code == status, r.text
    assert r.json()["error"]["code"] == code


@pytest.fixture
async def org(client, make_user, login):
    """Two departments A and B, an admin, and a manager of A."""
    await make_user(Role.admin)
    admin = await login("admin@example.com")
    a = await client.post(
        f"{API}/departments", headers=admin, json={"name": "Exam", "code": "exam"}
    )
    b = await client.post(f"{API}/departments", headers=admin, json={"name": "Acc", "code": "ACC"})
    assert a.status_code == b.status_code == 201, a.text
    a, b = a.json(), b.json()
    await make_user(Role.manager, department_id=a["id"])
    manager = await login("manager@example.com")
    return SimpleNamespace(admin=admin, manager=manager, a=a["id"], b=b["id"])


async def make_service(client, headers, dept_id, code="A", name="Document Verification"):
    r = await client.post(
        f"{API}/departments/{dept_id}/services",
        headers=headers,
        json={"name": name, "code": code, "average_duration_min": 10},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def make_staff(client, headers, dept_id, email="s1@example.com"):
    r = await client.post(
        f"{API}/departments/{dept_id}/staff",
        headers=headers,
        json={"name": "Staff One", "email": email, "password": "Secret@123"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_department_defaults_and_activity_log(client, org):
    r = await client.get(f"{API}/departments/{org.a}")
    d = r.json()
    assert d["code"] == "EXAM"  # uppercased
    assert d["working_hours"]["mon"] == {"start": "09:00:00", "end": "17:00:00"}
    assert d["working_hours"]["sat"] is None
    assert d["break_windows"] == [{"start": "13:00:00", "end": "14:00:00", "days": None}]
    async with SessionLocal() as db:
        n = await db.scalar(
            select(func.count()).where(
                ActivityLog.entity == "department", ActivityLog.action == "create"
            )
        )
    assert n == 2


async def test_department_validation(client, org):
    r = await client.post(
        f"{API}/departments", headers=org.admin, json={"name": "X", "code": "EXAM"}
    )
    assert_error(r, 409, "CODE_TAKEN")
    r = await client.post(
        f"{API}/departments",
        headers=org.admin,
        json={"name": "X", "code": "XX", "timezone": "Mars/Base"},
    )
    assert_error(r, 422, "VALIDATION_ERROR")
    bad_hours = {"mon": {"start": "17:00", "end": "09:00"}}
    r = await client.patch(
        f"{API}/departments/{org.a}", headers=org.admin, json={"working_hours": bad_hours}
    )
    assert_error(r, 422, "VALIDATION_ERROR")
    assert_error(await client.get(f"{API}/departments/999"), 404, "NOT_FOUND")


async def test_manager_cannot_touch_other_department(client, org):
    m = org.manager
    body = {"name": "Fees", "code": "F", "average_duration_min": 5}
    assert_error(
        await client.post(f"{API}/departments/{org.b}/services", headers=m, json=body),
        403,
        "FORBIDDEN",
    )
    assert_error(
        await client.post(f"{API}/departments/{org.b}/counters", headers=m, json={"name": "C1"}),
        403,
        "FORBIDDEN",
    )
    assert_error(await client.get(f"{API}/departments/{org.b}/staff", headers=m), 403, "FORBIDDEN")
    assert_error(
        await client.patch(f"{API}/departments/{org.b}", headers=m, json={"break_windows": []}),
        403,
        "FORBIDDEN",
    )

    other = await make_service(client, org.admin, org.b, code="F", name="Fees")
    r = await client.patch(f"{API}/services/{other['id']}", headers=m, json={"name": "Hacked"})
    assert_error(r, 403, "FORBIDDEN")
    assert_error(await client.delete(f"{API}/services/{other['id']}", headers=m), 403, "FORBIDDEN")

    # own department works
    await make_service(client, m, org.a)


async def test_manager_edits_only_hours_and_breaks(client, org):
    url = f"{API}/departments/{org.a}"
    assert_error(
        await client.patch(url, headers=org.manager, json={"name": "Renamed"}), 403, "FORBIDDEN"
    )
    fri_prayer = [{"start": "13:00", "end": "14:30", "days": ["fri"]}]
    r = await client.patch(url, headers=org.manager, json={"break_windows": fri_prayer})
    assert r.status_code == 200, r.text
    assert r.json()["break_windows"] == [{"start": "13:00:00", "end": "14:30:00", "days": ["fri"]}]
    assert_error(
        await client.post(
            f"{API}/departments", headers=org.manager, json={"name": "X", "code": "XX"}
        ),
        403,
        "FORBIDDEN",
    )


async def test_service_soft_delete(client, org):
    s = await make_service(client, org.manager, org.a)
    assert (
        await client.delete(f"{API}/services/{s['id']}", headers=org.manager)
    ).status_code == 204

    listed = (await client.get(f"{API}/departments/{org.a}/services")).json()
    assert listed["total"] == 0
    assert (await client.get(f"{API}/services/{s['id']}")).json()["active_status"] is False
    all_ = (await client.get(f"{API}/departments/{org.a}/services?include_inactive=true")).json()
    assert all_["total"] == 1


async def test_service_code_and_slot_config(client, org):
    s = await make_service(client, org.manager, org.a, code="a")
    assert s["code"] == "A"
    assert s["slot_config"] == {"slot_length_min": 30, "max_per_slot": 6, "daily_limit": None}

    r = await client.post(
        f"{API}/departments/{org.a}/services",
        headers=org.manager,
        json={"name": "Dup", "code": "A", "average_duration_min": 5},
    )
    assert_error(r, 409, "CODE_TAKEN")
    await make_service(
        client, org.admin, org.b, code="A"
    )  # same code in another department is fine

    url = f"{API}/services/{s['id']}"
    r = await client.patch(
        url, headers=org.manager, json={"slot_config": {"max_per_slot": 3, "daily_limit": 40}}
    )
    assert r.json()["slot_config"] == {"slot_length_min": 30, "max_per_slot": 3, "daily_limit": 40}
    r = await client.patch(url, headers=org.manager, json={"slot_config": {"daily_limit": None}})
    assert r.json()["slot_config"]["daily_limit"] is None


async def test_search_services(client, org):
    await make_service(client, org.manager, org.a, "A", "Document Verification")
    await make_service(client, org.manager, org.a, "C", "Certificate Verification")
    await make_service(client, org.admin, org.b, "F", "Fee Queries")
    names = lambda r: [s["name"] for s in r.json()["items"]]  # noqa: E731
    assert names(await client.get(f"{API}/services?q=VERIF")) == [
        "Certificate Verification",
        "Document Verification",
    ]
    assert names(await client.get(f"{API}/services?department_id={org.b}")) == ["Fee Queries"]
    assert names(await client.get(f"{API}/services?q=%25")) == []  # LIKE wildcards are escaped


async def test_counters_and_staff_assignment(client, org, login):
    mine = await make_service(client, org.manager, org.a)
    theirs = await make_service(client, org.admin, org.b, code="F", name="Fees")
    staff = await make_staff(client, org.manager, org.a)

    url = f"{API}/departments/{org.a}/counters"
    r = await client.post(
        url, headers=org.manager, json={"name": "C1", "service_ids": [theirs["id"]]}
    )
    assert_error(r, 422, "INVALID_REFERENCE")

    r = await client.post(
        url,
        headers=org.manager,
        json={"name": "C1", "service_ids": [mine["id"]], "assigned_staff_id": staff["id"]},
    )
    assert r.status_code == 201, r.text
    c1 = r.json()
    assert c1["service_ids"] == [mine["id"]] and c1["status"] == "closed"

    r = await client.post(
        url, headers=org.manager, json={"name": "C2", "assigned_staff_id": staff["id"]}
    )
    assert_error(r, 409, "STAFF_ALREADY_ASSIGNED")

    r = await client.patch(
        f"{API}/counters/{c1['id']}", headers=org.manager, json={"assigned_staff_id": None}
    )
    assert r.json()["assigned_staff_id"] is None

    # staff can see their department's counters but not change them
    s = await login("s1@example.com")
    assert (await client.get(url, headers=s)).json()["total"] == 1
    assert_error(await client.post(url, headers=s, json={"name": "C9"}), 403, "FORBIDDEN")
    assert_error(
        await client.get(f"{API}/departments/{org.b}/counters", headers=s), 403, "FORBIDDEN"
    )

    assert (
        await client.delete(f"{API}/counters/{c1['id']}", headers=org.manager)
    ).status_code == 204


async def test_shifts(client, org):
    staff = await make_staff(client, org.manager, org.a)
    c = (
        await client.post(
            f"{API}/departments/{org.a}/counters", headers=org.manager, json={"name": "C1"}
        )
    ).json()
    other = (
        await client.post(
            f"{API}/departments/{org.b}/counters", headers=org.admin, json={"name": "B1"}
        )
    ).json()

    url = f"{API}/departments/{org.a}/shifts"
    shift = {
        "staff_id": staff["id"],
        "counter_id": c["id"],
        "weekday": "mon",
        "start_time": "09:00",
        "end_time": "13:00",
    }
    r = await client.post(url, headers=org.manager, json=shift)
    assert r.status_code == 201, r.text
    assert_error(
        await client.post(url, headers=org.manager, json={**shift, "counter_id": other["id"]}),
        422,
        "INVALID_REFERENCE",
    )
    assert_error(
        await client.post(url, headers=org.manager, json={**shift, "end_time": "08:00"}),
        422,
        "VALIDATION_ERROR",
    )

    assert (await client.get(url, headers=org.manager)).json()["total"] == 1
    assert (
        await client.delete(f"{API}/shifts/{r.json()['id']}", headers=org.manager)
    ).status_code == 204


async def test_rule_override(client, org):
    async def value(key, dept=None):
        async with SessionLocal() as db:
            return await rules_engine.get(db, key, dept)

    key = "cancellation_limit"
    assert await value(key, org.a) == 3  # default

    r = await client.put(
        f"{API}/rules/{key}", headers=org.admin, json={"department_id": None, "value": 5}
    )
    assert r.json() == {"key": key, "value": 5, "source": "org"}
    assert await value(key, org.a) == 5

    r = await client.put(
        f"{API}/rules/{key}", headers=org.manager, json={"department_id": org.a, "value": 1}
    )
    assert r.status_code == 200, r.text
    assert await value(key, org.a) == 1  # department beats org
    assert await value(key, org.b) == 5  # other department still sees org value

    rules = (await client.get(f"{API}/rules?department_id={org.a}", headers=org.manager)).json()[
        "items"
    ]
    by_key = {x["key"]: x for x in rules}
    assert by_key[key] == {"key": key, "value": 1, "source": "department"}
    assert by_key["max_recalls"]["source"] == "default"

    r = await client.delete(f"{API}/rules/{key}?department_id={org.a}", headers=org.manager)
    assert r.status_code == 204
    assert await value(key, org.a) == 5  # back to org


async def test_rule_permissions_and_validation(client, org):
    r = await client.put(
        f"{API}/rules/max_recalls", headers=org.manager, json={"department_id": None, "value": 1}
    )
    assert_error(r, 403, "FORBIDDEN")
    r = await client.put(
        f"{API}/rules/max_recalls", headers=org.manager, json={"department_id": org.b, "value": 1}
    )
    assert_error(r, 403, "FORBIDDEN")
    r = await client.put(f"{API}/rules/max_recalls", headers=org.admin, json={"value": -1})
    assert_error(r, 422, "INVALID_RULE_VALUE")
    r = await client.put(f"{API}/rules/max_recalls", headers=org.admin, json={"value": True})
    assert_error(r, 422, "INVALID_RULE_VALUE")
    r = await client.put(
        f"{API}/rules/priority_services", headers=org.admin, json={"value": [1, 2]}
    )
    assert r.json()["value"] == [1, 2]
    assert_error(
        await client.put(f"{API}/rules/nope", headers=org.admin, json={"value": 1}),
        404,
        "UNKNOWN_RULE",
    )


async def test_admin_user_management(client, org, login):
    r = await client.post(
        f"{API}/admin/users",
        headers=org.admin,
        json={
            "name": "Boss",
            "email": "boss@example.com",
            "password": "Secret@123",
            "role": "manager",
            "department_id": org.b,
        },
    )
    assert r.status_code == 201, r.text
    boss = r.json()
    assert (boss["role"], boss["department_id"]) == ("manager", org.b)

    users = (await client.get(f"{API}/admin/users?role=manager", headers=org.admin)).json()
    assert users["total"] == 2

    # moving a staff member to another department takes them off their counter
    staff = await make_staff(client, org.manager, org.a)
    c = await client.post(
        f"{API}/departments/{org.a}/counters",
        headers=org.manager,
        json={"name": "C1", "assigned_staff_id": staff["id"]},
    )
    r = await client.patch(
        f"{API}/admin/users/{staff['id']}", headers=org.admin, json={"department_id": org.b}
    )
    assert r.json()["department_id"] == org.b
    counters = (
        await client.get(f"{API}/departments/{org.a}/counters", headers=org.manager)
    ).json()["items"]
    assert counters[0]["id"] == c.json()["id"] and counters[0]["assigned_staff_id"] is None

    # suspend via PATCH; suspended staff can't log in
    await client.patch(
        f"{API}/admin/users/{staff['id']}", headers=org.admin, json={"account_status": "suspended"}
    )
    r = await client.post(
        f"{API}/auth/login", json={"email": "s1@example.com", "password": "Secret@123"}
    )
    assert_error(r, 403, "ACCOUNT_SUSPENDED")

    assert_error(await client.get(f"{API}/admin/users/999", headers=org.admin), 404, "NOT_FOUND")
    assert_error(await client.get(f"{API}/admin/users", headers=org.manager), 403, "FORBIDDEN")
