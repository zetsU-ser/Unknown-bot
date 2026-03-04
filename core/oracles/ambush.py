from __future__ import annotations
from typing import Optional
import configs.btc_usdt_config as config
from core.interfaces.base_oracle import BaseOracle
from domain.models import MarketContext
from domain.trading import Signal
import logging

class AmbushOracle(BaseOracle):
    """
    Tier 2 -- Tendencia confirmada + confluencia SMC.
    Habitat: SOLO en tendencia (BULLISH o BEARISH). Retorna None en RANGING.
    Umbral: AMBUSH_PROB_MIN (55%).
    """

    def __init__(self):
        self.W_ZONE_FAVOR      =  15.0
        self.W_ZONE_HOSTIL     = -12.0
        self.W_SWEEP           =  15.0
        self.W_OB_TOUCH        =  12.0
        self.W_FVG_NEAR        =   7.0
        self.W_RSI             =   8.0
        self.W_VWAP_NEAR       =  10.0
        self.W_VWAP_FAR        =  -8.0
        self.W_CVD1M_ALIGNED   =   8.0
        self.W_CVD1M_CONTRA    = -14.0
        self.W_CVD15M_ALIGNED  =   8.0
        self.W_CVD15M_CONTRA   = -12.0
        self.W_ADX1H_HIGH      = -12.0
        self.W_ATR15M_HIGH     =  -8.0
        self.W_EMA1H_EXTEND    = -10.0

    @property
    def name(self) -> str:
        return "ambush"

    @property
    def tier(self) -> str:
        return "AMBUSH"

    def probability(
        self,
        c1m:       dict,
        c15m:      dict,
        c1h:       dict,
        direction: str,
        ctx:       MarketContext,
    ) -> float:
        prob   = ctx.priors.get(direction, 30.0)
        curr_p = c15m.get("close", 1) or 1

        zone = ctx.zone_15m
        if direction == "LONG":
            if zone == "DISCOUNT":   prob += self.W_ZONE_FAVOR
            elif zone == "PREMIUM":  prob += self.W_ZONE_HOSTIL
        else:
            if zone == "PREMIUM":    prob += self.W_ZONE_FAVOR
            elif zone == "DISCOUNT": prob += self.W_ZONE_HOSTIL

        if ctx.sweep.sweep:
            if direction == "LONG"  and ctx.sweep.direction == "BULL": prob += self.W_SWEEP
            if direction == "SHORT" and ctx.sweep.direction == "BEAR": prob += self.W_SWEEP

        if ctx.ob_touch.touching:
            if direction == "LONG"  and ctx.ob_touch.type == "bullish": prob += self.W_OB_TOUCH
            if direction == "SHORT" and ctx.ob_touch.type == "bearish": prob += self.W_OB_TOUCH

        if direction == "LONG"  and ctx.fvg_1m.bisi: prob += self.W_FVG_NEAR
        if direction == "SHORT" and ctx.fvg_1m.sibi: prob += self.W_FVG_NEAR

        vwap_1m  = c1m.get("vwap", curr_p) or curr_p
        dist_pct = abs(curr_p - vwap_1m) / max(vwap_1m, 1)
        if dist_pct < 0.0025:   prob += self.W_VWAP_NEAR
        elif dist_pct > 0.0040: prob += self.W_VWAP_FAR

        rsi    = c1m.get("rsi", 50) or 50
        rsi_ob = 100 - getattr(config, "RSI_TREND_MIN", 45)
        if direction == "LONG"  and rsi < getattr(config, "RSI_TREND_MIN", 45): prob += self.W_RSI
        if direction == "SHORT" and rsi > rsi_ob:                                prob += self.W_RSI

        cvd_1m       = c1m.get("cvd", 0) or 0
        cvd1m_thresh = getattr(config, "CVD_1M_CONTRA_THRESHOLD", -15000)
        if direction == "LONG":
            if cvd_1m  > (cvd1m_thresh / 2):    prob += self.W_CVD1M_ALIGNED
            elif cvd_1m < cvd1m_thresh:          prob += self.W_CVD1M_CONTRA
        else:
            if cvd_1m  < abs(cvd1m_thresh / 2): prob += self.W_CVD1M_ALIGNED
            elif cvd_1m > abs(cvd1m_thresh):     prob += self.W_CVD1M_CONTRA

        cvd_15m           = c15m.get("cvd", 0) or 0
        cvd15m_long_block = getattr(config, "CVD_15M_LONG_BLOCK",    -55000)
        cvd15m_short_supp = getattr(config, "CVD_15M_SHORT_SUPPORT", -40000)
        if direction == "LONG":
            if cvd_15m  > cvd15m_short_supp:         prob += self.W_CVD15M_ALIGNED
            elif cvd_15m < cvd15m_long_block:         prob += self.W_CVD15M_CONTRA
        else:
            if cvd_15m  < abs(cvd15m_long_block):     prob += self.W_CVD15M_ALIGNED
            elif cvd_15m > abs(cvd15m_short_supp):    prob += self.W_CVD15M_CONTRA

        if (c1h.get("adx", 20) or 20) > getattr(config, "ADX_STRONG", 25):
            prob += self.W_ADX1H_HIGH

        atr_15m     = c15m.get("atr", 0) or 0
        atr_max_pct = getattr(config, "ATR_15M_MAX_PCT", 0.0035)
        if (atr_15m / curr_p) > atr_max_pct:
            prob += self.W_ATR15M_HIGH

        ema_dist = c1h.get("ema_dist", None)
        if ema_dist is None:
            ema_dist = c1h.get("ema_trend_dist", 0) or 0
        if (ema_dist or 0) < getattr(config, "EMA_DIST_1H_EXTEND_PCT", -0.0055):
            prob += self.W_EMA1H_EXTEND

        return max(0.0, min(prob, 100.0))

    def evaluate(self, data: dict) -> Optional[Signal]:
        c1m, c15m, c1h = self._extract_candles(data)
        if not c1m or not c15m or not c1h:
            return None

        direction = data["direction"]
        ctx: MarketContext = data["ctx"]
        barriers  = data["barriers"]
        entry_p   = data["entry_p"]

        # Habitat: Ambush solo opera en tendencia confirmada
        if ctx.trend_15m not in ("BULLISH", "BEARISH"):
            return None

        prob = self.probability(c1m, c15m, c1h, direction, ctx)

        if prob >= barriers.prob_min:
            from core.risk_manager import enrich_barriers_with_tier
            if enrich_barriers_with_tier(barriers, prob, direction, entry_p):
                ts = c1m.get("timestamp")
                
                # AUDITORIA: Mismo fix general, sin fallas de Polars datetimes.
                if isinstance(ts, (int, float)):
                    timestamp_ms = int(ts)
                elif hasattr(ts, "timestamp"):
                    timestamp_ms = int(ts.timestamp() * 1000)
                else:
                    import time
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