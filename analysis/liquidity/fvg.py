import polars as pl
from typing import Dict, List, Any

def detect_fvg(df: pl.DataFrame, lookback: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Detecta Fair Value Gaps evitando estrictamente el repintado de velas en curso."""
    if len(df) < lookback: 
        return {"bisi": [], "sibi": []}
        
    subset = df.tail(lookback)
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    n      = len(highs)
    
    bisi_zones: List[Dict[str, Any]] = []
    sibi_zones: List[Dict[str, Any]] = []
    
    # PREVENCIÓN DE LOOKAHEAD BIAS: 
    # Detenemos el escaneo una vela antes (n - 1) para asegurar que la tercera vela 
    # que confirma el FVG esté completamente cerrada.
    limit = n - 1 
    
    for i in range(2, limit):
        if lows[i] > highs[i-2]:
            bisi_zones.append({
                "top": float(lows[i]), "bottom": float(highs[i-2]), "size": float(lows[i] - highs[i-2]),
                "idx": i - 1, "recency": n - i
            })
        elif highs[i] < lows[i-2]:
            sibi_zones.append({
                "top": float(lows[i-2]), "bottom": float(highs[i]), "size": float(lows[i-2] - highs[i]),
                "idx": i - 1, "recency": n - i
            })
            
    bisi_zones.sort(key=lambda x: x["recency"])
    sibi_zones.sort(key=lambda x: x["recency"])
    return {"bisi": bisi_zones, "sibi": sibi_zones}