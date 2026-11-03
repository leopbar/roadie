"""Motor de regras das políticas da Empório da Música.

Funções puras: recebem valores simples, devolvem vereditos com explicação em
português e a lista de cláusulas do manual que os sustentam. Cada parâmetro
numérico está em PARAMS, apontando para a cláusula de origem, e um teste de
deriva confere que o texto do manual ainda diz o que o código assume.
"""

from __future__ import annotations

import enum
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from roadie.clock import WEEKDAYS_PT
from roadie.textfmt import brl, money, pct

# ----------------------------------------------------------------------------
# Parâmetros: (valor, cláusula de origem, trecho literal esperado no manual)
# ----------------------------------------------------------------------------
PARAMS: dict[str, tuple[object, str, str]] = {
    "weekday_hours": ("09:00-18:00", "2", "09:00 às 18:00"),
    "saturday_hours": ("09:00-13:00", "2", "09:00 às 13:00"),
    "sunday_closed": (True, "2", "Fechado"),
    "pix_discount_percent": (Decimal("5"), "3", "5% de desconto"),
    "max_installments": (12, "3", "Até 12x sem juros"),
    "installment_min_2_3": (Decimal("50"), "3.1", "R$ 50,00"),
    "installment_min_4_6": (Decimal("80"), "3.1", "R$ 80,00"),
    "installment_min_7_12": (Decimal("100"), "3.1", "R$ 100,00"),
    "combo_payment_min": (Decimal("2000"), "3.1", "R$ 2.000,00"),
    "regret_days": (7, "4.1", "7 (sete) dias corridos"),
    "refund_business_days": (10, "4.1", "10 dias úteis"),
    "defect_days": (30, "4.2", "30 (trinta) dias corridos"),
    "preference_days": (7, "4.3", "até 7 dias"),
    "free_shipping_min": (Decimal("500"), "5.1", "R$ 500,00"),
    "metro_shipping_fee": (Decimal("35"), "5.1", "R$ 35,00"),
    "metro_delivery_days": ("1-3", "5.1", "1 a 3 dias úteis"),
    "pac_days": ("5-12", "5.2", "5 a 12 dias úteis"),
    "sedex_days": ("2-5", "5.2", "2 a 5 dias úteis"),
    "jadlog_days": ("3-8", "5.2", "3 a 8 dias úteis"),
    "tracking_format": ("BR+9+BR", "5.3", "BR seguido de 9 caracteres"),
    "promo_not_cumulative": (True, "6.2", "não são cumulativas"),
    "complaint_sla_hours": (24, "7.3", "24 horas úteis"),
    "legal_warranty_days": (90, "8.1", "90 (noventa) dias"),
}


def param(name: str):
    return PARAMS[name][0]


# Região metropolitana de Campo Grande. O manual não lista os municípios;
# assumimos a capital e vizinhos imediatos (premissa documentada no README).
METRO_CITIES = {
    "campo grande",
    "terenos",
    "jaraguari",
    "sidrolandia",
    "ribas do rio pardo",
    "nova alvorada do sul",
    "rochedo",
    "corguinho",
}

TRACKING_RE = re.compile(r"^BR[A-Z0-9]{9}BR$")

WEEKDAY_OPEN, WEEKDAY_CLOSE = time(9, 0), time(18, 0)
SATURDAY_OPEN, SATURDAY_CLOSE = time(9, 0), time(13, 0)


def _norm(text: str | None) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ----------------------------------------------------------------------------
# Horário de funcionamento (cláusula 2)
# ----------------------------------------------------------------------------
@dataclass
class HoursVerdict:
    is_open: bool
    now_label: str
    opens_at: datetime | None  # próxima abertura, se fechada
    closes_at: datetime | None  # fechamento de hoje, se aberta
    message: str
    schedule: list[str] = field(
        default_factory=lambda: [
            "Segunda a sexta: 09:00 às 18:00",
            "Sábado: 09:00 às 13:00",
            "Domingo e feriados: fechado",
        ]
    )
    clauses: list[str] = field(default_factory=lambda: ["2"])

    def as_dict(self) -> dict:
        d = asdict(self)
        d["opens_at"] = self.opens_at.isoformat() if self.opens_at else None
        d["closes_at"] = self.closes_at.isoformat() if self.closes_at else None
        return d


def _window_for(day: date) -> tuple[time, time] | None:
    wd = day.weekday()
    if wd <= 4:
        return WEEKDAY_OPEN, WEEKDAY_CLOSE
    if wd == 5:
        return SATURDAY_OPEN, SATURDAY_CLOSE
    return None


