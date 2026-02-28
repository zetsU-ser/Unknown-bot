import os
import polars as pl
import numpy as np
import math
import datetime

import configs.btc_usdt_config as config
from analysis.market_structure import get_full_market_ctx, detect_regime, detect_liquidity_sweep
from analysis.volume_profile import detect_volume_divergence
from core.risk_manager import compute_barriers
from core.strategy_manager import StrategyManager

# ── CARGA DEL JUEZ SUPREMO (LA IA) EN MEMORIA ──
try:
    import xgboost as xgb
    MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mlops", "models", "meta_labeler.json")
    _juez_supremo = xgb.XGBClassifier()
    if os.path.exists(MODEL_PATH):
        _juez_supremo.load_model(MODEL_PATH)
    else:
        _juez_supremo = None
except ImportError:
    _juez_supremo = None

_ctx_cache = {"ts_key": None, "ctx": None}

def _get_ctx_cached(df_1m, df_15m, df_1h):
    try:
        ts_key = df_15m["timestamp"].to_list()[-1]
    except Exception:
        return None

    if _ctx_cache.get("ts_key") == ts_key:
        return _ctx_cache["ctx"]
        
    try:
        ctx = get_full_market_ctx(df_1m, df_15m, df_1h)
    except Exception as e:
        print(f"\n\033[91m[CRÍTICO] Fallo interno en SMC Context: {e}\033[0m")
        ctx = None
        
    _ctx_cache["ts_key"] = ts_key
    _ctx_cache["ctx"]    = ctx
    return ctx

def _build_ml_tensor(df_1m, df_15m, df_1h, df_4h, df_1d, entry_price, barriers, prob):
    """
    Reconstruye el ADN exacto (42 variables) en el milisegundo de la entrada 
    para pasárselo a XGBoost, manteniendo el orden estricto de la Caja Negra.
    """
    c1m = df_1m.tail(1).to_dicts()[0]
    c15m = df_15m.tail(1).to_dicts()[0]
    c1h = df_1h.tail(1).to_dicts()[0]
    c4h = df_4h.tail(1).to_dicts()[0]
    c1d = df_1d.tail(1).to_dicts()[0]
    
    curr_p = c1m.get("close", entry_price)
    vwap_1m = c1m.get("vwap", curr_p)
    vwap_15m = c15m.get("vwap", curr_p)
    ema_1h = c1h.get("ema_trend", curr_p)
    ema_4h = c4h.get("ema_trend", curr_p)
    ema_1d = c1d.get("ema_trend", curr_p)
    
    regime = detect_regime(df_15m)
    sweep = detect_liquidity_sweep(df_1m)
    vol_div = detect_volume_divergence(df_1m, lookback=10)
    
    def pct_dist(a, b): return ((a - b) / b * 100) if b and b != 0 else 0.0
    
    sl = barriers.get("sl", 0)
    tp = barriers.get("tp", 0)
    rr = barriers.get("rr", 0)
    be_t = barriers.get("be_trigger", 0)
    
    risk_pct = abs(pct_dist(entry_price, sl))
    be_dist_pct = abs(pct_dist(be_t, entry_price))
    
    div_map = {"BULL_DIV": 1, "BEAR_DIV": -1, "NORMAL": 0}
    sweep_dir_map = {"BULL": 1, "BEAR": -1, None: 0}
    trend_map = {"BULLISH": 1, "BEARISH": -1, "RANGING": 0}
    zone_map  = {"PREMIUM": 1, "DISCOUNT": -1, "EQUILIBRIUM": 0}
    
    # Manejo robusto del tiempo para la IA
    ts_val = c1m.get("timestamp")
    if isinstance(ts_val, datetime.datetime):
        hora_dia = ts_val.hour
        dia_semana = ts_val.isoweekday() # 1=Lunes, 7=Domingo (Igual que Polars)
    else:
        ts_series = pl.Series([str(ts_val)]).str.to_datetime(strict=False)
        hora_dia = ts_series.dt.hour()[0]
        dia_semana = ts_series.dt.weekday()[0]
        
    tier = barriers.get("tier", "SCOUT")
    default_mult = config.SCOUT_MULT if tier == "SCOUT" else (config.AMBUSH_MULT if tier == "AMBUSH" else config.UNICORN_MULT)
    mult = barriers.get("mult", default_mult)
    
    features = [
        entry_price, sl, tp, rr, risk_pct, be_t, be_dist_pct,
        prob, mult,
        c1m.get("rsi", np.nan), c1m.get("atr", np.nan), c1m.get("adx", np.nan), c1m.get("z_score", np.nan), c1m.get("vol_ratio", np.nan), c1m.get("cvd", np.nan), pct_dist(curr_p, vwap_1m), 1 if sweep["sweep"] else 0, sweep_dir_map.get(sweep.get("direction"), 0),
        c15m.get("rsi", np.nan), c15m.get("atr", np.nan), c15m.get("adx", np.nan), c15m.get("cvd", np.nan), pct_dist(curr_p, vwap_15m), trend_map.get(regime.get("trend"), 0), zone_map.get(regime.get("zone"), 0),
        c1h.get("rsi", np.nan), c1h.get("adx", np.nan), ema_1h, pct_dist(curr_p, ema_1h),
        c4h.get("rsi", np.nan), c4h.get("atr", np.nan), c4h.get("adx", np.nan), ema_4h, pct_dist(curr_p, ema_4h),
        c1d.get("rsi", np.nan), c1d.get("atr", np.nan), c1d.get("adx", np.nan), ema_1d, pct_dist(curr_p, ema_1d),
        div_map.get(vol_div, 0),
        hora_dia, dia_semana
    ]
    
    return np.array([features], dtype=np.float32)

