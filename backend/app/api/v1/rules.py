from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_department_access, get_db, require_role
from app.core.errors import AppError, error_responses
from app.models import Department, Role, User
from app.schemas.common import Page
from app.schemas.org import RuleOut, RulePut
from app.services import org, rules_engine

router = APIRouter(prefix="/rules", tags=["rules"])
manager_or_admin = require_role(Role.manager, Role.admin)


async def _scope(db: AsyncSession, user: User, department_id: int | None) -> None:
    if department_id is None:
        if user.role != Role.admin:
            raise AppError(403, "FORBIDDEN", "Only admins can change organisation-wide rules.")
        return
    check_department_access(user, department_id)
    await org.get_or_404(db, Department, department_id, "Department")


@router.get(
    "",
    response_model=Page[RuleOut],
    summary="Effective rules for a department, or org-wide if omitted (manager, admin)",
    responses=error_responses(401, 403, 404),
)
async def list_rules(
    department_id: int | None = None,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    if department_id is not None:
        await _scope(db, user, department_id)
    items = await rules_engine.effective(db, department_id)
    return {"items": items, "total": len(items)}


@router.put(
    "/{key}",
    response_model=RuleOut,
    summary="Set a rule org-wide (admin) or for a department (its manager, admin)",
    responses=error_responses(401, 403, 404, 422),
)
async def put_rule(
    key: str,
    body: RulePut,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, user, body.department_id)
    return await rules_engine.set_rule(db, user, key, body.department_id, body.value)


@router.delete(
    "/{key}",
    status_code=204,
    summary="Remove a rule override, falling back to org-wide or default",
    responses=error_responses(401, 403, 404),
)
async def delete_rule(
    key: str,
    department_id: int | None = None,
    user: User = Depends(manager_or_admin),
    db: AsyncSession = Depends(get_db),
):
    await _scope(db, user, department_id)
    await rules_engine.delete_rule(db, user, key, department_id)
    return Response(status_code=204)
