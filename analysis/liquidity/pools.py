import numpy as np
import polars as pl
from typing import Dict, List, Any
from analysis.structure.fractals import find_swing_highs_lows

def detect_eqh_eql(df: pl.DataFrame, lookback: int = 80, tolerance_pct: float = 0.002) -> Dict[str, Any]:
    """Detecta EQL/EQH utilizando broadcasting matricial en lugar de bucles O(N^2)."""
    if len(df) < lookback:
        return {"eqh": [], "eql": [], "eqh_swept": False, "eql_swept": False, "nearest_eqh": None, "nearest_eql": None}
        
    subset = df.tail(lookback)
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    closes = subset["close"].to_numpy()
    curr_p = closes[-1]
    tol    = curr_p * tolerance_pct
    
    # Los swing highs/lows ya tienen un retraso natural por 'n=4', 
    # por lo que no usan la vela en curso. Son seguros.
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n=4)

    eqh_levels: List[float] = []
    eql_levels: List[float] = []
    
    if len(sh_idx) >= 2:
        sh_vals = highs[sh_idx]
        diffs = np.abs(sh_vals[:, None] - sh_vals[None, :])
        upper_tri = np.triu(diffs < tol, k=1)
        pairs = np.argwhere(upper_tri)
        
        seen_eqh = set()
        for i, j in pairs:
            lvl = round(float((sh_vals[i] + sh_vals[j]) / 2), 2)
            if lvl not in seen_eqh:
                eqh_levels.append(lvl)
                seen_eqh.add(lvl)

    if len(sl_idx) >= 2:
        sl_vals = lows[sl_idx]
        diffs = np.abs(sl_vals[:, None] - sl_vals[None, :])
        upper_tri = np.triu(diffs < tol, k=1)
        pairs = np.argwhere(upper_tri)
        
        seen_eql = set()
        for i, j in pairs:
            lvl = round(float((sl_vals[i] + sl_vals[j]) / 2), 2)
            if lvl not in seen_eql:
                eql_levels.append(lvl)
                seen_eql.add(lvl)

    # CORRECCIÓN FATAL: Evaluamos el barrido ÚNICAMENTE contra la última vela cerrada [-2].
    last_closed_h, last_closed_l, last_closed_c = highs[-2], lows[-2], closes[-2]
    
    eqh_swept = any((last_closed_h > lvl) and (last_closed_c < lvl) for lvl in eqh_levels)
    eql_swept = any((last_closed_l < lvl) and (last_closed_c > lvl) for lvl in eql_levels)
    
    above = [l for l in eqh_levels if l > curr_p]
    below = [l for l in eql_levels if l < curr_p]
    
    return {
        "eqh": eqh_levels, "eql": eql_levels,
        "eqh_swept": eqh_swept, "eql_swept": eql_swept,
        "nearest_eqh": float(min(above)) if above else None,
        "nearest_eql": float(max(below)) if below else None,
    }

def detect_liquidity_sweep(df: pl.DataFrame, lookback: int = 20) -> Dict[str, Any]:
    """Detecta SFP (Sweeps) validando únicamente sobre velas cerradas."""
    if len(df) < lookback + 2: 
        return {"sweep": False, "direction": None}
        
    subset = df.tail(lookback)
    lows   = subset["low"].to_numpy()
    highs  = subset["high"].to_numpy()
    closes = subset["close"].to_numpy()
    
    # Mantenido intacto: Esta función SÍ estaba bien protegida contra lookahead.
    p_low  = np.min(lows[:-2])
    p_high = np.max(highs[:-2])
    
    last_closed_h = highs[-2]
    last_closed_l = lows[-2]
    last_closed_c = closes[-2]
    
    if last_closed_h > p_high and last_closed_c < p_high:
        return {"sweep": True, "direction": "BEAR", "level": float(p_high), "sweep_size": float(last_closed_h - p_high)}
    if last_closed_l < p_low and last_closed_c > p_low:
        return {"sweep": True, "direction": "BULL", "level": float(p_low), "sweep_size": float(p_low - last_closed_l)}
        
    return {"sweep": False, "direction": None}