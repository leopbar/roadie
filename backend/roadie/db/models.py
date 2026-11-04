"""Modelo relacional do Roadie (PostgreSQL via SQLAlchemy 2.0).

Dois grupos de tabelas:
- Operação da loja, carregada dos CSVs e do manual: categorias, produtos,
  clientes, pedidos, itens, promoções e cláusulas de política.
- Operação do agente: usuários do console, conversas, mensagens (com recibo
  de evidências), tickets e sinalizações de qualidade de dados.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    # Enums como strings com constraint, sem tipos nativos do Postgres
    # (mais simples de evoluir e de inspecionar).
    return Enum(
        cls,
        name=name,
        native_enum=False,
        length=32,
        values_callable=lambda e: [m.value for m in e],
    )


# ----------------------------------------------------------------------------
# Enumerações
# ----------------------------------------------------------------------------
class ProductStatus(enum.StrEnum):
    active = "active"
    discontinued = "discontinued"
    coming_soon = "coming_soon"


class OrderStatus(enum.StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class UserRole(enum.StrEnum):
    admin = "admin"
    agent = "agent"


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"


class TicketCategory(enum.StrEnum):
    reclamacao = "reclamacao"
    cancelamento = "cancelamento"
    devolucao = "devolucao"
    troca = "troca"
    frete = "frete"
    cadastro = "cadastro"
    garantia = "garantia"
    outro = "outro"


class TicketStatus(enum.StrEnum):
    aberto = "aberto"
    em_andamento = "em_andamento"
    resolvido = "resolvido"


class FlagSeverity(enum.StrEnum):
    info = "info"
    warning = "warning"
    quarantine = "quarantine"


# ----------------------------------------------------------------------------
# Operação da loja
# ----------------------------------------------------------------------------
class Category(Base):
    __tablename__ = "categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(60))  # derivado do nome na ingestão
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.category_id"), nullable=False)
    price_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    stock_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[ProductStatus] = mapped_column(
        _enum(ProductStatus, "product_status"), nullable=False
    )
    specs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[date | None] = mapped_column(Date)
    # Sinalizações de qualidade detectadas na ingestão (ex.: brand_mismatch).
    quality_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    category: Mapped[Category] = relationship(back_populates="products")
    promotions: Mapped[list[Promotion]] = relationship(back_populates="product")

    @property
    def quarantined(self) -> bool:
        return bool(self.quality_flags)


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    phone_digits: Mapped[str | None] = mapped_column(String(20), index=True)  # só dígitos
    email: Mapped[str | None] = mapped_column(String(160), index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    quality_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus, "order_status"), nullable=False)
    total_brl: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(40))
    tracking_code: Mapped[str | None] = mapped_column(String(40))
    estimated_delivery: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    quality_flags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Promotion(Base):
    __tablename__ = "promotions"

    promotion_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.product_id"), nullable=False, index=True
    )
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    product: Mapped[Product] = relationship(back_populates="promotions")


class PolicyClause(Base):
    """Uma seção ou subseção do manual de políticas, extraída do PDF."""

    __tablename__ = "policy_clauses"

    clause_id: Mapped[str] = mapped_column(String(10), primary_key=True)  # ex.: "4.1"
    section: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class DataQualityFlag(Base):
    """Registro auditável de cada problema encontrado na ingestão."""

    __tablename__ = "data_quality_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity: Mapped[str] = mapped_column(String(40), nullable=False)  # product | order | customer
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    flag: Mapped[str] = mapped_column(String(60), nullable=False)
    severity: Mapped[FlagSeverity] = mapped_column(
        _enum(FlagSeverity, "flag_severity"), nullable=False
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ----------------------------------------------------------------------------
# Operação do agente
# ----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), nullable=False, default=UserRole.agent
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshSession(Base):
    """Sessões de refresh token (hash), permitindo revogação e rotação."""

    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(String(255))


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="simulador")
    sender_phone: Mapped[str | None] = mapped_column(String(32))  # número do remetente
    sender_phone_digits: Mapped[str | None] = mapped_column(String(20), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.customer_id"))
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_via: Mapped[str | None] = mapped_column(String(32))  # phone | order_email
    # tentativas de verificação que falharam, somadas em toda a conversa (limite: 3)
    identity_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    clock_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(200))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped[Customer | None] = relationship()
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Recibo de evidências: ferramentas chamadas, linhas lidas, cláusulas citadas,
    # modelo usado, tokens, latência. Só em mensagens do assistente.
    receipt: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    protocol: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)  # RD-2026-0001
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.customer_id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.order_id"))
    category: Mapped[TicketCategory] = mapped_column(
        _enum(TicketCategory, "ticket_category"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TicketStatus] = mapped_column(
        _enum(TicketStatus, "ticket_status"), nullable=False, default=TicketStatus.aberto
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppSetting(Base):
    """Configurações editáveis pelo console. Valores secretos ficam cifrados."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(String(160))
