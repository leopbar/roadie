"""Simulador de atendimento: conversas, mensagens e streaming."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from roadie.agent.llm import LLMNotConfigured
from roadie.api.deps import current_user, get_db, get_service, limiter
from roadie.api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationPatch,
    CustomerOut,
    MessageIn,
    MessageOut,
    ReplyOut,
)
from roadie.clock import get_clock
from roadie.config import get_settings
from roadie.db.models import Conversation, Customer, Message, Order, User

router = APIRouter(tags=["conversas"])


@router.get("/customers", response_model=list[CustomerOut])
async def list_customers(
    session: AsyncSession = Depends(get_db), _: User = Depends(current_user)
) -> list[dict]:
    """Clientes cadastrados, para escolher o remetente no simulador."""
    stmt = (
        select(Customer, func.count(Order.order_id))
        .outerjoin(Order, Order.customer_id == Customer.customer_id)
        .group_by(Customer.customer_id)
        .order_by(Customer.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "customer_id": c.customer_id,
            "name": c.name,
            "phone": c.phone,
            "city": c.city,
            "orders": n,
        }
        for c, n in rows
    ]


def _store_local(moment):
    """Instantes saem no fuso da loja, não em UTC, para o console mostrar como o cliente vê."""
    if moment is None:
        return None
    return moment.astimezone(get_clock().tz)


def _conversation_out(conv: Conversation, count: int = 0, last: str | None = None) -> dict:
    return {
        "id": conv.id,
        "title": conv.title,
        "channel": conv.channel,
        "sender_phone": conv.sender_phone,
        "customer_id": conv.customer_id,
        "customer_name": conv.customer.name if conv.customer else None,
        "identity_verified": conv.identity_verified,
        "verified_via": conv.verified_via,
        "clock_override": _store_local(conv.clock_override),
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": count,
        "last_message": last,
    }


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    user: User = Depends(current_user),
    service=Depends(get_service),
) -> dict:
    conv = await service.start_conversation(
        body.sender_phone, clock_override=body.clock_override, created_by_user_id=user.id
    )
    conv = await service.get_conversation(conv.id)
    return _conversation_out(conv)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> list[dict]:
    limit = max(1, min(limit, 200))
    counts = (
        select(Message.conversation_id, func.count(Message.id).label("n"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, func.coalesce(counts.c.n, 0))
        .options(selectinload(Conversation.customer))
        .outerjoin(counts, counts.c.conversation_id == Conversation.id)
        .where(Conversation.channel != "teste")
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    out = []
    for conv, n in rows:
        last = await session.scalar(
            select(Message.content)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        out.append(_conversation_out(conv, int(n), (last or "")[:140] or None))
    return out


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> dict:
    stmt = (
        select(Conversation)
        .options(selectinload(Conversation.customer), selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id)
    )
    conv = await session.scalar(stmt)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")
    data = _conversation_out(conv, len(conv.messages))
    data["messages"] = [
        MessageOut(
            id=m.id,
            role=m.role.value,
            content=m.content,
            receipt=m.receipt,
            created_at=m.created_at,
        )
        for m in conv.messages
    ]
    return data


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def patch_conversation(
    conversation_id: uuid.UUID,
    body: ConversationPatch,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
    service=Depends(get_service),
) -> dict:
    conv = await session.scalar(
        select(Conversation)
        .options(selectinload(Conversation.customer))
        .where(Conversation.id == conversation_id)
    )
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")
    if "clock_override" in body.model_fields_set:
        override = body.clock_override
        if override is not None and override.tzinfo is None:
            override = override.replace(tzinfo=service.clock.tz)
        conv.clock_override = override
    if body.title is not None:
        conv.title = body.title
    await session.commit()
    await session.refresh(conv)
    return _conversation_out(conv)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> None:
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversa não encontrada")
    await session.delete(conv)
    await session.commit()


@router.post("/conversations/{conversation_id}/messages", response_model=ReplyOut)
@limiter.limit(lambda: get_settings().rate_limit_chat)
async def send_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: MessageIn,
    _: User = Depends(current_user),
    service=Depends(get_service),
) -> dict:
    try:
        reply = await service.send(conversation_id, body.text)
    except LLMNotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return {
        "conversation_id": reply.conversation_id,
        "message_id": reply.message_id,
        "content": reply.content,
        "receipt": reply.receipt,
    }


@router.post("/conversations/{conversation_id}/messages/stream")
@limiter.limit(lambda: get_settings().rate_limit_chat)
async def stream_message(
    request: Request,
    conversation_id: uuid.UUID,
    body: MessageIn,
    _: User = Depends(current_user),
    service=Depends(get_service),
) -> EventSourceResponse:
    """Server-Sent Events: token, tool_start, tool_end, done ou error."""

    async def events():
        async for event in service.stream(conversation_id, body.text):
            yield {
                "event": event["type"],
                "data": json.dumps(event, ensure_ascii=False, default=str),
            }

    return EventSourceResponse(events(), ping=15)
