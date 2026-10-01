from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import check_owner_access, get_db, require_role
from app.core.errors import error_responses
from app.models import Role, Token, User
from app.schemas.common import Page
from app.schemas.token import JoinIn, TokenOut
from app.services import org
from app.services import queue_manager as qm

router = APIRouter(prefix="/tokens", tags=["tokens"])

customer = require_role(Role.customer)
anyone = require_role(Role.customer, Role.staff, Role.manager, Role.admin)
canceller = require_role(Role.customer, Role.manager, Role.admin)


async def _token(db: AsyncSession, token_id: int, user: User, manage: bool = False) -> Token:
    token = await org.get_or_404(db, Token, token_id, "Token")
    check_owner_access(user, token, "Token", manage)
    return token


@router.post(
    "",
    response_model=TokenOut,
    status_code=201,
    summary="Join a service's walk-in queue and get a token (customer)",
    responses=error_responses(401, 403, 404, 409),
)
async def join(body: JoinIn, user: User = Depends(customer), db: AsyncSession = Depends(get_db)):
    return await qm.join(db, user, body.service_id)


@router.get(
    "/me/active",
    response_model=Page[TokenOut],
    summary="My active tokens with live position and estimate (customer)",
    responses=error_responses(401, 403),
)
async def my_active(user: User = Depends(customer), db: AsyncSession = Depends(get_db)):
    tokens = list(await db.scalars(qm.mine_active_query(user)))
    for t in tokens:
        await qm.refresh(db, t)
    return {"items": tokens, "total": len(tokens)}


@router.get(
    "/{token_id}",
    response_model=TokenOut,
    summary="One token with live position and estimate (its customer, its department, admin)",
    responses=error_responses(401, 403, 404),
)
async def get_token(
    token_id: int, user: User = Depends(anyone), db: AsyncSession = Depends(get_db)
):
    return await qm.refresh(db, await _token(db, token_id, user))


@router.post(
    "/{token_id}/cancel",
    response_model=TokenOut,
    summary="Leave the queue (its customer, its department's manager, admin)",
    responses=error_responses(401, 403, 404, 409),
)
async def cancel(
    token_id: int, user: User = Depends(canceller), db: AsyncSession = Depends(get_db)
):
    return await qm.cancel(db, await _token(db, token_id, user, manage=True))
