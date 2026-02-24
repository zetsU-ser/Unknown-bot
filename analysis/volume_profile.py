"""
Bloque 3: Análisis de Volumen (Smart Money Footprint) - UNKNOWN-BOT V9.0
========================================================================
Cálculo de VWAP Institucional y Cumulative Volume Delta (CVD).
Convierte el volumen bruto en huellas de agresión compradora/vendedora.
"""

import polars as pl

def calculate_vwap(df: pl.DataFrame) -> pl.Series:
    """
    Calcula el VWAP (Volume Weighted Average Price) acumulado.
    Es el verdadero precio promedio pagado por el mercado, ponderado por el dinero real.
    """
    # Typical Price = (High + Low + Close) / 3
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    
    # TPV = Precio Típico * Volumen
    tpv = tp * df["volume"]
    
    # VWAP = Suma Acumulada(TPV) / Suma Acumulada(Volumen)
    vwap = tpv.cum_sum() / df["volume"].cum_sum()
    
    return vwap

def calculate_cvd(df: pl.DataFrame) -> pl.Series:
    """
    Estima el CVD (Cumulative Volume Delta) usando la anatomía de la vela.
    Mide la "Agresión" (quién tiene el control: compradores o vendedores).
    """
    high = df["high"]
    low = df["low"]
    open_p = df["open"]
    close_p = df["close"]
    vol = df["volume"]
    
    # Rango total de la vela
    rango = high - low
    
    # Evitar división por cero en velas sin movimiento (Dojis perfectos)
    rango = pl.when(rango == 0).then(0.00001).otherwise(rango)
    
    # Fórmula Quant de Delta Estimado:
    # Delta = Volumen * ((Close - Open) / Rango)
    # Si cierra exactamente en el máximo, es 100% volumen de agresión compradora.
    # Si cierra en el mínimo, es -100% volumen vendedor.
    delta = vol * ((close_p - open_p) / rango)
    
    # CVD es la suma acumulada de ese Delta para ver la tendencia de la presión
    cvd = delta.cum_sum()
    
    return cvd

def enrich_with_volume_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Inyecta las métricas institucionales de volumen al DataFrame.
    Esta función se llamará durante la fase de ETL/Carga de datos.
    """
    if "volume" not in df.columns or len(df) == 0:
        return df
        
    return df.with_columns([
        calculate_vwap(df).alias("vwap"),
        calculate_cvd(df).alias("cvd")
    ])

# Añade esto al final de analysis/volume_profile.py

def detect_volume_divergence(df: pl.DataFrame, lookback: int = 10) -> str:
    """
    Analiza la relación entre el Precio y el CVD para detectar trampas.
    Lookback: 10 velas de 1m (micro-estructura).
    """
    if len(df) < lookback: return "NORMAL"
    
    recent = df.tail(lookback)
    price_change = recent["close"][-1] - recent["close"][0]
    cvd_change = recent["cvd"][-1] - recent["cvd"][0]
    
    # 🐻 BEARISH DIVERGENCE: El precio sube pero el CVD baja (Ventas pasivas absorbiendo)
    if price_change > 0 and cvd_change < 0:
        return "BEAR_DIV"
    
    # 🐂 BULLISH DIVERGENCE: El precio baja pero el CVD sube (Compras pasivas acumulando)
    if price_change < 0 and cvd_change > 0:
        return "BULL_DIV"
        
    return "NORMAL"

