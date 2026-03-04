import talib
import numpy as np
from typing import Dict

def calc_trend(close: np.ndarray, fast_period: int, slow_period: int, trend_period: int) -> Dict[str, np.ndarray]:
    """Calcula indicadores de tendencia base optimizados para memoria C."""
    ema_fast  = talib.EMA(close, timeperiod=fast_period)
    ema_slow  = talib.EMA(close, timeperiod=slow_period)
    ema_trend = talib.EMA(close, timeperiod=trend_period)
    
    # Distancia Porcentual a la EMA Macro (Rubber Band Effect)
    ema_dist = np.full_like(close, fill_value=np.nan, dtype=np.float64)
    
    # Evitamos copias de memoria usando operaciones atómicas inplace
    diff = close - ema_trend
    valid_mask = (ema_trend > 0) & (~np.isnan(ema_trend))
    
    np.divide(diff, ema_trend, out=ema_dist, where=valid_mask)
    
    return {
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "ema_trend": ema_trend,
        "ema_dist": ema_dist
    }