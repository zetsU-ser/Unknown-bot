from __future__ import annotations

from typing import Optional
import configs.btc_usdt_config as config
from domain.models import BarrierSet, TradeState


def classify_tier(prob: float) -> Optional[str]:
    if prob >= getattr(config, "UNICORN_PROB_MIN", 88.0): return "UNICORN"
    if prob >= getattr(config, "AMBUSH_PROB_MIN",  81.0): return "AMBUSH"
    if prob >= getattr(config, "SCOUT_PROB_MIN",   66.4): return "SCOUT"
    return None


def get_tier_params(tier: str) -> dict:
    params = {
        "SCOUT": {
            "prob_min":     getattr(config, "SCOUT_PROB_MIN",   66.4),
            "mult":         getattr(config, "SCOUT_MULT",        1.0),
            "be_threshold": getattr(config, "SCOUT_BE_THRESHOLD", 0.645),
            "profit_lock":  getattr(config, "SCOUT_PROFIT_LOCK",  0.0),
            "max_bars":     getattr(config, "SCOUT_MAX_BARS",     240),
        },
        "AMBUSH": {
            "prob_min":     getattr(config, "AMBUSH_PROB_MIN",   81.0),
            "mult":         getattr(config, "AMBUSH_MULT",        1.25),
            "be_threshold": getattr(config, "AMBUSH_BE_THRESHOLD", 0.621),
            "profit_lock":  getattr(config, "AMBUSH_PROFIT_LOCK",  0.0),
            "max_bars":     getattr(config, "AMBUSH_MAX_BARS",     360),
        },
        "UNICORN": {
            "prob_min":     getattr(config, "UNICORN_PROB_MIN",   88.0),
            "mult":         getattr(config, "UNICORN_MULT",        3.0),
            "be_threshold": getattr(config, "UNICORN_BE_THRESHOLD", 0.95),
            "profit_lock":  getattr(config, "UNICORN_PROFIT_LOCK",  0.0),
            "max_bars":     getattr(config, "UNICORN_MAX_BARS",     720),
        },
    }
    return params.get(tier, params["AMBUSH"])


def kelly_position_size(
    cash: float, atr: float, entry_price: float, peak_capital: float
) -> float:
    drawdown = (peak_capital - cash) / peak_capital if peak_capital > 0 else 0.0
    if drawdown >= getattr(config, "MAX_DRAWDOWN_HALT", 0.12):
        return 0.0
    win_rate, avg_win_pct, avg_loss_pct = 0.55, 0.0035, 0.0035
    q = 1 - win_rate
    b = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1.0
    f = max(0.0, min((win_rate * b - q) / b, 0.05)) * getattr(config, "KELLY_FRACTION", 0.3)
    if drawdown >= getattr(config, "DRAWDOWN_REDUCE_2", 0.08):  f *= 0.50
    elif drawdown >= getattr(config, "DRAWDOWN_REDUCE_1", 0.04): f *= 0.75
    return max(0.0, min(f, getattr(config, "RISK_PER_TRADE_PCT", 0.02) * 2))


def compute_barriers(
    entry_price:  float,
    atr_15m:      float,
    direction:    str,
    nearest_res:  Optional[float] = None,
    nearest_sup:  Optional[float] = None,
) -> Optional[BarrierSet]:
    """
    Calcula los niveles de riesgo y retorna un BarrierSet tipado.
    """
    if not atr_15m or atr_15m <= 0:
        return None

    atr_pct         = atr_15m / entry_price
    dynamic_sl_mult = getattr(config, "ATR_SL_MULT", 2.142)
    if atr_pct > 0.003:
        dynamic_sl_mult = max(1.0, dynamic_sl_mult * (0.003 / atr_pct))

    min_rr = getattr(config, "RR_MIN_REQUIRED", 1.5)

    if direction == "LONG":
        limit_sl  = entry_price - (dynamic_sl_mult * atr_15m)
        struct_sl = (nearest_sup - 0.2 * atr_15m) if nearest_sup else limit_sl
        sl        = max(struct_sl, limit_sl)
        risk      = entry_price - sl
        min_tp    = entry_price + (risk * min_rr)
        tp        = max(nearest_res, min_tp) if nearest_res else entry_price + risk * 2.0
        reward    = tp - entry_price
    else:
        limit_sl  = entry_price + (dynamic_sl_mult * atr_15m)
        struct_sl = (nearest_res + 0.2 * atr_15m) if nearest_res else limit_sl
        sl        = min(struct_sl, limit_sl)
        risk      = sl - entry_price
        min_tp    = entry_price - (risk * min_rr)
        tp        = min(nearest_sup, min_tp) if nearest_sup else entry_price - risk * 2.0
        reward    = entry_price - tp

    if risk <= 0:
        return None

    rr = reward / risk
    RR_MAX = 5.0
    if rr > RR_MAX:
        tp     = entry_price + RR_MAX * risk if direction == "LONG" else entry_price - RR_MAX * risk
        reward = abs(tp - entry_price)
        rr     = RR_MAX

    be_threshold_default = getattr(config, "BE_DYNAMIC_THRESHOLD", 0.621)
    be_trigger           = entry_price + reward * be_threshold_default if direction == "LONG" \
                           else entry_price - reward * be_threshold_default

    return BarrierSet(
        sl             = sl,
        tp             = tp,
        rr             = round(rr, 4),
        be_trigger     = be_trigger,
        profit_lock_sl = entry_price,
        tier           = None,
        mult           = 1.0,
        max_bars       = getattr(config, "MAX_TRADE_BARS", 360),
        prob_min       = getattr(config, "SCOUT_PROB_MIN", 66.4),
    )


