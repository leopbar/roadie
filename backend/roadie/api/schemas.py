"""Contratos de entrada e saída da API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------- auth / users
class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=1, max_length=200)
    role: Literal["admin", "agent"] = "agent"


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["admin", "agent"] | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ---------------------------------------------------------------- conversas
class ConversationCreate(BaseModel):
    sender_phone: str | None = Field(default=None, max_length=32)
    clock_override: datetime | None = None


class ConversationPatch(BaseModel):
    clock_override: datetime | None = None
    title: str | None = Field(default=None, max_length=200)


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    receipt: dict[str, Any] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str | None
    channel: str
    sender_phone: str | None
    customer_id: int | None
    customer_name: str | None
    identity_verified: bool
    verified_via: str | None
    clock_override: datetime | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message: str | None = None


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = []


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ReplyOut(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    content: str
    receipt: dict[str, Any]


# ---------------------------------------------------------------- loja
class CustomerOut(BaseModel):
    customer_id: int
    name: str
    phone: str | None
    city: str | None
    orders: int = 0


class ProductOut(BaseModel):
    product_id: int
    name: str
    brand: str | None
    category: str | None
    price_brl: str
    stock_quantity: int
    status: str
    availability: str
    promotion: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None


class TicketOut(BaseModel):
    id: int
    protocol: str
    category: str
    status: str
    summary: str
    customer_id: int | None
    customer_name: str | None
    order_id: int | None
    conversation_id: uuid.UUID | None
    sla_due_at: datetime | None
    created_at: datetime


class TicketPatch(BaseModel):
    status: Literal["aberto", "em_andamento", "resolvido"]


class FlagOut(BaseModel):
    id: int
    entity: str
    entity_id: str
    entity_label: str | None
    flag: str
    severity: str
    detail: str


class QualityOut(BaseModel):
    summary: dict[str, int]
    flags: list[FlagOut]


class ClauseOut(BaseModel):
    clause_id: str
    section: int
    title: str
    body: str
    page: int | None


class ClauseHit(BaseModel):
    id: str
    titulo: str
    texto: str
    rank: float


class MetaOut(BaseModel):
    version: str
    env: str
    clock: dict[str, Any]
    model: dict[str, Any]
    counts: dict[str, int]
