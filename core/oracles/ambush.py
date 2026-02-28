import configs.btc_usdt_config as config

class AmbushOracle:
    def __init__(self):
        self.W_ZONE_FAVOR    = 15.0
        self.W_ZONE_HOSTIL   = -12.0
        self.W_SWEEP         = 15.0
        self.W_OB_TOUCH      = 12.0
        self.W_FVG_NEAR      =  7.0
        self.W_RSI           =  8.0
        self.W_VWAP_NEAR     = 10.0
        self.W_VWAP_FAR      = -8.0
        self.W_CVD1M_ALIGNED  =  8.0
        self.W_CVD1M_CONTRA   = -14.0
        self.W_CVD15M_ALIGNED =  8.0
        self.W_CVD15M_CONTRA  = -12.0
        self.W_ADX1H_HIGH    = -12.0
        self.W_ATR15M_HIGH   = -8.0
        self.W_EMA1H_EXTEND  = -10.0

    def probability(self, c1m, c15m, c1h, direction, ctx):
        prob   = ctx["priors"][direction] 
        curr_p = c15m.get("close", 1) or 1
        zone = ctx["zone_15m"]
        
        if direction == "LONG":
            if zone == "DISCOUNT":  prob += self.W_ZONE_FAVOR
            elif zone == "PREMIUM": prob += self.W_ZONE_HOSTIL
        else:
            if zone == "PREMIUM":   prob += self.W_ZONE_FAVOR
            elif zone == "DISCOUNT": prob += self.W_ZONE_HOSTIL

        sweep = ctx["sweep"]
        if sweep["sweep"]:
            if direction == "LONG"  and sweep["direction"] == "BULL": prob += self.W_SWEEP
            if direction == "SHORT" and sweep["direction"] == "BEAR": prob += self.W_SWEEP

        ob = ctx["ob_touch"]
        if ob["touching"]:
            if direction == "LONG"  and ob["type"] == "bullish": prob += self.W_OB_TOUCH
            if direction == "SHORT" and ob["type"] == "bearish": prob += self.W_OB_TOUCH

        fvg = ctx["fvg_1m"]
        if direction == "LONG"  and fvg["bisi"]: prob += self.W_FVG_NEAR
        if direction == "SHORT" and fvg["sibi"]: prob += self.W_FVG_NEAR

        vwap_1m  = c1m.get("vwap", curr_p) or curr_p
        dist_pct = abs(curr_p - vwap_1m) / max(vwap_1m, 1)
        if dist_pct < 0.0025: prob += self.W_VWAP_NEAR
        elif dist_pct > 0.0040: prob += self.W_VWAP_FAR

        # ── REFACTORIZACIÓN CONFIG (RSI y Tendencia) ──
        rsi = c1m.get("rsi", 50) or 50
        rsi_ob = 100 - config.RSI_TREND_MIN
        if direction == "LONG"  and rsi < config.RSI_TREND_MIN: prob += self.W_RSI
        if direction == "SHORT" and rsi > rsi_ob:               prob += self.W_RSI

        # ── REFACTORIZACIÓN CONFIG (Flujo Micro CVD) ──
        cvd_1m = c1m.get("cvd", 0) or 0
        if direction == "LONG":
            if cvd_1m  > (config.CVD_1M_CONTRA_THRESHOLD / 2):    prob += self.W_CVD1M_ALIGNED
            elif cvd_1m < config.CVD_1M_CONTRA_THRESHOLD:         prob += self.W_CVD1M_CONTRA
        else:
            if cvd_1m  < abs(config.CVD_1M_CONTRA_THRESHOLD / 2): prob += self.W_CVD1M_ALIGNED
            elif cvd_1m > abs(config.CVD_1M_CONTRA_THRESHOLD):    prob += self.W_CVD1M_CONTRA

        # ── REFACTORIZACIÓN CONFIG (Flujo Macro CVD) ──
        cvd_15m = c15m.get("cvd", 0) or 0
        if direction == "LONG":
            if cvd_15m  > config.CVD_15M_SHORT_SUPPORT: prob += self.W_CVD15M_ALIGNED
            elif cvd_15m < config.CVD_15M_LONG_BLOCK:   prob += self.W_CVD15M_CONTRA
        else:
            if cvd_15m  < config.CVD_15M_LONG_BLOCK:     prob += self.W_CVD15M_ALIGNED
            elif cvd_15m > config.CVD_15M_SHORT_SUPPORT: prob += self.W_CVD15M_CONTRA

        # ── REFACTORIZACIÓN CONFIG (Filtros de Calidad) ──
        if (c1h.get("adx", 20) or 20) > config.ADX_STRONG: prob += self.W_ADX1H_HIGH
        if (c15m.get("atr", 200) or 200) > config.ATR_15M_NOISE_MAX: prob += self.W_ATR15M_HIGH

        ema_dist = c1h.get("ema_dist", None)
        if ema_dist is None: ema_dist = c1h.get("ema_trend_dist", 0) or 0
        if (ema_dist or 0) < config.EMA_DIST_1H_EXTEND_PCT: prob += self.W_EMA1H_EXTEND

        return max(0.0, min(prob, 100.0))