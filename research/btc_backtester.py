# research/btc_backtester.py — V10.2 TIER SYSTEM (Event-Driven)
"""
Backtester V10.2 — Zetzu Hunt Tier System
==========================================
Cambio clave: el Decision Engine ahora es Event-Driven.
- Publicamos MTFDataEvent al EventBus
- Capturamos SignalEvent de vuelta (sincrono) sin romper el loop ni la wallet.

FIX V10.2: Pydantic v2 clona el dict al construir MTFDataEvent, por lo que
data_payload["barriers"] nunca recibe el valor escrito por strategy_manager.
Solucion: reconstruir barriers directamente desde el objeto Signal inmutable
(sl_price / tp_price / entry_price), que viaja intacto en el SignalEvent.
"""
import sys
import os
import math
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl
import numpy as np
import statistics
from collections import Counter
from typing import Optional

from tqdm import tqdm

import configs.btc_usdt_config as config
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from core.risk_manager import kelly_position_size, evaluate_exit, get_tier_params
from research.blackbox import TradeBlackbox

from engine.event_bus import EventBus
from domain.events import MTFDataEvent, SignalEvent
from core.decision_engine import DecisionEngine


GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"
BOLD, DIM, MAGENTA = "\033[1m", "\033[2m", "\033[95m"

BLACKBOX_OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "blackbox_export.parquet"
)

TIER_EMOJI = {"SCOUT": "S", "AMBUSH": "A", "UNICORN": "U"}
TIER_COLOR = {"SCOUT": CYAN, "AMBUSH": YELLOW, "UNICORN": GREEN}


class _SignalCollector:
    def __init__(self, bus: EventBus) -> None:
        self.last_signal = None
        bus.subscribe(SignalEvent, self._on_signal)

    def reset(self) -> None:
        self.last_signal = None

    def _on_signal(self, event: SignalEvent) -> None:
        self.last_signal = event.signal


def _enrich_barriers_by_tier(barriers: dict, tier: str, direction: str, entry_price: float) -> None:
    tier_p       = get_tier_params(tier)
    be_threshold = tier_p["be_threshold"]
    profit_lock  = tier_p["profit_lock"]
    tp_price     = float(barriers.get("tp", 0.0))

    if direction == "LONG":
        reward  = tp_price - entry_price
        be_trig = entry_price + (reward * be_threshold)
        pl_sl   = entry_price + ((be_trig - entry_price) * profit_lock) if profit_lock > 0 else entry_price
    else:
        reward  = entry_price - tp_price
        be_trig = entry_price - (reward * be_threshold)
        pl_sl   = entry_price - ((entry_price - be_trig) * profit_lock) if profit_lock > 0 else entry_price

    barriers.update({
        "tier":           tier,
        "mult":           tier_p["mult"],
        "max_bars":       tier_p["max_bars"],
        "prob_min":       tier_p["prob_min"],
        "be_trigger":     be_trig,
        "profit_lock_sl": pl_sl,
    })


def load_and_sync_data():
    print(f"{CYAN}  [1/3] Extrayendo data cruda de PostgreSQL...{RESET}", flush=True)
    df_1m = pl.read_database_uri("SELECT * FROM btc_usdt ORDER BY timestamp ASC", uri=config.DB_URL)
    df_1m = df_1m.unique(subset=["timestamp"], keep="last").sort("timestamp")
    df_1m = add_indicators(df_1m)

    print(f"{CYAN}  [2/3] Construyendo capas Estructura (15m), Momentum (1h), Swing (4h) y Macro (1d)...{RESET}", flush=True)

    def resample(every):
        return df_1m.group_by_dynamic("timestamp", every=every).agg([
            pl.col("open").first(), pl.col("high").max(),
            pl.col("low").min(),   pl.col("close").last(),
            pl.col("volume").sum(),
        ])

    df_15m = add_indicators(resample("15m"))
    df_1h  = add_indicators(resample("1h"))
    df_4h  = add_indicators(resample("4h"))
    df_1d  = add_indicators(resample("1d"))

    print(f"{CYAN}  [*] Inyectando escaner de volumen institucional (VWAP & CVD)...{RESET}", flush=True)
    df_1m  = enrich_with_volume_features(df_1m)
    df_15m = enrich_with_volume_features(df_15m)
    df_1h  = enrich_with_volume_features(df_1h)
    df_4h  = enrich_with_volume_features(df_4h)
    df_1d  = enrich_with_volume_features(df_1d)

    return df_1m, df_15m, df_1h, df_4h, df_1d


