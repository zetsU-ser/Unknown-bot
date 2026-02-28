# analysis/indicators/__init__.py
import polars as pl
import numpy as np
import configs.btc_usdt_config as config

# ── IMPORTACIONES GRANULARES ──
from analysis.indicators.trend import calc_trend
from analysis.indicators.momentum import calc_momentum
from analysis.indicators.volatility import calc_volatility
from analysis.indicators.volume import calc_volume_indicators

def add_indicators(df: pl.DataFrame) -> pl.DataFrame:
    """
    Orquestador de indicadores técnicos. 
    Extrae los vectores de Polars UNA sola vez para máximo rendimiento en C.
    """
    if len(df) < config.EMA_TREND:
        return df

    # Extracción vectorial ultra-rápida
    close  = df["close"].to_numpy().astype(np.float64)
    high   = df["high"].to_numpy().astype(np.float64)
    low    = df["low"].to_numpy().astype(np.float64)
    volume = df["volume"].to_numpy().astype(np.float64)
    timestamps = df["timestamp"].to_numpy()

    # Ejecución de los Legos Atómicos
    trend_data = calc_trend(close, config.EMA_FAST, config.EMA_SLOW, config.EMA_TREND)
    mom_data   = calc_momentum(high, low, close, config.RSI_PERIOD, config.ATR_PERIOD)
    vol_data   = calc_volatility(high, low, close, config.ATR_PERIOD, config.ZSCORE_LOOKBACK)
    v_data     = calc_volume_indicators(high, low, close, volume, timestamps, config.ZSCORE_LOOKBACK)

    # Reensamblaje en Polars
    return df.with_columns([
        pl.Series("ema_fast",  trend_data["ema_fast"]),
        pl.Series("ema_slow",  trend_data["ema_slow"]),
        pl.Series("ema_trend", trend_data["ema_trend"]),
        pl.Series("ema_dist",  trend_data["ema_dist"]),
        pl.Series("rsi",       mom_data["rsi"]),
        pl.Series("adx",       mom_data["adx"]),
        pl.Series("atr",       vol_data["atr"]),
        pl.Series("z_score",   vol_data["z_score"]),
        pl.Series("vol_ratio", v_data["vol_ratio"]),
        pl.Series("vwap",      v_data["vwap"])
    ])