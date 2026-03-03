from __future__ import annotations

from abc import ABC
from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from .market import Candle
from .trading import Order, Signal

class Event(BaseModel, ABC):
    """Evento base (inmutable)."""

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

class MTFDataEvent(Event):
    """
    Evento puente para transportar slices MTF (ej: DataFrames Polars).
    Permitimos tipos arbitrarios temporalmente.
    """

    data: Dict[str, Any]
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
