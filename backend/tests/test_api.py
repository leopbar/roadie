"""Testes da API com o modelo simulado: autenticação, conversas, streaming e visões de operação."""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, text

from roadie.agent.llm import ModelBundle
from roadie.agent.mock_llm import MockTom
from roadie.agent.service import TomService
from roadie.api.app import create_app
from roadie.api.deps import limiter
from roadie.auth.security import hash_password
from roadie.db.engine import get_session_factory
from roadie.db.models import Product, Ticket, User, UserRole

ADMIN_EMAIL = "teste-admin@exemplo.com.br"
AGENT_EMAIL = "teste-agente@exemplo.com.br"
PASSWORD = "SenhaForte123"


@pytest.fixture(scope="module", autouse=True)
async def _db_and_users():
    factory = get_session_factory()
    try:
        async with factory() as session:
            n = await session.scalar(select(Product.product_id).limit(1))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"banco indisponível: {exc}")
    if n is None:
        pytest.skip("banco sem carga; rode `roadie seed`")
    async with factory() as session:
        await session.execute(delete(User).where(User.email.in_([ADMIN_EMAIL, AGENT_EMAIL])))
        session.add(
            User(
                email=ADMIN_EMAIL,
                name="Admin Teste",
                password_hash=hash_password(PASSWORD),
                role=UserRole.admin,
            )
        )
        session.add(
            User(
                email=AGENT_EMAIL,
                name="Agente Teste",
                password_hash=hash_password(PASSWORD),
                role=UserRole.agent,
            )
        )
        await session.commit()
    yield
    async with factory() as session:
        await session.execute(delete(Ticket).where(Ticket.summary.like("[teste-api]%")))
        await session.execute(
            text(
                "DELETE FROM conversations WHERE channel = 'simulador' AND sender_phone = '(67) 90000-0001'"
            )
        )
        await session.execute(
            delete(User).where(User.email.in_([ADMIN_EMAIL, AGENT_EMAIL, "novo@exemplo.com.br"]))
        )
        await session.commit()


