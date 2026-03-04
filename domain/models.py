from __future__ import annotations
from typing import Literal, Optional, Any, List, Dict
from pydantic import BaseModel, ConfigDict, Field

# --- Tipos Personalizados ---
Direction = Literal["LONG", "SHORT"]
Trend     = Literal["BULLISH", "BEARISH", "RANGING"]
Zone      = Literal["PREMIUM", "DISCOUNT", "EQUILIBRIUM"]
SwingDir  = Literal["BULL", "BEAR"]
OBType    = Literal["bullish", "bearish"]

# --- Sub-Modelos para Tipado Estricto (Fin de Cajas Negras) ---

class FVGZone(BaseModel):
    """Representa un Fair Value Gap detectado."""
    top: float
    bottom: float
    size: float
    idx: int
    recency: int
    model_config = ConfigDict(frozen=True)

class OrderBlock(BaseModel):
    """Representa un bloque de órdenes institucional."""
    top: float
    bottom: float
    recency: int
    model_config = ConfigDict(frozen=True)

class SweepInfo(BaseModel):
    """Información sobre barridos de liquidez (SFP)."""
    sweep:      bool
    direction:  Optional[SwingDir] = None
    level:      Optional[float]    = None
    sweep_size: Optional[float]    = None
    model_config = ConfigDict(frozen=True)

class BosChochInfo(BaseModel):
    """Información sobre rompimientos de estructura (SMC)."""
    bos:        bool = False
    choch:      bool = False
    direction:  Optional[SwingDir] = None
    bos_bull:   bool = False
    bos_bear:   bool = False
    choch_bull: bool = False
    choch_bear: bool = False
    model_config = ConfigDict(frozen=True)

class FVGZones(BaseModel):
    """Colección de zonas FVG filtradas."""
    bisi: List[FVGZone] = Field(default_factory=list)
    sibi: List[FVGZone] = Field(default_factory=list)
    model_config = ConfigDict(frozen=True)

class KeyLevels(BaseModel):
    """Niveles clave de soporte, resistencia y Order Blocks."""
    bullish_obs: List[OrderBlock] = Field(default_factory=list)
    bearish_obs: List[OrderBlock] = Field(default_factory=list)
    nearest_resistance: Optional[float] = None
    nearest_support: Optional[float] = None
    model_config = ConfigDict(frozen=True)

class OBTouch(BaseModel):
    """Estado de contacto actual con un Order Block."""
    touching: bool               = False
    type:     Optional[OBType] = None
    ob:       Optional[OrderBlock] = None
    dist_pct: float            = 1.0
    model_config = ConfigDict(frozen=True)

class EqhEqlInfo(BaseModel):
    """Información de liquidez acumulada en máximos/mínimos iguales."""
    eqh: List[float] = Field(default_factory=list)
    eql: List[float] = Field(default_factory=list)
    eqh_swept: bool = False
    eql_swept: bool = False
    nearest_eqh: Optional[float] = None
    nearest_eql: Optional[float] = None
    model_config = ConfigDict(frozen=True)

# --- Modelo Principal de Contexto ---

class MarketContext(BaseModel):
    """
    Contrato de datos estricto para el Orquestador y el Feature Store de MLOps.
    Mantiene la jerarquía MTF (Multi-Timeframe).
    """
    trend_15m: Trend
    zone_15m:  Zone
    trend_1h:  Trend
    zone_1h:   Zone
    priors:    Dict[str, float]
    sweep:     SweepInfo
    bos_choch: BosChochInfo
    fvg_1m:    FVGZones
    levels:    KeyLevels
    ob_touch:  OBTouch
    eqh_eql:   EqhEqlInfo
    model_config = ConfigDict(frozen=True)

# --- Modelos de Trading y Estado ---

class BarrierSet(BaseModel):
    """Conjunto dinámico de barreras de riesgo para una operación."""
    sl:             float
    tp:             float
    rr:             float
    be_trigger:     float
    profit_lock_sl: float
    tier:           Optional[str] = None
    mult:           float         = 1.0
    max_bars:       int           = 360
    prob_min:       float         = 45.0
    model_config = ConfigDict(frozen=False) # Permite actualizaciones dinámicas del Risk Manager

class TradeState(BaseModel):
    """Estado persistente de la posición activa en el bot."""
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
    tier:       Optional[str]          = None
    model_config = ConfigDict(frozen=False)