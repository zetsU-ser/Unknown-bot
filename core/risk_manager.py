# core/risk_manager.py
import math
import configs.btc_usdt_config as config

def kelly_position_size(cash, atr, entry_price, peak_capital):
    drawdown = (peak_capital - cash) / peak_capital if peak_capital > 0 else 0.0
    if drawdown >= config.MAX_DRAWDOWN_HALT: return 0.0

    win_rate, avg_win_pct, avg_loss_pct = 0.55, 0.0035, 0.0035
    q = 1 - win_rate
    b = avg_win_pct / avg_loss_pct if avg_loss_pct > 0 else 1.0
    f = max(0.0, min((win_rate * b - q) / b, 0.05)) * config.KELLY_FRACTION

    if drawdown >= config.DRAWDOWN_REDUCE_2: f *= 0.50
    elif drawdown >= config.DRAWDOWN_REDUCE_1: f *= 0.75

    return max(0.0, min(f, config.RISK_PER_TRADE_PCT * 2))

def compute_barriers(entry_price, atr_15m, direction, nearest_res=None, nearest_sup=None) -> dict:
    """Calcula las barreras bidireccionales. Invierte la matemática si es SHORT."""
    if not atr_15m or atr_15m <= 0: return None

    if direction == "LONG":
        sl_limit = entry_price - (config.ATR_SL_MULT * atr_15m)
        sl = max(nearest_sup, sl_limit) if nearest_sup else sl_limit
        tp_min = entry_price + (config.ATR_TP_MULT * atr_15m)
        tp = max(nearest_res, tp_min) if nearest_res else (entry_price + 2.0 * atr_15m)
        risk, reward = entry_price - sl, tp - entry_price

    else: # SHORT
        sl_limit = entry_price + (config.ATR_SL_MULT * atr_15m)
        sl = min(nearest_res, sl_limit) if nearest_res else sl_limit
        tp_min = entry_price - (config.ATR_TP_MULT * atr_15m)
        tp = min(nearest_sup, tp_min) if nearest_sup else (entry_price - 2.0 * atr_15m)
        risk, reward = sl - entry_price, entry_price - tp

    if risk <= 0: return None
    rr = reward / risk
    if rr < config.RR_MIN_REQUIRED: return None

    # Profit Lock Bidireccional
    if direction == "LONG":
        be_trig = entry_price + (reward * config.BE_DYNAMIC_THRESHOLD)
        pl_sl = entry_price + ((be_trig - entry_price) * config.PROFIT_LOCK_FRACTION)
    else:
        be_trig = entry_price - (reward * config.BE_DYNAMIC_THRESHOLD)
        pl_sl = entry_price - ((entry_price - be_trig) * config.PROFIT_LOCK_FRACTION)

    return {"sl": sl, "tp": tp, "rr": rr, "be_trigger": be_trig, "profit_lock_sl": pl_sl}

def evaluate_exit(curr_price, trade_state):
    #print("DEBUG: Evaluando salida desde CORE")
    """
    Evalúa la salida. 
    REGLA DE ORO V9.1: Los Unicornios NO tienen Profit Lock para forzar Curtosis Positiva.
    """
    d = trade_state["direction"]
    b = trade_state["barriers"]
    be_on = trade_state["be_on"]
    is_unicorn = (trade_state.get("mult", 1.0) == 3.0)

    # Hard Stops (SL y TP)
    if d == "LONG":
        if curr_price <= b["sl"]: return "EXIT", "SL"
        if curr_price >= b["tp"]: return "EXIT", "TP"
        # Inmunidad Unicornio: Si es unicornio, ignoramos el Profit Lock (buscamos la Fat Tail)
        if not is_unicorn and be_on and curr_price <= b["profit_lock_sl"]: 
            return "EXIT", "PROFIT_LOCK"
    else: # SHORT
        if curr_price >= b["sl"]: return "EXIT", "SL"
        if curr_price <= b["tp"]: return "EXIT", "TP"
        if not is_unicorn and be_on and curr_price >= b["profit_lock_sl"]: 
            return "EXIT", "PROFIT_LOCK"

    # Regla de Tiempo (Bloque 4: Triple Barrier Method)
    # Unicornios: 12h (720 barras). Ambushes: 6h (360 barras).
    max_bars = config.MAX_TRADE_BARS * 2 if is_unicorn else config.MAX_TRADE_BARS
    if trade_state["bars_in_t"] >= max_bars:
        return "EXIT", "TIMEOUT"

    return "WAIT", None