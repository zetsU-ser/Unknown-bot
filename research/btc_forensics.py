# research/btc_forensics.py — V2.1 TIER SYSTEM
"""
Autopsia Forense V2.1 — Tier System Edition
=============================================
Módulos:
  1. Superficie de Probabilidad (Tiers)
  2. Sesgo Direccional (LONG vs SHORT)
  3. Optimizador de Kelly Empírico
  4. Anatomía de Salidas por Tier
  5. Distribución Estadística + Curtosis por Tier
  6. Auditoría de Config con sugerencias de Reajuste
  7. Análisis de Rendimiento por Tier (Scout/Ambush/Unicorn)
  8. Feature Importance Preview (Caja Negra)
"""
import sys
import os
import statistics
import numpy as np
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configs.btc_usdt_config as config
from research.btc_backtester import load_and_sync_data, run_simulation

GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"
BOLD, DIM, MAGENTA = "\033[1m", "\033[2m", "\033[95m"

TIER_EMOJI = {"SCOUT": "🍃", "AMBUSH": "⚔️ ", "UNICORN": "🦄"}
# V10.2: Tier por probabilidad, no por R:R
TIER_PROB_RANGE = {
    "SCOUT":   (config.SCOUT_PROB_MIN,   config.AMBUSH_PROB_MIN),    # 70-75%
    "AMBUSH":  (config.AMBUSH_PROB_MIN,  config.UNICORN_PROB_MIN),   # 75-80%
    "UNICORN": (config.UNICORN_PROB_MIN, 100.0),                      # 80-100%
}
TIER_RR_RANGE = {
    "SCOUT":   (config.SCOUT_RR_MIN,   config.SCOUT_RR_MAX),
    "AMBUSH":  (config.AMBUSH_RR_MIN,  config.AMBUSH_RR_MAX),
    "UNICORN": (config.UNICORN_RR_MIN, config.UNICORN_RR_MAX),
}
TIER_PROB_MIN = {
    "SCOUT":   config.SCOUT_PROB_MIN,
    "AMBUSH":  config.AMBUSH_PROB_MIN,
    "UNICORN": config.UNICORN_PROB_MIN,
}


def _kurtosis(data):
    n = len(data)
    if n < 4: return 0.0
    mu, std = np.mean(data), np.std(data)
    if std == 0: return 0.0
    return float(np.mean(((np.array(data) - mu) / std) ** 4) - 3)

def _skewness(data):
    n = len(data)
    if n < 3: return 0.0
    mu, std = np.mean(data), np.std(data)
    if std == 0: return 0.0
    return float(np.mean(((np.array(data) - mu) / std) ** 3))

