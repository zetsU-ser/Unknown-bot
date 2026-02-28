import talib
import numpy as np

def calc_volatility(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr_period: int, z_lookback: int) -> dict:
    """Calcula volatilidad absoluta (ATR) y relativa (Z-Score)."""
    atr = talib.ATR(high, low, close, timeperiod=atr_period)
    
    z_score = np.full_like(close, fill_value=np.nan)
    for i in range(z_lookback, len(close)):
        window = close[i-z_lookback : i]
        std_p = np.std(window)
        if std_p > 0:
            z_score[i] = (close[i] - np.mean(window)) / std_p
            
    return {"atr": atr, "z_score": z_score}