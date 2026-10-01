"""Organisation setup (§2, §5, §6): departments, services, counters, staff, shifts, users.

Every create/update/delete writes an activity log row in the same transaction (§10).
"""

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password
from app.models import Counter, Department, Role, Service, SlotConfig, StaffShift, User
from app.schemas.auth import RegisterIn
from app.schemas.org import (
    CounterCreate,
    CounterUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    ServiceCreate,
    ServiceUpdate,
    ShiftCreate,
)
from app.services import activity

MANAGER_DEPARTMENT_FIELDS = {"working_hours", "break_windows"}


async def get_or_404(db: AsyncSession, model, id: int, label: str):
    obj = await db.get(model, id)
    if obj is None:
        raise AppError(404, "NOT_FOUND", f"{label} not found.")
    return obj


def _changes(data, nullable: set[str] = frozenset()) -> dict[str, Any]:
    """Fields the client actually sent. Explicit null only counts for nullable fields."""
    sent = data.model_dump(mode="json", exclude_unset=True, exclude={"password", "slot_config"})
    return {k: v for k, v in sent.items() if v is not None or k in nullable}


def _apply(obj, changes: dict[str, Any]) -> None:
    for k, v in changes.items():
        setattr(obj, k, v)


def _invalid(message: str) -> AppError:
    return AppError(422, "INVALID_REFERENCE", message)


# --- departments ---


async def _check_dept_code(db: AsyncSession, code: str, exclude_id: int | None = None) -> None:
    stmt = select(Department.id).where(Department.code == code, Department.id != exclude_id)
    if await db.scalar(stmt):
        raise AppError(409, "CODE_TAKEN", f"A department with code {code} already exists.")


async def create_department(db: AsyncSession, actor: User, data: DepartmentCreate) -> Department:
    await _check_dept_code(db, data.code)
    dept = Department(**data.model_dump(mode="json"))
    db.add(dept)
    await db.flush()
    activity.log(db, actor, "create", "department", dept.id, data.model_dump(mode="json"))
    await db.commit()
    return dept


async def update_department(
    db: AsyncSession, actor: User, dept: Department, data: DepartmentUpdate
) -> Department:
    changes = _changes(data)
    if actor.role == Role.manager and set(changes) - MANAGER_DEPARTMENT_FIELDS:
        raise AppError(403, "FORBIDDEN", "Managers can only change working hours and breaks.")
    if "code" in changes:
        await _check_dept_code(db, changes["code"], dept.id)
    _apply(dept, changes)
    activity.log(db, actor, "update", "department", dept.id, changes)
    await db.commit()
    return dept


async def deactivate_department(db: AsyncSession, actor: User, dept: Department) -> None:
    dept.active = False
    activity.log(db, actor, "delete", "department", dept.id)
    await db.commit()


# --- services ---


async def _check_service_code(
    db: AsyncSession, department_id: int, code: str, exclude_id: int | None = None
) -> None:
    stmt = select(Service.id).where(
        Service.department_id == department_id, Service.code == code, Service.id != exclude_id
    )
    if await db.scalar(stmt):
        raise AppError(409, "CODE_TAKEN", f"Code {code} is already used in this department.")


async def create_service(
    db: AsyncSession, actor: User, department_id: int, data: ServiceCreate
) -> Service:
    await _check_service_code(db, department_id, data.code)
    service = Service(
        department_id=department_id,
        **data.model_dump(exclude={"slot_config"}),
        slot_config=SlotConfig(**data.slot_config.model_dump()),
    )
    db.add(service)
    await db.flush()
    activity.log(db, actor, "create", "service", service.id, data.model_dump(mode="json"))
    await db.commit()
    return service


async def update_service(
    db: AsyncSession, actor: User, service: Service, data: ServiceUpdate
) -> Service:
    changes = _changes(data, nullable={"description"})
    if "code" in changes:
        await _check_service_code(db, service.department_id, changes["code"], service.id)
    _apply(service, changes)
    if data.slot_config:
        slot_changes = _changes(data.slot_config, nullable={"daily_limit"})
        _apply(service.slot_config, slot_changes)
        changes["slot_config"] = slot_changes
    activity.log(db, actor, "update", "service", service.id, changes)
    await db.commit()
    return service


async def deactivate_service(db: AsyncSession, actor: User, service: Service) -> None:
    # Soft delete: appointments and tokens keep pointing at it; it just stops being offered.
    service.active_status = False
    activity.log(db, actor, "delete", "service", service.id)
    await db.commit()


# --- counters ---


