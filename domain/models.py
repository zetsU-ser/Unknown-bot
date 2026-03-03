from __future__ import annotations
from typing import Literal, Optional, Any
from pydantic import BaseModel, ConfigDict, Field

Direction = Literal["LONG", "SHORT"]
Trend     = Literal["BULLISH", "BEARISH", "RANGING"]
Zone      = Literal["PREMIUM", "DISCOUNT", "EQUILIBRIUM"]
SwingDir  = Literal["BULL", "BEAR"]
OBType    = Literal["bullish", "bearish"]

class SweepInfo(BaseModel):
    sweep:      bool
    direction:  Optional[SwingDir] = None
    level:      Optional[float]    = None
    sweep_size: Optional[float]    = None
    model_config = ConfigDict(frozen=True)

class BosChochInfo(BaseModel):
    bos:        bool = False
    choch:      bool = False
    direction:  Optional[SwingDir] = None
    bos_bull:   bool = False
    bos_bear:   bool = False
    choch_bull: bool = False
    choch_bear: bool = False
    model_config = ConfigDict(frozen=True)

class FVGZones(BaseModel):
    bisi: list = Field(default_factory=list)
    sibi: list = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)

class OBTouch(BaseModel):
    touching: bool               = False
    type:     Optional[OBType] = None
    ob:       Optional[dict]   = None
    dist_pct: float            = 1.0
    model_config = ConfigDict(frozen=True)

class EqhEqlInfo(BaseModel):
    eqh:         list            = Field(default_factory=list)
    eql:         list            = Field(default_factory=list)
    eqh_swept:   bool            = False
    eql_swept:   bool            = False
    nearest_eqh: Optional[float] = None
    nearest_eql: Optional[float] = None
    model_config = ConfigDict(frozen=True)

class KeyLevels(BaseModel):
    nearest_resistance: Optional[float] = None
    nearest_support:    Optional[float] = None
    bullish_obs:        list = Field(default_factory=list)
    bearish_obs:        list = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)

class MarketContext(BaseModel):
    trend_15m: Trend
    zone_15m:  Zone
    trend_1h:  Trend
    zone_1h:   Zone
    priors:    dict
    sweep:     SweepInfo
    bos_choch: BosChochInfo
    fvg_1m:    FVGZones
    levels:    KeyLevels
    ob_touch:  OBTouch
    eqh_eql:   EqhEqlInfo
    model_config = ConfigDict(frozen=True)

class BarrierSet(BaseModel):
    sl:             float
    tp:             float
    rr:             float
    be_trigger:     float
    profit_lock_sl: float
    tier:           Optional[str] = None
    mult:           float         = 1.0
    max_bars:       int           = 360
    prob_min:       float         = 45.0
    model_config = ConfigDict(frozen=False)

class TradeState(BaseModel):
    active:     bool                   = False
    buy_price:  float                  = 0.0
    units:      float                  = 0.0
    max_p:      float                  = 0.0
    min_p:      float                  = 0.0
    bars_in_t:  int                    = 0
    barriers:   Optional[BarrierSet] = None
    be_on:      bool                   = False
    direction:  Optional[Direction]  = None
    mult:       float                  = 1.0
    bayes_prob: float                  = 0.0
    tier:       Optional[str]        = None
    trade_id:   int                    = -1
    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    def update(self, data: dict) -> None:
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