def run_simulation(df_1m, df_15m, df_1h, df_4h, df_1d):
    print(f"{CYAN}  [3/3] Ejecutando simulacion V10.0 (Tier System + Event-Driven)...{RESET}", flush=True)

    bus = EventBus()
    _ = DecisionEngine(bus)
    collector = _SignalCollector(bus)

    closes_1m   = df_1m["close"].to_numpy()
    total_velas = len(closes_1m)

    if total_velas < 150:
        print(f"\n{RED}[FATAL ERROR] PRE-FLIGHT CHECK FALLIDO.{RESET}")
        print(f"{YELLOW}La base de datos tiene {total_velas} velas. Se necesitan al menos 150.{RESET}")
        print(f"{CYAN}Solucion: Ejecuta la opcion [3] para descargar datos historicos.{RESET}\n")
        sys.exit(1)

    print(f"{GREEN}[+] Pre-Flight Check OK: {total_velas} velas cargadas en memoria.{RESET}", flush=True)

    ts_1m   = df_1m["timestamp"].to_numpy()
    atrs_1m = df_1m["atr"].to_numpy()
    ts_15m  = df_15m["timestamp"].to_numpy()
    ts_1h   = df_1h["timestamp"].to_numpy()
    ts_4h   = df_4h["timestamp"].to_numpy()
    ts_1d   = df_1d["timestamp"].to_numpy()

    capital, peak = config.INITIAL_CASH, config.INITIAL_CASH

    wallet = {
        "active": False, "buy_price": 0, "units": 0,
        "max_p": 0, "min_p": 0, "bars_in_t": 0,
        "barriers": None, "be_on": False, "direction": None,
        "mult": 1.0, "bayes_prob": 0.0, "tier": None, "trade_id": -1,
    }

    blackbox = TradeBlackbox()
    trades   = []

    print(
        f"{YELLOW}[DEBUG V10.2] Kelly: {config.KELLY_FRACTION} | "
        f"Scout>={config.SCOUT_PROB_MIN}% | "
        f"Ambush>={config.AMBUSH_PROB_MIN}% | "
        f"Unicorn>={config.UNICORN_PROB_MIN}% | "
        f"Gate R:R>={config.RR_MIN_REQUIRED} | SL_MULT={config.ATR_SL_MULT}{RESET}",
        flush=True,
    )

    for idx in tqdm(
        range(150, len(closes_1m)),
        desc=f"{YELLOW}Cazando en la Matrix{RESET}",
        unit="vela",
        dynamic_ncols=True,
    ):
        curr_p  = closes_1m[idx]
        curr_ts = ts_1m[idx]

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
                invested_margin = wallet["units"] * wallet["buy_price"]

                if wallet["direction"] == "LONG":
                    pnl = (curr_p / wallet["buy_price"] - 1) * 100
                else:
                    pnl = (wallet["buy_price"] / curr_p - 1) * 100

                leverage        = getattr(config, "LEVERAGE", 1)
                profit_loss_usd = invested_margin * leverage * (pnl / 100)
                capital        += invested_margin + profit_loss_usd

                blackbox.label_exit(trade_id=wallet["trade_id"], pnl=pnl,
                                    reason=reason, bars=wallet["bars_in_t"])

                trades.append({
                    "pnl": pnl, "reason": reason, "rr": wallet["barriers"]["rr"],
                    "prob": wallet["bayes_prob"], "tier": wallet["tier"],
                    "mult": wallet["barriers"].get("mult", 1.0),
                    "dir": wallet["direction"], "bars": wallet["bars_in_t"],
                })

                if capital > peak: peak = capital
                wallet["active"] = False

            continue

        i15 = max(0, int(np.searchsorted(ts_15m, curr_ts, side="right")) - 1)
        i1h = max(0, int(np.searchsorted(ts_1h,  curr_ts, side="right")) - 1)
        i4h = max(0, int(np.searchsorted(ts_4h,  curr_ts, side="right")) - 1)
        i1d = max(0, int(np.searchsorted(ts_1d,  curr_ts, side="right")) - 1)

        slice_1m  = df_1m.slice(idx - 150, 151)
        slice_15m = df_15m.slice(max(0, i15 - 119), 120)
        slice_1h  = df_1h.slice(max(0, i1h - 48),   49)
        slice_4h  = df_4h.slice(max(0, i4h - 24),   25)
        slice_1d  = df_1d.slice(max(0, i1d - 14),   15)

        collector.reset()
        bus.publish(MTFDataEvent(data={
            "1m": slice_1m, "15m": slice_15m, "1h": slice_1h,
            "4h": slice_4h, "1d": slice_1d,   "trade_state": wallet,
        }))

        sig = collector.last_signal
        if sig is None:
            continue

        # FIX ARQUITECTONICO: Pydantic v2 clona el dict al construir MTFDataEvent.
        # data_payload["barriers"] jamas recibe el valor de strategy_manager.
        # Se reconstruye barriers desde el Signal inmutable (sl/tp/entry_price).
        entry  = float(sig.entry_price)
        sl_p   = float(sig.sl_price)
        tp_p   = float(sig.tp_price)
        risk   = abs(entry - sl_p)
        reward = abs(tp_p - entry)
        if risk <= 0:
            continue

        barriers = {
            "sl":             sl_p,
            "tp":             tp_p,
            "rr":             round(reward / risk, 4),
            "tier":           None,
            "mult":           1.0,
            "max_bars":       config.MAX_TRADE_BARS,
            "prob_min":       config.SCOUT_PROB_MIN,
            "be_trigger":     tp_p,    # sobrescrito por _enrich_barriers_by_tier
            "profit_lock_sl": entry,   # sobrescrito por _enrich_barriers_by_tier
        }

        _enrich_barriers_by_tier(barriers, sig.tier, sig.direction, entry)

        atr_1m = atrs_1m[idx]
        if np.isnan(atr_1m):
            continue

        tier       = barriers["tier"]
        multiplier = barriers["mult"]

        tier_caps   = {"SCOUT": 0.20, "AMBUSH": 0.30, "UNICORN": 0.45}
        invest_frac = min(config.RISK_PER_TRADE_PCT * 10.0 * multiplier, tier_caps.get(tier, 0.30))
        invest      = capital * invest_frac
        capital    -= invest

        trade_id = blackbox.capture_entry(
            timestamp=curr_ts, entry_price=curr_p, direction=sig.direction,
            barriers=barriers, prob=float(sig.prob), mult=multiplier,
            df_1m=slice_1m, df_15m=slice_15m, df_1h=slice_1h,
            df_4h=slice_4h, df_1d=slice_1d,
        )

        wallet.update({
            "active": True, "buy_price": curr_p, "units": invest / curr_p,
            "max_p": curr_p, "min_p": curr_p, "bars_in_t": 0,
            "barriers": barriers, "be_on": False, "direction": sig.direction,
            "bayes_prob": float(sig.prob), "tier": tier,
            "mult": multiplier, "trade_id": trade_id,
        })

    print(f"\n{MAGENTA}  [BLACKBOX] Exportando dataset ADN...{RESET}", flush=True)
    blackbox.export_parquet(BLACKBOX_OUTPUT)

    return trades, capital, blackbox


