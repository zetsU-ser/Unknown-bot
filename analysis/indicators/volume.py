import numpy as np
import pandas as pd

def calc_volume_indicators(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, timestamps: np.ndarray, z_lookback: int) -> dict:
    """Calcula VWAP intradiario y picos relativos de volumen."""
    vol_ratio = np.full_like(volume, fill_value=1.0)
    for i in range(z_lookback, len(volume)):
        vol_window = volume[i-z_lookback : i]
        mean_v = np.mean(vol_window)
        if mean_v > 0:
            vol_ratio[i] = volume[i] / mean_v

    typical_price = (high + low + close) / 3
    vwap = np.full(len(close), np.nan)
    day_cum_tpv = 0.0
    day_cum_vol = 0.0
    prev_day = None

    for i in range(len(close)):
        try:
            day = pd.Timestamp(timestamps[i]).date()
        except Exception:
            day = int(timestamps[i]) // 86_400_000
            
        if day != prev_day:
            day_cum_tpv = 0.0
            day_cum_vol = 0.0
            prev_day = day
            
        day_cum_tpv += typical_price[i] * volume[i]
        day_cum_vol += volume[i]
        vwap[i] = day_cum_tpv / day_cum_vol if day_cum_vol > 0 else typical_price[i]

    return {"vol_ratio": vol_ratio, "vwap": vwap}