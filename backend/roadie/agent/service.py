"""Serviço de conversa: abre conversas, roda o Tom, persiste mensagens e recibos.

Usado pela CLI, pela API e pelos testes. Uma única rotina de execução serve
tanto o modo síncrono (resposta completa) quanto o streaming (eventos de
token, chamada de ferramenta e fim), para que os dois nunca divirjam.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, ToolMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from roadie.agent.context import Identity, RunContext
from roadie.agent.graph import build_graph
from roadie.agent.llm import LLMNotConfigured, ModelBundle, build_models_from_config
from roadie.agent.receipt import build_receipt, final_answer
from roadie.agent.tools import ALL_TOOLS
from roadie.clock import StoreClock, get_clock
from roadie.config import Settings, get_settings
from roadie.db.engine import get_session_factory
from roadie.db.models import Conversation, Customer, Message, MessageRole, PolicyClause
from roadie.ingest.csv_loader import only_digits
from roadie.llm_config import resolve_llm_config

EventCallback = Callable[[dict], Awaitable[None]]
HISTORY_LIMIT = 40


@dataclass
class AgentReply:
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    content: str
    receipt: dict


class TomService:
    def __init__(
        self,
        settings: Settings | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        models: ModelBundle | None = None,
        clock: StoreClock | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory or get_session_factory()
        self.clock = clock or get_clock()
        self.models: ModelBundle | None = models
        self.graph = (
            build_graph(models, ALL_TOOLS, self.settings.max_tool_rounds) if models else None
        )
        self._toc: list[tuple[str, str]] | None = None

    # ------------------------------------------------------------------ modelo
    async def ensure_models(self) -> ModelBundle:
        """Monta o modelo na primeira necessidade, lendo banco e ambiente."""
        if self.models is None:
            cfg = await resolve_llm_config(self.session_factory, self.settings)
            self.models = build_models_from_config(cfg, ALL_TOOLS)
            self.graph = (
                build_graph(self.models, ALL_TOOLS, self.settings.max_tool_rounds)
                if self.models.mode != "unconfigured"
                else None
            )
        return self.models

    async def reload_llm(self) -> ModelBundle:
        """Chamado quando a chave ou os modelos mudam pelo console."""
        self.models = None
        self.graph = None
        return await self.ensure_models()

    # ------------------------------------------------------------------ apoio
    async def policy_toc(self) -> list[tuple[str, str]]:
        if self._toc is None:
            async with self.session_factory() as session:
                stmt = select(PolicyClause.clause_id, PolicyClause.title).order_by(
                    PolicyClause.order_index
                )
                self._toc = [(cid, title) for cid, title in (await session.execute(stmt)).all()]
        return self._toc

    async def _load_conversation(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> Conversation:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.customer))
            .where(Conversation.id == conversation_id)
        )
        conv = await session.scalar(stmt)
        if conv is None:
            raise LookupError(f"conversa {conversation_id} não existe")
        return conv

    async def _history(self, session: AsyncSession, conversation_id: uuid.UUID) -> list[AnyMessage]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
        rows = list((await session.scalars(stmt)).all())[::-1]
        out: list[AnyMessage] = []
        for m in rows:
            out.append(
                HumanMessage(content=m.content)
                if m.role == MessageRole.user
                else AIMessage(content=m.content)
            )
        return out

    # ------------------------------------------------------------------ conversas
    async def start_conversation(
        self,
        sender_phone: str | None,
        *,
        clock_override: datetime | None = None,
        created_by_user_id: uuid.UUID | None = None,
        channel: str = "simulador",
    ) -> Conversation:
        digits = only_digits(sender_phone) or None
        if clock_override is not None and clock_override.tzinfo is None:
            # relógio informado sem fuso: é hora local da loja
            clock_override = clock_override.replace(tzinfo=self.clock.tz)
        async with self.session_factory() as session:
            customer = None
            if digits:
                customer = await session.scalar(
                    select(Customer).where(Customer.phone_digits == digits)
                )
            conv = Conversation(
                channel=channel,
                sender_phone=sender_phone,
                sender_phone_digits=digits,
                customer_id=customer.customer_id if customer else None,
                identity_verified=customer is not None,
                verified_via="telefone" if customer else None,
                clock_override=clock_override,
                created_by_user_id=created_by_user_id,
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            return conv

    async def get_conversation(self, conversation_id: uuid.UUID) -> Conversation:
        async with self.session_factory() as session:
            return await self._load_conversation(session, conversation_id)

    # ------------------------------------------------------------------ execução
    async def send(self, conversation_id: uuid.UUID, text: str) -> AgentReply:
        return await self._run(conversation_id, text, None)

    async def stream(self, conversation_id: uuid.UUID, text: str) -> AsyncIterator[dict]:
        """Gera eventos: token, tool_start, tool_end, done ou error."""
        import asyncio

        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def emit(event: dict) -> None:
            await queue.put(event)

        async def worker() -> None:
            try:
                reply = await self._run(conversation_id, text, emit)
                await queue.put(
                    {
                        "type": "done",
                        "message_id": str(reply.message_id),
                        "conversation_id": str(reply.conversation_id),
                        "content": reply.content,
                        "receipt": reply.receipt,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                await queue.put({"type": "error", "detail": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            if not task.done():
                task.cancel()

    async def _run(
        self, conversation_id: uuid.UUID, text: str, emit: EventCallback | None
    ) -> AgentReply:
        text = text.strip()
        if not text:
            raise ValueError("mensagem vazia")
        started = perf_counter()
        models = await self.ensure_models()
        if models.mode == "unconfigured" or self.graph is None:
            raise LLMNotConfigured(
                "Nenhuma chave da OpenAI configurada. Cadastre em Configurações no console "
                "ou defina OPENAI_API_KEY no .env."
            )
        toc = await self.policy_toc()

        async with self.session_factory() as session:
            conv = await self._load_conversation(session, conversation_id)
            history = await self._history(session, conv.id)
            user_msg = Message(conversation_id=conv.id, role=MessageRole.user, content=text)
            session.add(user_msg)
            if conv.title is None:
                conv.title = text[:80]
            await session.commit()
            identity = Identity(
                customer_id=conv.customer_id,
                name=conv.customer.name if conv.customer else None,
                city=conv.customer.city if conv.customer else None,
                verified=conv.identity_verified,
                via=conv.verified_via,
                attempts=conv.identity_attempts,
            )
            now = self.clock.now(conv.clock_override)
            sender_phone, sender_digits = conv.sender_phone, conv.sender_phone_digits

        ctx = RunContext(
            conversation_id=conversation_id,
            sender_phone=sender_phone,
            sender_phone_digits=sender_digits,
            now=now,
            identity=identity,
            session_factory=self.session_factory,
            policy_toc=toc,
        )
        config = {
            "configurable": {"ctx": ctx},
            "recursion_limit": 4 * self.settings.max_tool_rounds + 6,
        }
        state = {"messages": [*history, HumanMessage(content=text)], "rounds": 0}

        new_messages: list[AnyMessage] = []
        async for mode, payload in self.graph.astream(
            state, config, stream_mode=["messages", "updates"]
        ):
            if mode == "messages":
                chunk, _meta = payload
                if emit and isinstance(chunk, AIMessageChunk) and not chunk.tool_call_chunks:
                    piece = _chunk_text(chunk.content)
                    if piece:
                        await emit({"type": "token", "text": piece})
            elif mode == "updates":
                for _node, update in (payload or {}).items():
                    for m in (update or {}).get("messages", []) or []:
                        new_messages.append(m)
                        if emit is None:
                            continue
                        if isinstance(m, AIMessage) and m.tool_calls:
                            for call in m.tool_calls:
                                await emit(
                                    {
                                        "type": "tool_start",
                                        "id": call.get("id"),
                                        "name": call.get("name"),
                                        "args": call.get("args", {}),
                                    }
                                )
                        elif isinstance(m, ToolMessage):
                            artifact = m.artifact if isinstance(m.artifact, dict) else {}
                            await emit(
                                {
                                    "type": "tool_end",
                                    "id": m.tool_call_id,
                                    "name": m.name,
                                    "ok": artifact.get("ok", True),
                                    "summary": artifact.get("summary"),
                                    "duration_ms": artifact.get("duration_ms"),
                                }
                            )

        content = final_answer(new_messages)
        if content is None:
            raise RuntimeError("o modelo não produziu uma resposta final")
        receipt = build_receipt(
            new_messages,
            ctx=ctx,
            primary_model=self.models.primary_name,
            latency_ms=(perf_counter() - started) * 1000,
            mode=self.models.mode,
        )

        async with self.session_factory() as session:
            conv = await self._load_conversation(session, conversation_id)
            reply = Message(
                conversation_id=conv.id,
                role=MessageRole.assistant,
                content=content,
                receipt=receipt,
            )
            session.add(reply)
            conv.identity_attempts = ctx.identity.attempts
            if ctx.identity_changed and ctx.identity.verified:
                conv.customer_id = ctx.identity.customer_id
                conv.identity_verified = True
                conv.verified_via = ctx.identity.via
            await session.commit()
            await session.refresh(reply)
            return AgentReply(
                conversation_id=conv.id, message_id=reply.id, content=content, receipt=receipt
            )


def _chunk_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block
            if isinstance(block, str)
            else (
                block.get("text", "")
                if isinstance(block, dict) and block.get("type") == "text"
                else ""
            )
            for block in content
        )
    return ""
