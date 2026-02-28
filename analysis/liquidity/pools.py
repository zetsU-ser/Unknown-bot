import numpy as np
import polars as pl
from analysis.structure.fractals import find_swing_highs_lows

def detect_eqh_eql(df: pl.DataFrame, lookback: int = 80, tolerance_pct: float = 0.002) -> dict:
    if len(df) < lookback:
        return {"eqh": [], "eql": [], "eqh_swept": False, "eql_swept": False, "nearest_eqh": None, "nearest_eql": None}
    subset = df.tail(lookback)
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    closes = subset["close"].to_numpy()
    curr_p = closes[-1]
    tol    = curr_p * tolerance_pct
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n=4)

    eqh_levels, eql_levels = [], []
    if len(sh_idx) >= 2:
        sh_vals = [highs[i] for i in sh_idx]
        seen = set()
        for i in range(len(sh_vals)):
            for j in range(i+1, len(sh_vals)):
                if abs(sh_vals[i] - sh_vals[j]) < tol:
                    lvl = round((sh_vals[i] + sh_vals[j]) / 2, 2)
                    if lvl not in seen:
                        eqh_levels.append(lvl); seen.add(lvl)
    if len(sl_idx) >= 2:
        sl_vals = [lows[i] for i in sl_idx]
        seen = set()
        for i in range(len(sl_vals)):
            for j in range(i+1, len(sl_vals)):
                if abs(sl_vals[i] - sl_vals[j]) < tol:
                    lvl = round((sl_vals[i] + sl_vals[j]) / 2, 2)
                    if lvl not in seen:
                        eql_levels.append(lvl); seen.add(lvl)

    last_h = highs[-1]; last_l = lows[-1]; last_c = closes[-1]
    eqh_swept = any(last_h > lvl and last_c < lvl for lvl in eqh_levels)
    eql_swept = any(last_l < lvl and last_c > lvl for lvl in eql_levels)
    above = [l for l in eqh_levels if l > curr_p]
    below = [l for l in eql_levels if l < curr_p]
    return {
        "eqh": eqh_levels, "eql": eql_levels,
        "eqh_swept": eqh_swept, "eql_swept": eql_swept,
        "nearest_eqh": min(above) if above else None,
        "nearest_eql": max(below) if below else None,
    }

def detect_liquidity_sweep(df: pl.DataFrame, lookback: int = 20) -> dict:
    if len(df) < lookback + 2: return {"sweep": False, "direction": None}
    subset = df.tail(lookback)
    lows   = subset["low"].to_numpy()
    highs  = subset["high"].to_numpy()
    closes = subset["close"].to_numpy()
    p_low  = np.min(lows[:-1])
    p_high = np.max(highs[:-1])
    if highs[-1] > p_high and closes[-1] < p_high:
        return {"sweep": True, "direction": "BEAR", "level": p_high, "sweep_size": highs[-1] - p_high}
    if lows[-1] < p_low and closes[-1] > p_low:
        return {"sweep": True, "direction": "BULL", "level": p_low, "sweep_size": p_low - lows[-1]}
    return {"sweep": False, "direction": None}