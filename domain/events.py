from __future__ import annotations

import time
from abc import ABC
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from .market import Candle
from .trading import Order, Signal


class Event(BaseModel, ABC):
    """
    Evento base (inmutable). 
    Estandarizado a milisegundos Unix para evitar colapsos de serialización.
    """
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
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
    """
    data: Dict[str, Any]
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)