"""
Caja Negra (Blackbox) — UNKNOWN-BOT — IA1 Foundation
=====================================================
Captura el "ADN" del mercado en el momento exacto de cada trade.
Tarea: Fotografiar el estado completo de todos los indicadores vectoriales
       en el instante de apertura, y etiquetar el resultado al cierre.

Output: Parquet estructurado de alta dimensionalidad para entrenamiento
        del Laboratorio Genético (IA2) con XGBoost / Random Forest / LSTM.

Arquitectura de Features (Fractal V11):
  ├── Identity   (trade_id, timestamp, direction)
  ├── Geometry   (entry, sl, tp, rr_expected, be_trigger)
  ├── Bayesian   (prob_bayesian, tier_mult)
  ├── Layer 1m   (rsi, atr, adx, z_score, vol_ratio, cvd, vwap_dist, sweep)
  ├── Layer 15m  (rsi, atr, adx, cvd, vwap_dist, trend, zone, vol_div)
  ├── Layer 1h   (rsi, adx, ema_dist_pct)
  ├── Layer 4h   (rsi, atr, adx, ema_dist_pct)  <-- NUEVO
  ├── Layer 1d   (rsi, atr, adx, ema_dist_pct)  <-- NUEVO
  └── Labels     (outcome, pnl_pct, exit_reason, bars_in_trade, rr_realized)
"""

import numpy as np
import polars as pl
from analysis.market_structure import detect_regime, detect_liquidity_sweep
from analysis.volume_profile import detect_volume_divergence


# ── CONSTANTES ────────────────────────────────────────────────────────────────
VERSION = "1.1"
FEATURE_COLS = [
    # Geometry
    "rr_expected", "be_trigger_dist_pct",
    # Bayesian
    "prob_bayesian", "tier_mult",
    # 1m Layer
    "rsi_1m", "atr_1m", "adx_1m", "z_score_1m", "vol_ratio_1m",
    "cvd_1m", "vwap_dist_1m_pct", "sweep_detected",
    # 15m Layer
    "rsi_15m", "atr_15m", "adx_15m", "cvd_15m", "vwap_dist_15m_pct",
    # 1h Layer
    "rsi_1h", "adx_1h", "ema_dist_1h_pct",
    # 4h Layer
    "rsi_4h", "atr_4h", "adx_4h", "ema_dist_4h_pct",
    # 1d Layer
    "rsi_1d", "atr_1d", "adx_1d", "ema_dist_1d_pct",
]
LABEL_COL = "outcome"