def next_opening(now: datetime) -> datetime:
    """Primeiro instante de abertura estritamente após `now` (ou agora, se aberta)."""
    for offset in range(0, 8):
        day = now.date() + timedelta(days=offset)
        window = _window_for(day)
        if not window:
            continue
        opening = datetime.combine(day, window[0], tzinfo=now.tzinfo)
        closing = datetime.combine(day, window[1], tzinfo=now.tzinfo)
        if offset == 0 and opening <= now < closing:
            return now
        if opening > now:
            return opening
    raise RuntimeError("sem abertura nos próximos 7 dias")  # impossível com a grade atual


def store_hours(now: datetime) -> HoursVerdict:
    window = _window_for(now.date())
    label = f"{WEEKDAYS_PT[now.weekday()]}, {now.strftime('%d/%m/%Y %H:%M')}"
    if window:
        opening = datetime.combine(now.date(), window[0], tzinfo=now.tzinfo)
        closing = datetime.combine(now.date(), window[1], tzinfo=now.tzinfo)
        if opening <= now < closing:
            return HoursVerdict(
                is_open=True,
                now_label=label,
                opens_at=None,
                closes_at=closing,
                message=f"A loja está aberta agora e fecha às {closing.strftime('%H:%M')}.",
            )
    opens = next_opening(now)
    when = "hoje" if opens.date() == now.date() else WEEKDAYS_PT[opens.weekday()]
    if opens.date() == now.date() + timedelta(days=1):
        when = "amanhã"
    return HoursVerdict(
        is_open=False,
        now_label=label,
        opens_at=opens,
        closes_at=None,
        message=f"A loja está fechada agora. Reabre {when} às {opens.strftime('%H:%M')}.",
    )


# ----------------------------------------------------------------------------
# Dias úteis e SLA de reclamação (cláusula 7.3)
# ----------------------------------------------------------------------------
def is_business_day(day: date) -> bool:
    # Feriados não estão no manual nem nos dados; premissa: só fins de semana.
    return day.weekday() <= 4


def add_business_days(day: date, n: int) -> date:
    current = day
    remaining = n
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current


@dataclass
class SlaVerdict:
    due_at: datetime
    message: str
    clauses: list[str] = field(default_factory=lambda: ["7.3"])

    def as_dict(self) -> dict:
        return {"due_at": self.due_at.isoformat(), "message": self.message, "clauses": self.clauses}


def complaint_sla(now: datetime) -> SlaVerdict:
    """24 horas úteis: um dia útil a partir do próximo momento de expediente."""
    base = now
    if not is_business_day(now.date()):
        base = datetime.combine(add_business_days(now.date(), 1), WEEKDAY_OPEN, tzinfo=now.tzinfo)
    due = datetime.combine(add_business_days(base.date(), 1), base.timetz())
    return SlaVerdict(
        due_at=due,
        message=f"Retorno da equipe até {WEEKDAYS_PT[due.weekday()]}, {due.strftime('%d/%m às %H:%M')} (24 horas úteis).",
    )


# ----------------------------------------------------------------------------
# Preço, PIX e promoção (cláusulas 3 e 6.2)
# ----------------------------------------------------------------------------
@dataclass
class PriceQuote:
    list_price: Decimal
    promo_percent: Decimal | None
    promo_description: str | None
    promo_price: Decimal | None
    pix_price_on_list: Decimal
    cash_price: Decimal  # melhor preço à vista respeitando a não cumulatividade
    cash_label: str
    notes: list[str]
    clauses: list[str]

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("list_price", "promo_percent", "promo_price", "pix_price_on_list", "cash_price"):
            if d[k] is not None:
                d[k] = str(d[k])
        d["display"] = {
            "tabela": brl(self.list_price),
            "promocao": brl(self.promo_price) if self.promo_price is not None else None,
            "pix": brl(self.cash_price),
        }
        return d


