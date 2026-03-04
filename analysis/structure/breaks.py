import polars as pl
from typing import Dict, Any
from analysis.structure.fractals import find_swing_highs_lows

def detect_bos_choch(df: pl.DataFrame, lookback: int = 40) -> Dict[str, Any]:
    """Detecta rompimientos SMC (BOS/ChoCh) exigiendo un cruce exacto y cierre de cuerpo."""
    empty = {
        "bos": False, "choch": False, "direction": None,
        "bos_bull": False, "bos_bear": False,
        "choch_bull": False, "choch_bear": False
    }
    
    if len(df) < lookback + 5: 
        return empty
    
    subset = df.tail(lookback)
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    closes = subset["close"].to_numpy()
    
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n=3)
    if len(sh_idx) < 2 or len(sl_idx) < 2: 
        return empty
    
    prev_hh = highs[sh_idx[-2]]
    last_hh = highs[sh_idx[-1]]
    
    prev_ll = lows[sl_idx[-2]]
    last_ll = lows[sl_idx[-1]]
    
    last_closed_c = closes[-2]
    prev_closed_c = closes[-3]
    
    # CORRECCIÓN FATAL: Detección de cruce discreto.
    # Garantiza que la señal se emita UNA sola vez en la vela de la ruptura.
    bos_bull  = (last_closed_c > last_hh) and (prev_closed_c <= last_hh)
    bos_bear  = (last_closed_c < last_ll) and (prev_closed_c >= last_ll)
    
    prior_bearish = (last_hh < prev_hh) and (last_ll < prev_ll)
    choch_bull    = prior_bearish and (last_closed_c > last_hh) and (prev_closed_c <= last_hh)
    
    prior_bullish = (last_hh > prev_hh) and (last_ll > prev_ll)
    choch_bear    = prior_bullish and (last_closed_c < last_ll) and (prev_closed_c >= last_ll)
    
    direction = None
    if choch_bull or bos_bull: direction = "BULL"
    elif choch_bear or bos_bear: direction = "BEAR"
    
    return {
        "bos": bos_bull or bos_bear,
        "choch": choch_bull or choch_bear,
        "direction": direction,
        "bos_bull": bos_bull,
        "bos_bear": bos_bear,
        "choch_bull": choch_bull,
        "choch_bear": choch_bear
    }