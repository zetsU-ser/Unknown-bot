# research/btc_backtester.py
import sys
import os

# ── FIX DE ENRUTAMIENTO (Apunta a la raíz del proyecto) ───────────────────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import polars as pl
import numpy as np
import statistics
from datetime import datetime

# Importamos nuestra nueva arquitectura
import configs.btc_usdt_config as config
from core.decision_engine import check_mtf_signals
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from core.risk_manager import kelly_position_size, compute_barriers, evaluate_exit

# ── ESTÉTICA DE CONSOLA ───────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"

def load_and_sync_data():
    """
    Extrae los datos crudos de la base de datos y construye las capas temporales.
    Aplica indicadores técnicos a cada capa (1m, 15m, 1h) de forma independiente.
    
    Returns:
        tuple: (df_1m, df_15m, df_1h) DataFrames de Polars listos para simulación.
    """
    print(f"{CYAN}  [1/3] Extrayendo data cruda de PostgreSQL...{RESET}")
    # Cargamos el nivel más bajo (Sniper - 1 minuto)
    df_1m = pl.read_database_uri("SELECT * FROM btc_usdt ORDER BY timestamp ASC", uri=config.DB_URL)
    df_1m = add_indicators(df_1m)

    print(f"{CYAN}  [2/3] Construyendo capas Estructura (15m) y Macro (1h)...{RESET}")
    # Agrupamos (resampling) velas de 1m en velas de 15m
    df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), 
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_15m = add_indicators(df_15m)

    # Agrupamos (resampling) velas de 1m en velas de 1h
    df_1h = df_1m.group_by_dynamic("timestamp", every="1h").agg([
        pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), 
        pl.col("close").last(), pl.col("volume").sum()
    ])
    df_1h = add_indicators(df_1h)
    
    # ── INYECCIÓN BLOQUE 3 (VOLUMEN) CORREGIDA ──
    print(f"{CYAN}  [*] Inyectando escáner de volumen institucional (VWAP & CVD)...{RESET}")
    df_1m  = enrich_with_volume_features(df_1m)
    df_15m = enrich_with_volume_features(df_15m)
    df_1h  = enrich_with_volume_features(df_1h)
    
    return df_1m, df_15m, df_1h

def run_simulation(df_1m, df_15m, df_1h):
    """Motor V9.1: Delegación Total al Risk Manager."""
    print(f"{CYAN}  [3/3] Ejecutando simulación V9.1 (Arquitectura Unificada)...{RESET}")
    ts_15m, ts_1h = df_15m["timestamp"].to_numpy(), df_1h["timestamp"].to_numpy()
    capital, peak = config.INITIAL_CASH, config.INITIAL_CASH
    # Wallet ampliada para soportar la lógica de evaluate_exit
    wallet = {"active": False, "buy_price": 0, "units": 0, "max_p": 0, "min_p": 0, 
              "bars_in_t": 0, "barriers": None, "be_on": False, "direction": None, "mult": 1.0}
    trades = []

    print(f"{YELLOW}[DEBUG] Kelly Fraction Activa: {config.KELLY_FRACTION}{RESET}")
     
    for idx in range(150, len(df_1m)):
        row = df_1m.row(idx, named=True)
        curr_p, curr_ts = row["close"], row["timestamp"]
        i15 = max(0, int(np.searchsorted(ts_15m, curr_ts, side="right")) - 1)
        i1h = max(0, int(np.searchsorted(ts_1h, curr_ts, side="right")) - 1)
        
        # 1. OBTENER SEÑAL
        signal, reason, barriers, prob, direction = check_mtf_signals(
            df_1m.slice(idx-150, 151), df_15m.slice(max(0, i15-60), 61), df_1h.slice(max(0, i1h-30), 31), wallet
        )

        # 2. EJECUCIÓN DE ENTRADA
        if signal == "ENTRY" and not wallet["active"]:
            atr_1m = row.get("atr")
            if not atr_1m or not barriers: continue
            
            base_frac = kelly_position_size(capital, atr_1m, curr_p, peak_capital=peak)
            if base_frac <= 0: continue

            # Sistema de Tiers
            if prob >= 85.0: multiplier = 3.0   
            elif prob >= 65.0: multiplier = 1.5 
            else: multiplier = 1.0              

            final_frac = min(base_frac * multiplier, 0.10)
            invest = capital * final_frac * 10.0
            capital -= invest
            
            wallet.update({
                "active": True, "buy_price": curr_p, "units": invest/curr_p, "max_p": curr_p, "min_p": curr_p,
                "bars_in_t": 0, "barriers": barriers, "be_on": False, "direction": direction,
                "bayes_prob": prob, "mult": multiplier
            })

        # 3. EJECUCIÓN DE SALIDA (DELEGADA A RISK_MANAGER)
        elif signal == "EXIT" and wallet["active"]:
            if wallet["direction"] == "LONG":
                pnl = (curr_p / wallet["buy_price"] - 1) * 100
                capital += (wallet["units"] * curr_p)
            else:
                pnl = (wallet["buy_price"] / curr_p - 1) * 100
                capital += (wallet["units"] * wallet["buy_price"] * (1 + (pnl/100)))
            
            trades.append({
                "pnl": pnl, "reason": reason, "rr": wallet["barriers"]["rr"], 
                "prob": wallet["bayes_prob"], "mult": wallet["mult"], "dir": wallet["direction"]
            })
            if capital > peak: peak = capital
            wallet["active"] = False

        # 4. MANTENIMIENTO (Crucial para actualizar BE_ON)
        elif wallet["active"]:
            wallet["bars_in_t"] += 1
            # Actualizamos extremos para que el Risk Manager tome decisiones con data real
            if wallet["direction"] == "LONG":
                if curr_p > wallet["max_p"]: wallet["max_p"] = curr_p
                if not wallet["be_on"] and curr_p >= wallet["barriers"]["be_trigger"]: 
                    wallet["be_on"] = True
            else:
                if curr_p < wallet["min_p"]: wallet["min_p"] = curr_p
                if not wallet["be_on"] and curr_p <= wallet["barriers"]["be_trigger"]: 
                    wallet["be_on"] = True

    return trades, capital

