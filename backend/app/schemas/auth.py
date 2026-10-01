from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.schemas.user import Name, Phone, UserOut


def _fits_bcrypt(v: str) -> str:
    if len(v.encode()) > 72:
        raise ValueError("Password is too long")
    return v


Password = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_fits_bcrypt)]


class RegisterIn(BaseModel):
    name: Name
    email: EmailStr
    password: Password
    phone: Phone | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class AuthOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut
