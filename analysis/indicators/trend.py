import talib
import numpy as np

def calc_trend(close: np.ndarray, fast_period: int, slow_period: int, trend_period: int) -> dict:
    """Calcula indicadores de tendencia base."""
    ema_fast  = talib.EMA(close, timeperiod=fast_period)
    ema_slow  = talib.EMA(close, timeperiod=slow_period)
    ema_trend = talib.EMA(close, timeperiod=trend_period)
    
    # Distancia Porcentual a la EMA Macro (Rubber Band Effect)
    ema_dist = np.full_like(close, fill_value=np.nan)
    valid = ema_trend > 0
    ema_dist[valid] = (close[valid] - ema_trend[valid]) / ema_trend[valid]
    
    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_trend": ema_trend,
        "ema_dist": ema_dist
    }