def quote_price(
    list_price: Decimal, promo_percent: Decimal | None = None, promo_description: str | None = None
) -> PriceQuote:
    list_price = money(list_price)
    pix_pct = param("pix_discount_percent")
    pix_on_list = money(list_price * (1 - pix_pct / 100))
    notes: list[str] = []
    if promo_percent and promo_percent > 0:
        promo_price = money(list_price * (1 - Decimal(promo_percent) / 100))
        notes.append(
            f"Preço promocional ({promo_description or 'promoção'}, {pct(promo_percent)} de desconto) "
            "deve ser apresentado junto do preço original e do percentual."
        )
        notes.append(
            "Promoções não são cumulativas: o desconto de PIX não se aplica sobre o preço promocional."
        )
        cash = promo_price
        label = f"{brl(promo_price)} na promoção (PIX, cartão ou boleto; sem desconto adicional)"
        if Decimal(promo_percent) < pix_pct:
            notes.append(
                "A promoção desconta menos que os 5% do PIX sobre a tabela; confirmar com a gerência qual preço prevalece (cláusula 10)."
            )
        return PriceQuote(
            list_price=list_price,
            promo_percent=Decimal(promo_percent),
            promo_description=promo_description,
            promo_price=promo_price,
            pix_price_on_list=pix_on_list,
            cash_price=cash,
            cash_label=label,
            notes=notes,
            clauses=["3", "6.2"],
        )
    return PriceQuote(
        list_price=list_price,
        promo_percent=None,
        promo_description=None,
        promo_price=None,
        pix_price_on_list=pix_on_list,
        cash_price=pix_on_list,
        cash_label=f"{brl(pix_on_list)} no PIX (5% sobre {brl(list_price)})",
        notes=notes,
        clauses=["3"],
    )


# ----------------------------------------------------------------------------
# Parcelamento (cláusulas 3 e 3.1)
# ----------------------------------------------------------------------------
@dataclass
class InstallmentOption:
    n: int
    amount: Decimal
    allowed: bool
    rule: str

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "amount": str(self.amount),
            "amount_display": brl(self.amount),
            "allowed": self.allowed,
            "rule": self.rule,
        }


@dataclass
class InstallmentPlan:
    total: Decimal
    options: list[InstallmentOption]
    max_installments: int
    combo_allowed: bool
    notes: list[str]
    clauses: list[str] = field(default_factory=lambda: ["3", "3.1"])

    def as_dict(self) -> dict:
        return {
            "total": str(self.total),
            "total_display": brl(self.total),
            "max_installments": self.max_installments,
            "best_option": next((o.as_dict() for o in reversed(self.options) if o.allowed), None),
            "options": [o.as_dict() for o in self.options],
            "combo_allowed": self.combo_allowed,
            "notes": self.notes,
            "clauses": self.clauses,
        }


def _min_installment(n: int) -> tuple[Decimal, str]:
    if n <= 3:
        return param("installment_min_2_3"), "até 3x: parcela mínima R$ 50,00"
    if n <= 6:
        return param("installment_min_4_6"), "4x a 6x: parcela mínima R$ 80,00"
    return param("installment_min_7_12"), "7x a 12x: parcela mínima R$ 100,00"


def installment_plan(total: Decimal) -> InstallmentPlan:
    total = money(total)
    options: list[InstallmentOption] = []
    max_n = 1
    for n in range(1, param("max_installments") + 1):
        amount = money(total / n)
        if n == 1:
            options.append(InstallmentOption(1, total, True, "à vista (PIX, débito ou boleto)"))
            continue
        minimum, rule = _min_installment(n)
        allowed = amount >= minimum
        options.append(InstallmentOption(n, amount, allowed, rule))
        if allowed:
            max_n = n
    notes = ["Todas as parcelas sem juros."]
    notes.append(
        "A tabela da cláusula 3 cita parcela mínima de R$ 100,00; a cláusula 3.1 detalha faixas por quantidade de parcelas e prevalece por ser mais específica."
    )
    combo = total > param("combo_payment_min")
    if combo:
        notes.append(
            "Compra acima de R$ 2.000,00: pode combinar formas de pagamento (ex.: PIX + cartão)."
        )
    return InstallmentPlan(
        total=total, options=options, max_installments=max_n, combo_allowed=combo, notes=notes
    )


# ----------------------------------------------------------------------------
# Frete (cláusulas 5.1 e 5.2)
# ----------------------------------------------------------------------------
@dataclass
class ShippingVerdict:
    region: str  # metro | outras | desconhecida
    city: str | None
    free: bool | None
    fee: Decimal | None
    deadline: str
    carriers: list[dict]
    needs_quote: bool
    notes: list[str]
    clauses: list[str]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["fee"] = str(self.fee) if self.fee is not None else None
        d["fee_display"] = brl(self.fee) if self.fee is not None else None
        return d


