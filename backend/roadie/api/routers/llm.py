"""Configuração do modelo de linguagem pelo console (somente admin).

Guarda a chave cifrada no banco, permite trocar os modelos e testa a conexão
com a OpenAI em três passos: autenticação, acesso aos modelos e uma chamada
mínima com o modelo principal.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.agent.llm import test_connection
from roadie.api.deps import get_db, get_service, require_admin
from roadie.config import get_settings
from roadie.db.models import User
from roadie.llm_config import (
    delete_llm_key,
    llm_status,
    resolve_llm_config,
    save_llm_settings,
    store_last_test,
)

router = APIRouter(prefix="/admin/llm", tags=["admin"])


class LLMSettingsIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=20, max_length=400)
    primary: str | None = Field(default=None, min_length=3, max_length=80)
    fallback: str | None = Field(default=None, max_length=80)
    clear_fallback: bool = False


class LLMTestIn(BaseModel):
    api_key: str | None = Field(default=None, min_length=20, max_length=400)
    primary: str | None = Field(default=None, min_length=3, max_length=80)
    fallback: str | None = Field(default=None, max_length=80)


def _check_key_format(key: str | None) -> None:
    if key is not None and not key.startswith("sk-"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "a chave da OpenAI começa com 'sk-'")


@router.get("")
async def get_llm_settings(
    session: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
) -> dict:
    return await llm_status(session, get_settings())


@router.put("")
async def put_llm_settings(
    request: Request,
    body: LLMSettingsIn,
    session: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    _check_key_format(body.api_key)
    await save_llm_settings(
        session,
        api_key=body.api_key,
        primary=body.primary,
        fallback=body.fallback,
        clear_fallback=body.clear_fallback,
        updated_by=admin.email,
    )
    await get_service(request).reload_llm()
    return await llm_status(session, get_settings())


@router.delete("/key")
async def delete_key(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    await delete_llm_key(session)
    await get_service(request).reload_llm()
    return await llm_status(session, get_settings())


@router.post("/test")
async def test_llm(
    request: Request,
    body: LLMTestIn,
    session: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """Testa a chave informada (sem salvar) ou, se omitida, a configuração em vigor."""
    _check_key_format(body.api_key)
    service = get_service(request)
    cfg = await resolve_llm_config(service.session_factory, get_settings())
    api_key = body.api_key or cfg.api_key
    if not api_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nenhuma chave da OpenAI para testar")
    primary = body.primary or cfg.primary
    fallback = body.fallback if body.fallback is not None else cfg.fallback
    result = await test_connection(api_key, primary, fallback or None)
    result["tested_saved_config"] = body.api_key is None
    if body.api_key is None:
        await store_last_test(session, result, admin.email)
    return result
