from __future__ import annotations

import math
from typing import Optional

import configs.btc_usdt_config as config
from analysis.market_structure import get_full_market_ctx
from core.oracles.ambush import AmbushOracle
from core.oracles.scout import ScoutOracle
from core.oracles.unicorn import UnicornOracle
from core.risk_manager import compute_barriers
from domain.trading import Signal
from domain.models import MarketContext, BarrierSet


class StrategyManager:
    """Orquestador optimizado, alineado con Pydantic y Fail-Fast."""

    def __init__(self):
        self.oracles = [
            UnicornOracle(),
            AmbushOracle(),
            ScoutOracle(),
        ]
        self.unicorn = self.oracles[0]
        self.ambush  = self.oracles[1]
        self.scout   = self.oracles[2]

    def evaluate_signal(self, c1m, c15m, c1h, direction, ctx, rr):
        """Legacy router."""
        trend_15m = ctx.trend_15m if isinstance(ctx, MarketContext) else ctx.get("trend_15m", "RANGING")

        if trend_15m in ["BULLISH", "BEARISH"]:
            if rr >= config.UNICORN_RR_MIN:
                u_prob = self.unicorn.probability(c1m, c15m, c1h, direction, ctx)
                if u_prob >= config.UNICORN_PROB_MIN:
                    return "UNICORN", u_prob

            if rr >= config.AMBUSH_RR_MIN:
                a_prob = self.ambush.probability(c1m, c15m, c1h, direction, ctx)
                if a_prob >= config.AMBUSH_PROB_MIN:
                    return "AMBUSH", a_prob

        if rr >= config.SCOUT_RR_MIN:
            s_prob = self.scout.probability(c1m, c15m, c1h, direction, ctx)
            if s_prob >= config.SCOUT_PROB_MIN:
                return "SCOUT", s_prob

        return None, 0.0

    def evaluate_all(self, data: dict) -> Optional[Signal]:
        slice_1m  = data.get("1m")
        slice_15m = data.get("15m")
        slice_1h  = data.get("1h")

        if slice_1m is None or slice_15m is None or slice_1h is None:
            return None

        if len(slice_1m) < 100 or len(slice_15m) < 30:
            return None

        c1m  = {col: slice_1m[col][-1]  for col in slice_1m.columns}
        c15m = {col: slice_15m[col][-1] for col in slice_15m.columns}
        c1h  = {col: slice_1h[col][-1]  for col in slice_1h.columns}

        ema_trend = c1h.get("ema_trend", 0.0)
        entry_p   = c1m.get("close", 0) or 0

        if ema_trend is None or ema_trend == 0.0 or math.isnan(float(ema_trend)):
            return None

        ema_trend_f = float(ema_trend)
        direction = "LONG" if entry_p > ema_trend_f else "SHORT"

        raw_ctx = get_full_market_ctx(slice_1m, slice_15m, slice_1h)
        if raw_ctx is None:
            return None

        ctx = _build_market_context(raw_ctx)

        atr_15m = c15m.get("atr") or 0
        barriers: Optional[BarrierSet] = compute_barriers(
            entry_price=entry_p,
            atr_15m=atr_15m,
            direction=direction,
            nearest_res=ctx.levels.nearest_resistance,
            nearest_sup=ctx.levels.nearest_support,
        )

        if barriers is None:
            return None

        data["direction"] = direction
        data["ctx"]       = ctx
        data["barriers"]  = barriers
        data["entry_p"]   = entry_p

        for oracle in self.oracles:
            sig = oracle.evaluate(data)
            if sig is not None:
                return sig

        return None


def _build_market_context(raw: dict) -> MarketContext:
    """Capa Anticorrupción: Transforma el dict crudo al modelo Pydantic seguro."""
    from domain.models import SweepInfo, BosChochInfo, FVGZones, OBTouch, EqhEqlInfo, KeyLevels

    sw  = raw.get("sweep",     {})
    boc = raw.get("bos_choch", {})
    fvg = raw.get("fvg_1m",    {})
    obt = raw.get("ob_touch",  {})
    eql = raw.get("eqh_eql",   {})
    lev = raw.get("levels",    {})

    return MarketContext(
        trend_15m = raw.get("trend_15m", "RANGING"),
        zone_15m  = raw.get("zone_15m",  "EQUILIBRIUM"),
        trend_1h  = raw.get("trend_1h",  "RANGING"),
        zone_1h   = raw.get("zone_1h",   "EQUILIBRIUM"),
        priors    = raw.get("priors",    {"LONG": 30.0, "SHORT": 30.0}),
        sweep     = SweepInfo(
            sweep      = sw.get("sweep", False),
            direction  = sw.get("direction"),
            level      = sw.get("level"),
            sweep_size = sw.get("sweep_size"),
        ),
        bos_choch = BosChochInfo(
            bos        = boc.get("bos",        False),
            choch      = boc.get("choch",      False),
            direction  = boc.get("direction"),
            bos_bull   = boc.get("bos_bull",   False),
            bos_bear   = boc.get("bos_bear",   False),
            choch_bull = boc.get("choch_bull", False),
            choch_bear = boc.get("choch_bear", False),
        ),
        fvg_1m    = FVGZones(
            bisi = fvg.get("bisi", []),
            sibi = fvg.get("sibi", []),
        ),
        ob_touch  = OBTouch(
            touching = obt.get("touching", False),
            type     = obt.get("type"),
            ob       = obt.get("ob"),
            dist_pct = obt.get("dist_pct", 1.0),
        ),
        eqh_eql   = EqhEqlInfo(
            eqh         = eql.get("eqh",         []),
            eql         = eql.get("eql",         []),
            eqh_swept   = eql.get("eqh_swept",   False),
            eql_swept   = eql.get("eql_swept",   False),
            nearest_eqh = eql.get("nearest_eqh"),
            nearest_eql = eql.get("nearest_eql"),
        ),
        levels    = KeyLevels(
            nearest_resistance = lev.get("nearest_resistance"),
            nearest_support    = lev.get("nearest_support"),
            bullish_obs        = lev.get("bullish_obs", []),
            bearish_obs        = lev.get("bearish_obs", []),
        ),
    )