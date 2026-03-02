from __future__ import annotations

from abc import ABC
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .market import Candle
from .trading import Signal, Order

class Event(BaseModel, ABC):
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(frozen=True)

class MarketEvent(Event):
    candle: Candle

    model_config = ConfigDict(frozen=True)

class SignalEvent(Event):
    signal: Signal

    model_config = ConfigDict(frozen=True)

class OrderEvent(Event):
    order: Order

    model_config = ConfigDict(frozen=True)
