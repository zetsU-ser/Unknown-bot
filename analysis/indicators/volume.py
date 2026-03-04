import numpy as np
import pandas as pd
from typing import Dict

def calc_volume_indicators(high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray, timestamps: np.ndarray, z_lookback: int) -> Dict[str, np.ndarray]:
    """
    Calcula VWAP intradiario y picos relativos de volumen con vectorización estricta.
    Fix Auditado: Protección contra arrays vacíos y resolución exacta de Nanosegundos/Microsegundos.
    """
    
    # PROTECCIÓN CAPA 8: Salida rápida si no hay datos (Evita IndexError)
    if len(close) == 0:
        return {
            "vwap": np.array([], dtype=np.float64),
            "vol_ratio": np.array([], dtype=np.float64)
        }
    
    # 1. Cálculo de Ratio de Volumen Relativo
    vol_s = pd.Series(volume)
    roll_mean = vol_s.rolling(window=z_lookback).mean().shift(1).to_numpy()
    
    vol_ratio = np.full_like(volume, fill_value=1.0, dtype=np.float64)
    valid_mask = (roll_mean > 0) & (~np.isnan(roll_mean))
    np.divide(volume, roll_mean, out=vol_ratio, where=valid_mask)

    # 2. Cálculo de VWAP Intradiario
    typical_price = (high + low + close) / 3.0
    tpv = typical_price * volume
    
    # CORRECCIÓN CRÍTICA DE MAGNITUDES TEMPORALES
    try:
        ts_int = timestamps.astype(np.int64)
        sample = ts_int[0]
        
        # Ajuste dinámico a Milisegundos dependiendo de la resolución nativa
        if sample > 10**17:  
            # Resolución en Nanosegundos (ej. Pandas por defecto)
            ts_int = ts_int // 1000000
        elif sample > 10**14: 
            # Resolución en Microsegundos
            ts_int = ts_int // 1000
    except Exception:
        ts_int = timestamps # Fallback en caso de error de casteo

    # 1 Día = 86,400,000 ms
    days_epoch = ts_int // 86400000
    
    df_vwap = pd.DataFrame({'tpv': tpv, 'vol': volume, 'day': days_epoch})
    grouped = df_vwap.groupby('day')
    
    day_cum_tpv = grouped['tpv'].cumsum().to_numpy()
    day_cum_vol = grouped['vol'].cumsum().to_numpy()
    
    vwap = np.full_like(close, fill_value=np.nan, dtype=np.float64)
    np.divide(day_cum_tpv, day_cum_vol, out=vwap, where=(day_cum_vol > 0))

    return {
        "vwap": vwap,
        "vol_ratio": vol_ratio
    }