def shipping_for(
    city: str | None, order_total: Decimal | None = None, large_item: bool = False
) -> ShippingVerdict:
    notes: list[str] = []
    if large_item:
        notes.append(
            "Instrumento de grande porte (bateria acústica, piano digital, contrabaixo): pode exigir frete especial com cotação individual."
        )
    if city is None:
        return ShippingVerdict(
            region="desconhecida",
            city=None,
            free=None,
            fee=None,
            deadline="",
            carriers=[],
            needs_quote=True,
            notes=notes + ["Informe a cidade (ou CEP) para calcular o frete."],
            clauses=["5.1", "5.2"],
        )
    if _norm(city) in METRO_CITIES:
        total = money(order_total or 0)
        free = total >= param("free_shipping_min")
        fee = Decimal("0") if free else param("metro_shipping_fee")
        notes.append(
            "Entrega por motoboy próprio; o cliente é contactado por telefone antes da entrega."
        )
        if order_total is None:
            notes.append(
                "Frete grátis para pedidos acima de R$ 500,00; abaixo disso, taxa fixa de R$ 35,00."
            )
        return ShippingVerdict(
            region="metro",
            city=city,
            free=free,
            fee=fee,
            deadline="1 a 3 dias úteis",
            carriers=[{"name": "Motoboy próprio", "deadline": "1 a 3 dias úteis"}],
            needs_quote=False,
            notes=notes,
            clauses=["5.1"],
        )
    notes.append(
        "Valor calculado por CEP, peso e dimensões; todos os envios têm seguro contra extravio e dano."
    )
    return ShippingVerdict(
        region="outras",
        city=city,
        free=False,
        fee=None,
        deadline="conforme a modalidade",
        carriers=[
            {"name": "PAC (Correios)", "deadline": "5 a 12 dias úteis"},
            {"name": "SEDEX (Correios)", "deadline": "2 a 5 dias úteis"},
            {"name": "Jadlog (.package)", "deadline": "3 a 8 dias úteis"},
        ],
        needs_quote=True,
        notes=notes,
        clauses=["5.2"],
    )


# ----------------------------------------------------------------------------
# Rastreio e atraso (cláusula 5.3)
# ----------------------------------------------------------------------------
def tracking_is_valid(code: str | None) -> bool:
    return bool(code) and bool(TRACKING_RE.match(code.strip().upper()))


@dataclass
class DeliveryVerdict:
    status: str
    overdue: bool
    days_overdue: int
    message: str
    clauses: list[str] = field(default_factory=lambda: ["5.1", "5.2", "5.3"])

    def as_dict(self) -> dict:
        return asdict(self)


def delivery_status(
    order_status: str, estimated_delivery: date | None, today: date
) -> DeliveryVerdict:
    status = str(order_status)
    if status == "shipped" and estimated_delivery and today > estimated_delivery:
        days = (today - estimated_delivery).days
        return DeliveryVerdict(
            status,
            True,
            days,
            f"Pedido enviado e {days} dia(s) além da previsão de entrega ({estimated_delivery:%d/%m/%Y}).",
        )
    if status == "shipped":
        when = f" Previsão: {estimated_delivery:%d/%m/%Y}." if estimated_delivery else ""
        return DeliveryVerdict(status, False, 0, f"Pedido enviado, dentro do prazo.{when}")
    if status == "delivered":
        return DeliveryVerdict(status, False, 0, "Pedido entregue.")
    if status == "cancelled":
        return DeliveryVerdict(status, False, 0, "Pedido cancelado.")
    if status == "confirmed":
        return DeliveryVerdict(
            status, False, 0, "Pagamento confirmado; pedido em preparação, ainda sem envio."
        )
    return DeliveryVerdict(
        status, False, 0, "Pedido pendente: aguardando confirmação do pagamento."
    )


# ----------------------------------------------------------------------------
# Trocas e devoluções (cláusulas 4.x, 8.x)
# ----------------------------------------------------------------------------
class ReturnReason(enum.StrEnum):
    arrependimento = "arrependimento"
    defeito = "defeito"
    preferencia = "preferencia"


@dataclass
class ReturnVerdict:
    reason: str
    path: str
    eligible: bool | None  # None: falta informação (ex.: data de recebimento)
    reference_date: date | None
    reference_basis: str | None
    deadline: date | None
    days_left: int | None
    conditions: list[str]
    next_steps: list[str]
    explanation: str
    clauses: list[str]

    def as_dict(self) -> dict:
        d = asdict(self)
        d["reference_date"] = self.reference_date.isoformat() if self.reference_date else None
        d["deadline"] = self.deadline.isoformat() if self.deadline else None
        return d


