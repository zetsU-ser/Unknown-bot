from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["LONG", "SHORT"]
Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELED", "REJECTED", "OPEN"]

class Signal(BaseModel):
    """Señal de trade (inmutable)."""

    asset: str
    direction: Direction
    entry_price: float
    sl_price: float
    tp_price: float
    tier: str
    prob: float
    timestamp: int = Field(..., description="Milisegundos Unix (int)")

    model_config = ConfigDict(frozen=True)

class Order(BaseModel):
    """Orden (inmutable; cambios se hacen vía model_copy(update=...))."""

    id: str
    symbol: str
    direction: str
    qty: float
    entry_price: float
    status: str
    sl_id: Optional[str] = None
    tp_id: Optional[str] = None

    model_config = ConfigDict(frozen=True)

class Position(BaseModel):
    """Estado de posición (puede ser mutable según la capa de ejecución)."""

    asset: str
    side: Side
    entry_price: float
    qty: float
    unrealized_pnl: float

    model_config = ConfigDict()