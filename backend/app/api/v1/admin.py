from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_role
from app.core.errors import ErrorResponse, error_responses
from app.models import Role, User
from app.schemas.common import Page
from app.schemas.org import AdminUserCreate, AdminUserUpdate
from app.schemas.user import UserOut
from app.services import org
from app.utils.pagination import paginate

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={
        401: {"model": ErrorResponse, "description": "Not logged in"},
        403: {"model": ErrorResponse, "description": "FORBIDDEN: admin only"},
    },
)
admin_only = require_role(Role.admin)


@router.get("/users", response_model=Page[UserOut], summary="List all users (admin)")
async def list_users(
    role: Role | None = None,
    department_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.id)
    if role:
        stmt = stmt.where(User.role == role)
    if department_id is not None:
        stmt = stmt.where(User.department_id == department_id)
    return await paginate(db, stmt, limit, offset)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    summary="Create a user with any role (admin)",
    responses=error_responses(404, 409, 422),
)
async def create_user(
    body: AdminUserCreate, user: User = Depends(admin_only), db: AsyncSession = Depends(get_db)
):
    return await org.create_user(db, user, body, body.role, body.department_id)


@router.get(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Get a user (admin)",
    responses=error_responses(404),
)
async def get_user(user_id: int, _: User = Depends(admin_only), db: AsyncSession = Depends(get_db)):
    return await org.get_or_404(db, User, user_id, "User")


@router.patch(
    "/users/{user_id}",
    response_model=UserOut,
    summary="Update a user: role, department, status, password (admin)",
    responses=error_responses(404, 422),
)
async def update_user(
    user_id: int,
    body: AdminUserUpdate,
    user: User = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    target = await org.get_or_404(db, User, user_id, "User")
    return await org.update_user(db, user, target, body)
