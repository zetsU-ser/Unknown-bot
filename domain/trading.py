from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

Direction = Literal["LONG", "SHORT"]
Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]
OrderStatus = Literal["PENDING", "FILLED", "CANCELLED", "REJECTED"]

class Signal(BaseModel):
    asset: str
    direction: Direction
    entry_price: float
    sl_price: float
    tp_price: float
    tier: str
    prob: float
    timestamp: int

    model_config = ConfigDict(frozen=True)

class Order(BaseModel):
    order_id: Optional[str] = None
    asset: str
    side: Side
    qty: float
    order_type: OrderType
    status: OrderStatus = "PENDING"

    model_config = ConfigDict(frozen=True)

class Position(BaseModel):
    asset: str
    side: Side
    entry_price: float
    qty: float
    unrealized_pnl: float

    model_config = ConfigDict(frozen=True)
