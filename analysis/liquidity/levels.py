import polars as pl
from analysis.structure.fractals import find_swing_highs_lows
from analysis.liquidity.fvg import detect_fvg

def find_key_levels(df: pl.DataFrame, lookback: int = 150) -> dict:
    if len(df) < 20:
        return {"nearest_resistance": None, "nearest_support": None, "bullish_obs": [], "bearish_obs": []}
    actual_lb = min(lookback, len(df))
    subset = df.tail(actual_lb)
    opens  = subset["open"].to_numpy()
    closes = subset["close"].to_numpy()
    highs  = subset["high"].to_numpy()
    lows   = subset["low"].to_numpy()
    curr_p = closes[-1]

    fvgs = detect_fvg(df, lookback=actual_lb)
    bullish_obs, bearish_obs = [], []

    for bisi in fvgs["bisi"]:
        fi = bisi.get("idx", 0)
        fi = min(fi, len(closes) - 2)
        for j in range(fi - 1, max(0, fi - 10), -1):
            if closes[j] < opens[j]:
                bullish_obs.append({"top": highs[j], "bottom": lows[j], "recency": len(closes) - fi})
                break

    for sibi in fvgs["sibi"]:
        fi = sibi.get("idx", 0)
        fi = min(fi, len(closes) - 2)
        for j in range(fi - 1, max(0, fi - 10), -1):
            if closes[j] > opens[j]:
                bearish_obs.append({"top": highs[j], "bottom": lows[j], "recency": len(closes) - fi})
                break

    sh_idx, sl_idx = find_swing_highs_lows(highs, lows, n=5)
    resists = [highs[i] for i in sh_idx if highs[i] > curr_p]
    supps   = [lows[i]  for i in sl_idx if lows[i]  < curr_p]

    valid_sup_ob = [ob["top"]    for ob in bullish_obs if ob["top"]    < curr_p]
    valid_res_ob = [ob["bottom"] for ob in bearish_obs if ob["bottom"] > curr_p]

    return {
        "nearest_resistance": min(valid_res_ob) if valid_res_ob else (min(resists) if resists else None),
        "nearest_support":    max(valid_sup_ob) if valid_sup_ob else (max(supps)   if supps   else None),
        "bullish_obs": bullish_obs, "bearish_obs": bearish_obs,
    }

def detect_ob_proximity(curr_p: float, levels: dict, tolerance_pct: float = 0.003) -> dict:
    tolerance = curr_p * tolerance_pct
    for ob in levels.get("bullish_obs", []):
        if ob["bottom"] - tolerance <= curr_p <= ob["top"] + tolerance:
            dist = abs(curr_p - (ob["top"] + ob["bottom"]) / 2) / curr_p
            return {"touching": True, "type": "bullish", "ob": ob, "dist_pct": dist}
    for ob in levels.get("bearish_obs", []):
        if ob["bottom"] - tolerance <= curr_p <= ob["top"] + tolerance:
            dist = abs(curr_p - (ob["top"] + ob["bottom"]) / 2) / curr_p
            return {"touching": True, "type": "bearish", "ob": ob, "dist_pct": dist}
    min_dist = 1.0
    for ob in levels.get("bullish_obs", []) + levels.get("bearish_obs", []):
        mid = (ob["top"] + ob["bottom"]) / 2
        d   = abs(curr_p - mid) / curr_p
        if d < min_dist: min_dist = d
    return {"touching": False, "type": None, "ob": None, "dist_pct": min_dist}