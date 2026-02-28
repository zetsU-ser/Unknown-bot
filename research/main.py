# main.py — UNKNOWN-BOT V10.2 — Loop en Vivo
"""
Motor en Vivo V10.2 — Zetzu Hunt Tier System
=============================================
Arquitectura: idéntica al backtester (mismo wallet dict, mismo pipeline).
La única diferencia vs. el backtester es que en lugar de iterar sobre datos
históricos, hace una query a la DB cada 60 segundos y procesa el último bar.

Flujo por ciclo:
  1. Cargar últimas CANDLE_LIMIT barras 1m de la DB
  2. Agregar a 15m y 1h
  3. Añadir indicadores + VWAP/CVD
  4. Si hay trade activo → evaluate_exit() directo (sin check_mtf_signals)
  5. Si no hay trade → check_mtf_signals() → busca ENTRY
  6. En ENTRY: sizing por tier, abrir posición
  7. En EXIT: cerrar posición, loguear resultado
"""
import sys
import os
import time
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import polars as pl
import numpy as np

import configs.btc_usdt_config as config
from core.decision_engine import check_mtf_signals
from core.risk_manager import evaluate_exit
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("zetzu_live")

# ── Colores consola ───────────────────────────────────────────────────────────
G, R, C, Y, M  = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[95m"
BOLD, DIM, RST = "\033[1m", "\033[2m", "\033[0m"

TIER_COLOR = {"SCOUT": C, "AMBUSH": Y, "UNICORN": G}
TIER_EMOJI = {"SCOUT": "🍃", "AMBUSH": "⚔️ ", "UNICORN": "🦄"}
EXIT_COLOR = {"SL": R, "TP": G, "PROFIT_LOCK": G, "TIMEOUT": Y}


# ─────────────────────────────────────────────────────────────────────────────
def load_live_data() -> tuple:
    """
    Carga las últimas CANDLE_LIMIT barras 1m de la DB y construye los
    tres timeframes que necesita el pipeline de decisión.

    Returns:
        (df_1m, df_15m, df_1h) — DataFrames con indicadores completos
    """
    df_1m = pl.read_database_uri(
        f"SELECT * FROM btc_usdt ORDER BY timestamp DESC LIMIT {config.CANDLE_LIMIT}",
        uri=config.DB_URL,
    ).sort("timestamp")

    df_1m = add_indicators(df_1m)

    # Agregar a 15m y 1h
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ])
    df_15m = add_indicators(df_15m)

    df_1h = df_1m.group_by_dynamic("timestamp", every="1h").agg([
        pl.col("open").first(),
        pl.col("high").max(),
        pl.col("low").min(),
        pl.col("close").last(),
        pl.col("volume").sum(),
    ])
    df_1h = add_indicators(df_1h)

    # Enriquecer con VWAP y CVD (Bloque 3)
    df_1m  = enrich_with_volume_features(df_1m)
    df_15m = enrich_with_volume_features(df_15m)
    df_1h  = enrich_with_volume_features(df_1h)

    return df_1m, df_15m, df_1h


# ─────────────────────────────────────────────────────────────────────────────
def compute_invest(capital: float, peak: float, tier: str, mult: float) -> float:
    """
    Calcula el capital a invertir usando la misma fórmula que el backtester V10.2.
    Incluye el drawdown guard del Bloque 5.
    """
    drawdown = (peak - capital) / peak if peak > 0 else 0.0

    # Drawdown guard (Bloque 5)
    if drawdown >= config.MAX_DRAWDOWN_HALT:
        log.warning(f"⛔ DRAWDOWN HALT: {drawdown*100:.1f}% >= {config.MAX_DRAWDOWN_HALT*100:.0f}%")
        return 0.0

    base_frac = config.RISK_PER_TRADE_PCT
    if drawdown >= config.DRAWDOWN_REDUCE_2:
        base_frac *= 0.50
        log.info(f"⚠️  Drawdown {drawdown*100:.1f}% → sizing reducido 50%")
    elif drawdown >= config.DRAWDOWN_REDUCE_1:
        base_frac *= 0.75
        log.info(f"⚠️  Drawdown {drawdown*100:.1f}% → sizing reducido 25%")

    tier_caps = {"SCOUT": 0.20, "AMBUSH": 0.30, "UNICORN": 0.45}
    cap       = tier_caps.get(tier, 0.30)
    frac      = min(base_frac * 10.0 * mult, cap)

    return capital * frac


