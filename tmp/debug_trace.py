"""
Debug trace — ejecutar desde ~/Unknown-bot con:
  poetry run python /tmp/debug_trace.py
"""
import sys, os
sys.path.insert(0, '/home/fapectm/Unknown-bot')

import polars as pl
import numpy as np
import configs.btc_usdt_config as config
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from analysis.market_structure import detect_regime, detect_liquidity_sweep, find_key_levels
from core.risk_manager import compute_barriers, classify_tier, enrich_barriers_with_tier
from core.decision_engine import zetzu_oraculo

print("="*60)
print("DEBUG TRACE V10.2 — DIAGNÓSTICO DE FILTROS")
print("="*60)

# Cargar datos reales
print("\n[1] Cargando datos de la DB...")
df_1m = pl.read_database_uri(
    "SELECT * FROM btc_usdt ORDER BY timestamp ASC",
    uri=config.DB_URL
)
df_1m = add_indicators(df_1m)
print(f"    df_1m: {len(df_1m)} filas")

df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
    pl.col("open").first(), pl.col("high").max(),
    pl.col("low").min(), pl.col("close").last(), pl.col("volume").sum()
])
df_15m = add_indicators(df_15m)
print(f"    df_15m: {len(df_15m)} filas")

df_1h = df_1m.group_by_dynamic("timestamp", every="1h").agg([
    pl.col("open").first(), pl.col("high").max(),
    pl.col("low").min(), pl.col("close").last(), pl.col("volume").sum()
])
df_1h = add_indicators(df_1h)
print(f"    df_1h: {len(df_1h)} filas")

df_1m  = enrich_with_volume_features(df_1m)
df_15m = enrich_with_volume_features(df_15m)
df_1h  = enrich_with_volume_features(df_1h)

# Tomar muestra de 500 puntos aleatorios para diagnóstico
import random
indices = sorted(random.sample(range(150, len(df_1m)), min(500, len(df_1m)-150)))

counters = {
    "total":          0,
    "GATE_RR":        0,   # compute_barriers retorna None
    "LOW_PROB":       0,   # prob < 70%
    "ENTRY":          0,   # señal válida
    "no_atr":         0,   # ATR nulo
    "no_levels":      0,   # sin niveles estructurales
}

prob_dist = []
rr_dist   = []

ts_15m = df_15m["timestamp"].to_numpy()
ts_1h  = df_1h["timestamp"].to_numpy()
ts_1m  = df_1m["timestamp"].to_numpy()
closes = df_1m["close"].to_numpy()
atrs   = df_1m["atr"].to_numpy()

print(f"\n[2] Analizando {len(indices)} puntos aleatorios...\n")

for idx in indices:
    counters["total"] += 1
    curr_ts = ts_1m[idx]
    curr_p  = closes[idx]

    i15 = max(0, int(np.searchsorted(ts_15m, curr_ts, side="right")) - 1)
    i1h = max(0, int(np.searchsorted(ts_1h,  curr_ts, side="right")) - 1)

    slice_1m  = df_1m.slice(idx - 150, 151)
    slice_15m = df_15m.slice(max(0, i15 - 119), 120)
    slice_1h  = df_1h.slice(max(0, i1h - 30), 31)

    c15m = slice_15m.tail(1).to_dicts()[0]
    c1h  = slice_1h.tail(1).to_dicts()[0]

    atr_15m = c15m.get("atr")
    if not atr_15m or np.isnan(atr_15m) or atr_15m <= 0:
        counters["no_atr"] += 1
        continue

    # Dirección
    direction = "LONG" if curr_p > c1h.get("ema_trend", 0) else "SHORT"

    # Key levels
    levels = find_key_levels(slice_15m)
    nearest_res = levels.get("nearest_resistance")
    nearest_sup = levels.get("nearest_support")

    if nearest_res is None and nearest_sup is None:
        counters["no_levels"] += 1
        continue

    # compute_barriers (gate R:R)
    barriers = compute_barriers(
        entry_price=curr_p, atr_15m=atr_15m, direction=direction,
        nearest_res=nearest_res, nearest_sup=nearest_sup,
    )

    if barriers is None:
        counters["GATE_RR"] += 1
        # Calcular cuál sería el R:R para diagnóstico
        if direction == "LONG" and nearest_res and nearest_sup:
            sl = max(nearest_sup, curr_p - config.ATR_SL_MULT * atr_15m)
            risk = curr_p - sl
            reward = nearest_res - curr_p
            if risk > 0:
                rr_dist.append(reward / risk)
        continue

    rr_dist.append(barriers["rr"])

    # Probabilidad
    prob = zetzu_oraculo.zetzu_hunt_probability(slice_1m, slice_15m, slice_1h, direction, barriers)
    prob_dist.append(prob)

    tier_ok = enrich_barriers_with_tier(barriers, prob, direction, curr_p)
    if not tier_ok:
        counters["LOW_PROB"] += 1
    else:
        counters["ENTRY"] += 1

