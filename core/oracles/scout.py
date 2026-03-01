import configs.btc_usdt_config as config

class ScoutOracle:
    def __init__(self):
        self.W_SWEEP         = 18.0
        self.W_ZONE_FAVOR    = 12.0
        self.W_ZONE_HOSTIL   = -10.0
        self.W_RSI           =  9.0
        self.W_VWAP_ALIGN    =  9.0
        self.W_ADX1H_HIGH    = -12.0
        self.W_ADX15M_OK     =  6.0
        self.W_ATR15M_HIGH   = -8.0
        self.W_VOLRATIO_HIGH = -6.0
        self.W_CVD1M_CONTRA  = -10.0
        self.W_CVD15M_CONTRA = -10.0
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

        rsi    = c1m.get("rsi", 50) or 50
        rsi_ob = 100 - getattr(config, "RSI_OVERSOLD", 35)
        if direction == "LONG"  and rsi < getattr(config, "RSI_OVERSOLD", 35): prob += self.W_RSI
        if direction == "SHORT" and rsi > rsi_ob:                              prob += self.W_RSI

        vwap_15m = c15m.get("vwap", curr_p) or curr_p
        if direction == "LONG"  and curr_p < vwap_15m: prob += self.W_VWAP_ALIGN
        if direction == "SHORT" and curr_p > vwap_15m: prob += self.W_VWAP_ALIGN

        if (c1h.get("adx",  20) or 20) > 28:    prob += self.W_ADX1H_HIGH
        if (c15m.get("adx", 20) or 20) > 20:    prob += self.W_ADX15M_OK
        
        atr_15m = c15m.get("atr", 0) or 0
        if (atr_15m / curr_p) * 100 > 0.35:     
            prob += self.W_ATR15M_HIGH
            
        if (c1m.get("vol_ratio", 1.0) or 1.0) > getattr(config, "VOL_RATIO_SPIKE_MAX", 2.0): 
            prob += self.W_VOLRATIO_HIGH

        cvd_1m = c1m.get("cvd", 0) or 0
        cvd1m_thresh = getattr(config, "CVD_1M_CONTRA_THRESHOLD", -15000)
        if direction == "LONG"  and cvd_1m < cvd1m_thresh: prob += self.W_CVD1M_CONTRA
        if direction == "SHORT" and cvd_1m > abs(cvd1m_thresh): prob += self.W_CVD1M_CONTRA

        cvd_15m = c15m.get("cvd", 0) or 0
        cvd15m_thresh = getattr(config, "CVD_15M_LONG_BLOCK", -55000)
        if direction == "LONG"  and cvd_15m < cvd15m_thresh: prob += self.W_CVD15M_CONTRA
        if direction == "SHORT" and cvd_15m > abs(cvd15m_thresh): prob += self.W_CVD15M_CONTRA

        ema_dist = c1h.get("ema_dist", None)
        if ema_dist is None: ema_dist = c1h.get("ema_trend_dist", 0) or 0
        if (ema_dist or 0) < getattr(config, "EMA_DIST_1H_EXTEND_PCT", -0.0055): prob += self.W_EMA1H_EXTEND

        return max(0.0, min(prob, 100.0))