class TradeBlackbox:
    """
    Grabadora de Caja Negra para el Agente Ejecutor (IA1).
    """

    def __init__(self):
        self.records: list[dict] = []
        self._next_id: int = 0

    # ─────────────────────────────────────────────────────────────────────────
    def capture_entry(
        self,
        timestamp: int,
        entry_price: float,
        direction: str,
        barriers: dict,
        prob: float,
        mult: float,
        df_1m: pl.DataFrame,
        df_15m: pl.DataFrame,
        df_1h: pl.DataFrame,
        df_4h: pl.DataFrame,
        df_1d: pl.DataFrame,
    ) -> int:
        """
        Fotografía instantánea del estado del mercado en el momento de entrada.
        """
        trade_id = self._next_id
        self._next_id += 1

        # ── Extraer valores de la última vela de cada capa ────────────────
        c1m  = df_1m.tail(1).to_dicts()[0]  if len(df_1m)  > 0 else {}
        c15m = df_15m.tail(1).to_dicts()[0] if len(df_15m) > 0 else {}
        c1h  = df_1h.tail(1).to_dicts()[0]  if len(df_1h)  > 0 else {}
        c4h  = df_4h.tail(1).to_dicts()[0]  if len(df_4h)  > 0 else {}
        c1d  = df_1d.tail(1).to_dicts()[0]  if len(df_1d)  > 0 else {}

        curr_p   = c1m.get("close", entry_price)
        vwap_1m  = c1m.get("vwap",  curr_p)
        vwap_15m = c15m.get("vwap", curr_p)
        
        ema_1h   = c1h.get("ema_trend", curr_p)
        ema_4h   = c4h.get("ema_trend", curr_p)
        ema_1d   = c1d.get("ema_trend", curr_p)

        # ── Señales de estructura ─────────────────────────────────────────
        regime   = detect_regime(df_15m)
        sweep    = detect_liquidity_sweep(df_1m)
        vol_div  = detect_volume_divergence(df_1m, lookback=10)

        # ── Distancias porcentuales normalizadas ──────────────────────────
        def pct_dist(a: float, b: float) -> float:
            return float(((a - b) / b * 100) if b and b != 0 else np.nan)

        sl   = float(barriers.get("sl", 0.0))
        tp   = float(barriers.get("tp", 0.0))
        rr   = float(barriers.get("rr", 0.0))
        be_t = float(barriers.get("be_trigger", 0.0))

        risk_pct    = abs(pct_dist(entry_price, sl))
        be_dist_pct = abs(pct_dist(be_t, entry_price))

        # ── Mapa a numérico ───────────────────────────────────────────────
        div_map = {"BULL_DIV": 1, "BEAR_DIV": -1, "NORMAL": 0, "NEUTRAL": 0}
        div_num = div_map.get(vol_div, 0)

        sweep_dir_map = {"BULL": 1, "BEAR": -1, None: 0}
        sweep_dir = sweep_dir_map.get(sweep.get("direction"), 0)

        trend_map = {"BULLISH": 1, "BEARISH": -1, "RANGING": 0}
        zone_map  = {"PREMIUM": 1, "DISCOUNT": -1, "EQUILIBRIUM": 0}

        snapshot = {
            # ── Identity ──────────────────────────────────────────────────
            "trade_id":  trade_id,
            "timestamp": str(timestamp),
            "direction": direction,

            # ── Geometry ──────────────────────────────────────────────────
            "entry_price":       entry_price,
            "sl":                sl,
            "tp":                tp,
            "rr_expected":       rr,
            "risk_pct":          risk_pct,
            "be_trigger":        be_t,
            "be_trigger_dist_pct": be_dist_pct,

            # ── Bayesian ──────────────────────────────────────────────────
            "prob_bayesian": prob,
            "tier_mult":     mult,

            # ── Layer 1m: SNIPER ──────────────────────────────────────────
            "rsi_1m":         c1m.get("rsi",       np.nan),
            "atr_1m":         c1m.get("atr",       np.nan),
            "adx_1m":         c1m.get("adx",       np.nan),
            "z_score_1m":     c1m.get("z_score",   np.nan),
            "vol_ratio_1m":   c1m.get("vol_ratio", np.nan),
            "cvd_1m":         c1m.get("cvd",       np.nan),
            "vwap_dist_1m_pct": pct_dist(curr_p, vwap_1m),
            "sweep_detected": 1 if sweep.get("sweep") else 0,
            "sweep_direction": sweep_dir,

            # ── Layer 15m: STRUCTURE ──────────────────────────────────────
            "rsi_15m":           c15m.get("rsi",      np.nan),
            "atr_15m":           c15m.get("atr",      np.nan),
            "adx_15m":           c15m.get("adx",      np.nan),
            "cvd_15m":           c15m.get("cvd",      np.nan),
            "vwap_dist_15m_pct": pct_dist(curr_p, vwap_15m),
            "trend_15m":         trend_map.get(regime.get("trend"), 0),
            "zone_15m":          zone_map.get(regime.get("zone"),   0),
            "trend_15m_raw":     regime.get("trend", "RANGING"),
            "zone_15m_raw":      regime.get("zone",  "EQUILIBRIUM"),

            # ── Layer 1h: MACRO ───────────────────────────────────────────
            "rsi_1h":         c1h.get("rsi", np.nan),
            "adx_1h":         c1h.get("adx", np.nan),
            "ema_trend_1h":   ema_1h,
            "ema_dist_1h_pct": pct_dist(curr_p, ema_1h),

            # ── Layer 4h: SWING (El Techo de Cristal) ─────────────────────
            "rsi_4h":         c4h.get("rsi", np.nan),
            "atr_4h":         c4h.get("atr", np.nan),
            "adx_4h":         c4h.get("adx", np.nan),
            "ema_trend_4h":   ema_4h,
            "ema_dist_4h_pct": pct_dist(curr_p, ema_4h),

            # ── Layer 1d: MACRO ANCHOR (El Jefe Final) ────────────────────
            "rsi_1d":         c1d.get("rsi", np.nan),
            "atr_1d":         c1d.get("atr", np.nan),
            "adx_1d":         c1d.get("adx", np.nan),
            "ema_trend_1d":   ema_1d,
            "ema_dist_1d_pct": pct_dist(curr_p, ema_1d),

            # ── Volume Intelligence ───────────────────────────────────────
            "vol_divergence":     vol_div,
            "vol_divergence_num": div_num,

            # ── Exit Labels (se llenan en label_exit) ─────────────────────
            "outcome":      -1,       
            "pnl_pct":      np.nan,
            "exit_reason":  None,
            "bars_in_trade": -1,
            "rr_realized":  np.nan,
        }

        self.records.append(snapshot)
        return trade_id

    # ─────────────────────────────────────────────────────────────────────────
    def label_exit(self, trade_id: int, pnl: float, reason: str, bars: int):
        if trade_id < 0 or trade_id >= len(self.records):
            return

        rec = self.records[trade_id]
        entry_p = rec["entry_price"]
        sl      = rec["sl"]

        risk_abs = abs(entry_p - sl) if sl and sl != 0 else 1.0
        pnl_abs  = abs(pnl) / 100.0 * entry_p
        rr_real  = (pnl_abs / risk_abs) * (1 if pnl >= 0 else -1)

        rec["outcome"]       = 1 if pnl > 0 else 0
        rec["pnl_pct"]       = round(pnl, 6)
        rec["exit_reason"]   = reason
        rec["bars_in_trade"] = bars
        rec["rr_realized"]   = round(rr_real, 4)

    # ─────────────────────────────────────────────────────────────────────────
    def export_parquet(self, path: str) -> pl.DataFrame:
        if not self.records:
            print("[BLACKBOX] ⚠️  Sin registros para exportar.")
            return None

        labeled = [r for r in self.records if r["outcome"] != -1]
        if not labeled:
            print("[BLACKBOX] ⚠️  Ningún trade fue etiquetado.")
            return None

        df = pl.DataFrame(labeled)
        df.write_parquet(path)

        wins = len([r for r in labeled if r["outcome"] == 1])
        losses = len(labeled) - wins

        print(f"\n  [BLACKBOX] ✓ Dataset ADN exportado → {path}")
        print(f"  [BLACKBOX]   Trades: {len(labeled)} | Wins: {wins} | Losses: {losses}")
        print(f"  [BLACKBOX]   Features capturadas por trade: {len(df.columns)}")
        print(f"  [BLACKBOX]   Tamaño del archivo: {df.estimated_size('mb'):.2f} MB")

        return df

    # ─────────────────────────────────────────────────────────────────────────
    def get_summary(self) -> dict:
        labeled = [r for r in self.records if r["outcome"] != -1]
        if not labeled:
            return {"total": 0, "labeled": 0}

        wins   = [r for r in labeled if r["outcome"] == 1]
        losses = [r for r in labeled if r["outcome"] == 0]

        pnls = [r["pnl_pct"] for r in labeled if not np.isnan(r["pnl_pct"])]

        return {
            "total":      len(self.records),
            "labeled":    len(labeled),
            "unlabeled":  len(self.records) - len(labeled),
            "wins":       len(wins),
            "losses":     len(losses),
            "win_rate":   round(len(wins) / len(labeled) * 100, 2),
            "avg_pnl":    round(float(np.mean(pnls)), 4) if pnls else 0,
            "n_features": len(FEATURE_COLS),
            "version":    VERSION,
        }

    # ─────────────────────────────────────────────────────────────────────────
    def get_feature_importance_preview(self) -> None:
        labeled = [r for r in self.records if r["outcome"] != -1]
        if not labeled:
            print("[BLACKBOX] Sin datos para análisis de features.")
            return

        wins   = [r for r in labeled if r["outcome"] == 1]
        losses = [r for r in labeled if r["outcome"] == 0]

        print(f"\n  {'FEATURE':<25} | {'WIN_AVG':>8} | {'LOSS_AVG':>9} | {'DELTA':>8} | {'STATUS'}")
        print(f"  {'-'*25}-+-{'-'*8}-+-{'-'*9}-+-{'-'*8}-+-{'-'*10}")

        for feat in FEATURE_COLS:
            w_vals = [r[feat] for r in wins   if isinstance(r.get(feat), (int, float)) and not np.isnan(r.get(feat, np.nan))]
            l_vals = [r[feat] for r in losses if isinstance(r.get(feat), (int, float)) and not np.isnan(r.get(feat, np.nan))]

            if not w_vals or not l_vals:
                print(f"  {feat:<25} | {'N/A':>8} | {'N/A':>9} | {'N/A':>8} | ⚪ SIN DATA")
                continue

            w_avg = np.mean(w_vals)
            l_avg = np.mean(l_vals)
            delta = abs(w_avg - l_avg)

            global_avg = np.mean(w_vals + l_vals)
            relevance = delta / (abs(global_avg) + 1e-9)

            if relevance > 0.15:   status = "🟢 ALTA SEÑAL"
            elif relevance > 0.05: status = "🟡 SEÑAL MEDIA"
            else:                  status = "🔴 RUIDO"

            print(f"  {feat:<25} | {w_avg:>8.3f} | {l_avg:>9.3f} | {delta:>8.3f} | {status}")