def print_fancy_report(trades, final_cap):
    """Genera un reporte visual de alto impacto con el tracker de Zetsu."""
    if not trades: 
        return print(f"\n{RED}Zetsu no encontró presas. Revisa los filtros en config.py.{RESET}")
    
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    
    wr = len(wins) / len(trades) * 100
    avg_win = statistics.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = statistics.mean([t["pnl"] for t in losses]) if losses else 0

    # Zetsu Hunt Tracker (Conteo de niveles de ataque)
    z_scout = len([t for t in trades if t.get("mult", 1.0) == 1.0])
    z_ambush = len([t for t in trades if t.get("mult", 1.0) == 1.5])
    z_unicorn = len([t for t in trades if t.get("mult", 1.0) == 3.0])
    
    print(f"\n{BOLD}{CYAN}╔{'═'*50}╗")
    print(f"║{'BACKTESTER V9.1 - ZETZU HUNT (BLOQUE 3)':^50}║")
    print(f"╚{'═'*50}╝{RESET}")
    print(f"  💰 CAPITAL FINAL  : {GREEN}${final_cap:,.2f}{RESET}")
    print(f"  📊 TOTAL TRADES   : {len(trades)} ({GREEN}{len(wins)}W{RESET} / {RED}{len(losses)}L{RESET})")
    print(f"  📈 WIN RATE       : {YELLOW}{wr:.2f}%{RESET}")
    print(f"  🎯 R:R REALIZADO  : {CYAN}{statistics.mean([t['rr'] for t in trades]):.2f}{RESET}")
    print(f"  🤑 AVG WIN / LOSS : {GREEN}+{avg_win:.3f}%{RESET} / {RED}{avg_loss:.3f}%{RESET}")
    
    asym_color = GREEN if (avg_win + avg_loss) > 0 else RED
    print(f"  ⚖️  ASIMETRÍA NETA : {asym_color}{avg_win+avg_loss:+.3f}%{RESET}")
    
    print(f"\n{DIM}  ── ZETZU HUNT TRACKER (FRACTIONAL KELLY) ──{RESET}")
    print(f"  🍃 Scout (x1.0)   : {z_scout} trades")
    print(f"  ⚔️  Ambush (x1.5)  : {YELLOW}{z_ambush} trades{RESET}")
    print(f"  🦄 Unicorn (x3.0) : {GREEN}{z_unicorn} trades{RESET}")
    print(f"{DIM}{'─'*52}{RESET}\n")

if __name__ == "__main__":
    # Pipeline de ejecución
    d1, d15, d1h = load_and_sync_data()
    results, cap = run_simulation(d1, d15, d1h)
    print_fancy_report(results, cap)