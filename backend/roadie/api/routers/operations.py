"""Visões de operação do console: tickets, qualidade de dados, políticas, catálogo e meta."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from roadie import __version__
from roadie.agent import catalog
from roadie.api.deps import current_user, get_db, get_service
from roadie.api.schemas import (
    ClauseHit,
    ClauseOut,
    MetaOut,
    ProductOut,
    QualityOut,
    TicketOut,
    TicketPatch,
)
from roadie.config import get_settings
from roadie.db.models import (
    Customer,
    DataQualityFlag,
    Order,
    PolicyClause,
    Product,
    Ticket,
    TicketStatus,
    User,
)
from roadie.policy.search import all_clauses, search_clauses
from roadie.textfmt import brl

router = APIRouter(tags=["operação"])


# ---------------------------------------------------------------- tickets
def _ticket_out(t: Ticket, customer_name: str | None) -> dict:
    return {
        "id": t.id,
        "protocol": t.protocol,
        "category": t.category.value,
        "status": t.status.value,
        "summary": t.summary,
        "customer_id": t.customer_id,
        "customer_name": customer_name,
        "order_id": t.order_id,
        "conversation_id": t.conversation_id,
        "sla_due_at": t.sla_due_at,
        "created_at": t.created_at,
    }


@router.get("/tickets", response_model=list[TicketOut])
async def list_tickets(
    status_filter: str | None = None,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> list[dict]:
    stmt = select(Ticket, Customer.name).outerjoin(
        Customer, Customer.customer_id == Ticket.customer_id
    )
    if status_filter:
        stmt = stmt.where(Ticket.status == TicketStatus(status_filter))
    stmt = stmt.order_by(Ticket.created_at.desc()).limit(200)
    return [_ticket_out(t, name) for t, name in (await session.execute(stmt)).all()]


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def patch_ticket(
    ticket_id: int,
    body: TicketPatch,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> dict:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ticket não encontrado")
    ticket.status = TicketStatus(body.status)
    await session.commit()
    name = (
        await session.scalar(
            select(Customer.name).where(Customer.customer_id == ticket.customer_id)
        )
        if ticket.customer_id
        else None
    )
    return _ticket_out(ticket, name)


# ---------------------------------------------------------------- qualidade
@router.get("/quality", response_model=QualityOut)
async def quality(session: AsyncSession = Depends(get_db), _: User = Depends(current_user)) -> dict:
    flags = list(
        (await session.scalars(select(DataQualityFlag).order_by(DataQualityFlag.id))).all()
    )
    products = {str(p.product_id): p.name for p in (await session.scalars(select(Product))).all()}
    customers = {
        str(c.customer_id): c.name for c in (await session.scalars(select(Customer))).all()
    }
    summary: dict[str, int] = {"quarantine": 0, "warning": 0, "info": 0}
    out = []
    for f in flags:
        summary[f.severity.value] = summary.get(f.severity.value, 0) + 1
        label = None
        if f.entity == "product":
            label = products.get(f.entity_id)
        elif f.entity == "customer":
            label = customers.get(f.entity_id)
        elif f.entity == "order":
            label = f"pedido {f.entity_id}"
        elif f.entity == "category":
            label = f"categoria {f.entity_id}"
        out.append(
            {
                "id": f.id,
                "entity": f.entity,
                "entity_id": f.entity_id,
                "entity_label": label,
                "flag": f.flag,
                "severity": f.severity.value,
                "detail": f.detail,
            }
        )
    return {"summary": summary, "flags": out}


# ---------------------------------------------------------------- políticas
@router.get("/policies", response_model=list[ClauseOut])
async def policies(
    session: AsyncSession = Depends(get_db), _: User = Depends(current_user)
) -> list[PolicyClause]:
    return await all_clauses(session)


@router.get("/policies/search", response_model=list[ClauseHit])
async def policies_search(
    q: str, session: AsyncSession = Depends(get_db), _: User = Depends(current_user)
) -> list[dict]:
    if not q.strip():
        return []
    return await search_clauses(session, q)


# ---------------------------------------------------------------- catálogo
@router.get("/products", response_model=list[ProductOut])
async def products(
    q: str | None = None,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> list[dict]:
    if q:
        cat_ids, terms = catalog.split_terms(q)
        rows = await catalog.search_products(
            session, terms=terms, category_ids=cat_ids, apenas_disponiveis=False, limite=100
        )
    else:
        stmt = (
            select(Product)
            .options(selectinload(Product.promotions), selectinload(Product.category))
            .order_by(Product.category_id, Product.price_brl)
        )
        rows = list((await session.scalars(stmt)).all())
    out = []
    for p in rows:
        _, label = catalog.availability(p)
        quote = catalog.price_quote(p)
        out.append(
            {
                "product_id": p.product_id,
                "name": p.name,
                "brand": p.brand,
                "category": p.category.name if p.category else None,
                "price_brl": brl(p.price_brl),
                "stock_quantity": p.stock_quantity,
                "status": p.status.value,
                "availability": label,
                "promotion": (
                    {
                        "description": quote.promo_description,
                        "percent": str(quote.promo_percent),
                        "price": brl(quote.promo_price),
                    }
                    if quote.promo_price
                    else None
                ),
                "quality": catalog.quality_notice(p),
            }
        )
    return out


# ---------------------------------------------------------------- meta
@router.get("/meta", response_model=MetaOut)
async def meta(
    request: Request, session: AsyncSession = Depends(get_db), _: User = Depends(current_user)
) -> dict:
    s = get_settings()
    service = get_service(request)
    now = service.clock.now()
    counts = {
        "products": await session.scalar(select(func.count(Product.product_id))) or 0,
        "customers": await session.scalar(select(func.count(Customer.customer_id))) or 0,
        "orders": await session.scalar(select(func.count(Order.order_id))) or 0,
        "clauses": await session.scalar(select(func.count(PolicyClause.clause_id))) or 0,
        "tickets_open": await session.scalar(
            select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.aberto)
        )
        or 0,
    }
    return {
        "version": __version__,
        "env": s.app_env,
        "clock": {
            "default_now": now.isoformat(),
            "label": service.clock.describe(now),
            "simulated": service.clock.is_simulated,
            "timezone": s.store_timezone,
        },
        "model": {
            "mode": service.models.mode,
            "primary": service.models.primary_name,
            "fallback": service.models.fallback_name,
        },
        "counts": counts,
    }
