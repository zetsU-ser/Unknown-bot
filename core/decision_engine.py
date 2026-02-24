# core/decision_engine.py
import polars as pl
import configs.btc_usdt_config as config
from analysis.market_structure import (
    detect_regime, detect_liquidity_sweep, find_key_levels
)
from core.risk_manager import compute_barriers, evaluate_exit
from analysis.volume_profile import detect_volume_divergence

class ZetzuHuntEngine:
    """Motor Probabilístico V9.0 (SMC + Premium/Discount + VWAP)"""
    def __init__(self):
        # ── PESOS SMC CALIBRADOS POR IA FORENSE ──
        self.W_SWEEP = 30.0           
        self.W_ZONE_FAVORABLE = 20.0  
        self.W_RSI   = 15.0     
        self.W_RR    = 10.0     
        
        # ── NUEVO: PESOS DE VOLUMEN (Bloque 3) ──
        self.W_VWAP_ALIGN = 15.0      # Premio si compramos barato vs VWAP
        self.W_VWAP_TRAP  = -20.0     # Castigo si caemos en trampa retail

        self.W_DIVERGENCE_TRAP = -35.0  # Castigo letal para evitar trampas
        #self.W_DIVERGENCE_CONF = 10.0   # Premio por confluencia de volumen
        
        self.W_ZONE_HOSTIL    = -15.0 
        self.W_ADX_HIGH       = -5.0  
        self.W_NOISE          = -25.0 

    def zetzu_hunt_probability(self, df_1m, df_15m, df_1h, direction, barriers):
        c1h = df_1h.tail(1).to_dicts()[0]
        c15m = df_15m.tail(1).to_dicts()[0]
        c1m = df_1m.tail(1).to_dicts()[0]
        curr_p = c15m["close"]
        
        regime_data = detect_regime(df_15m)
        trend_15m = regime_data["trend"]
        zone_15m  = regime_data["zone"]
        
        # 1. PRIOR (Basado en Estructura de Dow)
        prob = 20.0 
        if direction == "LONG":
            if trend_15m == "BULLISH" and c1h.get("ema_trend") and curr_p > c1h["ema_trend"]: prob = 40.0
            elif trend_15m == "RANGING": prob = 30.0
        elif direction == "SHORT":
            if trend_15m == "BEARISH" and c1h.get("ema_trend") and curr_p < c1h["ema_trend"]: prob = 40.0
            elif trend_15m == "RANGING": prob = 30.0

        # 2. FILTRO INSTITUCIONAL (Premium vs Discount)
        if direction == "LONG":
            if zone_15m == "DISCOUNT": prob += self.W_ZONE_FAVORABLE
            elif zone_15m == "PREMIUM": prob += self.W_ZONE_HOSTIL
        else: # SHORT
            if zone_15m == "PREMIUM": prob += self.W_ZONE_FAVORABLE
            elif zone_15m == "DISCOUNT": prob += self.W_ZONE_HOSTIL

        # 3. LIKELIHOOD (Gatillo Micro en 1m)
        sweep = detect_liquidity_sweep(df_1m)
        rsi = c1m.get("rsi", 50)
        rsi_overbought = 100 - config.RSI_OVERSOLD
        is_validated_sweep = False 

        if direction == "LONG":
            if sweep["sweep"] and sweep["direction"] == "BULL": 
                prob += self.W_SWEEP
                is_validated_sweep = True
            if rsi < config.RSI_OVERSOLD: prob += self.W_RSI
        else: # SHORT
            if sweep["sweep"] and sweep["direction"] == "BEAR": 
                prob += self.W_SWEEP
                is_validated_sweep = True
            if rsi > rsi_overbought: prob += self.W_RSI
            
        # ── INYECCIÓN BLOQUE 3: FILTRO VWAP INSTITUCIONAL ──
        vwap_15m = c15m.get("vwap", curr_p) 
        # Si el CVD actual es mayor al anterior, hay presión compradora neta
        cvd_actual = c1m.get("cvd", 0)
        
        if direction == "LONG":
            if curr_p < vwap_15m: 
                # Estamos en descuento, pero ¿hay compras reales?
                if cvd_actual > 0: 
                    prob += self.W_VWAP_ALIGN  # Descuento + Compras = Setup Institucional
                else: 
                    prob += self.W_VWAP_TRAP   # Descuento sin compras = Cuchillo cayendo
        else: # SHORT
            if curr_p > vwap_15m: 
                if cvd_actual < 0: 
                    prob += self.W_VWAP_ALIGN  # Premium + Ventas reales
                else: 
                    prob += self.W_VWAP_TRAP

        # Analizamos la micro-tendencia de los últimos 10 minutos
        vol_status = detect_volume_divergence(df_1m, lookback=10)

        if direction == "LONG":
            if vol_status == "BEAR_DIV": 
                prob += self.W_DIVERGENCE_TRAP  # VETO: El precio sube pero el volumen muere
        else: # SHORT
            if vol_status == "BULL_DIV":
                prob += self.W_DIVERGENCE_TRAP  # VETO: El precio cae pero el volumen compra

        return max(0.0, min(prob, 100.0))
    

# ── INSTANCIA DEL MOTOR ──
zetzu_oraculo = ZetzuHuntEngine()

def check_mtf_signals(df_1m, df_15m, df_1h, trade_state: dict = None):
    if len(df_1m) < 100 or len(df_15m) < 30: return "WAIT", "WARMUP", None, 0.0, None

    c1m = df_1m.tail(1).to_dicts()[0]
    
    if trade_state and trade_state.get("active"):
        sig, reason = evaluate_exit(curr_price=c1m["close"], trade_state=trade_state)
        return sig, reason, None, 0.0, None

    c1h = df_1h.tail(1).to_dicts()[0]
    direction = "LONG" if c1m["close"] > c1h.get("ema_trend", 0) else "SHORT"

    c15m = df_15m.tail(1).to_dicts()[0]
    levels = find_key_levels(df_15m)
    tentative_barriers = compute_barriers(
        entry_price = c1m["close"], atr_15m = c15m.get("atr"), direction = direction,
        nearest_res = levels.get("nearest_resistance"), nearest_sup = levels.get("nearest_support")
    )

    if not tentative_barriers: return "WAIT", "GATE", None, 0.0, None

    prob = zetzu_oraculo.zetzu_hunt_probability(df_1m, df_15m, df_1h, direction, tentative_barriers)

    # El filtro de paso se mantiene en 65.0. 
    if prob >= 65.0:
        return "ENTRY", f"ZETZU_{direction[:1]}:{prob:.1f}%", tentative_barriers, prob, direction

    return "WAIT", None, None, 0.0, None