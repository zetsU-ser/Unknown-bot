import configs.btc_usdt_config as config

def classify_tier(prob: float) -> str | None:
    if prob >= getattr(config, "UNICORN_PROB_MIN", 88.0):   return "UNICORN"
    elif prob >= getattr(config, "AMBUSH_PROB_MIN", 81.0):  return "AMBUSH"
    elif prob >= getattr(config, "SCOUT_PROB_MIN", 66.4):   return "SCOUT"
    return None

def get_tier_params(tier: str) -> dict:
    params = {
        "SCOUT":   {"prob_min": getattr(config, "SCOUT_PROB_MIN", 66.4),   "mult": getattr(config, "SCOUT_MULT", 1.0),   "be_threshold": getattr(config, "SCOUT_BE_THRESHOLD", 0.645),   "profit_lock": getattr(config, "SCOUT_PROFIT_LOCK", 0.0),   "max_bars": getattr(config, "SCOUT_MAX_BARS", 240)},
        "AMBUSH":  {"prob_min": getattr(config, "AMBUSH_PROB_MIN", 81.0),  "mult": getattr(config, "AMBUSH_MULT", 1.25),  "be_threshold": getattr(config, "AMBUSH_BE_THRESHOLD", 0.621),  "profit_lock": getattr(config, "AMBUSH_PROFIT_LOCK", 0.0),  "max_bars": getattr(config, "AMBUSH_MAX_BARS", 360)},
        "UNICORN": {"prob_min": getattr(config, "UNICORN_PROB_MIN", 88.0), "mult": getattr(config, "UNICORN_MULT", 3.0), "be_threshold": getattr(config, "UNICORN_BE_THRESHOLD", 0.95), "profit_lock": getattr(config, "UNICORN_PROFIT_LOCK", 0.0), "max_bars": getattr(config, "UNICORN_MAX_BARS", 720)}
    }
    return params.get(tier, params["AMBUSH"])

def kelly_position_size(cash, atr, entry_price, peak_capital):
    drawdown = (peak_capital - cash) / peak_capital if peak_capital > 0 else 0.0
    if drawdown >= getattr(config, "MAX_DRAWDOWN_HALT", 0.12): return 0.0
    win_rate, avg_win_pct, avg_loss_pct = 0.55, 0.0035, 0.0035
    q = 1 - win_rate
    b = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1.0
    f = max(0.0, min((win_rate * b - q) / b, 0.05)) * getattr(config, "KELLY_FRACTION", 0.3)
    if drawdown >= getattr(config, "DRAWDOWN_REDUCE_2", 0.08): f *= 0.50
    elif drawdown >= getattr(config, "DRAWDOWN_REDUCE_1", 0.04): f *= 0.75
    return max(0.0, min(f, getattr(config, "RISK_PER_TRADE_PCT", 0.02) * 2))

def compute_barriers(entry_price, atr_15m, direction, nearest_res=None, nearest_sup=None) -> dict | None:
    if not atr_15m or atr_15m <= 0: return None

    atr_pct = atr_15m / entry_price
    dynamic_sl_mult = getattr(config, "ATR_SL_MULT", 2.142)
    if atr_pct > 0.003: 
        dynamic_sl_mult = max(1.0, dynamic_sl_mult * (0.003 / atr_pct))

    min_rr = getattr(config, "RR_MIN_REQUIRED", 1.5)

    if direction == "LONG":
        limit_sl  = entry_price - (dynamic_sl_mult * atr_15m)
        struct_sl = (nearest_sup - (0.2 * atr_15m)) if nearest_sup else limit_sl
        sl        = max(struct_sl, limit_sl)
        risk      = entry_price - sl

        min_tp    = entry_price + (risk * min_rr)
        tp_price  = max(nearest_res, min_tp) if nearest_res else (entry_price + (risk * 2.0))
        reward    = tp_price - entry_price
    else:
        limit_sl  = entry_price + (dynamic_sl_mult * atr_15m)
        struct_sl = (nearest_res + (0.2 * atr_15m)) if nearest_res else limit_sl
        sl        = min(struct_sl, limit_sl)
        risk      = sl - entry_price

        min_tp    = entry_price - (risk * min_rr)
        tp_price  = min(nearest_sup, min_tp) if nearest_sup else (entry_price - (risk * 2.0))
        reward    = entry_price - tp_price

    if risk <= 0: return None
    rr = reward / risk

    RR_MAX = 5.0
    if rr > RR_MAX:
        tp_price = entry_price + (RR_MAX * risk) if direction == "LONG" else entry_price - (RR_MAX * risk)
        rr = RR_MAX

    return {
        "sl": sl, "tp": tp_price, "rr": round(rr, 4),
        "tier": None, "mult": 1.0, "max_bars": getattr(config, "MAX_TRADE_BARS", 360),
        "prob_min": getattr(config, "SCOUT_PROB_MIN", 66.4),
        "be_trigger": entry_price + reward * getattr(config, "BE_DYNAMIC_THRESHOLD", 0.621),
        "profit_lock_sl": entry_price,
    }

def enrich_barriers_with_tier(barriers: dict, prob: float, direction: str, entry_price: float) -> bool:
    tier = classify_tier(prob)
    if tier is None: return False
    
    tier_p = get_tier_params(tier)
    be_threshold, profit_lock = tier_p["be_threshold"], tier_p["profit_lock"]
    tp_price, sl = barriers["tp"], barriers["sl"]

    if direction == "LONG":
        reward  = tp_price - entry_price
        be_trig = entry_price + (reward * be_threshold)
        pl_sl   = entry_price + ((be_trig - entry_price) * profit_lock) if profit_lock > 0 else entry_price
    else:
        reward  = entry_price - tp_price
        be_trig = entry_price - (reward * be_threshold)
        pl_sl   = entry_price - ((entry_price - be_trig) * profit_lock) if profit_lock > 0 else entry_price

    barriers.update({"tier": tier, "mult": tier_p["mult"], "max_bars": tier_p["max_bars"], 
                     "prob_min": tier_p["prob_min"], "be_trigger": be_trig, "profit_lock_sl": pl_sl})
    return True

def evaluate_exit(curr_price: float, trade_state: dict) -> tuple[str, str | None]:
    d, b, be_on = trade_state["direction"], trade_state["barriers"], trade_state["be_on"]
    is_unicorn = (b.get("tier", "AMBUSH") == "UNICORN")

    if d == "LONG":
        if curr_price <= b["sl"]: return "EXIT", "SL"
        if curr_price >= b["tp"]: return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price <= b["profit_lock_sl"]: return "EXIT", "PROFIT_LOCK"
    else:
        if curr_price >= b["sl"]: return "EXIT", "SL"
        if curr_price <= b["tp"]: return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price >= b["profit_lock_sl"]: return "EXIT", "PROFIT_LOCK"

    if trade_state["bars_in_t"] >= b.get("max_bars", 360):
        return "EXIT", "TIMEOUT"
    return "WAIT", None