def print_fancy_report(trades, final_cap, blackbox=None):
    if not trades:
        return print(f"\n{RED}Zetzu no encontro presas. Revisa filtros en config.py.{RESET}")

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    wr     = len(wins) / len(trades) * 100

    avg_pnl  = statistics.mean([t["pnl"] for t in trades])
    med_pnl  = statistics.median([t["pnl"] for t in trades])
    avg_win  = statistics.mean([t["pnl"] for t in wins])   if wins   else 0.0
    avg_loss = statistics.mean([t["pnl"] for t in losses]) if losses else 0.0

    exits = Counter([t.get("reason", "?") for t in trades])

    # Drawdown maximo
    initial_cash = getattr(config, "INITIAL_CASH", 10000.0)
    equity = initial_cash
    peak_eq = initial_cash
    max_dd = 0.0
    for t in trades:
        equity  += equity * (t["pnl"] / 100)
        peak_eq  = max(peak_eq, equity)
        dd       = (peak_eq - equity) / peak_eq * 100
        max_dd   = max(max_dd, dd)

    # Sharpe simplificado
    pnls    = [t["pnl"] for t in trades]
    std_pnl = statistics.stdev(pnls) if len(pnls) > 1 else 1e-9
    sharpe  = (avg_pnl / std_pnl) * (len(pnls) ** 0.5) if std_pnl > 0 else 0.0

    W = 60
    cap_color = GREEN if final_cap >= initial_cash else RED
    wr_color  = GREEN if wr >= 50 else (YELLOW if wr >= 40 else RED)
    ev_color  = GREEN if avg_pnl > 0 else RED

    print(f"\n{CYAN}+{'='*W}+{RESET}")
    print(f"{CYAN}|{BOLD}{'REPORTE ZETSU V10.2 - QUANTITATIVE ANALYSIS':^{W}}{RESET}{CYAN}|{RESET}")
    print(f"{CYAN}+{'='*W}+{RESET}")

    def row(label, value):
        print(f"{CYAN}|{RESET}  {label:<20}{value:<{W-22}}{CYAN}|{RESET}")

    row("Capital Final   :", f"{cap_color}${final_cap:>10,.2f}{RESET}  inicial: ${initial_cash:,.2f}")
    row("Trades Totales  :", f"{YELLOW}{len(trades)}{RESET}  ({GREEN}{len(wins)}W{RESET} / {RED}{len(losses)}L{RESET})")
    row("Win Rate        :", f"{wr_color}{wr:.2f}%{RESET}")
    row("Avg Win / Loss  :", f"{GREEN}+{avg_win:.3f}%{RESET} / {RED}{avg_loss:.3f}%{RESET}")
    row("Avg PnL / Med   :", f"{YELLOW}{avg_pnl:+.3f}%{RESET} / {YELLOW}{med_pnl:+.3f}%{RESET}")
    row("Expected Value  :", f"{ev_color}{avg_pnl:+.3f}% por trade{RESET}")
    row("Max Drawdown    :", f"{RED}{max_dd:.2f}%{RESET}")
    row("Sharpe (aprox)  :", f"{YELLOW}{sharpe:.3f}{RESET}")

    print(f"{CYAN}+{'-'*W}+{RESET}")
    print(f"{CYAN}|{RESET}  {'Distribucion de Salidas':<{W-2}}{CYAN}|{RESET}")

    for reason in ["TP", "SL", "TIMEOUT", "PROFIT_LOCK"]:
        count = exits.get(reason, 0)
        pct   = count / len(trades) * 100
        bar   = "#" * int(pct / 4)
        color = GREEN if reason == "TP" else (RED if reason == "SL" else DIM)
        print(f"{CYAN}|{RESET}    {color}{reason:<14}{RESET}{YELLOW}{count:>4}{RESET} ({pct:5.1f}%)  {color}{bar:<20}{RESET}{CYAN}|{RESET}")

    print(f"{CYAN}+{'-'*W}+{RESET}")
    print(f"{CYAN}|{RESET}  {'Desglose por Escuadron (Tier)':<{W-2}}{CYAN}|{RESET}")

    for tier in ["SCOUT", "AMBUSH", "UNICORN"]:
        tier_trades = [t for t in trades if t["tier"] == tier]
        if not tier_trades:
            continue

        t_wins  = [t for t in tier_trades if t["pnl"] > 0]
        t_wr    = (len(t_wins) / len(tier_trades)) * 100
        t_ev    = statistics.mean([t["pnl"] for t in tier_trades])
        t_tp    = len([t for t in tier_trades if t.get("reason") == "TP"])
        t_tp_p  = t_tp / len(tier_trades) * 100
        valid_rr = [t["rr"] for t in tier_trades if not math.isnan(t.get("rr", float("nan")))]
        t_rr    = statistics.mean(valid_rr) if valid_rr else 0.0

        color = TIER_COLOR.get(tier, RESET)
        wr_c  = GREEN if t_wr >= 50 else (YELLOW if t_wr >= 40 else RED)
        ev_c  = GREEN if t_ev > 0 else RED

        print(f"{CYAN}+{'-'*W}+{RESET}")
        print(f"{CYAN}|{RESET}  {color}{BOLD}{tier}{RESET}  ({len(tier_trades)} trades){'':<{W-18-len(tier)}}{CYAN}|{RESET}")
        print(f"{CYAN}|{RESET}    Win Rate : {wr_c}{t_wr:.1f}%{RESET}   TP Hits: {CYAN}{t_tp} ({t_tp_p:.1f}%){RESET}{'':<{W-42}}{CYAN}|{RESET}")
        print(f"{CYAN}|{RESET}    Avg R:R  : {YELLOW}{t_rr:.2f}{RESET}    EV:     {ev_c}{t_ev:+.3f}%{RESET}{'':<{W-40}}{CYAN}|{RESET}")

    print(f"{CYAN}+{'='*W}+{RESET}\n")