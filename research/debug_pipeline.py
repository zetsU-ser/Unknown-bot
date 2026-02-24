# debug_pipeline.py — corre esto desde research/
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import polars as pl
import numpy as np
from core.config import *
from analysis.indicators import add_indicators
from analysis.market_structure import detect_regime, detect_liquidity_sweep
from core.risk_manager import compute_barriers

print("=" * 60)
print("DIAGNÓSTICO DEL PIPELINE")
print("=" * 60)

# ── 1. Cargar datos ───────────────────────────────────────────
query = "SELECT * FROM btc_usdt ORDER BY timestamp ASC"
df_1m = pl.read_database_uri(query=query, uri=DB_URL)
print(f"\n[DB] Filas cargadas: {len(df_1m)}")
print(f"[DB] Columnas: {df_1m.columns}")
print(f"[DB] Rango: {df_1m['timestamp'].min()} → {df_1m['timestamp'].max()}")

# ── 2. Indicadores ────────────────────────────────────────────
df_1m = add_indicators(df_1m)
print(f"\n[INDICADORES] Columnas después de add_indicators: {df_1m.columns}")

# Últimos valores
last = df_1m.tail(1).to_dicts()[0]
print(f"\n[ÚLTIMO CIERRE]")
print(f"  close      = {last.get('close')}")
print(f"  ema_fast   = {last.get('ema_fast')}")
print(f"  ema_slow   = {last.get('ema_slow')}")
print(f"  ema_trend  = {last.get('ema_trend')}")
print(f"  rsi        = {last.get('rsi')}")
print(f"  atr        = {last.get('atr')}")
print(f"  z_score    = {last.get('z_score')}")
print(f"  vwap       = {last.get('vwap')}")

# ── 3. Resampling 15m ─────────────────────────────────────────
df_15m = (
    df_1m.group_by_dynamic("timestamp", every="15m")
    .agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum()
    ])
)
df_15m = add_indicators(df_15m)
print(f"\n[15M] Filas: {len(df_15m)}")

last_15m = df_15m.tail(1).to_dicts()[0]
print(f"[15M ÚLTIMO]")
print(f"  close      = {last_15m.get('close')}")
print(f"  ema_trend  = {last_15m.get('ema_trend')}")
print(f"  rsi        = {last_15m.get('rsi')}")

# ── 4. Join ───────────────────────────────────────────────────
df_joined = df_1m.join_asof(df_15m, on="timestamp", strategy="backward", suffix="_15m")
print(f"\n[JOIN] Columnas 15m disponibles en joined:")
cols_15m = [c for c in df_joined.columns if c.endswith("_15m")]
print(f"  {cols_15m}")

# Verificar que los valores 15m llegan al loop
sample = df_joined.tail(5).select(cols_15m[:6]).to_dicts()
print(f"\n[JOIN SAMPLE últimas 5 filas]")
for row in sample:
    print(f"  {row}")

# ── 5. Régimen de mercado ─────────────────────────────────────
print(f"\n[RÉGIMEN 15M]")
regime = detect_regime(df_15m)
print(f"  Régimen actual: {regime}")
print(f"  Régimen requerido: {REGIME_REQUIRED}")
print(f"  → Filtro PASA: {regime == REGIME_REQUIRED}")

# ── 6. Filtro EMA trend ───────────────────────────────────────
last_1m = df_1m.tail(1).to_dicts()[0]
last_15m_d = df_15m.tail(1).to_dicts()[0]
curr_price = last_1m['close']
ema_trend_15m = last_15m_d.get('ema_trend') or last_15m_d.get('sma_200')
print(f"\n[FILTRO EMA TREND 15M]")
print(f"  Precio: {curr_price}")
print(f"  EMA200 15m: {ema_trend_15m}")
print(f"  → Filtro PASA: {curr_price > ema_trend_15m if ema_trend_15m else 'EMA None!'}")

# ── 7. RSI 15m ────────────────────────────────────────────────
rsi_15m = last_15m_d.get('rsi')
print(f"\n[FILTRO RSI 15M]")
print(f"  RSI 15m: {rsi_15m}")
print(f"  Umbral mínimo: {RSI_TREND_MIN}")
print(f"  → Filtro PASA: {rsi_15m > RSI_TREND_MIN if rsi_15m else 'RSI None!'}")

# ── 8. Z-Score ────────────────────────────────────────────────
z = last_1m.get('z_score')
print(f"\n[FILTRO Z-SCORE]")
print(f"  Z-Score: {z}")
print(f"  Umbral máx: {ZSCORE_ENTRY_MAX}")
print(f"  → Filtro PASA: {abs(z) < ZSCORE_ENTRY_MAX if z and z == z else 'Z None/NaN!'}")

# ── 9. EMA Distance ───────────────────────────────────────────
ema_1m = last_1m.get('ema_trend')
if ema_1m:
    dist = (curr_price - ema_1m) / ema_1m
    print(f"\n[FILTRO EMA DISTANCE]")
    print(f"  Precio: {curr_price} | EMA200 1m: {ema_1m}")
    print(f"  Distancia: {dist:.4f} ({dist*100:.2f}%)")
    print(f"  Máximo permitido: {EMA_DISTANCE_MAX*100:.1f}%")
    print(f"  → Filtro PASA: {dist <= EMA_DISTANCE_MAX}")

