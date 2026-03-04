import talib
import numpy as np
from typing import Dict

def calc_momentum(high: np.ndarray, low: np.ndarray, close: np.ndarray, rsi_period: int, adx_period: int) -> Dict[str, np.ndarray]:
    """Calcula osciladores de momentum de forma vectorizada."""
    return {
        "rsi": talib.RSI(close, timeperiod=rsi_period),
        "adx": talib.ADX(high, low, close, timeperiod=adx_period)
    }