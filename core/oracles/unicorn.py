import configs.btc_usdt_config as config

class UnicornOracle:
    def __init__(self):
        self.BASE_CHOCH      = 40.0
        self.BASE_SFP_EQL    = 35.0
        self.BASE_SFP_BASIC  = 28.0
        self.W_PD_BOTH_TF    = 20.0
        self.W_PD_ONE_TF     = 10.0
        self.W_PD_ADVERSE    = -15.0
        self.W_OB_TOUCH      = 12.0
        self.W_FVG_NEAR      =  8.0
        self.W_EQL_SWEPT     =  8.0
        self.W_EQH_SWEPT     =  8.0
        self.W_TREND_1H      = 10.0
        self.W_TREND_15M     =  5.0
        self.W_TREND_CONTRA  = -8.0
        self.W_CVD15M_OK     =  8.0
        self.W_CVD15M_BLOCK  = -20.0
        self.W_CVD1M_OK      =  5.0
        self.W_CVD1M_CONTRA  = -15.0
        self.W_RSI_EXTREME   =  7.0

    def probability(self, c1m, c15m, c1h, direction, ctx):
        bos_choch = ctx["bos_choch"]
        sweep     = ctx["sweep"]
        eqh_eql   = ctx["eqh_eql"]

        has_choch   = (bos_choch["choch"] and bos_choch["direction"] == ("BULL" if direction == "LONG" else "BEAR"))
        has_sfp_eql = (direction == "LONG"  and sweep["sweep"] and sweep["direction"] == "BULL" and eqh_eql["eql_swept"])
        has_sfp_eqh = (direction == "SHORT" and sweep["sweep"] and sweep["direction"] == "BEAR" and eqh_eql["eqh_swept"])
        has_sfp     = (sweep["sweep"] and sweep["direction"] == ("BULL" if direction == "LONG" else "BEAR"))

        if not (has_choch or has_sfp_eql or has_sfp_eqh or has_sfp):
            return 0.0  

        prob = (self.BASE_CHOCH if has_choch else self.BASE_SFP_EQL if (has_sfp_eql or has_sfp_eqh) else self.BASE_SFP_BASIC)

        zone_15m  = ctx["zone_15m"]
        zone_1h   = ctx["zone_1h"]
        pd_ok_15m = (direction == "LONG"  and zone_15m == "DISCOUNT") or (direction == "SHORT" and zone_15m == "PREMIUM")
        pd_ok_1h  = (direction == "LONG"  and zone_1h  == "DISCOUNT") or (direction == "SHORT" and zone_1h  == "PREMIUM")
        if pd_ok_15m and pd_ok_1h:    prob += self.W_PD_BOTH_TF
        elif pd_ok_15m:               prob += self.W_PD_ONE_TF
        else:                         prob += self.W_PD_ADVERSE

        # ── REFACTORIZACIÓN CONFIG (Flujo Macro CVD Exclusivo Unicornio) ──
        cvd_15m = c15m.get("cvd", 0) or 0
        if direction == "LONG":
            if cvd_15m > config.UNICORN_CVD15M_ALIGNED: prob += self.W_CVD15M_OK
            elif cvd_15m < config.UNICORN_CVD15M_BLOCK: prob += self.W_CVD15M_BLOCK
        else:
            if cvd_15m < abs(config.UNICORN_CVD15M_ALIGNED): prob += self.W_CVD15M_OK
            elif cvd_15m > abs(config.UNICORN_CVD15M_BLOCK): prob += self.W_CVD15M_BLOCK
            
        if prob <= 0: return 0.0

        ob = ctx["ob_touch"]
        if ob["touching"]:
            if direction == "LONG"  and ob["type"] == "bullish": prob += self.W_OB_TOUCH
            if direction == "SHORT" and ob["type"] == "bearish": prob += self.W_OB_TOUCH
        fvg = ctx["fvg_1m"]
        if direction == "LONG"  and fvg["bisi"]: prob += self.W_FVG_NEAR
        if direction == "SHORT" and fvg["sibi"]: prob += self.W_FVG_NEAR

        if direction == "LONG"  and eqh_eql["eql_swept"]: prob += self.W_EQL_SWEPT
        if direction == "SHORT" and eqh_eql["eqh_swept"]: prob += self.W_EQH_SWEPT

        t1h  = ctx["trend_1h"]
        t15m = ctx["trend_15m"]
        if direction == "LONG":
            if t1h  == "BULLISH": prob += self.W_TREND_1H
            elif t1h == "BEARISH": prob += self.W_TREND_CONTRA
            if t15m == "BULLISH": prob += self.W_TREND_15M
        else:
            if t1h  == "BEARISH": prob += self.W_TREND_1H
            elif t1h == "BULLISH": prob += self.W_TREND_CONTRA
            if t15m == "BEARISH": prob += self.W_TREND_15M

        # ── REFACTORIZACIÓN CONFIG (Flujo Micro CVD) ──
        cvd_1m = c1m.get("cvd", 0) or 0
        if direction == "LONG":
            if cvd_1m  > (config.CVD_1M_CONTRA_THRESHOLD / 1.5): prob += self.W_CVD1M_OK
            elif cvd_1m < config.CVD_1M_CONTRA_THRESHOLD:        prob += self.W_CVD1M_CONTRA
        else:
            if cvd_1m  < abs(config.CVD_1M_CONTRA_THRESHOLD / 1.5): prob += self.W_CVD1M_OK
            elif cvd_1m > abs(config.CVD_1M_CONTRA_THRESHOLD):      prob += self.W_CVD1M_CONTRA

        # ── REFACTORIZACIÓN CONFIG (RSI Extremo) ──
        rsi = c1m.get("rsi", 50) or 50
        rsi_extreme_ob = 100 - config.UNICORN_RSI_EXTREME
        if direction == "LONG"  and rsi < config.UNICORN_RSI_EXTREME: prob += self.W_RSI_EXTREME
        if direction == "SHORT" and rsi > rsi_extreme_ob:             prob += self.W_RSI_EXTREME

        return max(0.0, min(prob, 100.0))