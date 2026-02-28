# research/btc_backtester.py — V10.0 TIER SYSTEM
"""
Backtester V10.0 — Zetzu Hunt Tier System
==========================================
Cambios vs V9.2:
  - El tier viene de barriers["tier"] (R:R geométrico), no de la prob.
  - El multiplicador de posición viene de barriers["mult"].
  - El reporte desglosa performance por tier (Scout / Ambush / Unicorn).
  - Blackbox captura el tier real en el ADN del trade.
  - V10.3: Motor de Futuros (Apalancamiento) inyectado en el EXIT.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl
import numpy as np
import statistics
from collections import Counter

import configs.btc_usdt_config as config
from core.decision_engine import check_mtf_signals
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from core.risk_manager import kelly_position_size, compute_barriers, evaluate_exit
from research.blackbox import TradeBlackbox

# ── Estética ──────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"
BOLD, DIM, MAGENTA = "\033[1m", "\033[2m", "\033[95m"

BLACKBOX_OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "blackbox_export.parquet"
)

TIER_EMOJI  = {"SCOUT": "🍃", "AMBUSH": "⚔️ ", "UNICORN": "🦄"}
TIER_COLOR  = {"SCOUT": CYAN, "AMBUSH": YELLOW, "UNICORN": GREEN}


def load_and_sync_data():
    print(f"{CYAN}  [1/3] Extrayendo data cruda de PostgreSQL...{RESET}")
    df_1m = pl.read_database_uri(
        "SELECT * FROM btc_usdt ORDER BY timestamp ASC", uri=config.DB_URL
    )
    df_1m = add_indicators(df_1m)

    print(f"{CYAN}  [2/3] Construyendo capas Estructura (15m), Momentum (1h), Swing (4h) y Macro (1d)...{RESET}")
    
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_15m = add_indicators(df_15m)

    df_1h = df_1m.group_by_dynamic("timestamp", every="1h").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_1h = add_indicators(df_1h)

    # ── 4 HORAS (Swing) ──
    df_4h = df_1m.group_by_dynamic("timestamp", every="4h").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_4h = add_indicators(df_4h)

    # ── 1 DÍA (Macro) ──
    df_1d = df_1m.group_by_dynamic("timestamp", every="1d").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_1d = add_indicators(df_1d)

    print(f"{CYAN}  [*] Inyectando escáner de volumen institucional (VWAP & CVD)...{RESET}")
    df_1m  = enrich_with_volume_features(df_1m)
    df_15m = enrich_with_volume_features(df_15m)
    df_1h  = enrich_with_volume_features(df_1h)
    df_4h  = enrich_with_volume_features(df_4h)
    df_1d  = enrich_with_volume_features(df_1d)

    return df_1m, df_15m, df_1h, df_4h, df_1d


def run_simulation(df_1m, df_15m, df_1h, df_4h, df_1d):
    """Motor V10.0: Tier-based sizing + Blackbox integration (Ahora con 4H y 1D)."""
    print(f"{CYAN}  [3/3] Ejecutando simulación V10.0 (Tier System)...{RESET}")

    closes_1m = df_1m["close"].to_numpy()
    ts_1m     = df_1m["timestamp"].to_numpy()
    atrs_1m   = df_1m["atr"].to_numpy()
    
    # Índices vectorizados para sincronizar el tiempo
    ts_15m    = df_15m["timestamp"].to_numpy()
    ts_1h     = df_1h["timestamp"].to_numpy()
    ts_4h     = df_4h["timestamp"].to_numpy()
    ts_1d     = df_1d["timestamp"].to_numpy()

    capital, peak = config.INITIAL_CASH, config.INITIAL_CASH

    wallet = {
        "active": False, "buy_price": 0, "units": 0,
        "max_p": 0, "min_p": 0, "bars_in_t": 0,
        "barriers": None, "be_on": False,
        "direction": None, "mult": 1.0,
        "bayes_prob": 0.0, "tier": None,
        "trade_id": -1,
    }

    blackbox = TradeBlackbox()
    trades   = []

    print(f"{YELLOW}[DEBUG V10.2] Kelly: {config.KELLY_FRACTION} | "
          f"Scout≥{config.SCOUT_PROB_MIN}% (prob-based →17.5%) | "
          f"Ambush≥{config.AMBUSH_PROB_MIN}% (prob-based →26.3%) | "
          f"Unicorn≥{config.UNICORN_PROB_MIN}% (prob-based →45%) | "
          f"Gate R:R≥{config.RR_MIN_REQUIRED} | SL_MULT={config.ATR_SL_MULT}{RESET}")

    for idx in range(150, len(closes_1m)):
        curr_p  = closes_1m[idx]
        curr_ts = ts_1m[idx]

        # ── Mantenimiento de trade activo ────────────────────────────────────
        if wallet["active"]:
            wallet["bars_in_t"] += 1

            if wallet["direction"] == "LONG":
                if curr_p > wallet["max_p"]: wallet["max_p"] = curr_p
                if not wallet["be_on"] and curr_p >= wallet["barriers"]["be_trigger"]:
                    wallet["be_on"] = True
            else:
                if curr_p < wallet["min_p"]: wallet["min_p"] = curr_p
                if not wallet["be_on"] and curr_p <= wallet["barriers"]["be_trigger"]:
                    wallet["be_on"] = True

            signal, reason = evaluate_exit(curr_p, wallet)

            if signal == "EXIT":
                # ── MOTOR DE FUTUROS: CÁLCULO DE PNL APALANCADO ──
                # 1. Calculamos cuánto margen (plata tuya) se bloqueó en este trade
                invested_margin = wallet["units"] * wallet["buy_price"]
                
                # 2. Calculamos el movimiento real del precio en porcentaje
                if wallet["direction"] == "LONG":
                    pnl = (curr_p / wallet["buy_price"] - 1) * 100
                else:
                    pnl = (wallet["buy_price"] / curr_p - 1) * 100
                
                # 3. Aplicamos el multiplicador de apalancamiento
                leverage = getattr(config, "LEVERAGE", 1) 
                profit_loss_usd = invested_margin * leverage * (pnl / 100)
                
                # 4. Devolvemos tu margen a la cuenta + la ganancia/pérdida apalancada
                capital += (invested_margin + profit_loss_usd)

                blackbox.label_exit(
                    trade_id=wallet["trade_id"],
                    pnl=pnl,
                    reason=reason,
                    bars=wallet["bars_in_t"],
                )

                trades.append({
                    "pnl":    pnl,
                    "reason": reason,
                    "rr":     wallet["barriers"]["rr"],
                    "prob":   wallet["bayes_prob"],
                    "tier":   wallet["tier"],
                    "mult":   wallet["barriers"].get("mult", 1.0),
                    "dir":    wallet["direction"],
                    "bars":   wallet["bars_in_t"],
                })

                if capital > peak: peak = capital
                wallet["active"] = False

            continue

        # ── Búsqueda de entrada ───────────────────────────────────────────────
        i15 = max(0, int(np.searchsorted(ts_15m, curr_ts, side="right")) - 1)
        i1h = max(0, int(np.searchsorted(ts_1h,  curr_ts, side="right")) - 1)
        i4h = max(0, int(np.searchsorted(ts_4h,  curr_ts, side="right")) - 1)
        i1d = max(0, int(np.searchsorted(ts_1d,  curr_ts, side="right")) - 1)

        slice_1m  = df_1m.slice(idx - 150, 151)
        slice_15m = df_15m.slice(max(0, i15 - 119), 120)
        slice_1h  = df_1h.slice(max(0, i1h - 48),  49)
        slice_4h  = df_4h.slice(max(0, i4h - 24),  25) # 24 velas de 4H = 4 días
        slice_1d  = df_1d.slice(max(0, i1d - 14),  15) # 14 velas de 1D = 14 días

        # Pasamos las 5 temporalidades al motor de decisión
        signal, reason, barriers, prob, direction = check_mtf_signals(
            slice_1m, slice_15m, slice_1h, slice_4h, slice_1d, wallet
        )

        # ── Ejecución de entrada ──────────────────────────────────────────────
        if signal == "ENTRY":
            atr_1m = atrs_1m[idx]
            if np.isnan(atr_1m) or not barriers:
                continue

            tier       = barriers["tier"]
            multiplier = barriers["mult"]      
            base_frac  = config.RISK_PER_TRADE_PCT

            tier_caps  = {"SCOUT": 0.20, "AMBUSH": 0.30, "UNICORN": 0.45}
            cap        = tier_caps.get(tier, 0.30)
            invest_frac = min(base_frac * 10.0 * multiplier, cap)
            invest      = capital * invest_frac
            capital    -= invest

            # ── Blackbox: fotografiar ADN del trade con las nuevas temporalidades ──
            trade_id = blackbox.capture_entry(
                timestamp   = curr_ts,
                entry_price = curr_p,
                direction   = direction,
                barriers    = barriers,
                prob        = prob,
                mult        = multiplier,
                df_1m       = slice_1m,
                df_15m      = slice_15m,
                df_1h       = slice_1h,
                df_4h       = slice_4h, # ¡NUEVO!
                df_1d       = slice_1d, # ¡NUEVO!
            )

            wallet.update({
                "active":     True,
                "buy_price":  curr_p,
                "units":      invest / curr_p,
                "max_p":      curr_p,
                "min_p":      curr_p,
                "bars_in_t":  0,
                "barriers":   barriers,
                "be_on":      False,
                "direction":  direction,
                "bayes_prob": prob,
                "tier":       tier,
                "mult":       multiplier,
                "trade_id":   trade_id,
            })

    # ── Exportar Blackbox ─────────────────────────────────────────────────────
    print(f"\n{MAGENTA}  [BLACKBOX] Exportando dataset ADN...{RESET}")
    blackbox.export_parquet(BLACKBOX_OUTPUT)

    return trades, capital, blackbox


def print_fancy_report(trades, final_cap, blackbox=None):
    if not trades:
        return print(f"\n{RED}Zetzu no encontró presas. Revisa filtros en config.py.{RESET}")

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    wr     = len(wins) / len(trades) * 100
    avg_win  = statistics.mean([t["pnl"] for t in wins])   if wins   else 0
    avg_loss = statistics.mean([t["pnl"] for t in losses]) if losses else 0

    reason_counts = Counter(t["reason"] for t in trades)
    pnls  = [t["pnl"] for t in trades]
    sharpe = (statistics.mean(pnls) / statistics.stdev(pnls)) if len(pnls) > 1 else 0
    avg_bars = statistics.mean([t.get("bars", 0) for t in trades])

    print(f"\n{BOLD}{CYAN}╔{'═'*56}╗")
    print(f"║{'BACKTESTER V10.0 — ZETZU HUNT TIER SYSTEM':^56}║")
    print(f"╚{'═'*56}╝{RESET}")
    print(f"  💰 CAPITAL FINAL  : {GREEN}${final_cap:,.2f}{RESET}")
    print(f"  📊 TOTAL TRADES   : {len(trades)} ({GREEN}{len(wins)}W{RESET} / {RED}{len(losses)}L{RESET})")
    print(f"  📈 WIN RATE       : {YELLOW}{wr:.2f}%{RESET}")
    print(f"  🎯 R:R REALIZADO  : {CYAN}{statistics.mean([t['rr'] for t in trades]):.2f}{RESET}")
    print(f"  🤑 AVG WIN / LOSS : {GREEN}+{avg_win:.3f}%{RESET} / {RED}{avg_loss:.3f}%{RESET}")
    asym_c = GREEN if (avg_win + avg_loss) > 0 else RED
    print(f"  ⚖️  ASIMETRÍA NETA : {asym_c}{avg_win + avg_loss:+.3f}%{RESET}")
    print(f"  📐 SHARPE (PnL%)  : {CYAN}{sharpe:.3f}{RESET}")
    print(f"  ⏱️  DURACIÓN PROM  : {avg_bars:.0f} barras (~{avg_bars/60:.1f}h)")

    # ── Desglose por tier ─────────────────────────────────────────────────────
    print(f"\n{DIM}  ── PERFORMANCE POR TIER ────────────────────────────────{RESET}")
    print(f"  {'TIER':<12} | {'N':>5} | {'WR':>7} | {'AVG_WIN':>9} | {'AVG_LOSS':>9} | {'EV':>9} | {'RR_PROM':>7}")
    print(f"  {'─'*12}-+-{'─'*5}-+-{'─'*7}-+-{'─'*9}-+-{'─'*9}-+-{'─'*9}-+-{'─'*7}")

    for tier_name in ["SCOUT", "AMBUSH", "UNICORN"]:
        tier_t = [t for t in trades if t.get("tier") == tier_name]
        if not tier_t:
            emoji = TIER_EMOJI.get(tier_name, "")
            print(f"  {emoji}{tier_name:<10} | {'—':>5} | {'—':>7} | {'—':>9} | {'—':>9} | {'—':>9} | {'—':>7}")
            continue

        t_wins  = [t for t in tier_t if t["pnl"] > 0]
        t_loss  = [t for t in tier_t if t["pnl"] <= 0]
        t_wr    = len(t_wins) / len(tier_t) * 100
        t_aw    = statistics.mean([t["pnl"] for t in t_wins]) if t_wins else 0
        t_al    = statistics.mean([t["pnl"] for t in t_loss]) if t_loss else 0
        t_ev    = statistics.mean([t["pnl"] for t in tier_t])
        t_rr    = statistics.mean([t["rr"]  for t in tier_t])
        emoji   = TIER_EMOJI.get(tier_name, "")
        color   = TIER_COLOR.get(tier_name, RESET)
        ev_c    = GREEN if t_ev > 0 else RED

        print(f"  {emoji}{tier_name:<10} | {color}{len(tier_t):>5}{RESET} | "
              f"{t_wr:>6.1f}% | {GREEN}{t_aw:>+8.3f}%{RESET} | "
              f"{RED}{t_al:>+8.3f}%{RESET} | {ev_c}{t_ev:>+8.3f}%{RESET} | "
              f"{CYAN}{t_rr:>6.2f}{RESET}")

    # ── Distribución de salidas ───────────────────────────────────────────────
    print(f"\n{DIM}  ── DISTRIBUCIÓN DE SALIDAS ────────────────────────────{RESET}")
    for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(trades) * 100
        bar = "█" * int(pct / 5)
        print(f"  {reason:<20}: {cnt:>4} ({pct:>5.1f}%)  {DIM}{bar}{RESET}")

    # ── Blackbox summary ──────────────────────────────────────────────────────
    if blackbox:
        summary = blackbox.get_summary()
        print(f"\n{DIM}  ── CAJA NEGRA (IA1 → IA2) ─────────────────────────{RESET}")
        print(f"  🧬 ADN snapshots  : {MAGENTA}{summary.get('labeled', 0)} trades{RESET}")
        print(f"  📦 Features/trade : {summary.get('n_features', 0)}")
        print(f"  💾 Export         : {CYAN}blackbox_export.parquet{RESET}")

    print(f"{DIM}{'─'*58}{RESET}\n")


if __name__ == "__main__":
    d1, d15, d1h, d4h, d1d = load_and_sync_data()
    results, cap, bb = run_simulation(d1, d15, d1h, d4h, d1d)
    print_fancy_report(results, cap, bb)