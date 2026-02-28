import numpy as np
import configs.btc_usdt_config as config

try:
    from scipy.signal import argrelmax, argrelmin
    _SCIPY = True
except ImportError:
    _SCIPY = False

def find_swing_highs_lows(highs, lows, n=None):
    """Detecta fractales usando SciPy (10x más rápido) o NumPy puro."""
    n = n or config.SWING_LOOKBACK
    if _SCIPY and len(highs) > 2 * n:
        sh_idx = list(argrelmax(highs, order=n)[0])
        sl_idx = list(argrelmin(lows,  order=n)[0])
        return sh_idx, sl_idx
    
    sh_idx, sl_idx = [], []
    for i in range(n, len(highs) - n):
        if highs[i] == np.max(highs[i-n:i+n+1]): sh_idx.append(i)
        if lows[i]  == np.min(lows[i-n:i+n+1]):  sl_idx.append(i)
    return sh_idx, sl_idx