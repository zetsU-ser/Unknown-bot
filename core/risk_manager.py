# core/risk_manager.py — V10.0 TIER SYSTEM
"""
Gestor de Riesgo V10.0 — Sistema de Tiers Estandarizado
=========================================================
El tier ya NO lo decide la probabilidad bayesiana.
Lo decide la geometría del setup: el R:R que los niveles estructurales ofrecen.

Tier Classification (por R:R geométrico):
  🍃 Scout   : 1.50 – 1.59  → Conservative. BE rápido, protección alta.
  ⚔️  Ambush  : 1.60 – 2.50  → Standard. Balance entre protección y recorrido.
  🦄 Unicorn : 2.61 – 5.00  → Aggressive. Sin Profit Lock. Fat tail hunting.

Cada tier tiene su propio modelo de:
  - Probabilidad mínima requerida (confiabilidad)
  - Multiplicador de posición
  - BE trigger (% del recorrido al TP)
  - Profit lock fraction
  - Timeout máximo
"""

import configs.btc_usdt_config as config


# ─────────────────────────────────────────────────────────────────────────────
def classify_tier(prob: float) -> str | None:
    """
    V10.2: Clasifica el tier por PROBABILIDAD BAYESIANA.

    El R:R es el gate de admisión (en compute_barriers).
    El tier diferencia el sizing y la gestión de salidas.

    Args:
        prob: Probabilidad calculada por el Oráculo (0–100).

    Returns:
        "SCOUT" | "AMBUSH" | "UNICORN" | None (prob < Scout mínimo → no operar)
    """
    if prob >= config.UNICORN_PROB_MIN:   # ≥ 80%
        return "UNICORN"
    elif prob >= config.AMBUSH_PROB_MIN:  # ≥ 75%
        return "AMBUSH"
    elif prob >= config.SCOUT_PROB_MIN:   # ≥ 70%
        return "SCOUT"
    else:
        return None   # prob < 70% → setup de baja calidad, no operar


def get_tier_params(tier: str) -> dict:
    """
    Retorna todos los parámetros de gestión de salidas para un tier dado.

    Returns:
        dict con: prob_min, mult, be_threshold, profit_lock, max_bars
    """
    if tier == "SCOUT":
        return {
            "prob_min":    config.SCOUT_PROB_MIN,
            "mult":        config.SCOUT_MULT,
            "be_threshold": config.SCOUT_BE_THRESHOLD,
            "profit_lock": config.SCOUT_PROFIT_LOCK,
            "max_bars":    config.SCOUT_MAX_BARS,
        }
    elif tier == "AMBUSH":
        return {
            "prob_min":    config.AMBUSH_PROB_MIN,
            "mult":        config.AMBUSH_MULT,
            "be_threshold": config.AMBUSH_BE_THRESHOLD,
            "profit_lock": config.AMBUSH_PROFIT_LOCK,
            "max_bars":    config.AMBUSH_MAX_BARS,
        }
    elif tier == "UNICORN":
        return {
            "prob_min":    config.UNICORN_PROB_MIN,
            "mult":        config.UNICORN_MULT,
            "be_threshold": config.UNICORN_BE_THRESHOLD,
            "profit_lock": config.UNICORN_PROFIT_LOCK,
            "max_bars":    config.UNICORN_MAX_BARS,
        }
    # Fallback → AMBUSH params como default seguro
    return {
        "prob_min":    config.AMBUSH_PROB_MIN,
        "mult":        config.AMBUSH_MULT,
        "be_threshold": config.AMBUSH_BE_THRESHOLD,
        "profit_lock": config.AMBUSH_PROFIT_LOCK,
        "max_bars":    config.AMBUSH_MAX_BARS,
    }


# ─────────────────────────────────────────────────────────────────────────────
def kelly_position_size(cash, atr, entry_price, peak_capital):
    drawdown = (peak_capital - cash) / peak_capital if peak_capital > 0 else 0.0
    if drawdown >= config.MAX_DRAWDOWN_HALT:
        return 0.0

    win_rate, avg_win_pct, avg_loss_pct = 0.55, 0.0035, 0.0035
    q = 1 - win_rate
    b = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1.0
    f = max(0.0, min((win_rate * b - q) / b, 0.05)) * config.KELLY_FRACTION

    if drawdown >= config.DRAWDOWN_REDUCE_2:
        f *= 0.50
    elif drawdown >= config.DRAWDOWN_REDUCE_1:
        f *= 0.75

    return max(0.0, min(f, config.RISK_PER_TRADE_PCT * 2))



