import talib
import numpy as np
import pandas as pd
from typing import Dict

def calc_volatility(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr_period: int, z_lookback: int) -> Dict[str, np.ndarray]:
    """Calcula volatilidad absoluta (ATR) y relativa (Z-Score) mediante vectorización estricta y segura."""
    atr = talib.ATR(high, low, close, timeperiod=atr_period)
    
    # Vectorizamos la ventana móvil. Aunque Pandas añade un leve overhead, 
    # es aceptable aquí frente al costo Big O del bucle original.
    close_s = pd.Series(close)
    
    # Desplazamiento (shift) validado: evita el lookahead bias en las features del modelo.
    roll = close_s.rolling(window=z_lookback)
    roll_mean = roll.mean().shift(1).to_numpy()
    roll_std = roll.std().shift(1).to_numpy()
    
    # Prevención absoluta de RuntimeWarnings y evaluación ansiosa.
    diff = close - roll_mean
    z_score = np.full_like(close, fill_value=np.nan, dtype=np.float64)
    
    # Máscara estricta para divisores válidos
    valid_mask = (roll_std > 0) & (~np.isnan(roll_std))
    
    # np.divide con el parámetro 'where' realiza la división a nivel de C 
    # SOLO donde la máscara es True, salvando la latencia y evitando el I/O por warnings.
    np.divide(diff, roll_std, out=z_score, where=valid_mask)
        
    return {
        "atr": atr,
        "z_score": z_score
    }