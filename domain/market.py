from __future__ import annotations 

from datetime import datetime 
from typing import List, Tuple, Union 

from pydantic import BaseModel, ConfigDict 

TimestampType = Union[int, datetime] 

class Candle(BaseModel): 
    timestamp: TimestampType 
    open: float 
    high: float 
    low: float 
    close: float 
    volume: float 
    timeframe: str 

    model_config = ConfigDict(frozen=True) 

class OrderBook(BaseModel): 
    bids: List[Tuple[float, float]] 
    asks: List[Tuple[float, float]] 
    timestamp: int 

    model_config = ConfigDict(frozen=True) 
