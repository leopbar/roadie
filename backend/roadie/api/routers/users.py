"""Administração de usuários do console (somente admin)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.api.deps import get_db, require_admin
from roadie.api.schemas import UserCreate, UserOut, UserPatch
from roadie.auth.security import AuthError, hash_password, validate_password_strength
from roadie.db.models import User, UserRole

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.created_at))).all())


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, session: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> User:
    try:
        validate_password_strength(body.password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    exists = await session.scalar(select(User).where(User.email == body.email.lower()))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "já existe usuário com esse e-mail")
    user = User(
        email=body.email.lower(),
        name=body.name,
        password_hash=hash_password(body.password),
        role=UserRole(body.role),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    session: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    if user.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "você não pode rebaixar ou desativar a si mesmo"
        )
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role is not None:
        user.role = UserRole(body.role)
    if body.name is not None:
        user.name = body.name
    await session.commit()
    await session.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "você não pode remover a si mesmo")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário não encontrado")
    await session.delete(user)
    await session.commit()
