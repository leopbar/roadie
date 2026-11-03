"""Contexto de execução de uma rodada do agente.

Tudo o que as ferramentas precisam saber e que o modelo de linguagem não
pode inventar: quem é o cliente, que horas são, em que conversa estamos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@dataclass
class Identity:
    customer_id: int | None = None
    name: str | None = None
    city: str | None = None
    verified: bool = False
    via: str | None = None  # telefone | pedido+email | pedido+telefone
    attempts: int = 0

    @property
    def first_name(self) -> str | None:
        return self.name.split()[0] if self.name else None

    def as_dict(self) -> dict:
        return {
            "customer_id": self.customer_id,
            "name": self.name,
            "city": self.city,
            "verified": self.verified,
            "via": self.via,
        }


@dataclass
class RunContext:
    conversation_id: uuid.UUID
    sender_phone: str | None
    sender_phone_digits: str | None
    now: datetime
    identity: Identity
    session_factory: async_sessionmaker[AsyncSession]
    policy_toc: list[tuple[str, str]] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)
    identity_changed: bool = False


def ctx_from_config(config: RunnableConfig | None) -> RunContext:
    try:
        return config["configurable"]["ctx"]  # type: ignore[index]
    except (KeyError, TypeError) as exc:  # pragma: no cover - erro de programação
        raise RuntimeError("RunContext ausente em config['configurable']['ctx']") from exc
