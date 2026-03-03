from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional
from domain.trading import Signal
from domain.models import MarketContext

class BaseOracle(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador unico en minusculas."""

    @property
    @abstractmethod
    def tier(self) -> str:
        """Nivel de conviccion: 'SCOUT', 'AMBUSH', 'UNICORN'."""

    @abstractmethod
    def probability(
        self,
        c1m:        dict,
        c15m:       dict,
        c1h:        dict,
        direction:  str,
        ctx:        MarketContext,
    ) -> float:
        """Calcula la probabilidad bayesiana [0.0, 100.0]."""

    @abstractmethod
    def evaluate(self, data: dict) -> Optional[Signal]:
        """Evalua si hay entrada y retorna Signal o None."""

    def _extract_candles(self, data: dict) -> tuple[dict, dict, dict]:
        s1m, s15m, s1h = data.get("1m"), data.get("15m"), data.get("1h")
        c1m = {col: s1m[col][-1] for col in s1m.columns} if s1m is not None and len(s1m) > 0 else {}
        c15m = {col: s15m[col][-1] for col in s15m.columns} if s15m is not None and len(s15m) > 0 else {}
        c1h = {col: s1h[col][-1] for col in s1h.columns} if s1h is not None and len(s1h) > 0 else {}
        return c1m, c15m, c1h
