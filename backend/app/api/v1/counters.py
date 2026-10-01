from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_department_access, get_db, require_role
from app.core.errors import error_responses
from app.models import Counter, Role, StaffShift, User
from app.schemas.org import CounterOut, CounterUpdate
from app.services import org

router = APIRouter(tags=["counters"])
manager_or_admin = require_role(Role.manager, Role.admin)


async def _counter(db: AsyncSession, counter_id: int, user: User) -> Counter:
    counter = await org.get_or_404(db, Counter, counter_id, "Counter")
    check_department_access(user, counter.department_id)
    return counter


@router.patch(
    "/counters/{counter_id}",
    response_model=CounterOut,
    summary="Rename a counter, set its services, assign staff (manager, admin)",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def update_counter(
    counter_id: int,
    body: CounterUpdate,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    return await org.update_counter(db, user, await _counter(db, counter_id, user), body)


@router.delete(
    "/counters/{counter_id}",
    status_code=204,
    summary="Delete a counter (manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def delete_counter(
    counter_id: int, user: User = Depends(manager_or_admin), db: AsyncSession = Depends(get_db)
):
    await org.delete_counter(db, user, await _counter(db, counter_id, user))
    return Response(status_code=204)


@router.delete(
    "/shifts/{shift_id}",
    status_code=204,
    tags=["departments"],
    summary="Delete a staff shift (manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def delete_shift(
    shift_id: int, user: User = Depends(manager_or_admin), db: AsyncSession = Depends(get_db)
):
    shift = await org.get_or_404(db, StaffShift, shift_id, "Shift")
    await _counter(db, shift.counter_id, user)  # scope check via the shift's counter
    await org.delete_shift(db, user, shift)
    return Response(status_code=204)
