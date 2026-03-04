# analysis/volume_profile.py — V10.2
"""
Bloque 3: Volumen Institucional — CVD + Perfil de Volumen
=========================================================
"""
import numpy as np
import polars as pl

# ─────────────────────────────────────────────────────────────────────────────
def enrich_with_volume_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Añade el CVD (Cumulative Volume Delta) al DataFrame utilizando
    el motor nativo de Rust de Polars (Cero copias de memoria innecesarias).
    """
    if "cvd" in df.columns:
        return df   

    if len(df) == 0:
        return df.with_columns(pl.lit(0.0).alias("cvd"))

    # Operación 100% nativa en Polars. 
    # Evita el overhead de instanciar arrays de Numpy y mantiene la ejecución optimizada.
    return df.with_columns(
        pl.when(pl.col("close") >= pl.col("open"))
        .then(pl.col("volume"))
        .otherwise(-pl.col("volume"))
        .cum_sum()
        .alias("cvd")
    )

# ─────────────────────────────────────────────────────────────────────────────
def detect_volume_divergence(df: pl.DataFrame, lookback: int = 10) -> str:
    """
    Detecta divergencias entre el precio y el CVD asegurando el aislamiento
    de la vela viva para prevenir repintado.
    """
    if len(df) < lookback * 2 + 2:
        return "NEUTRAL"

    if "cvd" not in df.columns:
        return "NEUTRAL"

    # Extracción de arrays ignorando la vela viva en curso ([:-1])
    closes = df["close"].to_numpy()[:-1].astype(np.float64)
    cvds   = df["cvd"].to_numpy()[:-1].astype(np.float64)
    
    closes_window = closes[-(lookback * 2):]
    cvds_window   = cvds[-(lookback * 2):]

    mid = lookback
    prev_close_max = np.max(closes_window[:mid])
    curr_close_max = np.max(closes_window[mid:])
    prev_close_min = np.min(closes_window[:mid])
    curr_close_min = np.min(closes_window[mid:])

    prev_cvd_max   = np.max(cvds_window[:mid])
    curr_cvd_max   = np.max(cvds_window[mid:])
    prev_cvd_min   = np.min(cvds_window[:mid])
    curr_cvd_min   = np.min(cvds_window[mid:])

    # BEAR_DIV: precio HH pero CVD LH -> distribución institucional
    if curr_close_max > prev_close_max and curr_cvd_max < prev_cvd_max:
        return "BEAR_DIV"

    # BULL_DIV: precio LL pero CVD HL -> acumulación institucional
    if curr_close_min < prev_close_min and curr_cvd_min > prev_cvd_min:
        return "BULL_DIV"

    return "NEUTRAL"