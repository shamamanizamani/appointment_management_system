from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.core.errors import ErrorResponse
from app.models import Role, User
from app.schemas.common import Page
from app.schemas.user import UserOut

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_role(Role.admin))],
    responses={
        401: {"model": ErrorResponse, "description": "Not logged in"},
        403: {"model": ErrorResponse, "description": "FORBIDDEN: admin only"},
    },
)


@router.get("/users", response_model=Page[UserOut], summary="List all users (admin)")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    total = await db.scalar(select(func.count()).select_from(User))
    users = await db.scalars(select(User).order_by(User.id).limit(limit).offset(offset))
    return {"items": users.all(), "total": total}
