from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.errors import ErrorResponse
from app.models import User
from app.schemas.auth import AuthOut, LoginIn, RefreshIn, RegisterIn
from app.schemas.user import UserOut, UserUpdate
from app.services import auth

router = APIRouter(tags=["auth"])

E401 = {401: {"model": ErrorResponse, "description": "Not logged in or session invalid/expired"}}
E403 = {403: {"model": ErrorResponse, "description": "Account suspended"}}
E422 = {422: {"model": ErrorResponse, "description": "Invalid input"}}


@router.post(
    "/auth/register",
    response_model=AuthOut,
    status_code=201,
    summary="Register a customer account and log in",
    responses={409: {"model": ErrorResponse, "description": "EMAIL_TAKEN"}, **E422},
)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    return auth.issue_tokens(await auth.register(db, body))


@router.post(
    "/auth/login",
    response_model=AuthOut,
    summary="Log in with email and password (JSON)",
    responses={**E401, **E403, **E422},
)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    return auth.issue_tokens(await auth.authenticate(db, body.email, body.password))


@router.post(
    "/auth/token",
    response_model=AuthOut,
    summary="Log in with a form (used by the Authorize button in /docs)",
    description="Put the email in the `username` field. Apps should use `POST /auth/login`.",
    responses={**E401, **E403},
)
async def token(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    return auth.issue_tokens(await auth.authenticate(db, form.username, form.password))


@router.post(
    "/auth/refresh",
    response_model=AuthOut,
    summary="Exchange a refresh token for a new token pair",
    responses={**E401, **E403},
)
async def refresh(body: RefreshIn, db: AsyncSession = Depends(get_db)):
    return auth.issue_tokens(await auth.refresh(db, body.refresh_token))


@router.get("/me", response_model=UserOut, summary="Current user's profile", responses=E401)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Update own name and/or phone",
    responses={**E401, **E422},
)
async def update_me(
    body: UserUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if body.name is not None:
        user.name = body.name
    if "phone" in body.model_fields_set:
        user.phone = body.phone
    await db.commit()
    return user
