from __future__ import annotations
import time
from typing import Optional
import configs.btc_usdt_config as config
from core.interfaces.base_oracle import BaseOracle
from domain.models import MarketContext
from domain.trading import Signal


class UnicornOracle(BaseOracle):
    def __init__(self):
        self.BASE_CHOCH     = 40.0
        self.BASE_SFP_EQL   = 35.0
        self.BASE_SFP_BASIC = 28.0
        self.W_PD_BOTH_TF   =  20.0
        self.W_PD_ONE_TF    =  10.0
        self.W_PD_ADVERSE   = -15.0
        self.W_OB_TOUCH     =  12.0
        self.W_FVG_NEAR     =   8.0
        self.W_EQL_SWEPT    =   8.0
        self.W_EQH_SWEPT    =   8.0
        self.W_TREND_1H     =  10.0
        self.W_TREND_15M    =   5.0
        self.W_TREND_CONTRA =  -8.0
        self.W_CVD15M_OK    =   8.0
        self.W_CVD15M_BLOCK = -20.0
        self.W_CVD1M_OK     =   5.0
        self.W_CVD1M_CONTRA = -15.0
        self.W_RSI_EXTREME  =   7.0

    @property
    def name(self) -> str:
        return "unicorn"

    @property
    def tier(self) -> str:
        return "UNICORN"

    def probability(self, c1m, c15m, c1h, direction, ctx):
        has_choch   = (ctx.bos_choch.choch and
                       ctx.bos_choch.direction == ("BULL" if direction == "LONG" else "BEAR"))
        has_sfp_eql = (direction == "LONG"  and ctx.sweep.sweep and
                       ctx.sweep.direction == "BULL" and ctx.eqh_eql.eql_swept)
        has_sfp_eqh = (direction == "SHORT" and ctx.sweep.sweep and
                       ctx.sweep.direction == "BEAR" and ctx.eqh_eql.eqh_swept)
        has_sfp     = (ctx.sweep.sweep and
                       ctx.sweep.direction == ("BULL" if direction == "LONG" else "BEAR"))

        if not (has_choch or has_sfp_eql or has_sfp_eqh or has_sfp):
            return 0.0

        prob = (self.BASE_CHOCH if has_choch
                else self.BASE_SFP_EQL if (has_sfp_eql or has_sfp_eqh)
                else self.BASE_SFP_BASIC)

        pd_ok_15m = ((direction == "LONG"  and ctx.zone_15m == "DISCOUNT") or
                     (direction == "SHORT" and ctx.zone_15m == "PREMIUM"))
        pd_ok_1h  = ((direction == "LONG"  and ctx.zone_1h  == "DISCOUNT") or
                     (direction == "SHORT" and ctx.zone_1h  == "PREMIUM"))

        if pd_ok_15m and pd_ok_1h: prob += self.W_PD_BOTH_TF
        elif pd_ok_15m:            prob += self.W_PD_ONE_TF
        else:                      prob += self.W_PD_ADVERSE

        cvd_15m = c15m.get("cvd", 0) or 0
        if direction == "LONG":
            if cvd_15m > getattr(config, "UNICORN_CVD15M_ALIGNED", -48000):  prob += self.W_CVD15M_OK
            elif cvd_15m < getattr(config, "UNICORN_CVD15M_BLOCK",  -60000): prob += self.W_CVD15M_BLOCK
        else:
            if cvd_15m < abs(getattr(config, "UNICORN_CVD15M_ALIGNED", -48000)):  prob += self.W_CVD15M_OK
            elif cvd_15m > abs(getattr(config, "UNICORN_CVD15M_BLOCK",  -60000)): prob += self.W_CVD15M_BLOCK

        if prob <= 0:
            return 0.0

        if ctx.ob_touch.touching:
            if direction == "LONG"  and ctx.ob_touch.type == "bullish": prob += self.W_OB_TOUCH
            if direction == "SHORT" and ctx.ob_touch.type == "bearish": prob += self.W_OB_TOUCH

        if direction == "LONG"  and ctx.fvg_1m.bisi: prob += self.W_FVG_NEAR
        if direction == "SHORT" and ctx.fvg_1m.sibi: prob += self.W_FVG_NEAR

        if direction == "LONG"  and ctx.eqh_eql.eql_swept: prob += self.W_EQL_SWEPT
        if direction == "SHORT" and ctx.eqh_eql.eqh_swept: prob += self.W_EQH_SWEPT

        if direction == "LONG":
            if ctx.trend_1h  == "BULLISH":  prob += self.W_TREND_1H
            elif ctx.trend_1h == "BEARISH": prob += self.W_TREND_CONTRA
            if ctx.trend_15m == "BULLISH":  prob += self.W_TREND_15M
        else:
            if ctx.trend_1h  == "BEARISH":  prob += self.W_TREND_1H
            elif ctx.trend_1h == "BULLISH": prob += self.W_TREND_CONTRA
            if ctx.trend_15m == "BEARISH":  prob += self.W_TREND_15M

        cvd_1m       = c1m.get("cvd", 0) or 0
        cvd1m_thresh = getattr(config, "CVD_1M_CONTRA_THRESHOLD", -15000)
        if direction == "LONG":
            if cvd_1m  > (cvd1m_thresh / 1.5): prob += self.W_CVD1M_OK
            elif cvd_1m < cvd1m_thresh:         prob += self.W_CVD1M_CONTRA
        else:
            if cvd_1m  < abs(cvd1m_thresh / 1.5): prob += self.W_CVD1M_OK
            elif cvd_1m > abs(cvd1m_thresh):       prob += self.W_CVD1M_CONTRA

        rsi            = c1m.get("rsi", 50) or 50
        rsi_extreme_ob = 100 - getattr(config, "UNICORN_RSI_EXTREME", 30)
        if direction == "LONG"  and rsi < getattr(config, "UNICORN_RSI_EXTREME", 30): prob += self.W_RSI_EXTREME
        if direction == "SHORT" and rsi > rsi_extreme_ob:                              prob += self.W_RSI_EXTREME

        return max(0.0, min(prob, 100.0))

    def evaluate(self, data):
        c1m, c15m, c1h = self._extract_candles(data)
        if not c1m or not c15m or not c1h:
            return None

        direction = data["direction"]
        ctx       = data["ctx"]
        barriers  = data["barriers"]
        entry_p   = data["entry_p"]

        if ctx.trend_15m not in ("BULLISH", "BEARISH"):
            return None

        prob = self.probability(c1m, c15m, c1h, direction, ctx)

        if prob >= barriers.prob_min:
            from core.risk_manager import enrich_barriers_with_tier
            if enrich_barriers_with_tier(barriers, prob, direction, entry_p):
                ts = c1m.get("timestamp")
                if isinstance(ts, int):
                    timestamp_ms = ts
                elif hasattr(ts, "timestamp"):
                    timestamp_ms = int(ts.timestamp() * 1000)
                else:
                    timestamp_ms = int(time.time() * 1000)

                return Signal(
                    asset="BTC/USDT",
                    direction=direction,
                    entry_price=entry_p,
                    sl_price=barriers.sl,
                    tp_price=barriers.tp,
                    tier=self.tier,
                    prob=prob,
                    timestamp=timestamp_ms,
                )
        return None