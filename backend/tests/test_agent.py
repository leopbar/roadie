"""Testes do agente com o modelo simulado, contra o PostgreSQL carregado.

Exercitam o encanamento inteiro: identidade por telefone, ferramentas com
escopo por cliente, quarentena, políticas por busca textual, tickets,
recibos e persistência. Pulam quando o banco não está disponível.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import delete, select, text

from roadie.agent.llm import ModelBundle
from roadie.agent.mock_llm import MockTom
from roadie.agent.service import TomService
from roadie.db.engine import get_session_factory
from roadie.db.models import Message, Product, Ticket

TZ = ZoneInfo("America/Campo_Grande")
NOW = datetime(2026, 3, 24, 10, 0, tzinfo=TZ)
PHONE_CAMILA = "(67) 99567-8901"  # cliente 10, pedido 16 pendente
PHONE_UNKNOWN = "(67) 90000-0000"


@pytest.fixture(scope="module")
def service():
    factory = get_session_factory()
    mock = MockTom()
    models = ModelBundle(
        with_tools=mock, plain=mock, primary_name="mock-tom", fallback_name=None, mode="mock"
    )
    return TomService(session_factory=factory, models=models)


@pytest.fixture(scope="module", autouse=True)
async def _require_database():
    factory = get_session_factory()
    try:
        async with factory() as session:
            n = await session.scalar(select(Product.product_id).limit(1))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"banco indisponível: {exc}")
    if n is None:
        pytest.skip("banco sem carga; rode `roadie seed`")
    yield
    async with factory() as session:
        await session.execute(delete(Ticket).where(Ticket.summary.like("[teste]%")))
        await session.execute(text("DELETE FROM conversations WHERE channel = 'teste'"))
        await session.commit()


async def _conv(service: TomService, phone: str | None):
    return await service.start_conversation(phone, clock_override=NOW, channel="teste")


def _tool_names(receipt: dict) -> list[str]:
    return [t["name"] for t in receipt["tools"]]


async def test_identity_by_sender_phone(service):
    conv = await _conv(service, PHONE_CAMILA)
    assert conv.identity_verified and conv.customer_id == 10 and conv.verified_via == "telefone"
    unknown = await _conv(service, PHONE_UNKNOWN)
    assert not unknown.identity_verified and unknown.customer_id is None


async def test_catalog_search_with_price_cap(service):
    conv = await _conv(service, PHONE_CAMILA)
    reply = await service.send(conv.id, "Quais violões vocês têm até R$ 1000?")
    r = reply.receipt
    assert _tool_names(r) == ["buscar_produtos"]
    assert r["tools"][0]["args"]["preco_max"] == 1000.0
    assert "products" in r["sources"]["tables"] and r["sources"]["rows"]
    assert r["model"]["used"] == ["mock-tom"] and r["tokens"]["total"] > 0
    assert r["identity"]["name"] == "Camila Duarte Nascimento"
    assert "[simulado]" in reply.content

    # persistência: duas mensagens, recibo só na do assistente
    async with service.session_factory() as session:
        msgs = list(
            (
                await session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at)
                )
            ).all()
        )
    assert [m.role.value for m in msgs] == ["user", "assistant"]
    assert msgs[0].receipt is None and msgs[1].receipt["tools"][0]["name"] == "buscar_produtos"


async def test_quarantined_product_comes_with_notice(service):
    conv = await _conv(service, None)
    reply = await service.send(conv.id, "quanto custa o Korg Synth 1 Pro?")
    r = reply.receipt
    assert _tool_names(r) == ["detalhar_produto"]
    assert any(f.startswith("product:142:quarentena") for f in r["flags"])
    assert "aviso_cadastro" in reply.content and "quarentena" in reply.content


async def test_order_tools_are_scoped_to_identified_customer(service):
    # remetente desconhecido não vê pedido algum
    conv = await _conv(service, PHONE_UNKNOWN)
    reply = await service.send(conv.id, "qual o status do pedido 16?")
    assert _tool_names(reply.receipt) == ["consultar_pedido"]
    assert "identidade_nao_verificada" in reply.content
    assert reply.receipt["tools"][0]["result"]["ok"] is False

    # cliente identificado por telefone, mas pedido de outra pessoa
    conv2 = await _conv(service, PHONE_CAMILA)
    reply2 = await service.send(conv2.id, "qual o status do pedido 1?")
    assert "pedido_nao_encontrado_para_este_cliente" in reply2.content

    # pedido dela
    reply3 = await service.send(conv2.id, "qual o status do pedido 16?")
    assert "pendente" in reply3.content and "orders" in reply3.receipt["sources"]["tables"]


async def test_identity_verification_by_order_and_email(service):
    conv = await _conv(service, PHONE_UNKNOWN)
    bad = await service.send(conv.id, "meu pedido 8, e-mail errado@jmail.com")
    assert '"verificado": false' in bad.content
    good = await service.send(conv.id, "pedido 8, e-mail anacarol.ferreira@coldmail.com")
    assert '"verificado": true' in good.content
    assert good.receipt["identity_update"]["customer_id"] == 2
    assert good.receipt["sources"]["clauses"] == ["9"]
    # identidade persistida na conversa: próxima mensagem já consulta o pedido
    after = await service.send(conv.id, "e o pedido 8, como está?")
    assert "enviado" in after.content and after.receipt["identity"]["verified"] is True
    assert after.receipt["identity"]["via"] == "pedido+email"


async def test_identity_attempts_limit_spans_messages(service):
    conv = await _conv(service, PHONE_UNKNOWN)
    for i in range(3):
        bad = await service.send(conv.id, f"meu pedido 8, e-mail errado{i}@jmail.com")
        assert f'"tentativas_restantes": {2 - i}' in bad.content
    # o limite vale para a conversa inteira: nem o e-mail certo passa mais
    blocked = await service.send(conv.id, "pedido 8, e-mail anacarol.ferreira@coldmail.com")
    assert "limite_de_tentativas" in blocked.content
    assert blocked.receipt["identity"]["verified"] is False
    stored = await service.get_conversation(conv.id)
    assert stored.identity_attempts == 3 and not stored.identity_verified


async def test_return_evaluation_applies_policy_dates(service):
    conv = await _conv(service, PHONE_CAMILA)  # pedido 16 pendente
    reply = await service.send(conv.id, "me arrependi do pedido 16, posso devolver?")
    r = reply.receipt
    assert _tool_names(r) == ["avaliar_devolucao"]
    assert r["tools"][0]["result"]["summary"].startswith("cancelamento_antes_envio")
    assert "return_eligibility" in r["sources"]["rules"] and "4.1" in r["sources"]["clauses"]


async def test_policy_search_finds_the_right_clause(service):
    conv = await _conv(service, None)
    reply = await service.send(conv.id, "qual a política de garantia de vocês?")
    r = reply.receipt
    assert _tool_names(r) == ["consultar_politicas"]
    assert "8.1" in r["sources"]["clauses"]


async def test_store_info_and_hours(service):
    conv = await _conv(service, None)
    info = await service.send(conv.id, "qual o endereço da loja?")
    assert "Rua 14 de Maio" in info.content and "1.2" in info.receipt["sources"]["clauses"]
    hours = await service.send(conv.id, "vocês estão abertos agora?")
    assert '"is_open": true' in hours.content and hours.receipt["sources"]["rules"] == [
        "store_hours"
    ]


async def test_complaint_opens_ticket_with_protocol_and_sla(service):
    conv = await _conv(service, PHONE_CAMILA)
    reply = await service.send(
        conv.id, "[teste] quero fazer uma reclamação, meu violão chegou arranhado"
    )
    r = reply.receipt
    assert _tool_names(r) == ["abrir_ticket"]
    assert r["tickets"] and r["tickets"][0]["protocolo"].startswith("RD-2026-")
    assert "7.3" in r["sources"]["clauses"]
    async with service.session_factory() as session:
        ticket = await session.scalar(
            select(Ticket).where(Ticket.protocol == r["tickets"][0]["protocolo"])
        )
    assert ticket is not None and ticket.customer_id == 10 and ticket.conversation_id == conv.id
    assert ticket.sla_due_at.astimezone(TZ) == datetime(2026, 3, 25, 10, 0, tzinfo=TZ)


async def test_streaming_emits_tool_events_and_done(service):
    conv = await _conv(service, PHONE_CAMILA)
    events = [e async for e in service.stream(conv.id, "tem promoção?")]
    types = [e["type"] for e in events]
    assert types[0] == "tool_start" and "tool_end" in types and types[-1] == "done"
    assert events[0]["name"] == "promocoes_ativas"
    assert events[-1]["receipt"]["sources"]["clauses"] == ["6.1", "6.2"]


async def test_unknown_conversation_raises(service):
    with pytest.raises(LookupError):
        await service.send(uuid.uuid4(), "oi")
