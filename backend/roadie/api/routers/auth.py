"""Login, refresh, logout e perfil."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.api.deps import current_user, get_db, limiter
from roadie.api.schemas import LoginIn, PasswordChange, UserOut
from roadie.auth.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    AuthError,
    create_access_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    new_refresh_token,
    validate_password_strength,
    verify_password,
)
from roadie.config import get_settings
from roadie.db.models import RefreshSession, User

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de uma senha qualquer, para que login com e-mail inexistente leve o
# mesmo tempo de um login com senha errada (sem oráculo de existência).
_DUMMY_HASH = hash_password("senha-fantasma-para-tempo-constante-1")


def _set_cookies(response: Response, access: str, refresh: str) -> None:
    s = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        access,
        max_age=s.access_token_minutes * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=s.refresh_token_days * 24 * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


async def _issue_session(
    session: AsyncSession, user: User, request: Request, response: Response
) -> None:
    raw, token_hash, expires_at = new_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    await session.commit()
    _set_cookies(response, create_access_token(user.id, user.role.value), raw)


@router.post("/login", response_model=UserOut)
@limiter.limit(lambda: get_settings().rate_limit_login)
async def login(
    request: Request,
    response: Response,
    body: LoginIn,
    session: AsyncSession = Depends(get_db),
) -> User:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "e-mail ou senha inválidos")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    user.last_login_at = datetime.now(UTC)
    await _issue_session(session, user, request, response)
    return user


@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request, response: Response, session: AsyncSession = Depends(get_db)
) -> User:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sem sessão")
    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(raw))
    )
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at < now:
        _clear_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sessão expirada")
    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        _clear_cookies(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuário inativo")
    stored.revoked_at = now  # rotação: o token antigo morre aqui
    await _issue_session(session, user, request, response)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request, response: Response, session: AsyncSession = Depends(get_db)
) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        stored = await session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_refresh_token(raw))
        )
        if stored and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
            await session.commit()
    _clear_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "senha atual incorreta")
    try:
        validate_password_strength(body.new_password)
    except AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    db_user = await session.get(User, user.id)
    db_user.password_hash = hash_password(body.new_password)
    await session.commit()