def enrich_barriers_with_tier(
    barriers:    BarrierSet,
    prob:        float,
    direction:   str,
    entry_price: float,
) -> bool:
    """
    Enriquece un BarrierSet existente con los parametros del tier correcto.
    """
    tier = classify_tier(prob)
    if tier is None:
        return False
    _apply_tier_to_barriers(barriers, tier, direction, entry_price)
    return True


def _apply_tier_to_barriers(
    barriers:    BarrierSet,
    tier:        str,
    direction:   str,
    entry_price: float,
) -> None:
    """Mutación in-place del BarrierSet tipado con los parametros del tier."""
    tier_p       = get_tier_params(tier)
    be_threshold = tier_p["be_threshold"]
    profit_lock  = tier_p["profit_lock"]
    tp           = barriers.tp

    if direction == "LONG":
        reward  = tp - entry_price
        be_trig = entry_price + reward * be_threshold
        pl_sl   = entry_price + (be_trig - entry_price) * profit_lock if profit_lock > 0 else entry_price
    else:
        reward  = entry_price - tp
        be_trig = entry_price - reward * be_threshold
        pl_sl   = entry_price - (entry_price - be_trig) * profit_lock if profit_lock > 0 else entry_price

    barriers.tier           = tier
    barriers.mult           = tier_p["mult"]
    barriers.max_bars       = tier_p["max_bars"]
    barriers.prob_min       = tier_p["prob_min"]
    barriers.be_trigger     = be_trig
    barriers.profit_lock_sl = pl_sl


def evaluate_exit(curr_price: float, trade_state: TradeState) -> tuple[str, Optional[str]]:
    """
    Evalua si el trade activo debe cerrarse usando el TradeState.
    """
    d     = trade_state.direction if hasattr(trade_state, "direction") else trade_state["direction"]
    b     = trade_state.barriers  if hasattr(trade_state, "barriers")  else trade_state["barriers"]
    be_on = trade_state.be_on     if hasattr(trade_state, "be_on")     else trade_state["be_on"]
    bars  = trade_state.bars_in_t if hasattr(trade_state, "bars_in_t") else trade_state["bars_in_t"]

    def _get(key, default=None):
        if isinstance(b, BarrierSet):
            return getattr(b, key, default)
        return b.get(key, default) if isinstance(b, dict) else default

    sl             = _get("sl")
    tp             = _get("tp")
    profit_lock_sl = _get("profit_lock_sl")
    is_unicorn     = (_get("tier", "AMBUSH") == "UNICORN")
    max_bars       = _get("max_bars", 360)

    if d == "LONG":
        if curr_price <= sl:                                          return "EXIT", "SL"
        if curr_price >= tp:                                          return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price <= profit_lock_sl: return "EXIT", "PROFIT_LOCK"
    else:
        if curr_price >= sl:                                          return "EXIT", "SL"
        if curr_price <= tp:                                          return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price >= profit_lock_sl: return "EXIT", "PROFIT_LOCK"

    if bars >= max_bars:
        return "EXIT", "TIMEOUT"

    return "WAIT", None