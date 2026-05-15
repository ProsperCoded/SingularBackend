from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.auth import get_current_user
from core.database import get_db_session
from core.security import create_access_token, hash_password, verify_password
from models.user import User
from schemas.auth import AuthLoginRequest, AuthSessionResponse, AuthSignupRequest, AuthUserResponse


router = APIRouter(prefix="/auth", tags=["Authentication"])


def _serialize_user(user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
        vendor_id=user.vendor_id,
        created_at=user.created_at,
    )


@router.post("/signup", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: AuthSignupRequest,
    session: AsyncSession = Depends(get_db_session),
):
    existing_user = (await session.exec(select(User).where(User.email == payload.email.lower()))).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(
        full_name=payload.full_name.strip(),
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    return AuthSessionResponse(
        access_token=create_access_token(subject=user.id),
        user=_serialize_user(user),
    )


@router.post("/login", response_model=AuthSessionResponse)
async def login(
    payload: AuthLoginRequest,
    session: AsyncSession = Depends(get_db_session),
):
    user = (await session.exec(select(User).where(User.email == payload.email.lower()))).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    return AuthSessionResponse(
        access_token=create_access_token(subject=user.id),
        user=_serialize_user(user),
    )


@router.get("/me", response_model=AuthUserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return _serialize_user(current_user)
