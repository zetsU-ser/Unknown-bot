# analysis/volume_profile.py — V10.2
"""
Bloque 3: Volumen Institucional — CVD + Perfil de Volumen
=========================================================

Funciones:
  enrich_with_volume_features(df) → añade columna 'cvd' al DataFrame
  detect_volume_divergence(df, lookback) → detecta divergencias CVD/precio

CVD (Cumulative Volume Delta):
  Aproximación del flujo de órdenes neto (compra vs venta).
  Si cierre > apertura → barra alcista → delta = +volume
  Si cierre < apertura → barra bajista → delta = -volume
  CVD = suma acumulada del delta → proxy de presión compradora/vendedora

Bloque 6 (Arquitectura):
  Esta versión es la implementación vectorizada para backtesting/research.
  En producción real se usaría tick data o trades individuales de la API
  para calcular el CVD real (buy_qty - sell_qty por trade).
"""
import numpy as np
import polars as pl


# ─────────────────────────────────────────────────────────────────────────────
def enrich_with_volume_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Añade el CVD (Cumulative Volume Delta) al DataFrame.

    El CVD es la columna más importante del Bloque 3 para detectar:
    - Divergencias bajistas: precio sube, CVD baja → institucionales distribuyendo
    - Divergencias alcistas: precio baja, CVD sube → institucionales acumulando

    Args:
        df: DataFrame con columnas open, close, volume

    Returns:
        df enriquecido con columna 'cvd'
    """
    if "cvd" in df.columns:
        return df   # Ya enriquecido

    if len(df) == 0:
        return df.with_columns(pl.lit(0.0).alias("cvd"))

    closes   = df["close"].to_numpy().astype(np.float64)
    opens    = df["open"].to_numpy().astype(np.float64)
    volumes  = df["volume"].to_numpy().astype(np.float64)

    # Delta de volumen por barra
    # +volume si barra alcista, -volume si barra bajista
    delta = np.where(closes >= opens, volumes, -volumes)

    # CVD = suma acumulada del delta
    cvd = np.cumsum(delta)

    return df.with_columns(pl.Series("cvd", cvd))


# ─────────────────────────────────────────────────────────────────────────────
def detect_volume_divergence(df: pl.DataFrame, lookback: int = 10) -> str:
    """
    Detecta divergencias entre el precio y el CVD (Bloque 3 — Trampa de Volumen).

    Tipos:
      BULL_DIV: precio hace mínimos más bajos pero CVD hace mínimos más altos
                → institucionales comprando en la caída → setup LONG favorecido
      BEAR_DIV: precio hace máximos más altos pero CVD hace máximos más bajos
                → institucionales distribuyendo → setup SHORT favorecido
      NEUTRAL:  sin divergencia clara

    Args:
        df:       DataFrame con columnas close, cvd
        lookback: ventana de barras para comparar (default 10)

    Returns:
        "BULL_DIV" | "BEAR_DIV" | "NEUTRAL"
    """
    if len(df) < lookback * 2 + 1:
        return "NEUTRAL"

    if "cvd" not in df.columns:
        return "NEUTRAL"

    window = df.tail(lookback * 2)
    closes = window["close"].to_numpy().astype(np.float64)
    cvds   = window["cvd"].to_numpy().astype(np.float64)

    # Dividir en mitad anterior vs mitad reciente
    mid = lookback
    prev_close_max = np.max(closes[:mid])
    curr_close_max = np.max(closes[mid:])
    prev_close_min = np.min(closes[:mid])
    curr_close_min = np.min(closes[mid:])

    prev_cvd_max   = np.max(cvds[:mid])
    curr_cvd_max   = np.max(cvds[mid:])
    prev_cvd_min   = np.min(cvds[:mid])
    curr_cvd_min   = np.min(cvds[mid:])

    # BEAR_DIV: precio HH pero CVD LH → distribución institucional
    if curr_close_max > prev_close_max and curr_cvd_max < prev_cvd_max:
        return "BEAR_DIV"

    # BULL_DIV: precio LL pero CVD HL → acumulación institucional
    if curr_close_min < prev_close_min and curr_cvd_min > prev_cvd_min:
        return "BULL_DIV"

    return "NEUTRAL"