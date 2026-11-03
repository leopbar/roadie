"""Dependências compartilhadas: sessão de banco, usuário autenticado, limitador."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.auth.security import ACCESS_COOKIE, AuthError, decode_access_token
from roadie.db.engine import get_session_factory
from roadie.db.models import User, UserRole

limiter = Limiter(key_func=get_remote_address)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def current_user(request: Request, session: AsyncSession = Depends(get_db)) -> User:
    token = token_from_request(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload["sub"]))
    except (AuthError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc) or "token inválido") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "usuário inativo ou inexistente")
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requer perfil de administrador")
    return user


def get_service(request: Request):
    """Serviço do agente, criado uma vez por processo."""
    svc = getattr(request.app.state, "tom", None)
    if svc is None:
        from roadie.agent.service import TomService

        svc = TomService()
        request.app.state.tom = svc
    return svc
