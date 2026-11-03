"""Consultas ao catálogo e aos pedidos usadas pelas ferramentas do agente.

Tudo que o modelo de linguagem "sabe" sobre produtos e pedidos passa por aqui,
com SQL parametrizado. O modelo nunca escreve SQL.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from roadie.db.models import Category, Order, OrderItem, Product, ProductStatus, Promotion
from roadie.ingest.quality import worst_severity
from roadie.policy import rules
from roadie.textfmt import brl, pct

# ----------------------------------------------------------------------------
# Categorias: o cliente fala "violão", o banco diz "Violões"
# ----------------------------------------------------------------------------
CATEGORY_ALIASES: dict[str, list[int]] = {
    "guitarra": [1],
    "guitarras": [1],
    "eletrica": [1],
    "eletricas": [1],
    "stratocaster": [1],
    "telecaster": [1],
    "les paul": [1],
    "baixo": [2],
    "baixos": [2],
    "contrabaixo": [2],
    "contrabaixos": [2],
    "bass": [2],
    "bateria": [3],
    "baterias": [3],
    "percussao": [3],
    "bumbo": [3],
    "caixa": [3],
    "teclado": [4],
    "teclados": [4],
    "piano": [4],
    "pianos": [4],
    "sintetizador": [4],
    "sintetizadores": [4],
    "synth": [4],
    "midi": [4],
    "arranjador": [4],
    "violao": [5],
    "violoes": [5],
    "folk": [5],
    "classico": [5],
    "dreadnought": [5],
    "eletroacustico": [5, 9],
    "acustico": [5],
    "sopro": [6, 7],
    "sopros": [6, 7],
    "madeira": [6],
    "madeiras": [6],
    "flauta": [6],
    "flautas": [6],
    "clarinete": [6],
    "saxofone": [6],
    "sax": [6],
    "oboe": [6],
    "metal": [7],
    "metais": [7],
    "trompete": [7],
    "trombone": [7],
    "tuba": [7],
    "trompa": [7],
    "orquestral": [8],
    "orquestrais": [8],
    "violino": [8],
    "violinos": [8],
    "viola": [8],
    "violoncelo": [8],
    "cello": [8],
    "ukulele": [9],
    "ukuleles": [9],
    "uke": [9],
    "ukelele": [9],
}

STATUS_LABELS = {
    "pending": "pendente (aguardando confirmação do pagamento)",
    "confirmed": "confirmado (pagamento ok, em preparação)",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}

LARGE_CATEGORIES = {2, 3, 4}  # contrabaixos, baterias, pianos digitais: frete especial


def normalize(text: str | None) -> str:
    s = unicodedata.normalize("NFD", (text or "").lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def resolve_category_ids(text: str | None) -> list[int]:
    norm = normalize(text)
    if not norm:
        return []
    ids: list[int] = []
    for alias, cids in CATEGORY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", norm):
            ids.extend(c for c in cids if c not in ids)
    return ids


SEARCH_STOPWORDS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "com",
    "sem",
    "para",
    "pra",
    "um",
    "uma",
    "uns",
    "umas",
    "o",
    "a",
    "os",
    "as",
    "e",
    "ou",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "que",
    "qual",
    "quais",
    "quanto",
    "quanta",
    "custa",
    "custam",
    "preco",
    "valor",
    "voces",
    "vcs",
    "voce",
    "vc",
    "tem",
    "ter",
    "tenho",
    "ate",
    "reais",
    "por",
    "mais",
    "menos",
    "barato",
    "barata",
    "baratos",
    "caro",
    "cara",
    "opcoes",
    "opcao",
    "disponivel",
    "disponiveis",
    "quero",
    "queria",
    "gostaria",
    "procuro",
    "procurando",
    "preciso",
    "algum",
    "alguma",
    "alguns",
    "algumas",
    "sao",
    "esta",
    "estao",
    "existe",
    "existem",
    "ha",
    "me",
    "mim",
    "meu",
    "minha",
    "eu",
    "ola",
    "oi",
    "bom",
    "dia",
    "tarde",
    "noite",
    "favor",
    "pfv",
    "ai",
    "la",
    "aqui",
    "vende",
    "vendem",
    "trabalha",
    "trabalham",
    "modelo",
    "modelos",
    "instrumento",
    "instrumentos",
    "loja",
    "estoque",
}


def split_terms(termo: str | None) -> tuple[list[int], list[str]]:
    """Separa palavras que nomeiam categoria das que descrevem o produto.

    Palavras de ligação, verbos de pergunta e números (preços) são descartados:
    o modelo pode mandar a frase inteira do cliente e a busca continua útil.
    """
    cat_ids: list[int] = []
    rest: list[str] = []
    for word in re.findall(r"[\w\-]+", normalize(termo)):
        if word in CATEGORY_ALIASES:
            cat_ids.extend(c for c in CATEGORY_ALIASES[word] if c not in cat_ids)
        elif word not in SEARCH_STOPWORDS and len(word) > 1 and not word.replace("-", "").isdigit():
            rest.append(word)
    return cat_ids, rest


def payment_label(method: str | None) -> str:
    if not method:
        return "não informado"
    m = re.fullmatch(r"credit_(\d+)x", method)
    if m:
        return f"cartão de crédito em {m.group(1)}x"
    return {
        "pix": "PIX",
        "boleto": "boleto bancário",
        "debit": "cartão de débito",
        "credit": "cartão de crédito",
    }.get(method, method)


# ----------------------------------------------------------------------------
# Produtos
# ----------------------------------------------------------------------------
def active_promotion(p: Product) -> Promotion | None:
    active = [pr for pr in p.promotions if pr.is_active]
    return max(active, key=lambda pr: pr.discount_percent) if active else None


def price_quote(p: Product) -> rules.PriceQuote:
    promo = active_promotion(p)
    if promo:
        return rules.quote_price(p.price_brl, promo.discount_percent, promo.description)
    return rules.quote_price(p.price_brl)


def effective_price(p: Product) -> Decimal:
    promo = active_promotion(p)
    if promo:
        return rules.quote_price(p.price_brl, promo.discount_percent, promo.description).promo_price  # type: ignore[return-value]
    return p.price_brl


def availability(p: Product) -> tuple[str, str]:
    if p.status == ProductStatus.discontinued:
        return "descontinuado", "descontinuado (não faz mais parte do catálogo)"
    if p.status == ProductStatus.coming_soon:
        return "em_breve", "em breve (pré-venda, sem data confirmada de chegada)"
    if p.stock_quantity > 0:
        return "disponivel", f"disponível ({p.stock_quantity} un. em estoque)"
    return "esgotado", "esgotado no momento"


def quality_notice(p: Product) -> dict | None:
    flags = list(p.quality_flags or [])
    if not flags:
        return None
    worst = worst_severity(flags)
    if worst is None or worst.value == "info":
        return None
    details = [f["detail"] for f in flags if f["severity"] in ("quarantine", "warning")]
    if worst.value == "quarantine":
        return {
            "nivel": "quarentena",
            "divergencias": details,
            "instrucao": (
                "NÃO afirme preço nem especificações deste produto. Diga que o cadastro está com "
                "divergência, que a equipe vai confirmar, e ofereça abrir um ticket."
            ),
        }
    return {
        "nivel": "atencao",
        "divergencias": details,
        "instrucao": "Pode informar, com a ressalva de que o cadastro tem uma inconsistência menor.",
    }


def _strings_label(p: Product) -> str | None:
    s = (p.specs or {}).get("strings")
    if s in ("nylon", "steel"):
        return "nylon" if s == "nylon" else "aço"
    if s and str(s).isdigit():
        return f"{s} cordas"
    return None


def product_card(p: Product) -> dict:
    code, label = availability(p)
    quote = price_quote(p)
    card = {
        "id": p.product_id,
        "nome": p.name,
        "marca": p.brand,
        "categoria": p.category.name if p.category else None,
        "preco_tabela": brl(p.price_brl),
        "preco_pix": brl(quote.cash_price) if not quote.promo_price else None,
        "promocao": (
            {
                "descricao": quote.promo_description,
                "desconto": pct(quote.promo_percent),
                "preco_promocional": brl(quote.promo_price),
                "observacao": "sem desconto adicional de PIX",
            }
            if quote.promo_price
            else None
        ),
        "disponibilidade": label,
        "cordas": _strings_label(p),
        "eletronica": {"yes": "sim", "no": "não"}.get(
            str((p.specs or {}).get("electronics")), None
        ),
    }
    notice = quality_notice(p)
    if notice:
        card["aviso_cadastro"] = notice
    return {k: v for k, v in card.items() if v is not None}


def product_detail(p: Product, alternatives: list[Product]) -> dict:
    quote = price_quote(p)
    plan = rules.installment_plan(quote.cash_price if quote.promo_price else p.price_brl)
    best = next((o for o in reversed(plan.options) if o.allowed), None)
    detail = product_card(p)
    detail.update(
        {
            "descricao": p.description,
            "especificacoes": p.specs,
            "parcelamento": {
                "maximo": f"{plan.max_installments}x sem juros"
                + (f" de {brl(best.amount)}" if best and best.n > 1 else ""),
                "combinar_pagamentos": plan.combo_allowed,
            },
            "frete_especial": p.category_id in LARGE_CATEGORIES,
            "cadastrado_em": p.created_at.isoformat() if p.created_at else None,
        }
    )
    if alternatives:
        detail["alternativas"] = [product_card(a) for a in alternatives]
    return detail


async def search_products(
    session: AsyncSession,
    *,
    terms: list[str] | None = None,
    category_ids: list[int] | None = None,
    preco_min: Decimal | None = None,
    preco_max: Decimal | None = None,
    cordas: str | None = None,
    eletronica: bool | None = None,
    apenas_disponiveis: bool = True,
    limite: int = 8,
) -> list[Product]:
    stmt = select(Product).options(selectinload(Product.promotions), selectinload(Product.category))
    if category_ids:
        stmt = stmt.where(Product.category_id.in_(category_ids))
    if preco_min is not None:
        stmt = stmt.where(Product.price_brl >= preco_min)
    if preco_max is not None:
        # margem para promoções: o filtro final é pelo preço efetivo, em Python
        stmt = stmt.where(Product.price_brl <= preco_max / Decimal("0.6"))
    if cordas:
        stmt = stmt.where(
            Product.specs["strings"].astext
            == ("steel" if normalize(cordas) in ("aco", "steel") else "nylon")
        )
    if eletronica is not None:
        stmt = stmt.where(Product.specs["electronics"].astext == ("yes" if eletronica else "no"))
    if apenas_disponiveis:
        stmt = stmt.where(Product.status == ProductStatus.active, Product.stock_quantity > 0)

    terms = [normalize(t) for t in (terms or []) if t]
    base = stmt
    if terms:
        haystack = func.unaccent(
            func.lower(
                Product.name
                + " "
                + func.coalesce(Product.description, "")
                + " "
                + func.coalesce(Product.brand, "")
            )
        )
        # Pontuação: quantos termos casam (OR, não AND) + similaridade do nome
        # (tolera erros de digitação como "Takamini").
        hits = [case((haystack.like(f"%{t}%"), 1), else_=0) for t in terms]
        score = hits[0]
        for h in hits[1:]:
            score = score + h
        similarity = func.similarity(func.unaccent(func.lower(Product.name)), " ".join(terms))
        stmt = stmt.where(or_(score > 0, similarity > 0.3)).order_by(
            score.desc(), similarity.desc(), Product.price_brl
        )
    else:
        stmt = stmt.order_by(Product.price_brl)

    rows = list((await session.scalars(stmt)).all())
    if not rows and terms and category_ids:
        # Os termos não casaram com nada, mas a categoria sim: devolve a categoria.
        rows = list((await session.scalars(base.order_by(Product.price_brl))).all())
    if preco_max is not None:
        rows = [p for p in rows if effective_price(p) <= preco_max]
    return rows[:limite]


async def find_product(
    session: AsyncSession, produto_id: int | None, nome: str | None
) -> Product | None:
    if produto_id is not None:
        stmt = (
            select(Product)
            .options(selectinload(Product.promotions), selectinload(Product.category))
            .where(Product.product_id == produto_id)
        )
        return await session.scalar(stmt)
    if nome:
        _, terms = split_terms(nome)
        found = await search_products(
            session, terms=terms or [normalize(nome)], apenas_disponiveis=False, limite=1
        )
        return found[0] if found else None
    return None


async def alternatives_for(session: AsyncSession, p: Product, limit: int = 3) -> list[Product]:
    low, high = p.price_brl * Decimal("0.5"), p.price_brl * Decimal("1.6")
    stmt = (
        select(Product)
        .options(selectinload(Product.promotions), selectinload(Product.category))
        .where(
            Product.category_id == p.category_id,
            Product.product_id != p.product_id,
            Product.status == ProductStatus.active,
            Product.stock_quantity > 0,
            Product.price_brl.between(low, high),
        )
        .order_by(func.abs(Product.price_brl - p.price_brl))
    )
    rows = list((await session.scalars(stmt)).all())
    # prefere mesmo tipo de cordas e mesma eletrônica
    specs = p.specs or {}
    rows.sort(
        key=lambda a: (
            (a.specs or {}).get("strings") != specs.get("strings"),
            (a.specs or {}).get("electronics") != specs.get("electronics"),
            abs(a.price_brl - p.price_brl),
        )
    )
    return [a for a in rows if not quality_notice(a) or quality_notice(a)["nivel"] != "quarentena"][
        :limit
    ]


async def empty_category_names(session: AsyncSession, category_ids: list[int]) -> list[str]:
    if not category_ids:
        return []
    stmt = (
        select(Category.name)
        .outerjoin(Product, Product.category_id == Category.category_id)
        .where(Category.category_id.in_(category_ids))
        .group_by(Category.category_id, Category.name)
        .having(func.count(Product.product_id) == 0)
    )
    return list((await session.scalars(stmt)).all())


async def active_promotions(session: AsyncSession) -> list[Product]:
    stmt = (
        select(Product)
        .join(Promotion, Promotion.product_id == Product.product_id)
        .options(selectinload(Product.promotions), selectinload(Product.category))
        .where(Promotion.is_active.is_(True))
        .distinct()
        .order_by(Product.name)
    )
    return list((await session.scalars(stmt)).all())


# ----------------------------------------------------------------------------
# Pedidos
# ----------------------------------------------------------------------------
async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product), selectinload(Order.customer)
        )
        .where(Order.order_id == order_id)
    )
    return await session.scalar(stmt)


async def orders_for_customer(session: AsyncSession, customer_id: int) -> list[Order]:
    stmt = (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc())
    )
    return list((await session.scalars(stmt)).all())


def order_summary(o: Order, today: date) -> dict:
    delivery = rules.delivery_status(o.status.value, o.estimated_delivery, today)
    summary = {
        "pedido": o.order_id,
        "data": o.order_date.strftime("%d/%m/%Y"),
        "status": STATUS_LABELS.get(o.status.value, o.status.value),
        "total": brl(o.total_brl),
        "pagamento": payment_label(o.payment_method),
        "itens": [
            {
                "produto": it.product.name if it.product else f"produto {it.product_id}",
                "quantidade": it.quantity,
            }
            for it in o.items
        ],
        "rastreio": o.tracking_code,
        "rastreio_valido": rules.tracking_is_valid(o.tracking_code) if o.tracking_code else None,
        "previsao_entrega": o.estimated_delivery.strftime("%d/%m/%Y")
        if o.estimated_delivery
        else None,
        "situacao_entrega": delivery.message,
        "atrasado": delivery.overdue,
        "observacoes": o.notes,
    }
    warnings = [
        f["detail"] for f in (o.quality_flags or []) if f["severity"] in ("warning", "quarantine")
    ]
    if warnings:
        summary["avisos_cadastro"] = warnings
    return {k: v for k, v in summary.items() if v is not None}