# ─────────────────────────────────────────────────────────────────────────────
def compute_barriers(entry_price, atr_15m, direction,
                     nearest_res=None, nearest_sup=None) -> dict | None:
    """
    Calcula los niveles SL/TP del trade y verifica el gate de calidad (R:R ≥ 1.5).

    V10.2: compute_barriers ya NO asigna el tier.
    El tier se asigna DESPUÉS de calcular la probabilidad, via enrich_barriers_with_tier().

    Returns:
        dict con sl, tp, rr (y tier=None como placeholder)
        None si R:R < 1.5 (setup inválido)
    """
    if not atr_15m or atr_15m <= 0:
        return None

    # ── 1. Niveles estructurales ──────────────────────────────────────────────
    if direction == "LONG":
        sl_limit = entry_price - (config.ATR_SL_MULT * atr_15m)
        sl       = max(nearest_sup, sl_limit) if nearest_sup else sl_limit
        tp_min   = entry_price + (config.ATR_TP_MULT * atr_15m)
        tp_price = max(nearest_res, tp_min) if nearest_res else (entry_price + 2.0 * atr_15m)
        risk     = entry_price - sl
        reward   = tp_price - entry_price
    else:  # SHORT
        sl_limit = entry_price + (config.ATR_SL_MULT * atr_15m)
        sl       = min(nearest_res, sl_limit) if nearest_res else sl_limit
        tp_min   = entry_price - (config.ATR_TP_MULT * atr_15m)
        tp_price = min(nearest_sup, tp_min) if nearest_sup else (entry_price - 2.0 * atr_15m)
        risk     = sl - entry_price
        reward   = entry_price - tp_price

    if risk <= 0:
        return None

    rr = reward / risk

    # ── 2. Gate de R:R mínimo (1.5) ──────────────────────────────────────────
    if rr < config.RR_MIN_REQUIRED:
        return None   # Setup sin suficiente asimetría → no operar

    # ── 3. Cap de R:R máximo (5.0) ─────────────────────────────────────────
    # Si la resistencia está a R:R=236, el TP nunca se alcanza → siempre SL.
    # Truncamos el TP al nivel más cercano que produce R:R=5.0.
    # Resultado: TP alcanzable, WR sube, el sistema se vuelve profitable.
    RR_MAX = 5.0
    if rr > RR_MAX:
        if direction == "LONG":
            tp_price = entry_price + (RR_MAX * risk)
        else:
            tp_price = entry_price - (RR_MAX * risk)
        rr = RR_MAX

    # ── 3. Retornar geometría sin tier (se asigna después con la prob) ─────────
    return {
        "sl":             sl,
        "tp":             tp_price,
        "rr":             round(rr, 4),
        # Tier pendiente — se enriquece via enrich_barriers_with_tier(prob)
        "tier":           None,
        "mult":           1.0,      # placeholder
        "max_bars":       config.MAX_TRADE_BARS,
        "prob_min":       config.SCOUT_PROB_MIN,
        "be_trigger":     entry_price + reward * config.BE_DYNAMIC_THRESHOLD,
        "profit_lock_sl": entry_price,
    }


def enrich_barriers_with_tier(barriers: dict, prob: float,
                               direction: str, entry_price: float) -> bool:
    """
    Asigna el tier a las barreras basándose en la probabilidad (V10.2).
    Recalcula BE trigger y Profit Lock según los parámetros del tier.

    Modifica barriers in-place.

    Returns:
        True si se asignó tier válido (prob ≥ 70%)
        False si prob < 70% → no operar
    """
    tier = classify_tier(prob)
    if tier is None:
        return False   # prob insuficiente

    tier_p       = get_tier_params(tier)
    be_threshold = tier_p["be_threshold"]
    profit_lock  = tier_p["profit_lock"]

    tp_price = barriers["tp"]
    sl       = barriers["sl"]

    if direction == "LONG":
        reward  = tp_price - entry_price
        be_trig = entry_price + (reward * be_threshold)
        pl_sl   = entry_price + ((be_trig - entry_price) * profit_lock) if profit_lock > 0 else entry_price
    else:  # SHORT
        reward  = entry_price - tp_price
        be_trig = entry_price - (reward * be_threshold)
        pl_sl   = entry_price - ((entry_price - be_trig) * profit_lock) if profit_lock > 0 else entry_price

    barriers["tier"]           = tier
    barriers["mult"]           = tier_p["mult"]
    barriers["max_bars"]       = tier_p["max_bars"]
    barriers["prob_min"]       = tier_p["prob_min"]
    barriers["be_trigger"]     = be_trig
    barriers["profit_lock_sl"] = pl_sl

    return True


# ─────────────────────────────────────────────────────────────────────────────
def evaluate_exit(curr_price: float, trade_state: dict) -> tuple[str, str | None]:
    """
    Evalúa condición de salida con lógica específica por tier.

    Tier rules:
      Scout  : Profit Lock activo (50%). Timeout 4h.
      Ambush : Profit Lock activo (25%). Timeout 6h.
      Unicorn: SIN Profit Lock → fat tail hunting. Timeout 12h.
    """
    d      = trade_state["direction"]
    b      = trade_state["barriers"]
    be_on  = trade_state["be_on"]
    tier   = b.get("tier", "AMBUSH")   # fallback seguro

    is_unicorn = (tier == "UNICORN")

    # ── Hard Stops: SL y TP ───────────────────────────────────────────────────
    if d == "LONG":
        if curr_price <= b["sl"]:  return "EXIT", "SL"
        if curr_price >= b["tp"]:  return "EXIT", "TP"
        # Profit Lock (Scout y Ambush solamente)
        if not is_unicorn and be_on and curr_price <= b["profit_lock_sl"]:
            return "EXIT", "PROFIT_LOCK"
    else:  # SHORT
        if curr_price >= b["sl"]:  return "EXIT", "SL"
        if curr_price <= b["tp"]:  return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price >= b["profit_lock_sl"]:
            return "EXIT", "PROFIT_LOCK"

    # ── Timeout específico por tier ───────────────────────────────────────────
    max_bars = b.get("max_bars", config.MAX_TRADE_BARS)
    if trade_state["bars_in_t"] >= max_bars:
        return "EXIT", "TIMEOUT"

    return "WAIT", None