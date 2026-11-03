"""Estimativa de custo por mensagem a partir do modelo que a API realmente usou.

Preços em USD por milhão de tokens (entrada, saída), tabela padrão da OpenAI
em developers.openai.com/api/docs/pricing. Modelo desconhecido: custo None.
"""

from __future__ import annotations

PRICES_AS_OF = "2026-11-03"

PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-6-astra": (10.0, 50.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "gpt-6-sol": (2.0, 10.0),
    "gpt-6.1-terra": (1.0, 5.0),
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-sol": (4.0, 20.0),
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.0),
    "gpt-5.2": (1.75, 14.0),
    "gpt-5.1": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-5": (1.25, 10.0),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
}


def price_for(model: str | None) -> tuple[float, float] | None:
    if not model:
        return None
    best: str | None = None
    for key in PRICES_USD_PER_MTOK:
        if model.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return PRICES_USD_PER_MTOK[best] if best else None


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    prices = price_for(model)
    if prices is None:
        return None
    inp, out = prices
    return round((input_tokens * inp + output_tokens * out) / 1_000_000, 6)
