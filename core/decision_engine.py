from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from engine.event_bus import EventBus
from domain.events import MTFDataEvent, SignalEvent
from domain.trading import Signal
from core.strategy_manager import StrategyManager

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).resolve().parent.parent
MODEL_DIR   = BASE_DIR / "mlops" / "models"
MODEL_PATH  = MODEL_DIR / "meta_labeler.json"
CONFIG_PATH = MODEL_DIR / "meta_labeler_config.json"


# ── META-LABELER FILTER (EL JUEZ SUPREMO) ─────────────────────────────────────

class MetaLabelerFilter:
    """Carga el XGBoost entrenado y filtra señales en tiempo real."""

    def __init__(self) -> None:
        self._model      = None
        self._threshold  = 0.60
        self._feat_names: list[str] = []
        self._available  = False
        self._load()

    def _load(self) -> None:
        try:
            import xgboost as xgb
            if not MODEL_PATH.exists():
                print(f"\033[93m[MetaLabeler] Modelo no encontrado en {MODEL_PATH} -> PASS-THROUGH\033[0m")
                return
            self._model = xgb.XGBClassifier()
            self._model.load_model(str(MODEL_PATH))
            if CONFIG_PATH.exists():
                cfg = json.loads(CONFIG_PATH.read_text())
                self._threshold  = cfg.get("threshold", 0.60)
                self._feat_names = cfg.get("feature_names", [])
                prec = cfg.get("precision_final", cfg.get("precision_at_thresh", 0.0))
                print(f"\033[92m[MetaLabeler] Juez Supremo Cargado. Umbral={self._threshold:.2f} | Prec={prec * 100:.1f}%\033[0m")
            self._available = True
        except Exception as exc:
            print(f"\033[91m[MetaLabeler] Error al cargar: {exc} -> PASS-THROUGH\033[0m")

    def approve(self, signal: Signal, data: dict) -> bool:
        """True = aprobar trade; False = bloquear."""
        if not self._available or self._model is None:
            return True
        try:
            vec = self._build_vector(signal, data)
            if vec is None:
                return True
            
            prob     = self._model.predict_proba(vec)[0, 1]
            aprobado = bool(prob >= self._threshold)
            
            # Print visual en consola para ver a la IA trabajando
            color = "\033[92m" if aprobado else "\033[91m"
            estado = "APROBADO " if aprobado else "BLOQUEADO"
            # print(f"  {color}[Juez ML] {estado} | {signal.tier} {signal.direction} | Confianza: {prob*100:.1f}% (Min: {self._threshold*100:.0f}%)\033[0m")
            
            return aprobado
        except Exception as exc:
            print(f"\033[91m[MetaLabeler] Error inferencia: {exc} -> pass-through\033[0m")
            return True

    def _build_vector(self, signal: Signal, data: dict) -> Optional[np.ndarray]:
        candles: dict[str, dict] = {}
        for tf in ("1m", "15m", "1h", "4h", "1d"):
            df = data.get(tf)
            if df is not None and len(df) > 0:
                try:
                    # Extracción O(1) del último elemento
                    candles[tf] = {col: df[col][-1] for col in df.columns}
                except Exception:
                    pass

        flat: dict[str, float] = {
            "entry_price"   : float(signal.entry_price),
            "sl_price"      : float(signal.sl_price),
            "tp_price"      : float(signal.tp_price),
            "prob_bayesian" : float(signal.prob),
            "rr_expected"   : (
                abs(signal.tp_price - signal.entry_price)
                / max(abs(signal.entry_price - signal.sl_price), 1e-9)
            ),
        }
        for tf, candle in candles.items():
            for col, val in candle.items():
                try:
                    # FIX ARQUITECTONICO: Formato exacto del DataPrep (ej: rsi_1m)
                    flat[f"{col}_{tf}"] = float(val) if val is not None else 0.0
                except (TypeError, ValueError):
                    flat[f"{col}_{tf}"] = 0.0

        if self._feat_names:
            row = [flat.get(f, 0.0) for f in self._feat_names]
        else:
            fallback_keys = ["rsi", "adx", "atr", "cvd", "vwap", "vol_ratio"]
            row = []
            for tf in ("1m", "15m", "1h"):
                candle = candles.get(tf, {})
                for k in fallback_keys:
                    row.append(float(candle.get(k, 0.0) or 0.0))
            if not row:
                return None

        return np.array(row, dtype=np.float32).reshape(1, -1)

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def threshold(self) -> float:
        return self._threshold


# ── DECISION ENGINE ───────────────────────────────────────────────────────────

class DecisionEngine:
    """
    Recibe MTFDataEvent -> evalua oracles -> filtra con ML -> publica SignalEvent.
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
        # 1. Evaluacion tecnica (3 oracles)
        signal_obj = self.strategy_manager.evaluate_all(event.data)
        if signal_obj is None:
            return

        self._total_signals += 1

        # 2. Filtro ML: Juez Supremo
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
            "block_rate_pct": round(self._blocked / total * 100, 1),
            "ml_available"  : self.meta_filter.is_available,
            "threshold"     : self.meta_filter.threshold,
        }