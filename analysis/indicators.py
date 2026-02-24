"""
Módulo de Indicadores Técnicos - UNKNOWN-BOT V6.0
=================================================
Aplica transformaciones matemáticas a los datos OHLCV utilizando TA-Lib,
una librería escrita en C de altísima eficiencia, indispensable para
el procesamiento cuantitativo de alta frecuencia.
"""

import polars as pl
import talib
import numpy as np
import configs.btc_usdt_config as config

def add_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """
    Calcula y adjunta indicadores técnicos al DataFrame de Polars.
    Extrae los parámetros dinámicamente del archivo de configuración agnóstico.

    Args:
        df (pl.DataFrame): DataFrame con datos crudos (open, high, low, close, volume).

    Returns:
        pl.DataFrame: DataFrame enriquecido con columnas de indicadores.
    """
    # Retorno temprano si no hay suficientes velas para calcular el ancla macro
    if len(df) < config.EMA_TREND:
        return df

    # Extracción de vectores NumPy para procesamiento ultra rápido en C (TA-Lib)
    closes = df["close"].to_numpy()
    highs  = df["high"].to_numpy()
    lows   = df["low"].to_numpy()
    volumes = df["volume"].to_numpy()

    # ── INDICADORES NATIVOS (TA-LIB) ─────────────────────────────────────────
    rsi = talib.RSI(closes, timeperiod=config.RSI_PERIOD)
    atr = talib.ATR(highs, lows, closes, timeperiod=config.ATR_PERIOD)
    ema_trend = talib.EMA(closes, timeperiod=config.EMA_TREND)
    adx = talib.ADX(highs, lows, closes, timeperiod=config.ATR_PERIOD)

    # ── INDICADORES CUSTOM (ESTADÍSTICOS) ────────────────────────────────────
    # Z-Score: Mide cuántas desviaciones estándar se alejó el precio de su media
    z_score = np.full_like(closes, fill_value=np.nan)
    # Vol Ratio: Compara el volumen actual contra el promedio reciente
    vol_ratio = np.full_like(volumes, fill_value=1.0)
    
    # Cálculo con ventanas móviles (Rolling windows)
    for i in range(config.ZSCORE_LOOKBACK, len(closes)):
        window = closes[i-config.ZSCORE_LOOKBACK : i]
        mean_p, std_p = np.mean(window), np.std(window)
        if std_p > 0:
            z_score[i] = (closes[i] - mean_p) / std_p
            
        vol_window = volumes[i-config.ZSCORE_LOOKBACK : i]
        mean_vol = np.mean(vol_window)
        if mean_vol > 0:
            vol_ratio[i] = volumes[i] / mean_vol

    # Retornamos el DataFrame inyectando las nuevas series vectorizadas
    return df.with_columns([
        pl.Series("rsi", rsi),
        pl.Series("atr", atr),
        pl.Series("ema_trend", ema_trend),
        pl.Series("adx", adx),
        pl.Series("z_score", z_score),
        pl.Series("vol_ratio", vol_ratio)
    ])