# ─────────────────────────────────────────────────────────────────────────────
def display_status(wallet: dict, capital: float, peak: float,
                   curr_p: float, cycle: int):
    """Imprime el estado del bot en consola cada ciclo."""
    dd = (peak - capital) / peak * 100 if peak > 0 else 0.0
    dd_c = R if dd > 5 else Y if dd > 2 else G

    print(f"\n{DIM}{'─'*62}{RST}")
    print(f"  {BOLD}Ciclo #{cycle}{RST} | "
          f"BTC ${curr_p:,.2f} | "
          f"Capital {G}${capital:,.2f}{RST} | "
          f"DD {dd_c}{dd:.1f}%{RST}")

    if wallet["active"]:
        tier   = wallet["tier"] or "—"
        emoji  = TIER_EMOJI.get(tier, "")
        tc     = TIER_COLOR.get(tier, RST)
        b      = wallet["barriers"]
        d      = wallet["direction"]
        d_c    = G if d == "LONG" else R

        if d == "LONG":
            pnl = (curr_p / wallet["buy_price"] - 1) * 100
        else:
            pnl = (wallet["buy_price"] / curr_p - 1) * 100

        pnl_c = G if pnl > 0 else R
        be_str = f"{Y}[BE ON]{RST}" if wallet["be_on"] else ""

        print(f"  {emoji}{tc}{tier}{RST} | "
              f"{d_c}{d}{RST} @ ${wallet['buy_price']:,.2f} | "
              f"PnL {pnl_c}{pnl:+.2f}%{RST} {be_str}")
        print(f"  SL ${b['sl']:,.2f} | TP ${b['tp']:,.2f} | "
              f"R:R {b['rr']:.2f} | Bar {wallet['bars_in_t']}/{b.get('max_bars', 360)}")
    else:
        print(f"  {DIM}Sin posición abierta — buscando setup...{RST}")


# ─────────────────────────────────────────────────────────────────────────────
def log_entry(wallet: dict, capital: float):
    tier  = wallet["tier"]
    emoji = TIER_EMOJI.get(tier, "")
    tc    = TIER_COLOR.get(tier, RST)
    b     = wallet["barriers"]
    d     = wallet["direction"]
    d_c   = G if d == "LONG" else R

    msg = (f"\n  {BOLD}{'═'*58}{RST}\n"
           f"  {emoji} {tc}{BOLD}NUEVA POSICIÓN — {tier}{RST}\n"
           f"  Dirección  : {d_c}{d}{RST}\n"
           f"  Entry      : ${wallet['buy_price']:,.2f}\n"
           f"  SL         : ${b['sl']:,.2f}\n"
           f"  TP         : ${b['tp']:,.2f}\n"
           f"  R:R        : {b['rr']:.2f}\n"
           f"  Prob       : {wallet['bayes_prob']:.1f}%\n"
           f"  Sizing     : ×{wallet['mult']} ({wallet['invest_pct']:.1f}% capital)\n"
           f"  Capital    : ${capital:,.2f}\n"
           f"  {BOLD}{'═'*58}{RST}")
    print(msg)
    log.warning(f"ENTRY {tier} {d} @ {wallet['buy_price']:.2f} | "
                f"SL={b['sl']:.2f} TP={b['tp']:.2f} RR={b['rr']:.2f} "
                f"prob={wallet['bayes_prob']:.1f}%")


