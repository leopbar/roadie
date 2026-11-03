"""Quarentena de dados.

Os CSVs do desafio trazem registros contraditórios (nome de uma marca,
descrição de outra; especificações que não batem com o texto; preços fora
de qualquer faixa plausível; totais que não somam). O manual da loja proíbe
informar preço ou estoque errado. Então, em vez de confiar no cadastro, a
ingestão marca cada problema e o agente trata o registro com cautela.

Severidades:
- info        só registro, não muda o atendimento
- warning     o agente pode citar o produto, mas avisa que há inconsistência
- quarantine  o agente não afirma preço nem especificação sem a equipe confirmar
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from decimal import Decimal
from statistics import median

from roadie.db.models import FlagSeverity, OrderStatus, ProductStatus
from roadie.ingest.csv_loader import Dataset
from roadie.textfmt import brl

# Marcas compostas antes das simples, para o primeiro casamento ser o certo.
BRANDS = [
    "Music Man",
    "Yamaha",
    "Tagima",
    "Giannini",
    "Rozini",
    "Shelby",
    "Crafter",
    "Martin",
    "Taylor",
    "Takamine",
    "Kalani",
    "Kala",
    "Ohana",
    "Fender",
    "Gibson",
    "Ibanez",
    "PRS",
    "Pearl",
    "Tama",
    "Korg",
    "Nord",
    "Roland",
    "Squier",
    "Epiphone",
    "Cort",
    "Casio",
]
_BRAND_RE = {b: re.compile(rf"(?<![\w-]){re.escape(b)}(?![\w-])", re.IGNORECASE) for b in BRANDS}

TRACKING_RE = re.compile(r"^BR[A-Z0-9]{9}BR$")
PLACEHOLDER_NAME_RE = re.compile(r"\b(Bass \dX|Kit \d|Synth \d)\b", re.IGNORECASE)
PRICE_OUTLIER_LOW_RATIO = Decimal("0.2")

# (palavra na descrição, chave em specs)
SPEC_NUMERIC_CHECKS = [("teclas", "keys"), ("cordas", "strings"), ("peças", "pieces")]


@dataclass(frozen=True)
class Flag:
    entity: str
    entity_id: str
    flag: str
    severity: FlagSeverity
    detail: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


def find_brands(text: str | None) -> list[str]:
    if not text:
        return []
    found = [(m.start(), b) for b, rx in _BRAND_RE.items() if (m := rx.search(text))]
    return [b for _, b in sorted(found)]


def brand_of(name: str) -> str | None:
    brands = find_brands(name)
    return brands[0] if brands else None


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------------------
# Produtos
# ----------------------------------------------------------------------------
def check_products(ds: Dataset) -> list[Flag]:
    flags: list[Flag] = []
    by_category: dict[int, list[Decimal]] = defaultdict(list)
    for p in ds.products:
        by_category[p.category_id].append(p.price_brl)
    medians = {
        cid: Decimal(str(median(prices))) for cid, prices in by_category.items() if len(prices) >= 3
    }

    for p in ds.products:
        pid = str(p.product_id)
        name_brand = brand_of(p.name)
        desc_brands = find_brands(p.description)

        if name_brand and desc_brands and name_brand not in desc_brands:
            flags.append(
                Flag(
                    "product",
                    pid,
                    "brand_mismatch",
                    FlagSeverity.quarantine,
                    f"nome diz {name_brand}, descrição fala de {', '.join(desc_brands)}",
                )
            )

        desc = p.description or ""
        for word, key in SPEC_NUMERIC_CHECKS:
            m = re.search(rf"\b(\d+)\s+{word}\b", desc, re.IGNORECASE)
            spec_val = p.specs.get(key)
            if m and spec_val is not None and str(spec_val).strip().isdigit():
                if int(m.group(1)) != int(str(spec_val).strip()):
                    flags.append(
                        Flag(
                            "product",
                            pid,
                            "spec_mismatch",
                            FlagSeverity.quarantine,
                            f"descrição fala em {m.group(1)} {word}, specs dizem {spec_val}",
                        )
                    )

        med = medians.get(p.category_id)
        if med and med > 0:
            ratio = p.price_brl / med
            # Só o lado de baixo: instrumentos premium custam várias vezes a mediana
            # legitimamente; um baixo a R$ 441 não existe.
            if ratio < PRICE_OUTLIER_LOW_RATIO:
                flags.append(
                    Flag(
                        "product",
                        pid,
                        "price_outlier",
                        FlagSeverity.quarantine,
                        f"{brl(p.price_brl)} é {ratio * 100:.1f}% da mediana da categoria ({brl(med)})",
                    )
                )

        if PLACEHOLDER_NAME_RE.search(p.name):
            flags.append(
                Flag(
                    "product",
                    pid,
                    "placeholder_name",
                    FlagSeverity.warning,
                    "nome parece genérico (modelo não identificado no cadastro)",
                )
            )

        if p.specs.get("_parse_error"):
            flags.append(
                Flag(
                    "product",
                    pid,
                    "specs_unparseable",
                    FlagSeverity.warning,
                    "specs não é JSON válido",
                )
            )

        if p.status == ProductStatus.active and p.stock_quantity <= 0:
            flags.append(
                Flag(
                    "product", pid, "zero_stock_active", FlagSeverity.info, "ativo, mas sem estoque"
                )
            )
        if p.status == ProductStatus.discontinued and p.stock_quantity > 0:
            flags.append(
                Flag(
                    "product",
                    pid,
                    "discontinued_with_stock",
                    FlagSeverity.info,
                    f"descontinuado com {p.stock_quantity} un. em estoque",
                )
            )
    return flags


# ----------------------------------------------------------------------------
# Pedidos
# ----------------------------------------------------------------------------
def check_orders(ds: Dataset) -> list[Flag]:
    flags: list[Flag] = []
    products = {p.product_id: p for p in ds.products}
    customers = {c.customer_id for c in ds.customers}
    items_by_order: dict[int, list] = defaultdict(list)
    for it in ds.order_items:
        items_by_order[it.order_id].append(it)
        if it.product_id not in products:
            flags.append(
                Flag(
                    "order",
                    str(it.order_id),
                    "orphan_product",
                    FlagSeverity.warning,
                    f"item cita produto {it.product_id} inexistente",
                )
            )

    for o in ds.orders:
        oid = str(o.order_id)
        if o.customer_id not in customers:
            flags.append(
                Flag(
                    "order",
                    oid,
                    "orphan_customer",
                    FlagSeverity.warning,
                    f"cliente {o.customer_id} inexistente",
                )
            )

        items = items_by_order.get(o.order_id, [])
        if not items:
            flags.append(Flag("order", oid, "no_items", FlagSeverity.warning, "pedido sem itens"))
        else:
            expected = sum(
                (
                    products[i.product_id].price_brl * i.quantity
                    for i in items
                    if i.product_id in products
                ),
                Decimal("0"),
            )
            if abs(expected - o.total_brl) > Decimal("0.01"):
                flags.append(
                    Flag(
                        "order",
                        oid,
                        "total_mismatch",
                        FlagSeverity.warning,
                        f"total {brl(o.total_brl)} difere da soma dos itens {brl(expected)}",
                    )
                )
            for i in items:
                prod = products.get(i.product_id)
                if prod and prod.status == ProductStatus.coming_soon:
                    flags.append(
                        Flag(
                            "order",
                            oid,
                            "preorder_item",
                            FlagSeverity.info,
                            f"contém produto em pré-venda ({prod.name})",
                        )
                    )

        if o.status in (OrderStatus.shipped, OrderStatus.delivered):
            if not o.tracking_code:
                flags.append(
                    Flag(
                        "order",
                        oid,
                        "missing_tracking",
                        FlagSeverity.warning,
                        "enviado sem código de rastreio",
                    )
                )
            elif not TRACKING_RE.match(o.tracking_code):
                flags.append(
                    Flag(
                        "order",
                        oid,
                        "tracking_format",
                        FlagSeverity.warning,
                        f"rastreio fora do padrão BR+9+BR: {o.tracking_code}",
                    )
                )
    return flags


# ----------------------------------------------------------------------------
# Clientes
# ----------------------------------------------------------------------------
def _name_tokens(name: str) -> list[str]:
    return [
        t
        for t in strip_accents(name).lower().split()
        if t not in {"da", "de", "do", "dos", "das", "e"}
    ]


def check_customers(ds: Dataset) -> list[Flag]:
    flags: list[Flag] = []
    by_email: dict[str, list[int]] = defaultdict(list)
    by_phone: dict[str, list[int]] = defaultdict(list)
    for c in ds.customers:
        if c.email:
            by_email[c.email].append(c.customer_id)
        if c.phone_digits:
            by_phone[c.phone_digits].append(c.customer_id)
    for email, ids in by_email.items():
        if len(ids) > 1:
            for cid in ids:
                flags.append(
                    Flag(
                        "customer",
                        str(cid),
                        "duplicate_email",
                        FlagSeverity.warning,
                        f"e-mail {email} compartilhado por clientes {ids}",
                    )
                )
    for phone, ids in by_phone.items():
        if len(ids) > 1:
            for cid in ids:
                flags.append(
                    Flag(
                        "customer",
                        str(cid),
                        "duplicate_phone",
                        FlagSeverity.warning,
                        f"telefone {phone} compartilhado por clientes {ids}",
                    )
                )

    tokens = {c.customer_id: _name_tokens(c.name) for c in ds.customers}
    ordered = sorted(ds.customers, key=lambda c: c.customer_id)
    for i, a in enumerate(ordered):
        ta = tokens[a.customer_id]
        for b in ordered[i + 1 :]:
            tb = tokens[b.customer_id]
            if not ta or not tb or ta[0] != tb[0] or ta == tb:
                continue
            if (len(ta) > 1 and ta[-1] in tb[1:]) or (len(tb) > 1 and tb[-1] in ta[1:]):
                flags.append(
                    Flag(
                        "customer",
                        str(a.customer_id),
                        "possible_duplicate",
                        FlagSeverity.info,
                        f"'{a.name}' (#{a.customer_id}) e '{b.name}' (#{b.customer_id}) podem ser a mesma pessoa",
                    )
                )
    return flags


# ----------------------------------------------------------------------------
# Categorias e promoções
# ----------------------------------------------------------------------------
def check_categories(ds: Dataset) -> list[Flag]:
    used = {p.category_id for p in ds.products}
    return [
        Flag(
            "category",
            str(c.category_id),
            "empty_category",
            FlagSeverity.info,
            f"categoria '{c.name}' não tem produtos",
        )
        for c in ds.categories
        if c.category_id not in used
    ]


def check_promotions(ds: Dataset) -> list[Flag]:
    flags: list[Flag] = []
    products = {p.product_id: p for p in ds.products}
    by_product: dict[int, list[int]] = defaultdict(list)
    for pr in ds.promotions:
        by_product[pr.product_id].append(pr.promotion_id)
        if pr.product_id not in products:
            flags.append(
                Flag(
                    "promotion",
                    str(pr.promotion_id),
                    "orphan_product",
                    FlagSeverity.warning,
                    f"produto {pr.product_id} inexistente",
                )
            )
        elif pr.is_active:
            prod = products[pr.product_id]
            if prod.status != ProductStatus.active or prod.stock_quantity <= 0:
                flags.append(
                    Flag(
                        "promotion",
                        str(pr.promotion_id),
                        "active_promo_unavailable_product",
                        FlagSeverity.warning,
                        f"promoção ativa em produto indisponível ({prod.name})",
                    )
                )
    for pid, promos in by_product.items():
        if len(promos) > 1:
            flags.append(
                Flag(
                    "product",
                    str(pid),
                    "multiple_promotions",
                    FlagSeverity.info,
                    f"produto com {len(promos)} promoções cadastradas",
                )
            )
    return flags


def run_all(ds: Dataset) -> list[Flag]:
    return [
        *check_products(ds),
        *check_orders(ds),
        *check_customers(ds),
        *check_categories(ds),
        *check_promotions(ds),
    ]


def group_flags(flags: list[Flag]) -> dict[tuple[str, str], list[dict]]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in flags:
        grouped[(f.entity, f.entity_id)].append(
            {"flag": f.flag, "severity": f.severity.value, "detail": f.detail}
        )
    return grouped


def worst_severity(flag_dicts: list[dict]) -> FlagSeverity | None:
    order = [FlagSeverity.quarantine, FlagSeverity.warning, FlagSeverity.info]
    present = {d["severity"] for d in flag_dicts}
    for sev in order:
        if sev.value in present:
            return sev
    return None
