import polars as pl

def detect_fvg(df: pl.DataFrame, lookback: int = 50) -> dict:
    if len(df) < lookback: return {"bisi": [], "sibi": []}
    subset = df.tail(lookback)
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    n      = len(highs)
    bisi_zones, sibi_zones = [], []
    for i in range(2, n):
        if lows[i] > highs[i-2]:
            bisi_zones.append({
                "top": lows[i], "bottom": highs[i-2], "size": lows[i] - highs[i-2],
                "idx": i - 1, "recency": n - i
            })
        elif highs[i] < lows[i-2]:
            sibi_zones.append({
                "top": lows[i-2], "bottom": highs[i], "size": lows[i-2] - highs[i],
                "idx": i - 1, "recency": n - i
            })
    bisi_zones.sort(key=lambda x: x["recency"])
    sibi_zones.sort(key=lambda x: x["recency"])
    return {"bisi": bisi_zones, "sibi": sibi_zones}