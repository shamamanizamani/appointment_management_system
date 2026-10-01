from datetime import timedelta

import bcrypt
import jwt

from app.core.config import settings
from app.core.errors import AppError
from app.core.time import now

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(settings.bcrypt_rounds)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode()
    return len(raw) <= 72 and bcrypt.checkpw(raw, password_hash.encode())  # bcrypt's 72-byte cap


def create_token(user_id: int, token_type: str) -> str:
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    issued = now()
    payload = {"sub": str(user_id), "type": token_type, "iat": issued, "exp": issued + lifetime}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str) -> int:
    """Return the user id. Time claims are checked against core.time.now(), not the real clock,
    so frozen time in tests works (PyJWT would otherwise reject a future iat)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
            options={"verify_exp": False, "verify_iat": False},
        )
        user_id, exp = int(payload["sub"]), payload["exp"]
    except (jwt.InvalidTokenError, KeyError, ValueError) as e:
        raise AppError(401, "INVALID_TOKEN", "Your session is invalid. Please log in again.") from e
    if payload.get("type") != expected_type:
        raise AppError(401, "INVALID_TOKEN", "Your session is invalid. Please log in again.")
    if exp <= now().timestamp():
        raise AppError(401, "TOKEN_EXPIRED", "Your session has expired. Please log in again.")
    return user_id