REGRET_CONDITIONS = [
    "Produto na embalagem original, sem sinais de uso, com todos os acessórios e manuais.",
    "Reembolso na mesma forma de pagamento em até 10 dias úteis.",
    "Frete de devolução por conta da loja.",
    "Vale para compras online (todos os pedidos do sistema são online).",
]
NOT_ELIGIBLE_ITEMS = [
    "Instrumentos com personalização ou ajustes sob encomenda (setup, regulagem especial).",
    "Produtos de liquidação com aviso explícito de 'venda final'.",
    "Boquilhas de instrumentos de sopro.",
]
DEFECT_EXCLUSIONS = [
    "Danos por mau uso, quedas, umidade excessiva ou modificações não autorizadas não são cobertos.",
]


def return_eligibility(
    order_status: str,
    order_date: date,
    estimated_delivery: date | None,
    reason: ReturnReason | str,
    today: date,
    received_on: date | None = None,
) -> ReturnVerdict:
    reason = ReturnReason(reason)
    status = str(order_status)

    if status == "cancelled":
        return ReturnVerdict(
            reason=reason.value,
            path="nao_aplicavel",
            eligible=False,
            reference_date=None,
            reference_basis=None,
            deadline=None,
            days_left=None,
            conditions=[],
            next_steps=["Pedido já cancelado; nenhum produto a devolver."],
            explanation="O pedido consta como cancelado, então não há devolução ou troca a fazer.",
            clauses=["4"],
        )

    if status in ("pending", "confirmed"):
        return ReturnVerdict(
            reason=reason.value,
            path="cancelamento_antes_envio",
            eligible=True,
            reference_date=order_date,
            reference_basis="data do pedido",
            deadline=None,
            days_left=None,
            conditions=[
                "O pedido ainda não foi enviado, então o caminho é o cancelamento, não a devolução."
            ],
            next_steps=[
                "Registrar pedido de cancelamento para a equipe (estorno na forma de pagamento original).",
            ],
            explanation=(
                "O pedido ainda não saiu da loja. O manual não detalha cancelamento antes do envio; "
                "a prática da loja é cancelar e estornar, e a equipe confirma o estorno."
            ),
            clauses=["4.1", "10"],
        )

    # shipped ou delivered
    if received_on is None and status == "shipped":
        return ReturnVerdict(
            reason=reason.value,
            path="aguardando_recebimento",
            eligible=None,
            reference_date=None,
            reference_basis=None,
            deadline=None,
            days_left=None,
            conditions=[],
            next_steps=["Perguntar ao cliente se já recebeu o produto e em que data."],
            explanation="O pedido consta como enviado, mas o sistema não tem a data de recebimento; os prazos contam a partir dela.",
            clauses=["4.1", "4.2", "4.3"],
        )

    receipt = received_on or estimated_delivery or order_date
    basis = (
        "data de recebimento informada"
        if received_on
        else (
            "data estimada de entrega (o sistema não registra o recebimento)"
            if estimated_delivery
            else "data do pedido"
        )
    )

    if reason == ReturnReason.arrependimento:
        deadline = receipt + timedelta(days=param("regret_days"))
        left = (deadline - today).days
        ok = today <= deadline
        return ReturnVerdict(
            reason=reason.value,
            path="devolucao_arrependimento",
            eligible=ok,
            reference_date=receipt,
            reference_basis=basis,
            deadline=deadline,
            days_left=left,
            conditions=REGRET_CONDITIONS + ["Não elegíveis: " + " ".join(NOT_ELIGIBLE_ITEMS)],
            next_steps=(
                ["Registrar a devolução e combinar a coleta (frete por conta da loja)."]
                if ok
                else [
                    "Prazo de arrependimento encerrado; verificar se é caso de defeito (30 dias) ou garantia."
                ]
            ),
            explanation=(
                f"Direito de arrependimento: até {param('regret_days')} dias corridos após o recebimento "
                f"({receipt:%d/%m/%Y}, {basis}). Prazo final {deadline:%d/%m/%Y}; "
                + (f"faltam {left} dia(s)." if ok else f"encerrado há {-left} dia(s).")
            ),
            clauses=["4.1", "4.4"],
        )

    if reason == ReturnReason.preferencia:
        deadline = receipt + timedelta(days=param("preference_days"))
        left = (deadline - today).days
        ok = today <= deadline
        return ReturnVerdict(
            reason=reason.value,
            path="troca_preferencia",
            eligible=ok,
            reference_date=receipt,
            reference_basis=basis,
            deadline=deadline,
            days_left=left,
            conditions=[
                "Produto em perfeito estado e na embalagem original.",
                "Sujeita à disponibilidade do produto desejado.",
                "Diferenças de valor são cobradas ou reembolsadas.",
            ],
            next_steps=(
                ["Registrar a troca e verificar disponibilidade do modelo desejado."]
                if ok
                else ["Prazo de troca por preferência encerrado."]
            ),
            explanation=(
                f"Troca por preferência: até {param('preference_days')} dias após o recebimento ({receipt:%d/%m/%Y}). "
                f"Prazo final {deadline:%d/%m/%Y}; "
                + (f"faltam {left} dia(s)." if ok else f"encerrado há {-left} dia(s).")
            ),
            clauses=["4.3"],
        )

    # defeito
    deadline = order_date + timedelta(days=param("defect_days"))
    left = (deadline - today).days
    ok = today <= deadline
    legal_until = receipt + timedelta(days=param("legal_warranty_days"))
    legal_active = today <= legal_until
    if ok:
        return ReturnVerdict(
            reason=reason.value,
            path="troca_defeito",
            eligible=True,
            reference_date=order_date,
            reference_basis="data da compra",
            deadline=deadline,
            days_left=left,
            conditions=DEFECT_EXCLUSIONS,
            next_steps=["Registrar a troca por defeito e orientar sobre a análise do produto."],
            explanation=(
                f"Troca por defeito de fabricação: até {param('defect_days')} dias corridos após a compra "
                f"({order_date:%d/%m/%Y}). Prazo final {deadline:%d/%m/%Y}; faltam {left} dia(s)."
            ),
            clauses=["4.2", "8.3"],
        )
    return ReturnVerdict(
        reason=reason.value,
        path="garantia_fabricante",
        eligible=False,
        reference_date=order_date,
        reference_basis="data da compra",
        deadline=deadline,
        days_left=left,
        conditions=DEFECT_EXCLUSIONS,
        next_steps=[
            "Acionar a garantia com o fabricante; a loja pode intermediar mediante solicitação.",
            (
                f"Garantia legal de {param('legal_warranty_days')} dias vigente até {legal_until:%d/%m/%Y}."
                if legal_active
                else f"Garantia legal de {param('legal_warranty_days')} dias encerrada em {legal_until:%d/%m/%Y}; verificar a garantia do fabricante (6 meses a 2 anos)."
            ),
        ],
        explanation=(
            f"O prazo de troca na loja por defeito ({param('defect_days')} dias após a compra em {order_date:%d/%m/%Y}) "
            f"encerrou em {deadline:%d/%m/%Y}. A partir daí vale a garantia: legal de {param('legal_warranty_days')} dias "
            f"contados do recebimento ({receipt:%d/%m/%Y}) e a do fabricante."
        ),
        clauses=["4.2", "8.1", "8.2", "8.3"],
    )


