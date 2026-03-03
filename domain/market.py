from __future__ import annotations

from datetime import datetime
from typing import List, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

class Candle(BaseModel):
    """Dato histórico del mercado (inmutable)."""

    timestamp: Union[int, datetime]
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = Field(..., description='Ej: "1m", "15m", "1h"')

    model_config = ConfigDict(frozen=True)

    @field_validator("timestamp", mode="before")
    @classmethod
    def _coerce_timestamp(cls, v: object) -> object:
        """
        Acepta int (ms o s) o datetime.
        - Si viene en segundos (heurística 10 dígitos), lo convierte a ms.
        - Si viene datetime, lo convierte a ms.
        """
        if isinstance(v, datetime):
            return int(v.timestamp() * 1000)
        if isinstance(v, int):
            return v * 1000 if v < 10_000_000_000 else v
        return v

class OrderBook(BaseModel):
    """Estructura opcional (futuro)."""

    bids: List[Tuple[float, float]] = Field(default_factory=list)
    asks: List[Tuple[float, float]] = Field(default_factory=list)
    timestamp: int

    model_config = ConfigDict(frozen=True)
