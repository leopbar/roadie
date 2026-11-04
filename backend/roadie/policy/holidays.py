"""Feriados de Campo Grande/MS: nacionais, estadual (MS) e municipal.

O manual diz "Domingo e Feriados: fechado" (cláusula 2) e conta prazos em
dias úteis, mas não lista os feriados; a premissa (docs/premissas.md) é o
calendário oficial da cidade. Pontos facultativos (Carnaval, Corpus Christi,
vésperas) não entram: o manual não diz nada sobre eles.

Conferido com o decreto municipal 16.469/2025 (calendário de 2026 de Campo
Grande) e com o feriado municipal do aniversário da cidade (26/08).
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import cache

FIXED: dict[tuple[int, int], str] = {
    (1, 1): "Confraternização Universal",
    (4, 21): "Tiradentes",
    (5, 1): "Dia do Trabalho",
    (8, 26): "Aniversário de Campo Grande",
    (9, 7): "Independência do Brasil",
    (10, 11): "Criação do Estado de Mato Grosso do Sul",
    (10, 12): "Nossa Senhora Aparecida",
    (11, 2): "Finados",
    (11, 15): "Proclamação da República",
    (11, 20): "Dia Nacional de Zumbi e da Consciência Negra",
    (12, 25): "Natal",
}


def easter(year: int) -> date:
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


@cache
def holidays(year: int) -> dict[date, str]:
    days = {date(year, m, d): name for (m, d), name in FIXED.items()}
    days[easter(year) - timedelta(days=2)] = "Paixão de Cristo"
    return days


def holiday_name(day: date) -> str | None:
    return holidays(day.year).get(day)