@pytest.fixture(scope="module")
def app():
    limiter.enabled = False
    application = create_app()
    mock = MockTom()
    application.state.tom = TomService(
        session_factory=get_session_factory(),
        models=ModelBundle(
            with_tools=mock, plain=mock, primary_name="mock-tom", fallback_name=None, mode="mock"
        ),
    )
    yield application
    limiter.enabled = True


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def admin(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.post("/auth/login", json={"email": ADMIN_EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
async def agent(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.post("/auth/login", json={"email": AGENT_EMAIL, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


async def test_health_is_public(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_protected_routes_require_login(client):
    for path in [
        "/auth/me",
        "/conversations",
        "/customers",
        "/tickets",
        "/quality",
        "/policies",
        "/meta",
    ]:
        r = await client.get(path)
        assert r.status_code == 401, path


async def test_login_rejects_bad_credentials_without_leaking(client):
    bad_pw = await client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "errada"})
    no_user = await client.post(
        "/auth/login", json={"email": "ninguem@exemplo.com.br", "password": "errada"}
    )
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["detail"] == no_user.json()["detail"]


async def test_login_sets_httponly_cookies_and_me_works(admin):
    r = await admin.get("/auth/me")
    assert r.status_code == 200 and r.json()["role"] == "admin"
    cookies = {c.name: c for c in admin.cookies.jar}
    assert "roadie_access" in cookies and "roadie_refresh" in cookies


async def test_refresh_rotates_and_logout_revokes(admin):
    old_refresh = admin.cookies.get("roadie_refresh")
    r = await admin.post("/auth/refresh")
    assert r.status_code == 200
    assert admin.cookies.get("roadie_refresh") != old_refresh
    r = await admin.post("/auth/logout")
    assert r.status_code == 204
    r = await admin.post("/auth/refresh")
    assert r.status_code == 401


async def test_simulator_conversation_flow(agent):
    customers = await agent.get("/customers")
    assert customers.status_code == 200 and len(customers.json()) == 50

    created = await agent.post(
        "/conversations",
        json={"sender_phone": "(67) 99567-8901", "clock_override": "2026-03-24T10:00:00"},
    )
    assert created.status_code == 201, created.text
    conv = created.json()
    assert conv["identity_verified"] and conv["customer_name"] == "Camila Duarte Nascimento"

    sent = await agent.post(
        f"/conversations/{conv['id']}/messages", json={"text": "quanto custa o Taylor 110e?"}
    )
    assert sent.status_code == 200, sent.text
    reply = sent.json()
    assert reply["receipt"]["tools"][0]["name"] == "detalhar_produto"
    assert reply["receipt"]["clock"]["label"].endswith("24/03/2026 10:00")

    detail = await agent.get(f"/conversations/{conv['id']}")
    assert detail.status_code == 200
    assert [m["role"] for m in detail.json()["messages"]] == ["user", "assistant"]

    listed = await agent.get("/conversations")
    assert any(c["id"] == conv["id"] and c["message_count"] == 2 for c in listed.json())

    patched = await agent.patch(
        f"/conversations/{conv['id']}", json={"clock_override": "2026-03-29T11:00:00"}
    )
    assert patched.status_code == 200 and patched.json()["clock_override"].startswith(
        "2026-03-29T11:00:00"
    )

    deleted = await agent.delete(f"/conversations/{conv['id']}")
    assert deleted.status_code == 204
    assert (await agent.get(f"/conversations/{conv['id']}")).status_code == 404


async def test_stream_emits_sse_events(agent):
    created = await agent.post("/conversations", json={"sender_phone": "(67) 90000-0001"})
    conv_id = created.json()["id"]
    events = []
    async with agent.stream(
        "POST", f"/conversations/{conv_id}/messages/stream", json={"text": "tem promoção?"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for line in r.aiter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if line.startswith("data:") and events and events[-1] == "done":
                payload = json.loads(line.split(":", 1)[1].strip())
                assert payload["receipt"]["tools"][0]["name"] == "promocoes_ativas"
                break
    assert events[0] == "tool_start" and "tool_end" in events and events[-1] == "done"


async def test_operations_views(agent):
    q = await agent.get("/quality")
    assert q.status_code == 200
    assert q.json()["summary"]["quarantine"] == 10
    assert any(
        f["entity_label"] == "Teclado Sintetizador Korg Synth 1 Pro" for f in q.json()["flags"]
    )

    p = await agent.get("/policies")
    assert p.status_code == 200 and len(p.json()) == 29

    s = await agent.get("/policies/search", params={"q": "garantia"})
    assert s.status_code == 200 and "8.1" in [c["id"] for c in s.json()]

    # verbo e substantivo têm radicais diferentes ("devolver" x "devolução")
    s = await agent.get("/policies/search", params={"q": "posso devolver?"})
    assert s.status_code == 200 and "4.1" in [c["id"] for c in s.json()]
    s = await agent.get("/policies/search", params={"q": "como posso pagar?"})
    assert s.status_code == 200 and "3.1" in [c["id"] for c in s.json()]

    prods = await agent.get("/products", params={"q": "ukulele tenor"})
    assert prods.status_code == 200 and all("Tenor" in x["name"] for x in prods.json())

    meta = await agent.get("/meta")
    assert meta.status_code == 200 and meta.json()["model"]["mode"] == "mock"
    assert meta.json()["counts"]["products"] == 65


async def test_tickets_listed_and_updated(agent):
    created = await agent.post("/conversations", json={"sender_phone": "(67) 90000-0001"})
    conv_id = created.json()["id"]
    sent = await agent.post(
        f"/conversations/{conv_id}/messages",
        json={"text": "[teste-api] quero fazer uma reclamação"},
    )
    protocol = sent.json()["receipt"]["tickets"][0]["protocolo"]
    listed = await agent.get("/tickets")
    ticket = next(t for t in listed.json() if t["protocol"] == protocol)
    assert ticket["status"] == "aberto"
    patched = await agent.patch(f"/tickets/{ticket['id']}", json={"status": "resolvido"})
    assert patched.status_code == 200 and patched.json()["status"] == "resolvido"


async def test_admin_user_management_and_role_guard(admin, agent):
    forbidden = await agent.get("/admin/users")
    assert forbidden.status_code == 403

    weak = await admin.post(
        "/admin/users", json={"email": "novo@exemplo.com.br", "name": "Novo", "password": "fraca"}
    )
    assert weak.status_code == 400

    created = await admin.post(
        "/admin/users",
        json={
            "email": "novo@exemplo.com.br",
            "name": "Novo",
            "password": "OutraSenha123",
            "role": "agent",
        },
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    dup = await admin.post(
        "/admin/users",
        json={"email": "novo@exemplo.com.br", "name": "Novo", "password": "OutraSenha123"},
    )
    assert dup.status_code == 409

    me = (await admin.get("/auth/me")).json()
    self_delete = await admin.delete(f"/admin/users/{me['id']}")
    assert self_delete.status_code == 400

    deactivated = await admin.patch(f"/admin/users/{new_id}", json={"is_active": False})
    assert deactivated.status_code == 200 and deactivated.json()["is_active"] is False

    removed = await admin.delete(f"/admin/users/{new_id}")
    assert removed.status_code == 204
    assert (await admin.delete(f"/admin/users/{uuid.uuid4()}")).status_code == 404