# ----------------------------------------------------------------------------
# Garantia (cláusulas 8.x)
# ----------------------------------------------------------------------------
@dataclass
class WarrantyVerdict:
    legal_until: date
    legal_active: bool
    days_left: int
    message: str
    exclusions: list[str]
    clauses: list[str] = field(default_factory=lambda: ["8.1", "8.2", "8.3"])

    def as_dict(self) -> dict:
        d = asdict(self)
        d["legal_until"] = self.legal_until.isoformat()
        return d


def warranty_status(receipt_date: date, today: date) -> WarrantyVerdict:
    until = receipt_date + timedelta(days=param("legal_warranty_days"))
    left = (until - today).days
    active = today <= until
    return WarrantyVerdict(
        legal_until=until,
        legal_active=active,
        days_left=left,
        message=(
            f"Garantia legal de {param('legal_warranty_days')} dias contra defeito de fabricação, contada do recebimento "
            f"({receipt_date:%d/%m/%Y}): "
            + (f"vigente até {until:%d/%m/%Y}." if active else f"encerrada em {until:%d/%m/%Y}.")
            + " A garantia do fabricante (6 meses a 2 anos) vale além dela, conforme o certificado do produto."
        ),
        exclusions=[
            "Desgaste natural de peças (trastes, cordas, feltros, palhetas de sopro).",
            "Danos por mau uso, queda, condições climáticas extremas.",
            "Reparos por terceiros não autorizados.",
            "Danos estéticos que não afetem a funcionalidade.",
        ],
    )
