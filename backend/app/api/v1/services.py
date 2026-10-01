from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_department_access, get_db, require_role
from app.core.errors import error_responses
from app.models import Role, Service, User
from app.schemas.appointment import AvailableDate, SlotGrid
from app.schemas.common import Page
from app.schemas.org import ServiceOut, ServiceUpdate
from app.schemas.token import TokenOut
from app.services import appointment_manager, org, queue_manager
from app.utils.pagination import paginate

router = APIRouter(prefix="/services", tags=["services"])
manager_or_admin = require_role(Role.manager, Role.admin)
dept_member = require_role(Role.staff, Role.manager, Role.admin)


async def _service(db: AsyncSession, service_id: int, user: User | None = None) -> Service:
    service = await org.get_or_404(db, Service, service_id, "Service")
    if user is not None:
        check_department_access(user, service.department_id)
    return service


@router.get("", response_model=Page[ServiceOut], summary="Search active services (public, §9)")
async def search_services(
    q: str | None = Query(None, max_length=100, description="Matches the name, case-insensitive"),
    department_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Service).where(Service.active_status).order_by(Service.name)
    if q:
        stmt = stmt.where(Service.name.icontains(q, autoescape=True))
    if department_id is not None:
        stmt = stmt.where(Service.department_id == department_id)
    return await paginate(db, stmt, limit, offset)


@router.get(
    "/{service_id}",
    response_model=ServiceOut,
    summary="Get a service (public)",
    responses=error_responses(404),
)
async def get_service(service_id: int, db: AsyncSession = Depends(get_db)):
    return await _service(db, service_id)


@router.patch(
    "/{service_id}",
    response_model=ServiceOut,
    summary="Update a service and its slot config (manager of its department, admin)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def update_service(
    service_id: int,
    body: ServiceUpdate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    return await org.update_service(db, user, await _service(db, service_id, user), body)


@router.delete(
    "/{service_id}",
    status_code=204,
    summary="Deactivate a service (soft delete; manager of its department, admin)",
    responses=error_responses(401, 403, 404),
)
async def delete_service(
    service_id: int, user: User = Depends(manager_or_admin), db: AsyncSession = Depends(get_db)
):
    await org.deactivate_service(db, user, await _service(db, service_id, user))
    return Response(status_code=204)


@router.get(
    "/{service_id}/slots",
    response_model=SlotGrid,
    summary="Appointment slot grid for one day (public, §5)",
    responses=error_responses(404, 409, 422),
)
async def get_slots(
    service_id: int,
    date: date = Query(description="Department-local date, YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    return await appointment_manager.slot_grid(db, await _service(db, service_id), date)


@router.get(
    "/{service_id}/available-dates",
    response_model=Page[AvailableDate],
    summary="Which days have free slots (public; defaults to the whole booking window)",
    responses=error_responses(404, 409, 422),
)
async def get_available_dates(
    service_id: int,
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = await _service(db, service_id)
    items = await appointment_manager.available_dates(db, service, from_, to)
    return {"items": items, "total": len(items)}


@router.get(
    "/{service_id}/queue",
    response_model=Page[TokenOut],
    summary="Today's waiting list in call order (staff/manager of its department, admin)",
    responses=error_responses(401, 403, 404),
)
async def get_queue(
    service_id: int, user: User = Depends(dept_member), db: AsyncSession = Depends(get_db)
):
    service = await _service(db, service_id, user)
    tokens = await queue_manager.recalculate_queue(db, service)
    current = await queue_manager.current_token(db, service)
    for t in tokens:
        t.current_token = current
    return {"items": tokens, "total": len(tokens)}
