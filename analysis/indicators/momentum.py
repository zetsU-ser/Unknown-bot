import talib
import numpy as np

def calc_momentum(high: np.ndarray, low: np.ndarray, close: np.ndarray, rsi_period: int, adx_period: int) -> dict:
    """Calcula osciladores de momentum."""
    return {
        "rsi": talib.RSI(close, timeperiod=rsi_period),
        "adx": talib.ADX(high, low, close, timeperiod=adx_period)
    }