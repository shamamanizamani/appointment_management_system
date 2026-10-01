from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_department_access, get_db, require_role
from app.core.errors import error_responses
from app.models import Counter, Department, Role, Service, StaffShift, User
from app.schemas.common import Page
from app.schemas.org import (
    CounterCreate,
    CounterOut,
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    ServiceCreate,
    ServiceOut,
    ShiftCreate,
    ShiftOut,
    StaffCreate,
    StaffUpdate,
)
from app.schemas.user import UserOut
from app.services import org
from app.utils.pagination import paginate

router = APIRouter(prefix="/departments", tags=["departments"])

admin_only = require_role(Role.admin)
manager_or_admin = require_role(Role.manager, Role.admin)
dept_member = require_role(Role.staff, Role.manager, Role.admin)

Limit = Query(100, ge=1, le=500)
Offset = Query(0, ge=0)


async def _dept(db: AsyncSession, department_id: int, user: User | None = None) -> Department:
    """Scope check first (403), then existence (404)."""
    if user is not None:
        check_department_access(user, department_id)
    return await org.get_or_404(db, Department, department_id, "Department")


# --- departments ---


@router.get("", response_model=Page[DepartmentOut], summary="List departments (public)")
async def list_departments(
    include_inactive: bool = False,
    limit: int = Limit,
    offset: int = Offset,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Department).order_by(Department.name)
    if not include_inactive:
        stmt = stmt.where(Department.active)
    return await paginate(db, stmt, limit, offset)


@router.get(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Get a department (public)",
    responses=error_responses(404),
)
async def get_department(department_id: int, db: AsyncSession = Depends(get_db)):
    return await _dept(db, department_id)


@router.post(
    "",
    response_model=DepartmentOut,
    status_code=201,
    summary="Create a department (admin)",
    responses=error_responses(401, 403, 409, 422),
)
async def create_department(
    body: DepartmentCreate, user: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await org.create_department(db, user, body)


@router.patch(
    "/{department_id}",
    response_model=DepartmentOut,
    summary="Update a department (admin: any field; manager: own working hours and breaks)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def update_department(
    department_id: int,
    body: DepartmentUpdate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    return await org.update_department(db, user, await _dept(db, department_id, user), body)


@router.delete(
    "/{department_id}",
    status_code=204,
    summary="Deactivate a department (admin, soft delete)",
    responses=error_responses(401, 403, 404),
)
async def delete_department(
    department_id: int, user: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    await org.deactivate_department(db, user, await _dept(db, department_id, user))
    return Response(status_code=204)


# --- services in a department ---


@router.get(
    "/{department_id}/services",
    response_model=Page[ServiceOut],
    summary="List a department's services (public)",
    responses=error_responses(404),
)
async def list_services(
    department_id: int,
    include_inactive: bool = False,
    limit: int = Limit,
    offset: int = Offset,
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id)
    stmt = select(Service).where(Service.department_id == department_id).order_by(Service.code)
    if not include_inactive:
        stmt = stmt.where(Service.active_status)
    return await paginate(db, stmt, limit, offset)


@router.post(
    "/{department_id}/services",
    response_model=ServiceOut,
    status_code=201,
    summary="Create a service (manager of this department, admin)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def create_service(
    department_id: int,
    body: ServiceCreate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    return await org.create_service(db, user, department_id, body)


# --- counters in a department ---


@router.get(
    "/{department_id}/counters",
    response_model=Page[CounterOut],
    summary="List a department's counters (its staff and manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def list_counters(
    department_id: int,
    limit: int = Limit,
    offset: int = Offset,
    user: User = Depends(dept_member),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    stmt = select(Counter).where(Counter.department_id == department_id).order_by(Counter.name)
    return await paginate(db, stmt, limit, offset)


@router.post(
    "/{department_id}/counters",
    response_model=CounterOut,
    status_code=201,
    summary="Create a counter (manager of this department, admin)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def create_counter(
    department_id: int,
    body: CounterCreate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    return await org.create_counter(db, user, department_id, body)


# --- staff in a department ---


@router.get(
    "/{department_id}/staff",
    response_model=Page[UserOut],
    summary="List a department's staff (manager of this department, admin)",
    responses=error_responses(401, 403, 404),
)
async def list_staff(
    department_id: int,
    limit: int = Limit,
    offset: int = Offset,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    stmt = (
        select(User)
        .where(User.department_id == department_id, User.role == Role.staff)
        .order_by(User.name)
    )
    return await paginate(db, stmt, limit, offset)


@router.post(
    "/{department_id}/staff",
    response_model=UserOut,
    status_code=201,
    summary="Create a staff account in this department (manager, admin)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def create_staff(
    department_id: int,
    body: StaffCreate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    return await org.create_user(db, user, body, Role.staff, department_id)


@router.patch(
    "/{department_id}/staff/{user_id}",
    response_model=UserOut,
    summary="Update a staff member: name, phone, suspend/reactivate (manager, admin)",
    responses=error_responses(401, 403, 404, 422),
)
async def update_staff(
    department_id: int,
    user_id: int,
    body: StaffUpdate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    staff = await org.get_department_staff(db, department_id, user_id)
    return await org.update_user(db, user, staff, body)


# --- shifts in a department ---


@router.get(
    "/{department_id}/shifts",
    response_model=Page[ShiftOut],
    summary="List staff shifts in this department (manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def list_shifts(
    department_id: int,
    staff_id: int | None = None,
    limit: int = Limit,
    offset: int = Offset,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    stmt = (
        select(StaffShift)
        .join(Counter, Counter.id == StaffShift.counter_id)
        .where(Counter.department_id == department_id)
        .order_by(StaffShift.staff_id, StaffShift.id)  # weekday strings would sort fri < mon
    )
    if staff_id is not None:
        stmt = stmt.where(StaffShift.staff_id == staff_id)
    return await paginate(db, stmt, limit, offset)


@router.post(
    "/{department_id}/shifts",
    response_model=ShiftOut,
    status_code=201,
    summary="Add a staff shift (manager, admin)",
    responses=error_responses(401, 403, 404, 422),
)
async def create_shift(
    department_id: int,
    body: ShiftCreate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _dept(db, department_id, user)
    return await org.create_shift(db, user, department_id, body)