# Reporte
print(f"{'─'*50}")
print(f"RESULTADOS ({counters['total']} puntos analizados):")
print(f"{'─'*50}")
print(f"  Sin ATR válido     : {counters['no_atr']:>5}")
print(f"  Sin niveles struct : {counters['no_levels']:>5}")
print(f"  Bloqueados GATE_RR : {counters['GATE_RR']:>5}  ({counters['GATE_RR']/counters['total']*100:.1f}%)")
print(f"  Bloqueados LOW_PROB: {counters['LOW_PROB']:>5}  ({counters['LOW_PROB']/counters['total']*100:.1f}%)")
print(f"  ENTRY válidos      : {counters['ENTRY']:>5}  ({counters['ENTRY']/counters['total']*100:.1f}%)")

if rr_dist:
    import statistics
    print(f"\nDistribución R:R (todos los setups, incl. rechazados):")
    print(f"  Count: {len(rr_dist)} | Min: {min(rr_dist):.2f} | Max: {max(rr_dist):.2f}")
    print(f"  Media: {statistics.mean(rr_dist):.2f} | Mediana: {statistics.median(rr_dist):.2f}")
    below_gate = sum(1 for r in rr_dist if r < config.RR_MIN_REQUIRED)
    print(f"  R:R < {config.RR_MIN_REQUIRED}: {below_gate}/{len(rr_dist)} ({below_gate/len(rr_dist)*100:.1f}% rechazados por gate)")

if prob_dist:
    import statistics
    print(f"\nDistribución PROBABILIDAD (post-gate R:R):")
    print(f"  Count: {len(prob_dist)} | Min: {min(prob_dist):.1f}% | Max: {max(prob_dist):.1f}%")
    print(f"  Media: {statistics.mean(prob_dist):.1f}% | Mediana: {statistics.median(prob_dist):.1f}%")
    p60 = sum(1 for p in prob_dist if p >= 60)
    p70 = sum(1 for p in prob_dist if p >= 70)
    p75 = sum(1 for p in prob_dist if p >= 75)
    p80 = sum(1 for p in prob_dist if p >= 80)
    print(f"  ≥60%: {p60} | ≥70% (Scout): {p70} | ≥75% (Ambush): {p75} | ≥80% (Unicorn): {p80}")

# Diagnóstico de un punto específico
print(f"\n{'─'*50}")
print("MUESTRA DIAGNÓSTICA — último punto analizado:")
idx_sample = indices[-10]
curr_p = closes[idx_sample]
i15 = max(0, int(np.searchsorted(ts_15m, ts_1m[idx_sample], side="right")) - 1)
i1h = max(0, int(np.searchsorted(ts_1h,  ts_1m[idx_sample], side="right")) - 1)
sl15m = df_15m.slice(max(0, i15 - 119), 120)
sl1h  = df_1h.slice(max(0, i1h - 30), 31)
c15m  = sl15m.tail(1).to_dicts()[0]
c1h   = sl1h.tail(1).to_dicts()[0]
levels = find_key_levels(sl15m)
print(f"  Price    : ${curr_p:,.2f}")
print(f"  ATR 15m  : {c15m.get('atr')}")
print(f"  EMA_trend: {c1h.get('ema_trend')}")
print(f"  Direction: {'LONG' if curr_p > c1h.get('ema_trend',0) else 'SHORT'}")
print(f"  Nearest R: {levels['nearest_resistance']}")
print(f"  Nearest S: {levels['nearest_support']}")
print(f"  Res %dist: {levels['resistance_dist_pct']}")
print(f"  Sup %dist: {levels['support_dist_pct']}")