from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_department_access, check_owner_access, get_db, require_role
from app.core.errors import error_responses
from app.models import Appointment, AppointmentStatus, Role, User
from app.schemas.appointment import AppointmentOut, BookIn, RescheduleIn
from app.schemas.common import Page
from app.services import appointment_manager as am
from app.services import org
from app.utils.pagination import paginate

router = APIRouter(prefix="/appointments", tags=["appointments"])

customer = require_role(Role.customer)
anyone = require_role(Role.customer, Role.staff, Role.manager, Role.admin)
dept_member = require_role(Role.staff, Role.manager, Role.admin)
canceller = require_role(Role.customer, Role.manager, Role.admin)


async def _appointment(db: AsyncSession, appointment_id: int, user: User, manage: bool = False):
    appt = await org.get_or_404(db, Appointment, appointment_id, "Appointment")
    check_owner_access(user, appt, "Appointment", manage)
    return appt


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=201,
    summary="Book an appointment slot (customer)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def book(body: BookIn, user: User = Depends(customer), db: AsyncSession = Depends(get_db)):
    return await am.book(db, user, body.service_id, body.start)


@router.get(
    "/me",
    response_model=Page[AppointmentOut],
    summary="My appointments: upcoming and history (customer)",
    responses=error_responses(401, 403),
)
async def my_appointments(
    when: Literal["upcoming", "past", "all"] = "all",
    status: AppointmentStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(customer),
    db: AsyncSession = Depends(get_db),
):
    return await paginate(db, am.mine_query(user, when, status), limit, offset)


@router.get(
    "",
    response_model=Page[AppointmentOut],
    summary="Department appointments (staff/manager: own department; admin: any)",
    responses=error_responses(401, 403),
)
async def department_appointments(
    department_id: int | None = None,
    service_id: int | None = None,
    date: date | None = None,
    status: AppointmentStatus | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(dept_member),
    db: AsyncSession = Depends(get_db),
):
    if user.role != Role.admin:
        department_id = department_id or user.department_id
        check_department_access(user, department_id)
    stmt = am.department_query(department_id, service_id, date, status)
    return await paginate(db, stmt, limit, offset)


@router.get(
    "/{appointment_id}",
    response_model=AppointmentOut,
    summary="One appointment (its customer, its department's staff/manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def get_appointment(
    appointment_id: int, user: User = Depends(anyone), db: AsyncSession = Depends(get_db)
):
    return await _appointment(db, appointment_id, user)


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentOut,
    summary="Cancel (its customer, its department's manager, admin)",
    responses=error_responses(401, 403, 404, 409),
)
async def cancel(
    appointment_id: int, user: User = Depends(canceller), db: AsyncSession = Depends(get_db)
):
    return await am.cancel(db, user, await _appointment(db, appointment_id, user, manage=True))


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentOut,
    status_code=201,
    summary="Move to another slot of the same service; returns the new appointment",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def reschedule(
    appointment_id: int,
    body: RescheduleIn,
    user: User = Depends(canceller),
    db: AsyncSession = Depends(get_db),
):
    appt = await _appointment(db, appointment_id, user, manage=True)
    return await am.reschedule(db, user, appt, body.start)
