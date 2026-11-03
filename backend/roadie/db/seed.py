"""Carga do banco a partir dos CSVs e do manual, com as sinalizações de qualidade."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from roadie.db.models import (
    Category,
    Customer,
    DataQualityFlag,
    Order,
    OrderItem,
    PolicyClause,
    Product,
    Promotion,
)
from roadie.ingest.csv_loader import Dataset, load_dataset
from roadie.ingest.policy_pdf import ClauseDraft, find_policy_pdf, load_policy_clauses
from roadie.ingest.quality import Flag, brand_of, group_flags, run_all

STORE_TABLES = [
    "order_items",
    "orders",
    "promotions",
    "products",
    "categories",
    "customers",
    "policy_clauses",
    "data_quality_flags",
]


@dataclass
class SeedReport:
    counts: dict[str, int] = field(default_factory=dict)
    flags_by_severity: dict[str, int] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    clauses: int = 0


async def is_empty(session: AsyncSession) -> bool:
    total = await session.scalar(select(func.count(Product.product_id)))
    return (total or 0) == 0


async def truncate_store_tables(session: AsyncSession) -> None:
    await session.execute(text(f"TRUNCATE {', '.join(STORE_TABLES)} RESTART IDENTITY CASCADE"))


async def seed_database(
    session: AsyncSession,
    dataset: Dataset,
    clauses: list[ClauseDraft],
    flags: list[Flag],
) -> SeedReport:
    grouped = group_flags(flags)

    session.add_all(
        Category(category_id=c.category_id, name=c.name, description=c.description)
        for c in dataset.categories
    )
    session.add_all(
        Customer(
            customer_id=c.customer_id,
            name=c.name,
            phone=c.phone,
            phone_digits=c.phone_digits,
            email=c.email,
            city=c.city,
            quality_flags=grouped.get(("customer", str(c.customer_id)), []),
        )
        for c in dataset.customers
    )
    session.add_all(
        Product(
            product_id=p.product_id,
            name=p.name,
            brand=brand_of(p.name),
            category_id=p.category_id,
            price_brl=p.price_brl,
            description=p.description,
            stock_quantity=p.stock_quantity,
            status=p.status,
            specs=p.specs,
            created_at=p.created_at,
            quality_flags=grouped.get(("product", str(p.product_id)), []),
        )
        for p in dataset.products
    )
    await session.flush()

    session.add_all(
        Order(
            order_id=o.order_id,
            customer_id=o.customer_id,
            order_date=o.order_date,
            status=o.status,
            total_brl=o.total_brl,
            payment_method=o.payment_method,
            tracking_code=o.tracking_code,
            estimated_delivery=o.estimated_delivery,
            notes=o.notes,
            quality_flags=grouped.get(("order", str(o.order_id)), []),
        )
        for o in dataset.orders
    )
    await session.flush()
    session.add_all(
        OrderItem(order_id=i.order_id, product_id=i.product_id, quantity=i.quantity)
        for i in dataset.order_items
    )
    session.add_all(
        Promotion(
            promotion_id=pr.promotion_id,
            product_id=pr.product_id,
            discount_percent=pr.discount_percent,
            description=pr.description,
            is_active=pr.is_active,
        )
        for pr in dataset.promotions
    )
    session.add_all(
        PolicyClause(
            clause_id=c.clause_id,
            section=c.section,
            title=c.title,
            body=c.body,
            page=c.page,
            order_index=c.order_index,
        )
        for c in clauses
    )
    session.add_all(
        DataQualityFlag(
            entity=f.entity,
            entity_id=f.entity_id,
            flag=f.flag,
            severity=f.severity,
            detail=f.detail,
        )
        for f in flags
    )
    await session.flush()

    report = SeedReport(
        counts=dataset.counts(), sources={k: v.name for k, v in dataset.sources.items()}
    )
    report.clauses = len(clauses)
    for f in flags:
        report.flags_by_severity[f.severity.value] = (
            report.flags_by_severity.get(f.severity.value, 0) + 1
        )
    return report


def prepare(data_dir: Path) -> tuple[Dataset, list[ClauseDraft], list[Flag]]:
    """Lê tudo do disco e roda as checagens, sem tocar no banco."""
    dataset = load_dataset(data_dir)
    clauses = load_policy_clauses(find_policy_pdf(data_dir))
    flags = run_all(dataset)
    return dataset, clauses, flags
