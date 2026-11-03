"""Formatação de valores em português do Brasil."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def money(value: Decimal | float | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def brl(value: Decimal | float | int) -> str:
    """Ex.: 1234.5 -> 'R$ 1.234,50'."""
    q = money(value)
    sign = "-" if q < 0 else ""
    q = abs(q)
    inteiro, _, centavos = f"{q:.2f}".partition(".")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{sign}R$ {'.'.join(grupos)},{centavos}"


def pct(value: Decimal | float | int) -> str:
    """Ex.: 12 -> '12%', 12.5 -> '12,5%'."""
    d = Decimal(str(value)).normalize()
    text = f"{d:f}".replace(".", ",")
    return f"{text}%"