# ── 10. RSI entry en 1m ───────────────────────────────────────
rsi_1m = last_1m.get('rsi')
print(f"\n[FILTRO RSI 1M ENTRADA]")
print(f"  RSI 1m: {rsi_1m}")
print(f"  Umbral oversold: {RSI_OVERSOLD}")
print(f"  → Condición activa: {rsi_1m < RSI_OVERSOLD if rsi_1m else 'None!'}")

# ── 11. Sweep detector ────────────────────────────────────────
sweep = detect_liquidity_sweep(df_1m.tail(25))
print(f"\n[SWEEP DETECTOR]")
print(f"  Resultado: {sweep}")

# ── 12. ATR ───────────────────────────────────────────────────
atr = last_1m.get('atr')
print(f"\n[ATR]")
print(f"  ATR: {atr}")
print(f"  → Válido: {atr is not None and atr > 0 and atr == atr}")

# ── 13. Scan histórico: ¿cuántas velas pasarían cada filtro? ──
print(f"\n{'='*60}")
print("SCAN HISTÓRICO — Cuántas velas pasan cada filtro")
print("="*60)

# Usamos el df_joined completo
rows_sample = df_joined.tail(5000).iter_rows(named=True)

cnt_total = 0
cnt_regime = 0
cnt_ema_trend = 0
cnt_rsi_15m = 0
cnt_zscore = 0
cnt_ema_dist = 0
cnt_atr = 0
cnt_rsi_entry = 0
cnt_sweep = 0
cnt_vwap = 0
cnt_ema_cross = 0
cnt_score_2plus = 0

for row in df_joined.tail(5000).iter_rows(named=True):
    cnt_total += 1
    p = row['close']

    # Simular filtros uno a uno
    ema_t_15 = row.get('ema_trend_15m') or row.get('sma_200_15m')
    rsi_15   = row.get('rsi_15m')
    z        = row.get('z_score')
    ema_t_1  = row.get('ema_trend')
    rsi_1    = row.get('rsi')
    vwap     = row.get('vwap')
    ef       = row.get('ema_fast')
    es       = row.get('ema_slow')
    atr_v    = row.get('atr')

    # Filtro 1: Régimen — aproximamos con EMA trend 15m (no tenemos swing en row)
    regime_ok = ema_t_15 is not None and p > ema_t_15
    if regime_ok: cnt_ema_trend += 1

    # Filtro 2: RSI 15m
    rsi15_ok = rsi_15 is not None and rsi_15 > RSI_TREND_MIN
    if regime_ok and rsi15_ok: cnt_rsi_15m += 1

    # Filtro 3: Z-Score
    z_ok = z is None or z != z or abs(z) < ZSCORE_ENTRY_MAX
    if regime_ok and rsi15_ok and z_ok: cnt_zscore += 1

    # Filtro 4: EMA distance
    dist_ok = ema_t_1 is None or ema_t_1 <= 0 or ((p - ema_t_1) / ema_t_1) <= EMA_DISTANCE_MAX
    if regime_ok and rsi15_ok and z_ok and dist_ok: cnt_ema_dist += 1

    # Filtro 5: ATR
    atr_ok = atr_v is not None and atr_v > 0 and atr_v == atr_v
    if regime_ok and rsi15_ok and z_ok and dist_ok and atr_ok: cnt_atr += 1

    # Scoring
    if regime_ok and rsi15_ok and z_ok and dist_ok and atr_ok:
        s1 = rsi_1 is not None and rsi_1 < RSI_OVERSOLD
        s3 = vwap is not None and p < vwap
        s4 = ef is not None and es is not None and ef < es
        score = s1 + s3 + s4  # sweep no lo podemos calcular en row
        if s1: cnt_rsi_entry += 1
        if s3: cnt_vwap += 1
        if s4: cnt_ema_cross += 1
        if score >= 2: cnt_score_2plus += 1

print(f"  Filas analizadas (últimas 5000):  {cnt_total}")
print(f"  Pasan precio > EMA200 15m:        {cnt_ema_trend}")
print(f"  + RSI 15m > {RSI_TREND_MIN}:               {cnt_rsi_15m}")
print(f"  + Z-Score < {ZSCORE_ENTRY_MAX}:              {cnt_zscore}")
print(f"  + EMA dist < {EMA_DISTANCE_MAX*100:.0f}%:             {cnt_ema_dist}")
print(f"  + ATR válido:                     {cnt_atr}")
print(f"  ↳ RSI 1m < {RSI_OVERSOLD} (cond 1):         {cnt_rsi_entry}")
print(f"  ↳ Precio < VWAP (cond 3):         {cnt_vwap}")
print(f"  ↳ EMA cross setup (cond 4):       {cnt_ema_cross}")
print(f"  ↳ Score >= 2 (SIN sweep):         {cnt_score_2plus}")
print()
print("NOTA: El régimen real (HH/HL) es más estricto que EMA > precio.")
print("      Si cnt_ema_dist es 0 → el precio siempre está >3% de EMA200.")
print("      Si cnt_rsi_entry es 0 → RSI nunca bajó de", RSI_OVERSOLD, "en zona válida.")