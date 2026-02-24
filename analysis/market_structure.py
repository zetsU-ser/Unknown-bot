"""
Bloque de Estructura y Liquidez - UNKNOWN-BOT V8.0 (SMC Edition)
================================================================
Implementa Smart Money Concepts: Order Blocks (OB), Fair Value Gaps (FVG),
Premium/Discount, y barridos de liquidez. 
"""

import numpy as np
import polars as pl
import configs.btc_usdt_config as config

def find_swing_highs_lows(highs, lows, n=None):
    """Detecta fractales básicos (BSL / SSL)."""
    n = n or config.SWING_LOOKBACK
    swing_highs, swing_lows = [], []
    for i in range(n, len(highs) - n):
        if highs[i] == np.max(highs[i-n : i+n+1]): swing_highs.append(i)
        if lows[i] == np.min(lows[i-n : i+n+1]):   swing_lows.append(i)
    return swing_highs, swing_lows

def detect_premium_discount(highs, lows, curr_p):
    """
    Divide el rango en Premium y Discount (Fibonacci 0.50).
    Premium: Zona superior (vender caro). Discount: Zona inferior (comprar barato).
    """
    if len(highs) < 20: return "EQUILIBRIUM"
    
    # Tomamos el rango reciente (Swing macro)
    max_h = np.max(highs[-100:])
    min_l = np.min(lows[-100:])
    equilibrium = (max_h + min_l) / 2.0
    
    if curr_p < equilibrium: return "DISCOUNT"
    if curr_p > equilibrium: return "PREMIUM"
    return "EQUILIBRIUM"

def detect_regime(df: pl.DataFrame, n: int = None) -> dict:
    """Retorna la tendencia macro y en qué zona del rango nos encontramos."""
    n = n or config.SWING_LOOKBACK
    if len(df) < 100: return {"trend": "RANGING", "zone": "EQUILIBRIUM"}
    
    highs, lows, closes = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n)
    
    zone = detect_premium_discount(highs, lows, closes[-1])
    
    if len(sh_idx) < 2 or len(sl_idx) < 2: 
        return {"trend": "RANGING", "zone": zone}
        
    last_sh, last_sl = [highs[i] for i in sh_idx[-2:]], [lows[i] for i in sl_idx[-2:]]
    
    trend = "RANGING"
    if last_sh[-1] > last_sh[-2] and last_sl[-1] > last_sl[-2]: trend = "BULLISH"
    elif last_sh[-1] < last_sh[-2] and last_sl[-1] < last_sl[-2]: trend = "BEARISH"
    
    return {"trend": trend, "zone": zone}

def detect_fvg(df: pl.DataFrame, lookback: int = 50) -> dict:
    """
    Detecta Imbalances / Fair Value Gaps (IFV).
    BISI: Vacío alcista (Low de vela 3 > High de vela 1).
    SIBI: Vacío bajista (High de vela 3 < Low de vela 1).
    """
    if len(df) < lookback: return {"bisi": [], "sibi": []}
    
    subset = df.tail(lookback)
    highs, lows = subset["high"].to_numpy(), subset["low"].to_numpy()
    
    bisi_zones = [] # Buyside Imbalance Sellside Inefficiency (Alcista)
    sibi_zones = [] # Sellside Imbalance Buyside Inefficiency (Bajista)
    
    for i in range(2, len(highs)):
        # Bullish FVG (BISI)
        if lows[i] > highs[i-2]:
            bisi_zones.append({"top": lows[i], "bottom": highs[i-2], "idx": i-1})
        # Bearish FVG (SIBI)
        elif highs[i] < lows[i-2]:
            sibi_zones.append({"top": lows[i-2], "bottom": highs[i], "idx": i-1})
            
    return {"bisi": bisi_zones, "sibi": sibi_zones}

def find_key_levels(df: pl.DataFrame, lookback: int = 150) -> dict:
    """
    Bloque de Liquidez: Order Blocks + FVG + Equal Highs/Lows.
    Identifica Puntos de Interés (POI) institucionales reales.
    """
    if len(df) < lookback: return {"nearest_resistance": None, "nearest_support": None}
    
    subset = df.tail(lookback)
    opens, closes = subset["open"].to_numpy(), subset["close"].to_numpy()
    highs, lows = subset["high"].to_numpy(), subset["low"].to_numpy()
    curr_p = closes[-1]

    # 1. Buscamos ineficiencias (FVG) como confirmación
    fvgs = detect_fvg(df, lookback=lookback)
    
    bullish_obs = []
    bearish_obs = []

    # 2. RASTREO DE ORDER BLOCKS INSTITUCIONALES
    # Un verdadero OB es la vela contraria que origina el FVG.
    
    # OB Alcista (Bullish OB): Última vela bajista antes de un BISI
    for bisi in fvgs["bisi"]:
        fvg_idx = bisi["idx"]
        # Buscamos hacia atrás la última vela bajista (close < open)
        for j in range(fvg_idx - 1, max(0, fvg_idx - 10), -1):
            if closes[j] < opens[j]:
                bullish_obs.append({"top": highs[j], "bottom": lows[j]})
                break # Encontramos el bloque

    # OB Bajista (Bearish OB): Última vela alcista antes de un SIBI
    for sibi in fvgs["sibi"]:
        fvg_idx = sibi["idx"]
        for j in range(fvg_idx - 1, max(0, fvg_idx - 10), -1):
            if closes[j] > opens[j]:
                bearish_obs.append({"top": highs[j], "bottom": lows[j]})
                break

    # 3. TRAMPAS RETAIL (Equal Highs / Lows)
    # Si hay dos máximos muy cerca, es liquidez (BSL), el precio los va a romper.
    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n=5)
    
    resists = [highs[i] for i in sh_idx if highs[i] > curr_p]
    supps   = [lows[i]  for i in sl_idx if lows[i]  < curr_p]
    
    # 4. SÍNTESIS: Definir las barreras reales para Zetsu
    
    # Soporte Institucional (nearest_support): 
    # Prioridad 1: Techo de un Order Block alcista mitigable.
    valid_sup_ob = [ob["top"] for ob in bullish_obs if ob["top"] < curr_p]
    # Prioridad 2: Soporte geométrico clásico (si no hay OB)
    nearest_sup = max(valid_sup_ob) if valid_sup_ob else (max(supps) if supps else None)

    # Resistencia Institucional (nearest_resistance):
    # Prioridad 1: Base de un Order Block bajista mitigable.
    valid_res_ob = [ob["bottom"] for ob in bearish_obs if ob["bottom"] > curr_p]
    nearest_res = min(valid_res_ob) if valid_res_ob else (min(resists) if resists else None)

    return {
        "nearest_resistance": nearest_res, 
        "nearest_support": nearest_sup
    }

def detect_liquidity_sweep(df: pl.DataFrame, lookback: int = 20) -> dict:
    """Detecta SFP (Swing Failure Pattern) / Caza de Stops."""
    if len(df) < lookback + 2: return {"sweep": False, "direction": None}
    
    subset = df.tail(lookback)
    lows, highs, closes = subset["low"].to_numpy(), subset["high"].to_numpy(), subset["close"].to_numpy()
    
    p_low, p_high = np.min(lows[:-1]), np.max(highs[:-1])
    
    # Toma de BSL (Buy-Side Liquidity) y rechazo
    if highs[-1] > p_high and closes[-1] < p_high: return {"sweep": True, "direction": "BEAR"}
    # Toma de SSL (Sell-Side Liquidity) y rechazo
    if lows[-1] < p_low and closes[-1] > p_low: return {"sweep": True, "direction": "BULL"}
    
    return {"sweep": False, "direction": None}