def log_exit(wallet: dict, pnl: float, reason: str, capital: float):
    rc    = EXIT_COLOR.get(reason, RST)
    emoji = "✅" if pnl > 0 else "❌"
    tier  = wallet["tier"] or "—"
    tc    = TIER_COLOR.get(tier, RST)

    msg = (f"\n  {BOLD}{'─'*58}{RST}\n"
           f"  {emoji} {tc}{tier}{RST} CERRADO [{rc}{reason}{RST}]\n"
           f"  PnL    : {G if pnl > 0 else R}{pnl:+.3f}%{RST} | "
           f"Barras: {wallet['bars_in_t']}\n"
           f"  Capital: ${capital:,.2f}\n"
           f"  {BOLD}{'─'*58}{RST}")
    print(msg)
    log.warning(f"EXIT {reason} {tier} {wallet['direction']} | "
                f"pnl={pnl:+.3f}% bars={wallet['bars_in_t']} capital={capital:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}{C}{'═'*62}")
    print(f"   UNKNOWN-BOT V10.2 — ZETZU HUNT TIER SYSTEM — EN VIVO")
    print(f"{'═'*62}{RST}")
    print(f"  Config: SL×{config.ATR_SL_MULT} | "
          f"Risk {config.RISK_PER_TRADE_PCT*100:.2f}% | "
          f"Scout≥{config.SCOUT_PROB_MIN:.0f}% "
          f"Ambush≥{config.AMBUSH_PROB_MIN:.0f}% "
          f"Unicorn≥{config.UNICORN_PROB_MIN:.0f}%")
    print(f"  Capital inicial: ${config.INITIAL_CASH:,.2f}\n")
    log.info("UNKNOWN-BOT V10.2 INICIADO")

    # ── Estado del bot (idéntico al backtester) ───────────────────────────────
    capital = config.INITIAL_CASH
    peak    = config.INITIAL_CASH
    cycle   = 0

    wallet = {
        "active":     False,
        "buy_price":  0.0,
        "units":      0.0,
        "invest":     0.0,
        "invest_pct": 0.0,
        "max_p":      0.0,
        "min_p":      0.0,
        "bars_in_t":  0,
        "barriers":   None,
        "be_on":      False,
        "direction":  None,
        "bayes_prob": 0.0,
        "tier":       None,
        "mult":       1.0,
    }

    while True:
        try:
            cycle += 1

            # ── 1. Cargar datos ───────────────────────────────────────────────
            df_1m, df_15m, df_1h = load_live_data()

            if len(df_1m) < 150:
                print(f"  {Y}[WARMUP] Datos insuficientes ({len(df_1m)} barras){RST}")
                time.sleep(60)
                continue

            curr_p = float(df_1m["close"].tail(1)[0])
            display_status(wallet, capital, peak, curr_p, cycle)

            # ── 2. Gestión del trade activo ───────────────────────────────────
            if wallet["active"]:
                wallet["bars_in_t"] += 1

                # Actualizar extremo de precio
                if wallet["direction"] == "LONG":
                    if curr_p > wallet["max_p"]:
                        wallet["max_p"] = curr_p
                    # Activar breakeven
                    if not wallet["be_on"] and curr_p >= wallet["barriers"]["be_trigger"]:
                        wallet["be_on"] = True
                        print(f"  {Y}🔒 BREAKEVEN ACTIVADO @ ${curr_p:,.2f}{RST}")
                        log.info(f"BREAKEVEN ON @ {curr_p:.2f}")
                else:  # SHORT
                    if curr_p < wallet["min_p"]:
                        wallet["min_p"] = curr_p
                    if not wallet["be_on"] and curr_p <= wallet["barriers"]["be_trigger"]:
                        wallet["be_on"] = True
                        print(f"  {Y}🔒 BREAKEVEN ACTIVADO @ ${curr_p:,.2f}{RST}")
                        log.info(f"BREAKEVEN ON @ {curr_p:.2f}")

                # Evaluar salida
                signal, reason = evaluate_exit(curr_p, wallet)

                if signal == "EXIT":
                    # Calcular PnL
                    if wallet["direction"] == "LONG":
                        pnl = (curr_p / wallet["buy_price"] - 1) * 100
                        returned = wallet["units"] * curr_p
                    else:  # SHORT (simulado: ganancia = compra barata después de vender caro)
                        pnl      = (wallet["buy_price"] / curr_p - 1) * 100
                        returned = wallet["invest"] * (1 + pnl / 100)

                    capital += returned
                    if capital > peak:
                        peak = capital

                    log_exit(wallet, pnl, reason, capital)

                    # Reset wallet
                    wallet.update({
                        "active": False, "buy_price": 0.0, "units": 0.0,
                        "invest": 0.0, "invest_pct": 0.0,
                        "max_p": 0.0, "min_p": 0.0, "bars_in_t": 0,
                        "barriers": None, "be_on": False,
                        "direction": None, "bayes_prob": 0.0,
                        "tier": None, "mult": 1.0,
                    })

                time.sleep(60)
                continue

            # ── 3. Búsqueda de nueva entrada ──────────────────────────────────
            # Slices para la ventana de decisión (igual que el backtester)
            slice_1m  = df_1m.tail(151)
            slice_15m = df_15m.tail(61)
            slice_1h  = df_1h.tail(31)

            signal, reason, barriers, prob, direction = check_mtf_signals(
                slice_1m, slice_15m, slice_1h, wallet
            )

            print(f"  {DIM}Señal: {signal} | {reason} | prob={prob:.1f}%{RST}")

            # ── 4. Ejecución de entrada ───────────────────────────────────────
            if signal == "ENTRY" and barriers and barriers.get("tier"):
                tier = barriers["tier"]
                mult = barriers["mult"]

                invest = compute_invest(capital, peak, tier, mult)
                if invest <= 0:
                    print(f"  {Y}⚠️  Sizing bloqueado (drawdown halt o capital insuficiente){RST}")
                    time.sleep(60)
                    continue

                invest_pct = invest / capital * 100
                capital   -= invest
                units      = invest / curr_p   # Para LONG; SHORT es diferente en live real

                wallet.update({
                    "active":     True,
                    "buy_price":  curr_p,
                    "units":      units,
                    "invest":     invest,
                    "invest_pct": invest_pct,
                    "max_p":      curr_p,
                    "min_p":      curr_p,
                    "bars_in_t":  0,
                    "barriers":   barriers,
                    "be_on":      False,
                    "direction":  direction,
                    "bayes_prob": prob,
                    "tier":       tier,
                    "mult":       mult,
                })

                log_entry(wallet, capital)

            time.sleep(60)

        except KeyboardInterrupt:
            print(f"\n{Y}  Bot detenido manualmente.{RST}")
            log.warning("BOT DETENIDO — KeyboardInterrupt")
            # Resumen final
            print(f"\n  Capital final: ${capital:,.2f} | "
                  f"Peak: ${peak:,.2f} | "
                  f"Drawdown máx: {(peak-capital)/peak*100:.1f}%")
            break

        except Exception as e:
            print(f"\n{R}  ERROR: {e}{RST}")
            log.error(f"ERROR: {e}", exc_info=True)
            time.sleep(30)


if __name__ == "__main__":
    main()