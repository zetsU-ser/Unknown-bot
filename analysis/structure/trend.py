import numpy as np
import polars as pl
import configs.btc_usdt_config as config
from analysis.structure.fractals import find_swing_highs_lows

def detect_premium_discount(highs, lows, curr_p):
    if len(highs) < 20: return "EQUILIBRIUM"
    max_h = np.max(highs[-100:])
    min_l = np.min(lows[-100:])
    eq    = (max_h + min_l) / 2.0
    if curr_p < eq: return "DISCOUNT"
    if curr_p > eq: return "PREMIUM"
    return "EQUILIBRIUM"

def detect_regime(df: pl.DataFrame, n: int = None) -> dict:
    n = n or config.SWING_LOOKBACK
    if len(df) < 100: return {"trend": "RANGING", "zone": "EQUILIBRIUM"}
    highs  = df["high"].to_numpy()
    lows   = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n)
    zone = detect_premium_discount(highs, lows, closes[-1])
    
    if len(sh_idx) < 2 or len(sl_idx) < 2:
        return {"trend": "RANGING", "zone": zone}
        
    last_sh = [highs[i] for i in sh_idx[-2:]]
    last_sl = [lows[i]  for i in sl_idx[-2:]]
    trend = "RANGING"
    
    if last_sh[-1] > last_sh[-2] and last_sl[-1] > last_sl[-2]: trend = "BULLISH"
    elif last_sh[-1] < last_sh[-2] and last_sl[-1] < last_sl[-2]: trend = "BEARISH"
    return {"trend": trend, "zone": zone}