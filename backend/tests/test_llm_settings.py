"""Configuração do modelo pelo console: cifra, precedência banco > ambiente, teste de conexão."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from roadie.agent.service import TomService
from roadie.api.app import create_app
from roadie.api.deps import limiter
from roadie.api.routers import llm as llm_router
from roadie.auth.crypto import CryptoError, decrypt, encrypt
from roadie.auth.security import hash_password
from roadie.config import get_settings
from roadie.db.engine import get_session_factory
from roadie.db.models import AppSetting, Product, User, UserRole
from roadie.llm_config import ALL_KEYS, LLMConfig, resolve_llm_config

ADMIN_EMAIL = "teste-llm-admin@exemplo.com.br"
PASSWORD = "SenhaForte123"
FAKE_KEY = "sk-test-chave-de-teste-nao-real-0123456789"


def test_crypto_roundtrip_and_tamper_detection():
    token = encrypt("sk-segredo")
    assert token != "sk-segredo" and decrypt(token) == "sk-segredo"
    with pytest.raises(CryptoError):
        decrypt(token[:-3] + "abc")


def test_env_placeholder_key_is_ignored():
    s = get_settings().model_copy(update={"openai_api_key": "sk-...", "llm_mode": "openai"})
    cfg = LLMConfig.from_settings(s)
    assert cfg.api_key is None and cfg.key_source is None
    s2 = s.model_copy(update={"openai_api_key": "sk-uma-chave-com-tamanho-suficiente-123"})
    assert LLMConfig.from_settings(s2).key_source == "ambiente"


@pytest.fixture(scope="module", autouse=True)
async def _db_state():
    factory = get_session_factory()
    try:
        async with factory() as session:
            n = await session.scalar(select(Product.product_id).limit(1))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"banco indisponível: {exc}")
    if n is None:
        pytest.skip("banco sem carga; rode `roadie seed`")
    # preserva o que o usuário já tiver configurado e restaura no fim
    async with factory() as session:
        saved = [
            (r.key, r.value, r.is_secret, r.updated_by)
            for r in (
                await session.scalars(select(AppSetting).where(AppSetting.key.in_(ALL_KEYS)))
            ).all()
        ]
        await session.execute(delete(AppSetting).where(AppSetting.key.in_(ALL_KEYS)))
        await session.execute(delete(User).where(User.email == ADMIN_EMAIL))
        session.add(
            User(
                email=ADMIN_EMAIL,
                name="Admin LLM",
                password_hash=hash_password(PASSWORD),
                role=UserRole.admin,
            )
        )
        await session.commit()
    yield
    async with factory() as session:
        await session.execute(delete(AppSetting).where(AppSetting.key.in_(ALL_KEYS)))
        for key, value, is_secret, updated_by in saved:
            session.add(
                AppSetting(key=key, value=value, is_secret=is_secret, updated_by=updated_by)
            )
        await session.execute(delete(User).where(User.email == ADMIN_EMAIL))
        await session.commit()


@pytest.fixture(scope="module")
def app():
    limiter.enabled = False
    application = create_app()
    # serviço sem modelo pré-montado: resolve banco + ambiente na primeira necessidade
    application.state.tom = TomService(session_factory=get_session_factory())
    yield application
    limiter.enabled = True


@pytest.fixture
async def admin(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


async def test_settings_lifecycle_with_connection_test(app, admin, monkeypatch):
    settings = get_settings()
    if settings.llm_mode == "mock":
        pytest.skip("LLM_MODE=mock no ambiente")

    before = (await admin.get("/admin/llm")).json()
    env_has_key = before["key"]["source"] == "ambiente"

    bad = await admin.put("/admin/llm", json={"api_key": "chave-sem-prefixo-esperado-123456"})
    assert bad.status_code == 400

    saved = await admin.put(
        "/admin/llm",
        json={"api_key": FAKE_KEY, "primary": "gpt-6.1-terra", "fallback": "gpt-6-luna"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["key"] == {
        "configured": True,
        "source": "banco",
        "suffix": FAKE_KEY[-4:],
        "unreadable": False,
    }
    assert saved.json()["primary"] == "gpt-6.1-terra"

    cfg = await resolve_llm_config(get_session_factory(), settings)
    assert cfg.api_key == FAKE_KEY and cfg.key_source == "banco"

    meta = await admin.get("/meta")
    assert meta.json()["model"] == {
        "mode": "openai",
        "primary": "gpt-6.1-terra",
        "fallback": "gpt-6-luna",
        "configured": True,
        "key_source": "banco",
    }

    calls: list[tuple] = []

    async def fake_test(api_key, primary, fallback, timeout=25.0):
        calls.append((api_key, primary, fallback))
        return {
            "ok": True,
            "steps": [{"step": "autenticacao", "ok": True, "detail": "simulado"}],
            "warnings": [],
            "latency_ms": 12,
        }

    monkeypatch.setattr(llm_router, "test_connection", fake_test)
    tested = await admin.post("/admin/llm/test", json={})
    assert (
        tested.status_code == 200 and tested.json()["ok"] and tested.json()["tested_saved_config"]
    )
    assert calls[-1] == (FAKE_KEY, "gpt-6.1-terra", "gpt-6-luna")
    status = (await admin.get("/admin/llm")).json()
    assert status["last_test"]["ok"] and status["last_test"]["tested_by"] == ADMIN_EMAIL

    unsaved = await admin.post(
        "/admin/llm/test", json={"api_key": "sk-outra-chave-so-para-testar-1234567"}
    )
    assert unsaved.status_code == 200 and not unsaved.json()["tested_saved_config"]
    assert calls[-1][0] == "sk-outra-chave-so-para-testar-1234567"

    removed = await admin.delete("/admin/llm/key")
    assert removed.status_code == 200
    assert removed.json()["key"]["source"] == ("ambiente" if env_has_key else None)

    if not env_has_key:
        conv = await admin.post("/conversations", json={"sender_phone": "(67) 99567-8901"})
        reply = await admin.post(
            f"/conversations/{conv.json()['id']}/messages", json={"text": "oi"}
        )
        assert reply.status_code == 503 and "Configurações" in reply.json()["detail"]
        no_key = await admin.post("/admin/llm/test", json={})
        assert no_key.status_code == 400
        await admin.delete(f"/conversations/{conv.json()['id']}")


async def test_non_admin_cannot_touch_llm_settings(app):
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(User).where(User.email == "teste-llm-agente@exemplo.com.br"))
        session.add(
            User(
                email="teste-llm-agente@exemplo.com.br",
                name="Agente",
                password_hash=hash_password(PASSWORD),
                role=UserRole.agent,
            )
        )
        await session.commit()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
            await c.post(
                "/auth/login",
                json={"email": "teste-llm-agente@exemplo.com.br", "password": PASSWORD},
            )
            assert (await c.get("/admin/llm")).status_code == 403
            assert (await c.post("/admin/llm/test", json={})).status_code == 403
    finally:
        async with factory() as session:
            await session.execute(
                delete(User).where(User.email == "teste-llm-agente@exemplo.com.br")
            )
            await session.commit()
