"""Configuração efetiva do modelo de linguagem: banco por cima do ambiente.

A chave da OpenAI e os nomes dos modelos podem vir do .env ou ser cadastrados
pelo console (admin). O que está no banco prevalece. A chave é guardada
cifrada; só o sufixo fica legível, para exibição.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from roadie.auth.crypto import CryptoError, decrypt, encrypt
from roadie.config import Settings
from roadie.db.models import AppSetting

log = logging.getLogger(__name__)

KEY_API_KEY = "openai_api_key"
KEY_API_KEY_SUFFIX = "openai_api_key_suffix"
KEY_PRIMARY = "openai_model_primary"
KEY_FALLBACK = "openai_model_fallback"
KEY_LAST_TEST = "llm_last_test"
ALL_KEYS = [KEY_API_KEY, KEY_API_KEY_SUFFIX, KEY_PRIMARY, KEY_FALLBACK, KEY_LAST_TEST]


def _usable_env_key(value: str | None) -> str | None:
    if not value or value.startswith("sk-...") or len(value) < 20:
        return None
    return value


@dataclass
class LLMConfig:
    mode: str  # openai | mock
    api_key: str | None
    key_source: str | None  # banco | ambiente | None
    primary: str
    fallback: str | None
    timeout_seconds: float

    @classmethod
    def from_settings(cls, s: Settings) -> LLMConfig:
        key = _usable_env_key(s.openai_api_key)
        return cls(
            mode=s.llm_mode,
            api_key=key,
            key_source="ambiente" if key else None,
            primary=s.openai_model_primary,
            fallback=s.openai_model_fallback or None,
            timeout_seconds=s.llm_timeout_seconds,
        )


async def _rows(session: AsyncSession) -> dict[str, AppSetting]:
    stmt = select(AppSetting).where(AppSetting.key.in_(ALL_KEYS))
    return {r.key: r for r in (await session.scalars(stmt)).all()}


async def resolve_llm_config(
    session_factory: async_sessionmaker[AsyncSession], settings: Settings
) -> LLMConfig:
    cfg = LLMConfig.from_settings(settings)
    if cfg.mode == "mock":
        return cfg
    async with session_factory() as session:
        rows = await _rows(session)
    if KEY_API_KEY in rows and rows[KEY_API_KEY].value:
        try:
            cfg = replace(cfg, api_key=decrypt(rows[KEY_API_KEY].value), key_source="banco")
        except CryptoError as exc:
            log.warning("chave da OpenAI no banco ilegível: %s", exc)
    if KEY_PRIMARY in rows and rows[KEY_PRIMARY].value:
        cfg = replace(cfg, primary=rows[KEY_PRIMARY].value)
    if KEY_FALLBACK in rows:
        cfg = replace(cfg, fallback=rows[KEY_FALLBACK].value or None)
    return cfg


async def _upsert(
    session: AsyncSession, key: str, value: str | None, *, secret: bool, updated_by: str | None
) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value, is_secret=secret, updated_by=updated_by))
    else:
        row.value = value
        row.is_secret = secret
        row.updated_by = updated_by


async def save_llm_settings(
    session: AsyncSession,
    *,
    api_key: str | None = None,
    primary: str | None = None,
    fallback: str | None = None,
    clear_fallback: bool = False,
    updated_by: str | None = None,
) -> None:
    if api_key:
        await _upsert(session, KEY_API_KEY, encrypt(api_key), secret=True, updated_by=updated_by)
        await _upsert(
            session, KEY_API_KEY_SUFFIX, api_key[-4:], secret=False, updated_by=updated_by
        )
    if primary:
        await _upsert(session, KEY_PRIMARY, primary.strip(), secret=False, updated_by=updated_by)
    if clear_fallback:
        await _upsert(session, KEY_FALLBACK, None, secret=False, updated_by=updated_by)
    elif fallback:
        await _upsert(session, KEY_FALLBACK, fallback.strip(), secret=False, updated_by=updated_by)
    await session.commit()


async def delete_llm_key(session: AsyncSession) -> None:
    await session.execute(
        delete(AppSetting).where(AppSetting.key.in_([KEY_API_KEY, KEY_API_KEY_SUFFIX]))
    )
    await session.commit()


async def store_last_test(session: AsyncSession, result: dict, updated_by: str | None) -> None:
    payload = dict(result)
    payload["tested_at"] = datetime.now(UTC).isoformat()
    payload["tested_by"] = updated_by
    await _upsert(
        session,
        KEY_LAST_TEST,
        json.dumps(payload, ensure_ascii=False),
        secret=False,
        updated_by=updated_by,
    )
    await session.commit()


async def llm_status(session: AsyncSession, settings: Settings) -> dict:
    """Visão para o console: nunca inclui a chave, só se existe e de onde vem."""
    env = LLMConfig.from_settings(settings)
    rows = await _rows(session)
    db_key = KEY_API_KEY in rows and bool(rows[KEY_API_KEY].value)
    readable = True
    if db_key:
        try:
            decrypt(rows[KEY_API_KEY].value)
        except CryptoError:
            readable = False
    source = "banco" if db_key and readable else ("ambiente" if env.api_key else None)
    suffix = None
    if source == "banco":
        suffix = rows.get(KEY_API_KEY_SUFFIX).value if rows.get(KEY_API_KEY_SUFFIX) else None
    elif source == "ambiente":
        suffix = env.api_key[-4:]  # type: ignore[index]
    last_test = None
    if rows.get(KEY_LAST_TEST) and rows[KEY_LAST_TEST].value:
        try:
            last_test = json.loads(rows[KEY_LAST_TEST].value)
        except json.JSONDecodeError:
            last_test = None
    return {
        "mode": env.mode,
        "key": {
            "configured": source is not None,
            "source": source,
            "suffix": suffix,
            "unreadable": db_key and not readable,
        },
        "primary": (
            rows.get(KEY_PRIMARY).value
            if rows.get(KEY_PRIMARY) and rows[KEY_PRIMARY].value
            else env.primary
        ),
        "fallback": (rows[KEY_FALLBACK].value if KEY_FALLBACK in rows else env.fallback),
        "env_defaults": {"primary": env.primary, "fallback": env.fallback},
        "last_test": last_test,
        "updated_at": max((r.updated_at for r in rows.values() if r.updated_at), default=None),
    }
