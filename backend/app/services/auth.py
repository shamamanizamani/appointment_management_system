from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import AccountStatus, Role, User
from app.schemas.auth import AuthOut, RegisterIn
from app.schemas.user import UserOut

# Compared against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def issue_tokens(user: User) -> AuthOut:
    return AuthOut(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
        user=UserOut.model_validate(user),
    )


async def register(db: AsyncSession, data: RegisterIn) -> User:
    """Public registration always creates a customer (§2); other roles are created by admins."""
    user = User(
        name=data.name,
        email=data.email.lower(),
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=Role.customer,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise AppError(409, "EMAIL_TAKEN", "An account with this email already exists.") from e
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    if not verify_password(password, user.password_hash if user else _DUMMY_HASH) or not user:
        raise AppError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    if user.account_status != AccountStatus.active:
        raise AppError(403, "ACCOUNT_SUSPENDED", "Your account has been suspended.")
    return user


async def refresh(db: AsyncSession, refresh_token: str) -> User:
    user = await db.get(User, decode_token(refresh_token, "refresh"))
    if user is None:
        raise AppError(401, "INVALID_TOKEN", "Your session is invalid. Please log in again.")
    if user.account_status != AccountStatus.active:
        raise AppError(403, "ACCOUNT_SUSPENDED", "Your account has been suspended.")
    return user
