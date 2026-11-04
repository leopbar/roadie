from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from roadie.policy import rules
from roadie.policy.holidays import easter, holiday_name

TZ = ZoneInfo("America/Campo_Grande")


def at(y, m, d, hh=10, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


# ---------------------------------------------------------------- horário
def test_store_hours_weekday_open_and_closing_time():
    v = rules.store_hours(at(2026, 3, 24, 10))  # terça
    assert v.is_open and v.closes_at.hour == 18 and "fecha às 18:00" in v.message


def test_store_hours_saturday_afternoon_reopens_monday():
    v = rules.store_hours(at(2026, 3, 28, 14))  # sábado 14h
    assert not v.is_open
    assert v.opens_at == at(2026, 3, 30, 9)
    assert "segunda-feira às 09:00" in v.message


def test_store_hours_friday_night_reopens_saturday_morning():
    v = rules.store_hours(at(2026, 3, 27, 18, 30))  # sexta 18h30
    assert not v.is_open and v.opens_at == at(2026, 3, 28, 9) and "amanhã" in v.message


def test_store_hours_sunday_closed():
    v = rules.store_hours(at(2026, 3, 29, 11))
    assert not v.is_open and v.opens_at == at(2026, 3, 30, 9)


# ---------------------------------------------------------------- SLA
def test_complaint_sla_business_day_is_next_business_day_same_time():
    assert rules.complaint_sla(at(2026, 3, 24, 10)).due_at == at(2026, 3, 25, 10)
    assert rules.complaint_sla(at(2026, 3, 27, 17)).due_at == at(
        2026, 3, 30, 17
    )  # sexta -> segunda


def test_easter_and_good_friday():
    assert [easter(y) for y in (2025, 2026, 2027)] == [
        date(2025, 4, 20),
        date(2026, 4, 5),
        date(2027, 3, 28),
    ]
    assert holiday_name(date(2026, 4, 3)) == "Paixão de Cristo"
    assert holiday_name(date(2026, 6, 4)) is None  # Corpus Christi: ponto facultativo


def test_store_closed_on_holiday():
    v = rules.store_hours(at(2026, 4, 21, 10))  # terça, Tiradentes
    assert not v.is_open and v.opens_at == at(2026, 4, 22, 9)
    assert "Tiradentes" in v.message


def test_complaint_sla_skips_holidays():
    # quinta antes da Paixão de Cristo: sexta é feriado, retorno na segunda
    assert rules.complaint_sla(at(2026, 4, 2, 10)).due_at == at(2026, 4, 6, 10)
    # aberta no aniversário de Campo Grande (quarta, 26/08): conta a partir de quinta 9h
    assert rules.complaint_sla(at(2026, 8, 26, 10)).due_at == at(2026, 8, 28, 9)
    assert rules.complaint_sla(at(2026, 8, 25, 15)).due_at == at(2026, 8, 27, 15)


def test_complaint_sla_weekend_starts_counting_on_monday():
    assert rules.complaint_sla(at(2026, 3, 28, 10)).due_at == at(
        2026, 3, 31, 9
    )  # sábado -> terça 9h


# ---------------------------------------------------------------- preço
def test_quote_price_pix_discount_on_list_price():
    q = rules.quote_price(Decimal("2199"))
    assert q.pix_price_on_list == Decimal("2089.05") and q.cash_price == q.pix_price_on_list
    assert q.promo_price is None and q.clauses == ["3"]


def test_quote_price_promo_is_not_cumulative_with_pix():
    q = rules.quote_price(Decimal("5999"), Decimal("8"), "Desconto Exclusivo")
    assert q.promo_price == Decimal("5519.08")
    assert q.cash_price == q.promo_price  # sem 5% extra
    assert any("não são cumulativas" in n for n in q.notes)
    assert q.clauses == ["3", "6.2"]
    assert q.as_dict()["display"]["promocao"] == "R$ 5.519,08"


# ---------------------------------------------------------------- parcelas
@pytest.mark.parametrize(
    "total,max_n",
    [
        (Decimal("2199"), 12),  # 183,25 por parcela
        (Decimal("159.9"), 3),  # 4x daria 39,98 < 80
        (Decimal("429.9"), 5),  # 5x = 85,98 ok; 6x = 71,65 não
        (Decimal("1199"), 11),  # 12x = 99,92 < 100; 11x = 109 ok
        (Decimal("80"), 1),  # 2x = 40 < 50
    ],
)
def test_installment_tiers(total, max_n):
    plan = rules.installment_plan(total)
    assert plan.max_installments == max_n
    assert plan.options[0].allowed and plan.options[0].n == 1
    for opt in plan.options:
        if opt.n > max_n:
            assert not opt.allowed


def test_installment_combo_threshold():
    assert rules.installment_plan(Decimal("2000")).combo_allowed is False
    assert rules.installment_plan(Decimal("2000.01")).combo_allowed is True


# ---------------------------------------------------------------- frete
def test_shipping_metro_fee_and_free_threshold():
    assert rules.shipping_for("Campo Grande", Decimal("349.9")).fee == Decimal("35")
    free = rules.shipping_for("campo grande", Decimal("599"))
    assert free.free and free.fee == Decimal("0") and free.clauses == ["5.1"]


def test_shipping_other_cities_need_quote():
    v = rules.shipping_for("Dourados", Decimal("4599"))
    assert v.region == "outras" and v.needs_quote and len(v.carriers) == 3


def test_shipping_unknown_city_asks():
    v = rules.shipping_for(None)
    assert v.region == "desconhecida" and v.needs_quote


# ---------------------------------------------------------------- rastreio / entrega
def test_tracking_format():
    assert rules.tracking_is_valid("BRAB1234567BR")
    assert not rules.tracking_is_valid("BR123BR") and not rules.tracking_is_valid(None)


def test_delivery_overdue_for_shipped_orders():
    v = rules.delivery_status("shipped", date(2026, 2, 28), date(2026, 3, 24))
    assert v.overdue and v.days_overdue == 24
    assert not rules.delivery_status("shipped", date(2026, 3, 30), date(2026, 3, 24)).overdue


# ---------------------------------------------------------------- devoluções
TODAY = date(2026, 3, 24)


def test_regret_window_counts_from_receipt():
    v = rules.return_eligibility(
        "delivered", date(2026, 3, 10), date(2026, 3, 20), "arrependimento", TODAY
    )
    assert v.eligible and v.deadline == date(2026, 3, 27) and v.days_left == 3
    assert v.reference_basis.startswith("data estimada")
    assert "4.1" in v.clauses


def test_regret_window_expired_then_suggests_other_paths():
    v = rules.return_eligibility(
        "delivered", date(2026, 2, 3), date(2026, 2, 17), "arrependimento", TODAY
    )
    assert v.eligible is False and v.deadline == date(2026, 2, 24)
    assert "encerrado" in v.explanation


def test_received_on_overrides_estimate():
    v = rules.return_eligibility(
        "delivered",
        date(2026, 2, 3),
        date(2026, 2, 17),
        "arrependimento",
        TODAY,
        received_on=date(2026, 3, 22),
    )
    assert v.eligible and v.reference_basis == "data de recebimento informada"


def test_defect_window_from_purchase_then_warranty():
    v = rules.return_eligibility("delivered", date(2026, 3, 1), date(2026, 3, 10), "defeito", TODAY)
    assert v.path == "troca_defeito" and v.eligible and v.deadline == date(2026, 3, 31)
    late = rules.return_eligibility(
        "delivered", date(2026, 2, 3), date(2026, 2, 17), "defeito", TODAY
    )
    assert late.path == "garantia_fabricante" and late.eligible is False
    assert any("vigente até 18/05/2026" in s for s in late.next_steps)
    assert {"8.1", "8.2"} <= set(late.clauses)


def test_pending_order_is_a_cancellation_not_a_return():
    v = rules.return_eligibility("pending", date(2026, 3, 22), None, "arrependimento", TODAY)
    assert v.path == "cancelamento_antes_envio" and v.eligible


def test_shipped_without_receipt_date_needs_a_question():
    v = rules.return_eligibility(
        "shipped", date(2026, 2, 15), date(2026, 2, 28), "arrependimento", TODAY
    )
    assert v.eligible is None and v.path == "aguardando_recebimento"


def test_cancelled_order_has_nothing_to_return():
    v = rules.return_eligibility("cancelled", date(2026, 1, 28), None, "defeito", TODAY)
    assert v.path == "nao_aplicavel" and v.eligible is False


def test_warranty_status():
    w = rules.warranty_status(date(2026, 2, 17), TODAY)
    assert w.legal_active and w.legal_until == date(2026, 5, 18)
    assert not rules.warranty_status(date(2025, 10, 25), TODAY).legal_active


# ---------------------------------------------------------------- deriva código x manual
def test_rule_parameters_still_match_the_manual_text(clauses):
    by_id = {c.clause_id: c for c in clauses}
    for name, (_value, clause_id, snippet) in rules.PARAMS.items():
        assert clause_id in by_id, f"{name}: cláusula {clause_id} não existe no manual"
        assert snippet in by_id[clause_id].body, (
            f"{name}: '{snippet}' não está na cláusula {clause_id}"
        )


def test_every_cited_clause_exists(clauses):
    ids = {c.clause_id for c in clauses}
    cited = set()
    cited |= set(rules.store_hours(at(2026, 3, 24)).clauses)
    cited |= set(rules.complaint_sla(at(2026, 3, 24)).clauses)
    cited |= set(rules.quote_price(Decimal("100"), Decimal("10"), "x").clauses)
    cited |= set(rules.installment_plan(Decimal("100")).clauses)
    cited |= set(rules.shipping_for("Campo Grande", Decimal("100")).clauses)
    cited |= set(rules.shipping_for("Dourados").clauses)
    cited |= set(rules.warranty_status(TODAY, TODAY).clauses)
    for status in ("pending", "shipped", "delivered", "cancelled"):
        for reason in ("arrependimento", "defeito", "preferencia"):
            cited |= set(
                rules.return_eligibility(
                    status, date(2026, 1, 1), date(2026, 1, 10), reason, TODAY
                ).clauses
            )
    assert cited <= ids, cited - ids
