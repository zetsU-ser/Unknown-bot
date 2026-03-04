from __future__ import annotations
import os
import json
import pickle
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
import numpy as np

# Suprimir logs intrusivos de TensorFlow en consola
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

from engine.event_bus import EventBus
from domain.events import MTFDataEvent, SignalEvent
from domain.trading import Signal
from core.strategy_manager import StrategyManager

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).resolve().parent.parent
MODEL_DIR   = BASE_DIR / "mlops" / "models"
MODEL_PATH  = MODEL_DIR / "meta_labeler_nn.keras"
SCALER_PATH = MODEL_DIR / "scaler.pkl"

G, R, Y, B, RS = "\033[92m", "\033[91m", "\033[93m", "\033[1m", "\033[0m"

class MetaLabelerFilter:
    """
    Carga la Red Tri-Neuronal y filtra señales en tiempo real.
    Implementa un patrón Singleton y reconstrucción exacta de tensores.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MetaLabelerFilter, cls).__new__(cls)
            cls._instance._model = None
            cls._instance._scaler = None
            cls._instance._threshold = 0.68
            cls._instance._available = False
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        
        if not MODEL_PATH.exists() or not SCALER_PATH.exists():
            print(f"{Y}[MetaLabeler] Artefactos no encontrados en {MODEL_DIR} -> FALLBACK: Operando solo con Oráculos SMC{RS}")
            return
        try:
            import tensorflow as tf
            self._model = tf.keras.models.load_model(str(MODEL_PATH))
            with open(SCALER_PATH, "rb") as f:
                self._scaler = pickle.load(f)
            self._available = True
            print(f"{G}{B}[MetaLabeler] Red Tri-Neuronal y Scaler cargados en memoria. Juez Supremo ACTIVO.{RS}")
        except Exception as e:
            print(f"{R}[!] Error cargando Juez Supremo: {e} -> FALLBACK ACTIVADO{RS}")
            self._available = False

    def approve(self, signal: Signal, data: dict) -> bool:
        if not self._available:
            return True  # Fallback: Aprobación por defecto si no hay IA

        try:
            # 1. Feature Engineering en vivo (Alineado milimétricamente)
            features = self._build_feature_vector(signal, data)
            
            # 2. Normalización Z-Score estricta
            features_scaled = self._scaler.transform(features)
            
            # 3. Predicción (Inferencia Forward Pass)
            prob = self._model.predict(features_scaled, verbose=0)[0][0]

            # 4. Filtro de Decisión (SILENCIADO PARA ALTO RENDIMIENTO EN BACKTEST)
            if prob < self._threshold:
                # print(f"{R}[Juez Supremo] SEÑAL VETADA | Prob. Éxito: {prob:.2%} (Mínimo requerido: {self._threshold:.2%}){RS}")
                return False
            
            # print(f"{G}[Juez Supremo] SEÑAL APROBADA | Prob. Éxito: {prob:.2%}{RS}")
            return True

        except Exception as e:
            # Solo imprimimos errores críticos estructurales
            print(f"{R}[!] Error crítico en Inferencia (Tensor desalineado): {e} -> Vetando por seguridad de capital{RS}")
            return False

    def _build_feature_vector(self, signal: Signal, data: dict) -> np.ndarray:
        """
        Reconstruye la instantánea del mercado incluyendo el tiempo real.
        """
        ctx  = data.get("ctx")
        c1m  = data.get("df_1m").tail(1).to_dicts()[0]  if "df_1m"  in data and len(data["df_1m"])  > 0 else {}
        c15m = data.get("df_15m").tail(1).to_dicts()[0] if "df_15m" in data and len(data["df_15m"]) > 0 else {}
        c1h  = data.get("df_1h").tail(1).to_dicts()[0]  if "df_1h"  in data and len(data["df_1h"])  > 0 else {}
        c4h  = data.get("df_4h").tail(1).to_dicts()[0]  if "df_4h"  in data and len(data["df_4h"])  > 0 else {}
        c1d  = data.get("df_1d").tail(1).to_dicts()[0]  if "df_1d"  in data and len(data["df_1d"])  > 0 else {}

        curr_p = signal.entry_price

        def pct_dist(a: float, b: float) -> float:
            return float(((a - b) / b * 100) if b and b != 0 else 0.0)

        # Mapas categóricos
        trend_map = {"BULLISH": 1, "BEARISH": -1, "RANGING": 0}
        zone_map  = {"PREMIUM": 1, "DISCOUNT": -1, "EQUILIBRIUM": 0}
        div_map   = {"BULL_DIV": 1, "BEAR_DIV": -1, "NORMAL": 0, "NEUTRAL": 0}

        sl = float(signal.sl_price)
        tp = float(signal.tp_price)
        risk_pct = abs(pct_dist(curr_p, sl))
        
        # Extracción temporal exacta (Unix ms a hora/día)
        dt = datetime.fromtimestamp(signal.timestamp / 1000.0)
        hora_dia = dt.hour
        dia_semana = dt.weekday()

        vector = [
            # -- Geometría
            curr_p, sl, tp, 
            abs((tp - curr_p) / (curr_p - sl)) if (curr_p - sl) != 0 else 0.0, 
            risk_pct, 0.0, 0.0, signal.prob, 1.0, 

            # -- Layer 1m
            c1m.get("rsi", 0.0), c1m.get("atr", 0.0), c1m.get("adx", 0.0), 
            c1m.get("z_score", 0.0), c1m.get("vol_ratio", 0.0), c1m.get("cvd", 0.0),
            pct_dist(curr_p, c1m.get("vwap", curr_p)),
            1 if c1m.get("sweep_detected") else 0,
            c1m.get("sweep_direction", 0),

            # -- Layer 15m
            c15m.get("rsi", 0.0), c15m.get("atr", 0.0), c15m.get("adx", 0.0), c15m.get("cvd", 0.0),
            pct_dist(curr_p, c15m.get("vwap", curr_p)),
            trend_map.get(getattr(ctx, "trend_15m", "RANGING"), 0),
            zone_map.get(getattr(ctx, "zone_15m", "EQUILIBRIUM"), 0),

            # -- Layer 1h
            c1h.get("rsi", 0.0), c1h.get("adx", 0.0),
            c1h.get("ema_trend", curr_p), pct_dist(curr_p, c1h.get("ema_trend", curr_p)),

            # -- Layer 4h
            c4h.get("rsi", 0.0), c4h.get("atr", 0.0), c4h.get("adx", 0.0),
            c4h.get("ema_trend", curr_p), pct_dist(curr_p, c4h.get("ema_trend", curr_p)),

            # -- Layer 1d
            c1d.get("rsi", 0.0), c1d.get("atr", 0.0), c1d.get("adx", 0.0),
            c1d.get("ema_trend", curr_p), pct_dist(curr_p, c1d.get("ema_trend", curr_p)),

            # -- Volume Intelligence
            div_map.get(c1m.get("vol_divergence", "NEUTRAL"), 0),
            
            # -- Temporal Features
            hora_dia,
            dia_semana
        ]
        
        arr = np.array(vector, dtype=float)

        # Validación de integridad del tensor
        if hasattr(self._scaler, 'feature_names_in_'):
            expected_features = len(self._scaler.feature_names_in_)
            if len(arr) != expected_features:
                raise ValueError(f"Desfase de características. Esperadas: {expected_features}, Recibidas: {len(arr)}")

        return arr.reshape(1, -1)

class DecisionEngine:
    """
    Recibe MTFDataEvent -> Evalúa Oráculos -> Filtra con ML -> Publica SignalEvent.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus        = event_bus
        self.strategy_manager = StrategyManager()
        self.meta_filter      = MetaLabelerFilter()
        self._total_signals   = 0
        self._approved        = 0
        self._blocked         = 0
        self.event_bus.subscribe(MTFDataEvent, self.handle_mtf_data)

    def handle_mtf_data(self, event: MTFDataEvent) -> None:
        signal_obj = self.strategy_manager.evaluate_all(event.data)
        if signal_obj is None:
            return

        self._total_signals += 1

        if self.meta_filter.approve(signal_obj, event.data):
            self._approved += 1
            self.event_bus.publish(SignalEvent(signal=signal_obj))
        else:
            self._blocked += 1

    @property
    def filter_stats(self) -> dict:
        total = max(self._total_signals, 1)
        return {
            "total_signals" : self._total_signals,
            "approved"      : self._approved,
            "blocked"       : self._blocked,
            "block_rate_pct": round(self._blocked / total * 100, 2)
        }