def calculate_empirical_kelly_raw(wr, avg_win, avg_loss):
    if avg_loss == 0: return 0
    r = avg_win / avg_loss
    return max(0.0, wr - ((1 - wr) / r))


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 1: Superficie de Probabilidad
# ─────────────────────────────────────────────────────────────────────────────
def analyze_probability_tiers(trades):
    tiers = {
        "Basura (< 65%)":     [t for t in trades if t["prob"] < 65.0],
        "Scout (65% - 70%)":  [t for t in trades if 65.0 <= t["prob"] < 70.0],
        "Ambush (70% - 80%)": [t for t in trades if 70.0 <= t["prob"] < 80.0],
        "Unicorn (80% +)":    [t for t in trades if t["prob"] >= 80.0],
    }
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 1: SUPERFICIE DE PROBABILIDAD{RESET}")
    print(f"{'TIER':<22} | {'N':>5} | {'WR':>8} | {'EV':>10} | {'AVG_WIN':>9} | {'AVG_LOSS':>9}")
    print("─" * 78)
    for name, subset in tiers.items():
        if not subset:
            print(f"{name:<22} | {'—':>5} | {'—':>8} | {'—':>10} | {'—':>9} | {'—':>9}")
            continue
        wins  = [t for t in subset if t["pnl"] > 0]
        loss  = [t for t in subset if t["pnl"] <= 0]
        wr    = len(wins) / len(subset) * 100
        ev    = statistics.mean([t["pnl"] for t in subset])
        aw    = statistics.mean([t["pnl"] for t in wins]) if wins else 0
        al    = statistics.mean([t["pnl"] for t in loss]) if loss else 0
        ec    = GREEN if ev > 0 else RED
        print(f"{name:<22} | {len(subset):>5} | {wr:>7.2f}% | {ec}{ev:>+9.4f}%{RESET} | "
              f"{GREEN}{aw:>+8.3f}%{RESET} | {RED}{al:>+8.3f}%{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 2: Sesgo Direccional
# ─────────────────────────────────────────────────────────────────────────────
def analyze_directional_bias(trades):
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 2: SESGO DIRECCIONAL (LONG vs SHORT){RESET}")
    for name in ["LONG", "SHORT"]:
        subset = [t for t in trades if t["dir"] == name]
        if not subset: continue
        wins = [t for t in subset if t["pnl"] > 0]
        wr   = len(wins) / len(subset) * 100
        ev   = statistics.mean([t["pnl"] for t in subset])
        c    = GREEN if ev > 0 else RED
        print(f"  ➔ {name:<5}: {len(subset):>4} trades | WR: {wr:.1f}% | EV: {c}{ev:+.3f}%{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 3: Kelly Empírico
# ─────────────────────────────────────────────────────────────────────────────
def module_kelly(trades):
    wins  = [t for t in trades if t["pnl"] > 0]
    loss  = [t for t in trades if t["pnl"] <= 0]
    if not wins or not loss:
        print(f"\n{DIM}[*] MÓDULO 3: Sin datos suficientes.{RESET}"); return

    w       = len(wins) / len(trades)
    avg_win = statistics.mean([t["pnl"] for t in wins])
    avg_los = abs(statistics.mean([t["pnl"] for t in loss]))
    r       = avg_win / avg_los if avg_los else 1
    kelly   = max(0.0, w - ((1 - w) / r))

    print(f"\n{BOLD}{CYAN}[*] MÓDULO 3: OPTIMIZADOR DE KELLY EMPÍRICO{RESET}")
    print(f"  ➔ Kelly Puro       : {GREEN}{kelly * 100:.2f}%{RESET}")
    print(f"  ➔ Half-Kelly       : {CYAN}{kelly / 2:.4f}{RESET}  → RISK_PER_TRADE_PCT recomendado")
    print(f"  ➔ Config actual    : {config.RISK_PER_TRADE_PCT:.4f}")

    half_k = kelly / 2
    if kelly <= 0:
        print(f"  {RED}⚠️  Kelly negativo. EV negativa.{RESET}")
    elif config.RISK_PER_TRADE_PCT > half_k * 1.3:
        print(f"  {RED}⚠️  Sobrearriesgando. Half-Kelly = {half_k:.4f}.{RESET}")
    elif config.RISK_PER_TRADE_PCT < half_k * 0.6:
        print(f"  {YELLOW}💡 Infrarriesgando. Puedes subir a {half_k:.4f}.{RESET}")
    else:
        print(f"  {GREEN}✅ RISK_PER_TRADE_PCT correctamente calibrado.{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 4: Anatomía de Salidas por Tier
# ─────────────────────────────────────────────────────────────────────────────
def analyze_exit_anatomy(trades):
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 4: ANATOMÍA DE SALIDAS POR TIER{RESET}")

    for tier_name in ["SCOUT", "AMBUSH", "UNICORN"]:
        tier_t = [t for t in trades if t.get("tier") == tier_name]
        if not tier_t:
            continue

        emoji  = TIER_EMOJI.get(tier_name, "")
        p_min, p_max = TIER_PROB_RANGE[tier_name]
        rr_min, rr_max = TIER_RR_RANGE[tier_name]
        prob_min = TIER_PROB_MIN[tier_name]

        print(f"\n  {emoji} {BOLD}{tier_name}{RESET}  "
              f"[prob {p_min:.0f}%–{p_max:.0f}% | R:R≥{rr_min}]  "
              f"→ {len(tier_t)} trades")

        by_reason = {}
        for t in tier_t:
            r = t.get("reason", "UNKNOWN")
            # Normalizar razones que incluyen el label del tier
            for known in ["SL", "TP", "PROFIT_LOCK", "TIMEOUT"]:
                if known in r:
                    r = known
                    break
            by_reason.setdefault(r, []).append(t)

        total = len(tier_t)
        tp_pct = len(by_reason.get("TP", [])) / total * 100
        sl_pct = len(by_reason.get("SL", [])) / total * 100

        print(f"  {'RAZÓN':<16} | {'N':>4} | {'%':>6} | {'WR':>7} | {'AVG_PNL':>9} | DIAGNÓSTICO")
        print(f"  {'─'*16}-+-{'─'*4}-+-{'─'*6}-+-{'─'*7}-+-{'─'*9}-+─────────────")

        priority = ["TP", "PROFIT_LOCK", "TIMEOUT", "SL"]
        for reason in sorted(by_reason.keys(), key=lambda x: priority.index(x) if x in priority else 99):
            subset = by_reason[reason]
            wins   = [t for t in subset if t["pnl"] > 0]
            wr_r   = len(wins) / len(subset) * 100
            avg_p  = statistics.mean([t["pnl"] for t in subset])
            pct_r  = len(subset) / total * 100

            if reason == "TP":
                diag = f"{GREEN}✅ IDEAL{RESET}"
            elif reason == "PROFIT_LOCK":
                diag = f"{GREEN}✓ PROTECCIÓN OK{RESET}" if tier_name != "UNICORN" else f"{RED}⚠️  Unicorn no debería tener PL{RESET}"
            elif reason == "SL":
                diag = f"{RED}⛔ REVISAR FILTROS{RESET}" if sl_pct > 40 else f"{YELLOW}SL {sl_pct:.0f}%{RESET}"
            elif reason == "TIMEOUT":
                diag = f"{YELLOW}⏱️  Ajustar MAX_BARS{RESET}"
            else:
                diag = f"{DIM}—{RESET}"

            c = GREEN if avg_p > 0 else RED
            print(f"  {reason:<16} | {len(subset):>4} | {pct_r:>5.1f}% | {wr_r:>6.1f}% | "
                  f"{c}{avg_p:>+8.3f}%{RESET} | {diag}")

        # Alertas automáticas por tier
        if tier_name == "SCOUT" and tp_pct < 20:
            print(f"  {YELLOW}  ⚠️  Scout: solo {tp_pct:.0f}% llega al TP (R:R=1.5). "
                  f"BE_THRESHOLD={config.SCOUT_BE_THRESHOLD} podría ser demasiado agresivo.{RESET}")
        if tier_name == "UNICORN" and tp_pct < 15:
            print(f"  {YELLOW}  ⚠️  Unicorn: {tp_pct:.0f}% llega al TP (R:R>2.6). "
                  f"Verificar que UNICORN_BE_THRESHOLD={config.UNICORN_BE_THRESHOLD} deja correr.{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 5: Distribución Estadística + Curtosis
# ─────────────────────────────────────────────────────────────────────────────
def analyze_statistical_distribution(trades):
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 5: DISTRIBUCIÓN ESTADÍSTICA + FAT TAIL ANALYSIS{RESET}")

    pnls = [t["pnl"] for t in trades]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    loss = [t["pnl"] for t in trades if t["pnl"] <= 0]

    kurt  = _kurtosis(pnls)
    skew  = _skewness(pnls)
    pf    = abs(sum(wins)) / abs(sum(loss)) if loss else float("inf")
    std_p = np.std(pnls)

    print(f"\n  {'GLOBAL':<28} | {'VALOR':>10} | INTERPRETACIÓN")
    print(f"  {'─'*28}-+-{'─'*10}-+────────────────────────────────────────")

    kurt_i = (f"{GREEN}✅ LEPTOCÚRTICA — Fat Tails activas{RESET}" if kurt > 1.0
              else f"{YELLOW}⚠️  Normal/Plana — Sin ventaja de outliers{RESET}" if kurt <= 0
              else f"{CYAN}Ligera cola gruesa{RESET}")
    skew_i = (f"{GREEN}✅ Cola derecha — wins outliers{RESET}" if skew > 0.5
              else f"{RED}⚠️  Cola izquierda — losses outliers{RESET}" if skew < -0.5
              else f"{CYAN}Asimetría leve{RESET}")
    pf_i   = (f"{GREEN}✅ Excelente{RESET}" if pf > 2.0
              else f"{CYAN}Aceptable{RESET}" if pf > 1.2
              else f"{RED}⚠️  Bajo{RESET}")

    print(f"  {'Curtosis (exceso)':<28} | {kurt:>+9.4f} | {kurt_i}")
    print(f"  {'Skewness':<28} | {skew:>+9.4f} | {skew_i}")
    print(f"  {'Profit Factor':<28} | {pf:>9.4f} | {pf_i}")
    print(f"  {'Desv. Estándar PnL':<28} | {std_p:>9.4f}% |")
    print(f"  {'Mayor Win':<28} | {max(wins):>+9.3f}% |")
    print(f"  {'Mayor Loss':<28} | {min(loss):>+9.3f}% |")

    # Curtosis por tier
    print(f"\n  {DIM}Por tier:{RESET}")
    for tier_name in ["SCOUT", "AMBUSH", "UNICORN"]:
        tier_t = [t["pnl"] for t in trades if t.get("tier") == tier_name]
        if len(tier_t) < 5: continue
        tk = _kurtosis(tier_t)
        ts = _skewness(tier_t)
        rr_min, rr_max = TIER_RR_RANGE[tier_name]
        emoji = TIER_EMOJI.get(tier_name, "")
        print(f"  {emoji}{tier_name:<9} (R:R {rr_min}–{rr_max}): "
              f"Curtosis {tk:+.3f} | Skew {ts:+.3f} | "
              f"N={len(tier_t)}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 6: Auditoría de Config
# ─────────────────────────────────────────────────────────────────────────────
def audit_config_parameters(trades):
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 6: AUDITORÍA DE CONFIG + SUGERENCIAS DE REAJUSTE{RESET}")

    pnls    = [t["pnl"] for t in trades]
    kurt    = _kurtosis(pnls)
    wr      = len([t for t in trades if t["pnl"] > 0]) / len(trades) * 100
    wins    = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses  = [t["pnl"] for t in trades if t["pnl"] <= 0]
    avg_win = statistics.mean(wins)   if wins   else 0
    avg_los = abs(statistics.mean(losses)) if losses else 0

    sl_pct = len([t for t in trades if "SL" in str(t.get("reason",""))]) / len(trades) * 100
    tp_pct = len([t for t in trades if "TP" in str(t.get("reason",""))]) / len(trades) * 100

    params = [
        # Global
        ("RR_MIN_REQUIRED",       config.RR_MIN_REQUIRED,       "Gate global R:R"),
        ("ATR_SL_MULT",           config.ATR_SL_MULT,           "Amplitud SL"),
        ("ATR_TP_MULT",           config.ATR_TP_MULT,           "Target mínimo TP"),
        ("RISK_PER_TRADE_PCT",    config.RISK_PER_TRADE_PCT,    "Riesgo base por trade"),
        ("KELLY_FRACTION",        config.KELLY_FRACTION,        "Fracción de Kelly"),
        ("MAX_DRAWDOWN_HALT",     config.MAX_DRAWDOWN_HALT,     "DD máximo halt"),
        # Por tier
        ("SCOUT_BE_THRESHOLD",    config.SCOUT_BE_THRESHOLD,    "BE Scout (% recorrido)"),
        ("AMBUSH_BE_THRESHOLD",   config.AMBUSH_BE_THRESHOLD,   "BE Ambush"),
        ("UNICORN_BE_THRESHOLD",  config.UNICORN_BE_THRESHOLD,  "BE Unicorn"),
        ("SCOUT_PROFIT_LOCK",     config.SCOUT_PROFIT_LOCK,     "Profit Lock Scout"),
        ("AMBUSH_PROFIT_LOCK",    config.AMBUSH_PROFIT_LOCK,    "Profit Lock Ambush"),
        ("UNICORN_PROFIT_LOCK",   config.UNICORN_PROFIT_LOCK,   "Profit Lock Unicorn (debe ser 0)"),
        ("SCOUT_MAX_BARS",        config.SCOUT_MAX_BARS,        "Timeout Scout (barras)"),
        ("AMBUSH_MAX_BARS",       config.AMBUSH_MAX_BARS,       "Timeout Ambush"),
        ("UNICORN_MAX_BARS",      config.UNICORN_MAX_BARS,      "Timeout Unicorn"),
    ]

    print(f"\n  {'PARÁMETRO':<28} | {'VALOR':>12} | ESTADO")
    print(f"  {'─'*28}-+-{'─'*12}-+──────────────────────────────────────────")

    for name, val, desc in params:
        suggestion = _audit_param(name, val, kurt, wr, sl_pct, tp_pct, avg_win, avg_los)
        print(f"  {name:<28} | {str(val):>12} | {suggestion}")


def _audit_param(name, val, kurt, wr, sl_pct, tp_pct, avg_win, avg_los):
    G, R, Y, C, D = GREEN, RED, YELLOW, CYAN, DIM

    if name == "RR_MIN_REQUIRED":
        return f"{G}✅ Definido por SCOUT_RR_MIN={config.SCOUT_RR_MIN}{RESET}"

    elif name == "ATR_SL_MULT":
        if sl_pct > 40:
            return f"{R}⚠️  SL exits={sl_pct:.0f}%. Muy ajustado. Subir a {val*1.1:.2f}.{RESET}"
        return f"{G}OK ({sl_pct:.0f}% SL exits).{RESET}"

    elif name == "SCOUT_BE_THRESHOLD":
        scout_tp = len([1 for _ in range(1)]) # placeholder, se calcula arriba
        return f"{C}Scout BE al {val*100:.0f}% del recorrido. OK si TP% Scout > 20%.{RESET}"

    elif name == "UNICORN_BE_THRESHOLD":
        if kurt > 1.0:
            return f"{G}✅ Curtosis={kurt:+.2f}. Fat tails activas. BE tardío correcto.{RESET}"
        return f"{Y}Curtosis={kurt:+.2f}. Monitorear si Unicorn llega al TP.{RESET}"

    elif name == "UNICORN_PROFIT_LOCK":
        if val == 0.0:
            return f"{G}✅ Correcto. Unicorn sin Profit Lock → fat tail hunting.{RESET}"
        return f"{R}⚠️  Debe ser 0.0 para Unicorn. Actualmente {val}.{RESET}"

    elif name == "RISK_PER_TRADE_PCT":
        half_k = calculate_empirical_kelly_raw(wr/100, avg_win, avg_los) / 2
        if half_k <= 0: return f"{D}Half-Kelly no computable.{RESET}"
        if val > half_k * 1.3: return f"{R}⚠️  Sobrearriesgando. Half-Kelly={half_k:.4f}.{RESET}"
        if val < half_k * 0.6: return f"{Y}Infrarriesgando. Half-Kelly={half_k:.4f}.{RESET}"
        return f"{G}✅ Calibrado. Half-Kelly={half_k:.4f}.{RESET}"

    elif name == "KELLY_FRACTION":
        if val > 0.40: return f"{R}⚠️  Muy alto. Máximo recomendado: 0.35.{RESET}"
        return f"{G}✅ OK ({val}).{RESET}"

    elif name == "MAX_DRAWDOWN_HALT":
        return f"{G}✅ Halt en {val*100:.0f}% DD. Config conservadora correcta.{RESET}"

    elif "MAX_BARS" in name:
        hours = val / 60
        return f"{C}{hours:.0f}h de timeout. Ajustar si el tier necesita más tiempo.{RESET}"

    return f"{D}—{RESET}"


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 7: Rendimiento por Tier (el más nuevo e importante)
# ─────────────────────────────────────────────────────────────────────────────
def analyze_tier_performance(trades):
    """
    Análisis profundo por tier: rentabilidad, eficiencia del sizing,
    validación del modelo de confiabilidad y detección de reajustes.
    """
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 7: RENDIMIENTO DETALLADO POR TIER{RESET}")

    total = len(trades)

    for tier_name in ["SCOUT", "AMBUSH", "UNICORN"]:
        tier_t = [t for t in trades if t.get("tier") == tier_name]
        rr_min, rr_max = TIER_RR_RANGE[tier_name]
        p_min, p_max   = TIER_PROB_RANGE[tier_name]
        prob_min       = TIER_PROB_MIN[tier_name]
        emoji          = TIER_EMOJI.get(tier_name, "")
        mult_expected  = {"SCOUT": config.SCOUT_MULT,
                          "AMBUSH": config.AMBUSH_MULT,
                          "UNICORN": config.UNICORN_MULT}[tier_name]

        print(f"\n  {emoji} {BOLD}{tier_name}{RESET}  "
              f"prob [{p_min:.0f}%–{p_max:.0f}%] | R:R≥{rr_min} | sizing ×{mult_expected}")

        if not tier_t:
            print(f"  {DIM}  Sin trades en este tier. Filtros pueden ser demasiado restrictivos.{RESET}")
            continue

        wins   = [t for t in tier_t if t["pnl"] > 0]
        losses = [t for t in tier_t if t["pnl"] <= 0]
        wr     = len(wins) / len(tier_t) * 100
        ev     = statistics.mean([t["pnl"] for t in tier_t])
        aw     = statistics.mean([t["pnl"] for t in wins])   if wins   else 0
        al     = statistics.mean([t["pnl"] for t in losses]) if losses else 0
        rr_avg = statistics.mean([t["rr"]  for t in tier_t])
        prob_avg = statistics.mean([t["prob"] for t in tier_t])
        pct_total = len(tier_t) / total * 100

        kurt_t = _kurtosis([t["pnl"] for t in tier_t])
        skew_t = _skewness([t["pnl"] for t in tier_t])

        ev_c = GREEN if ev > 0 else RED

        print(f"    N: {len(tier_t)} ({pct_total:.1f}% del total) | "
              f"WR: {wr:.1f}% | Prob prom: {prob_avg:.1f}%")
        print(f"    EV: {ev_c}{ev:+.3f}%{RESET} | "
              f"Avg Win: {GREEN}{aw:+.3f}%{RESET} | "
              f"Avg Loss: {RED}{al:+.3f}%{RESET}")
        print(f"    R:R prom: {rr_avg:.2f} | Curtosis: {kurt_t:+.3f} | Skew: {skew_t:+.3f}")

        # ── Diagnóstico específico por tier ───────────────────────────────────
        if tier_name == "SCOUT":
            asym = aw + al
            if asym < 0:
                print(f"    {RED}⚠️  Scout: asimetría negativa ({asym:+.3f}%). "
                      f"Las pérdidas superan las ganancias. Considerar subir SCOUT_PROB_MIN a {prob_min+5:.0f}%.{RESET}")
            else:
                print(f"    {GREEN}✅ Scout: asimetría positiva. Tier funcional como base del sistema.{RESET}")

        elif tier_name == "AMBUSH":
            if wr < 45:
                print(f"    {YELLOW}⚠️  Ambush WR={wr:.1f}% — bajo para un tier de sizing ×1.5. "
                      f"Revisar AMBUSH_PROB_MIN (actualmente {prob_min}%).{RESET}")
            elif ev > 0 and wr > 50:
                print(f"    {GREEN}✅ Ambush: WR y EV positivos. El sizing ×1.5 está justificado.{RESET}")

        elif tier_name == "UNICORN":
            if len(tier_t) < 5:
                print(f"    {YELLOW}⚠️  Muy pocos Unicornios ({len(tier_t)}). "
                      f"Bajar UNICORN_PROB_MIN a {max(75, prob_min-5):.0f}% para generar más setups.{RESET}")
            elif kurt_t > 1.0:
                print(f"    {GREEN}✅ UNICORN con curtosis {kurt_t:+.3f} — Fat tails activas. "
                      f"El sizing ×3.0 está capturando outliers. NO cambiar parámetros.{RESET}")
            elif ev < 0:
                print(f"    {RED}⚠️  Unicorn con EV negativa. El sizing ×3.0 está amplificando pérdidas. "
                      f"Subir UNICORN_PROB_MIN a {prob_min+5:.0f}%.{RESET}")

        # ── Recomendación de reajuste de sizing ────────────────────────────────
        kelly_t = calculate_empirical_kelly_raw(wr/100, abs(aw), abs(al)) if aw and al else 0
        half_k  = kelly_t / 2
        base_risk = config.RISK_PER_TRADE_PCT
        effective_risk = base_risk * mult_expected

        print(f"    Riesgo efectivo: {effective_risk*100:.3f}% | "
              f"Half-Kelly del tier: {half_k*100:.3f}%", end="")
        if half_k > 0 and effective_risk > half_k * 1.3:
            print(f"  {RED}⚠️  Sobrearriesgando en {tier_name}{RESET}")
        elif half_k > 0 and effective_risk < half_k * 0.6:
            print(f"  {YELLOW}💡 Puede subir sizing en {tier_name}{RESET}")
        else:
            print(f"  {GREEN}✅{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO 8: Feature Importance Preview
# ─────────────────────────────────────────────────────────────────────────────
def analyze_blackbox_features(blackbox):
    labeled = [r for r in blackbox.records if r["outcome"] != -1] if blackbox else []
    if len(labeled) < 10:
        print(f"\n{DIM}[*] MÓDULO 8: Pocos registros Blackbox ({len(labeled)}). Necesitas más trades.{RESET}")
        return
    print(f"\n{BOLD}{CYAN}[*] MÓDULO 8: FEATURE IMPORTANCE PREVIEW (ADN → IA2){RESET}")
    blackbox.get_feature_importance_preview()
    s = blackbox.get_summary()
    print(f"\n  {DIM}Dataset: {s['labeled']} trades | {s['wins']}W / {s['losses']}L | WR: {s['win_rate']:.1f}%{RESET}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run_dynamic_forensics():
    print(f"\n{BOLD}Iniciando Autopsia Forense Dinámica V2.1...{RESET}")
    
    # NUEVO: Desempaquetamos las 5 temporalidades
    d1, d15, d1h, d4h, d1d = load_and_sync_data()
    
    # NUEVO: Pasamos las 5 temporalidades a la simulación
    trades, final_cap, blackbox = run_simulation(d1, d15, d1h, d4h, d1d)

    if not trades:
        print(f"{RED}No hay trades para analizar.{RESET}"); return

    print(f"\n{BOLD}{YELLOW}╔{'═'*66}╗{RESET}")
    print(f"{BOLD}{YELLOW}║{'LABORATORIO DE INFERENCIA DINÁMICA V2.1 — TIER SYSTEM':^66}║{RESET}")
    print(f"{BOLD}{YELLOW}╚{'═'*66}╝{RESET}")

    analyze_probability_tiers(trades)
    analyze_directional_bias(trades)
    module_kelly(trades)
    analyze_exit_anatomy(trades)
    analyze_statistical_distribution(trades)
    audit_config_parameters(trades)
    analyze_tier_performance(trades)
    analyze_blackbox_features(blackbox)

    # ── Diagnóstico ejecutivo ──────────────────────────────────────────────
    pnls = [t["pnl"] for t in trades]
    kurt = _kurtosis(pnls)
    skew = _skewness(pnls)
    wr   = len([t for t in trades if t["pnl"] > 0]) / len(trades) * 100

    print(f"\n{BOLD}{MAGENTA}╔{'═'*66}╗")
    print(f"║{'DIAGNÓSTICO EJECUTIVO':^66}║")
    print(f"╚{'═'*66}╝{RESET}")
    print(f"  Capital: ${final_cap:,.2f} | Trades: {len(trades)} | WR: {wr:.1f}%")
    print(f"  Curtosis Global: {kurt:+.4f} | Skewness Global: {skew:+.4f}")

    tier_counts = Counter(t.get("tier") for t in trades)
    for tier_name in ["SCOUT", "AMBUSH", "UNICORN"]:
        n = tier_counts.get(tier_name, 0)
        pct = n / len(trades) * 100 if trades else 0
        emoji = TIER_EMOJI.get(tier_name, "")
        mult  = {"SCOUT": config.SCOUT_MULT, "AMBUSH": config.AMBUSH_MULT, "UNICORN": config.UNICORN_MULT}[tier_name]
        print(f"  {emoji} {tier_name:<8}: {n:>4} trades ({pct:>5.1f}%) × {mult}")

    if kurt > 0.5 and skew > 0:
        print(f"\n  {GREEN}✅ Sistema con Fat Tails positivas. Estructura de Unicornio favorable.{RESET}")
    elif kurt < 0:
        print(f"\n  {RED}⚠️  Distribución Platicúrtica. El sistema no genera outliers. Revisar filtros.{RESET}")
    else:
        print(f"\n  {YELLOW}Sistema cercano a normal. Aumentar selectividad o revisar BE por tier.{RESET}")
    print()


if __name__ == "__main__":
    run_dynamic_forensics()