import polars as pl
from typing import Dict, Any

# ── ESTRUCTURA ──
from analysis.structure.trend import detect_regime
from analysis.structure.breaks import detect_bos_choch

# ── LIQUIDEZ ──
from analysis.liquidity.fvg import detect_fvg
from analysis.liquidity.pools import detect_eqh_eql, detect_liquidity_sweep
from analysis.liquidity.levels import find_key_levels, detect_ob_proximity

def get_full_market_ctx(df_1m: pl.DataFrame, df_15m: pl.DataFrame, df_1h: pl.DataFrame) -> Dict[str, Any]:
    """
    Construye el contexto de mercado agregando las métricas de SMC y liquidez.
    """
    # Tomamos el precio vivo para medir proximidad real a los niveles
    curr_p     = float(df_15m["close"][-1])
    regime_15m = detect_regime(df_15m)
    regime_1h  = detect_regime(df_1h)

    sweep_1m  = detect_liquidity_sweep(df_1m)
    bos_choch = detect_bos_choch(df_1m, lookback=40)
    fvg_1m    = detect_fvg(df_1m, lookback=30)

    levels_15m = find_key_levels(df_15m, lookback=150)
    ob_touch   = detect_ob_proximity(curr_p, levels_15m, tolerance_pct=0.003)
    eqh_eql    = detect_eqh_eql(df_15m, lookback=80)

    trend_15m = regime_15m.get("trend", "RANGING")
    priors = {"LONG": 30.0, "SHORT": 30.0}
    
    if trend_15m == "BULLISH":   
        priors["LONG"] = 40.0; priors["SHORT"] = 20.0
    elif trend_15m == "BEARISH": 
        priors["LONG"] = 20.0; priors["SHORT"] = 40.0

    return {
        "trend_15m":  trend_15m, 
        "zone_15m":   regime_15m.get("zone", "EQUILIBRIUM"),
        "trend_1h":   regime_1h.get("trend", "RANGING"), 
        "zone_1h":    regime_1h.get("zone", "EQUILIBRIUM"),
        "priors":     priors, 
        "sweep":      sweep_1m,
        "bos_choch":  bos_choch, 
        "fvg_1m":     fvg_1m,
        "levels":     levels_15m, 
        "ob_touch":   ob_touch, 
        "eqh_eql":    eqh_eql,
    }