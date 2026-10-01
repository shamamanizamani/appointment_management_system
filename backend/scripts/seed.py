"""Demo data: one account per role plus a small university (brief §5, §6).

Idempotent: anything that already exists (matched by email / code / name) is left untouched,
so the demo accounts never change. Run: python -m scripts.seed
"""

import asyncio
from datetime import time

from sqlalchemy import select

from app.core.db import SessionLocal, engine
from app.core.security import hash_password
from app.models import (
    Counter,
    CounterStatus,
    Department,
    Role,
    Service,
    SlotConfig,
    StaffShift,
    User,
)
from app.schemas.org import DEFAULT_BREAKS, DEFAULT_WORKING_HOURS, WEEKDAYS

DEMO_PASSWORD = "Demo@1234"
SLOT_LENGTH_MIN = 30

# code -> (name, [(service name, code, minutes)], [(counter, [service codes])], manager, [staff])
UNIVERSITY = {
    "EXAM": (
        "Examination",
        [("Document Verification", "A", 10), ("Certificate Verification", "C", 10)],
        [("Counter 1", ["A"]), ("Counter 2", ["A", "C"]), ("Counter 3", ["C"])],
        "manager@demo.com",
        ["staff@demo.com", "staff2.exam@demo.com"],
    ),
    "SA": (
        "Student Affairs",
        [("Document Collection", "B", 5), ("New Registration", "D", 20)],
        [("Counter 1", ["B"]), ("Counter 2", ["D"]), ("Counter 3", ["B", "D"])],
        "manager.sa@demo.com",
        ["staff1.sa@demo.com", "staff2.sa@demo.com"],
    ),
    "ACC": (
        "Accounts",
        [("Fee Queries", "F", 5)],
        [("Counter 1", ["F"]), ("Counter 2", ["F"])],
        "manager.acc@demo.com",
        ["staff1.acc@demo.com", "staff2.acc@demo.com"],
    ),
}

# The four stable demo accounts from API.md. Names here are only used on first creation.
DEMO_USERS = [
    ("Demo Customer", "customer@demo.com", Role.customer),
    ("Demo Staff", "staff@demo.com", Role.staff),
    ("Demo Manager", "manager@demo.com", Role.manager),
    ("Demo Admin", "admin@demo.com", Role.admin),
]


async def get_or_create(db, model, where: dict, **create):
    obj = await db.scalar(select(model).filter_by(**where))
    if obj is None:
        obj = model(**where, **create)
        db.add(obj)
        await db.flush()
        print(f"created  {model.__tablename__}: {where}")
    return obj


async def user(db, email: str, name: str, role: Role, department_id: int | None = None) -> User:
    u = await get_or_create(
        db, User, {"email": email}, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD)
    )
    if department_id and u.department_id is None:
        u.department_id = department_id  # links the pre-existing demo staff/manager
    return u


async def seed() -> None:
    async with SessionLocal() as db:
        for name, email, role in DEMO_USERS:
            await user(db, email, name, role)

        for dept_code, (dept_name, services, counters, manager, staff) in UNIVERSITY.items():
            dept = await get_or_create(
                db,
                Department,
                {"code": dept_code},
                name=dept_name,
                working_hours=DEFAULT_WORKING_HOURS.model_dump(mode="json"),
                break_windows=[b.model_dump(mode="json") for b in DEFAULT_BREAKS],
            )
            await user(db, manager, f"{dept_name} Manager", Role.manager, dept.id)

            by_code = {}
            for svc_name, code, minutes in services:
                # Capacity per slot ≈ counters serving it × slot length ÷ duration (§5).
                n_counters = sum(code in codes for _, codes in counters)
                by_code[code] = await get_or_create(
                    db,
                    Service,
                    {"department_id": dept.id, "code": code},
                    name=svc_name,
                    average_duration_min=minutes,
                    slot_config=SlotConfig(
                        slot_length_min=SLOT_LENGTH_MIN,
                        max_per_slot=max(1, n_counters * SLOT_LENGTH_MIN // minutes),
                    ),
                )

            for i, (counter_name, codes) in enumerate(counters):
                staff_user = None
                if i < len(staff):
                    staff_user = await user(
                        db, staff[i], f"{dept_name} Staff {i + 1}", Role.staff, dept.id
                    )
                counter = await get_or_create(
                    db,
                    Counter,
                    {"department_id": dept.id, "name": counter_name},
                    status=CounterStatus.available,
                    assigned_staff_id=staff_user.id if staff_user else None,
                    services=[by_code[c] for c in codes],
                )
                if staff_user and not await db.scalar(
                    select(StaffShift.id).where(StaffShift.staff_id == staff_user.id)
                ):
                    for day in WEEKDAYS[:5]:
                        db.add(
                            StaffShift(
                                staff_id=staff_user.id,
                                counter_id=counter.id,
                                weekday=day,
                                start_time=time(9),
                                end_time=time(17),
                            )
                        )
        await db.commit()
    await engine.dispose()
    print("seed done")


if __name__ == "__main__":
    asyncio.run(seed())
