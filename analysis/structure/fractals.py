import numpy as np
from typing import Tuple, List, Optional
import configs.btc_usdt_config as config

try:
    from scipy.signal import argrelmax, argrelmin
    _SCIPY = True
except ImportError:
    _SCIPY = False

def find_swing_highs_lows(highs: np.ndarray, lows: np.ndarray, n: Optional[int] = None) -> Tuple[List[int], List[int]]:
    """Detecta fractales (swings) vectorizados asegurando que la vela viva jamás intervenga."""
    n = n or getattr(config, "SWING_LOOKBACK", 5)
    
    # CORRECCIÓN FATAL: len(highs) - 2 es el índice de la última vela CERRADA.
    # Así, el vecindario derecho del fractal (i+n) nunca tocará a len(highs) - 1.
    safe_limit = len(highs) - 2 - n
    
    if _SCIPY and len(highs) > 2 * n:
        raw_sh = argrelmax(highs, order=n)[0]
        raw_sl = argrelmin(lows, order=n)[0]
        
        sh_idx = [int(i) for i in raw_sh if i <= safe_limit]
        sl_idx = [int(i) for i in raw_sl if i <= safe_limit]
        return sh_idx, sl_idx
    
    sh_idx: List[int] = []
    sl_idx: List[int] = []
    for i in range(n, safe_limit + 1):
        if highs[i] == np.max(highs[i-n:i+n+1]): 
            sh_idx.append(i)
        if lows[i] == np.min(lows[i-n:i+n+1]):  
            sl_idx.append(i)
            
    return sh_idx, sl_idx