# ── INSTANCIAMOS EL DIRECTOR TÉCNICO ──
strategy_manager = StrategyManager()
_DIAG = {"n": 0, "shown": 0, "entries": 0}

def check_mtf_signals(df_1m, df_15m, df_1h, df_4h, df_1d, trade_state: dict = None):
    _DIAG["n"] += 1
    
    if len(df_1m) < 100 or len(df_15m) < 30:
        return _log_diag("WAIT", "WARMUP_DATAFRAMES", None, 0.0, "NONE")

    c1m  = df_1m.tail(1).to_dicts()[0]
    c1h  = df_1h.tail(1).to_dicts()[0]
    c15m = df_15m.tail(1).to_dicts()[0]

    ema_trend = c1h.get("ema_trend", 0.0)
    entry_p   = c1m.get("close", 0) or 0

    if ema_trend is None or math.isnan(ema_trend) or ema_trend == 0.0:
        return _log_diag("WAIT", "WARMUP_MACRO_NAN", None, 0.0, "NONE")

    direction = "LONG" if entry_p > ema_trend else "SHORT"

    ctx = _get_ctx_cached(df_1m, df_15m, df_1h)
    if ctx is None:
        return _log_diag("WAIT", "CTX_FAIL_OR_CRASH", None, 0.0, direction)

    atr_15m = c15m.get("atr") or 0
    levels  = ctx.get("levels", {})

    barriers = compute_barriers(
        entry_price = entry_p,
        atr_15m     = atr_15m,
        direction   = direction,
        nearest_res = levels.get("nearest_resistance"),
        nearest_sup = levels.get("nearest_support")
    )
    
    if not barriers:
        return _log_diag("WAIT", "NO_BARRIERS_RR_TOO_LOW", None, 0.0, direction)

    rr = barriers.get("rr", 0)
    if rr < config.SCOUT_RR_MIN:
        return _log_diag("WAIT", f"LOW_RR:{rr:.2f}", None, 0.0, direction)

    # ── EVALUACIÓN BASE (LOS ORÁCULOS) ──
    tier, prob = strategy_manager.evaluate_signal(c1m, c15m, c1h, direction, ctx, rr)
    
    if tier:
        barriers["tier"] = tier
        
        # ── INTERVENCIÓN DE LA IA (EL JUEZ SUPREMO) ──
        if _juez_supremo is not None:
            X_tensor = _build_ml_tensor(df_1m, df_15m, df_1h, df_4h, df_1d, entry_p, barriers, prob)
            prob_ia = _juez_supremo.predict_proba(X_tensor)[0][1]
            
            if prob_ia < 0.70:
                # El Juez Supremo deniega la operación
                return _log_diag("WAIT", f"VETO_IA_70% (score={prob_ia*100:.1f}%)", None, 0.0, direction)
            else:
                # El Juez Supremo aprueba
                return _log_diag("ENTRY", f"IA_APPROVED_{tier}:{prob_ia*100:.1f}%", barriers, prob, direction)

        # Si no hay IA cargada, dispara normal
        return _log_diag("ENTRY", f"ZETZU_{direction[:1]}_{tier}:{prob:.1f}%", barriers, prob, direction)

    return _log_diag("WAIT", "LOW_PROB_ALL_TIERS", None, 0.0, direction)

def _log_diag(signal, reason, barriers, prob, direction):
    if signal == "ENTRY":
        _DIAG["entries"] += 1
    elif _DIAG["shown"] < 5 and reason not in ["WARMUP_DATAFRAMES", "WARMUP_MACRO_NAN"]:
        _DIAG["shown"] += 1
        print(f"\033[93m[DIAG #{_DIAG['shown']}] reason={reason} prob={prob:.1f}%\033[0m")
        
    if _DIAG["n"] == 500:
        print(f"\033[96m[DIAG] 500 barras OK: {_DIAG['entries']} entradas detectadas.\033[0m")
        
    return signal, reason, barriers, prob, direction