async def _check_counter_refs(
    db: AsyncSession,
    department_id: int,
    service_ids: list[int] | None,
    staff_id: int | None,
    counter_id: int | None = None,
) -> list[Service] | None:
    services = None
    if service_ids is not None:
        services = list(
            await db.scalars(
                select(Service).where(
                    Service.id.in_(service_ids), Service.department_id == department_id
                )
            )
        )
        if len(services) != len(set(service_ids)):
            raise _invalid("Every service on a counter must belong to the counter's department.")
    if staff_id is not None:
        staff = await db.get(User, staff_id)
        if not staff or staff.role != Role.staff or staff.department_id != department_id:
            raise _invalid("The assigned person must be a staff member of this department.")
        taken = await db.scalar(
            select(Counter.name).where(
                Counter.assigned_staff_id == staff_id, Counter.id != counter_id
            )
        )
        if taken:
            raise AppError(
                409, "STAFF_ALREADY_ASSIGNED", f"This staff member is already on {taken}."
            )
    return services


async def create_counter(
    db: AsyncSession, actor: User, department_id: int, data: CounterCreate
) -> Counter:
    services = await _check_counter_refs(
        db, department_id, data.service_ids, data.assigned_staff_id
    )
    counter = Counter(
        department_id=department_id,
        name=data.name,
        assigned_staff_id=data.assigned_staff_id,
        services=services,
    )
    db.add(counter)
    await db.flush()
    activity.log(db, actor, "create", "counter", counter.id, data.model_dump(mode="json"))
    await db.commit()
    return counter


async def update_counter(
    db: AsyncSession, actor: User, counter: Counter, data: CounterUpdate
) -> Counter:
    changes = _changes(data, nullable={"assigned_staff_id"})
    services = await _check_counter_refs(
        db,
        counter.department_id,
        changes.pop("service_ids", None),
        changes.get("assigned_staff_id"),
        counter.id,
    )
    _apply(counter, changes)
    if services is not None:
        counter.services = services
        changes["service_ids"] = data.service_ids
    activity.log(db, actor, "update", "counter", counter.id, changes)
    await db.commit()
    return counter


async def delete_counter(db: AsyncSession, actor: User, counter: Counter) -> None:
    activity.log(db, actor, "delete", "counter", counter.id, {"name": counter.name})
    await db.delete(counter)
    await db.commit()


# --- users and staff ---


async def create_user(
    db: AsyncSession, actor: User, data: RegisterIn, role: Role, department_id: int | None
) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    if department_id is not None:
        await get_or_404(db, Department, department_id, "Department")
    user = User(
        name=data.name,
        email=email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=role,
        department_id=department_id,
    )
    db.add(user)
    await db.flush()
    activity.log(
        db, actor, "create", "user", user.id, {"role": role, "department_id": department_id}
    )
    await db.commit()
    return user


async def update_user(db: AsyncSession, actor: User, user: User, data) -> User:
    """Shared by managers (StaffUpdate) and admins (AdminUserUpdate)."""
    changes = _changes(data, nullable={"phone", "department_id"})
    if changes.get("department_id") is not None:
        await get_or_404(db, Department, changes["department_id"], "Department")
    moved = any(k in changes and changes[k] != getattr(user, k) for k in ("role", "department_id"))
    _apply(user, changes)
    if getattr(data, "password", None):
        user.password_hash = hash_password(data.password)
        changes["password"] = "changed"
    if moved:
        # A staff member who changes role or department leaves their counter and shifts.
        await db.execute(
            update(Counter)
            .where(Counter.assigned_staff_id == user.id)
            .values(assigned_staff_id=None)
        )
        await db.execute(delete(StaffShift).where(StaffShift.staff_id == user.id))
    activity.log(db, actor, "update", "user", user.id, changes)
    await db.commit()
    return user


async def get_department_staff(db: AsyncSession, department_id: int, user_id: int) -> User:
    user = await db.get(User, user_id)
    if not user or user.role != Role.staff or user.department_id != department_id:
        raise AppError(404, "NOT_FOUND", "Staff member not found in this department.")
    return user


# --- shifts ---


async def create_shift(
    db: AsyncSession, actor: User, department_id: int, data: ShiftCreate
) -> StaffShift:
    await get_department_staff(db, department_id, data.staff_id)
    counter = await db.get(Counter, data.counter_id)
    if not counter or counter.department_id != department_id:
        raise _invalid("The counter must belong to this department.")
    shift = StaffShift(**data.model_dump())
    db.add(shift)
    await db.flush()
    activity.log(db, actor, "create", "shift", shift.id, data.model_dump(mode="json"))
    await db.commit()
    return shift


async def delete_shift(db: AsyncSession, actor: User, shift: StaffShift) -> None:
    activity.log(db, actor, "delete", "shift", shift.id)
    await db.delete(shift)
    await db.commit()
