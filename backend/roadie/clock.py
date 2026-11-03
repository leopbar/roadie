"""Relógio da loja.

O agente nunca pergunta ao modelo "que horas são". O "agora" vem daqui,
é determinístico e pode ser simulado por conversa, para que prazos de
política (7 dias, 30 dias, horário de funcionamento) sejam reproduzíveis.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from roadie.config import get_settings

WEEKDAYS_PT = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]


class StoreClock:
    def __init__(self, timezone: str, fixed: str | None) -> None:
        self.tz = ZoneInfo(timezone)
        self._fixed: datetime | None = None
        if fixed and fixed.lower() != "real":
            parsed = datetime.fromisoformat(fixed)
            self._fixed = parsed if parsed.tzinfo else parsed.replace(tzinfo=self.tz)

    @property
    def is_simulated(self) -> bool:
        return self._fixed is not None

    def now(self, override: datetime | None = None) -> datetime:
        """Retorna o "agora" no fuso da loja, respeitando override por conversa."""
        if override is not None:
            base = override if override.tzinfo else override.replace(tzinfo=self.tz)
        elif self._fixed is not None:
            base = self._fixed
        else:
            base = datetime.now(tz=self.tz)
        return base.astimezone(self.tz)

    @staticmethod
    def describe(moment: datetime) -> str:
        """Ex.: 'terça-feira, 24/03/2026 10:00'."""
        return f"{WEEKDAYS_PT[moment.weekday()]}, {moment.strftime('%d/%m/%Y %H:%M')}"


def get_clock() -> StoreClock:
    s = get_settings()
    return StoreClock(s.store_timezone, s.store_clock)
