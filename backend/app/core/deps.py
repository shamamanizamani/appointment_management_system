from collections.abc import AsyncIterator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.errors import AppError
from app.core.security import decode_token
from app.models import AccountStatus, Role, User

# tokenUrl powers the Authorize button in /docs; the Flutter app uses POST /auth/login.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    if not token:
        raise AppError(401, "NOT_AUTHENTICATED", "Please log in to continue.")
    user = await db.get(User, decode_token(token, "access"))
    if user is None:
        raise AppError(401, "INVALID_TOKEN", "Your session is invalid. Please log in again.")
    if user.account_status != AccountStatus.active:
        raise AppError(403, "ACCOUNT_SUSPENDED", "Your account has been suspended.")
    return user


def require_role(*roles: Role):
    async def check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "FORBIDDEN", "You don't have permission to do this.")
        return user

    return check
