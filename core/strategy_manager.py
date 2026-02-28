import configs.btc_usdt_config as config
from core.oracles.scout import ScoutOracle
from core.oracles.ambush import AmbushOracle
from core.oracles.unicorn import UnicornOracle

class StrategyManager:
    def __init__(self):
        self.scout   = ScoutOracle()
        self.ambush  = AmbushOracle()
        self.unicorn = UnicornOracle()

    def evaluate_signal(self, c1m, c15m, c1h, direction, ctx, rr):
        """
        El Director Técnico: Enruta la decisión según el Régimen de Mercado.
        Retorna el (tier, probabilidad) si encuentra un setup válido.
        """
        trend_15m = ctx.get("trend_15m", "RANGING")
        
        # ── 1. MERCADO EN TENDENCIA (Hábitat de Unicornio y Ambush) ──
        if trend_15m in ["BULLISH", "BEARISH"]:
            # Prioridad Absoluta: El setup perfecto
            if rr >= config.UNICORN_RR_MIN:
                u_prob = self.unicorn.probability(c1m, c15m, c1h, direction, ctx)
                if u_prob >= config.UNICORN_PROB_MIN:
                    return "UNICORN", u_prob
            
            # Segunda Opción: Continuación de tendencia
            if rr >= config.AMBUSH_RR_MIN:
                a_prob = self.ambush.probability(c1m, c15m, c1h, direction, ctx)
                if a_prob >= config.AMBUSH_PROB_MIN:
                    return "AMBUSH", a_prob

        # ── 2. MERCADO LATERAL O FALLO DE TENDENCIA (Hábitat de Scout) ──
        # Si el mercado está en RANGING, o si estando en tendencia no se 
        # formaron setups institucionales, mandamos a Scout a buscar barridos.
        if rr >= config.SCOUT_RR_MIN:
            s_prob = self.scout.probability(c1m, c15m, c1h, direction, ctx)
            if s_prob >= config.SCOUT_PROB_MIN:
                return "SCOUT", s_prob

        # Si nadie encontró nada bueno, no operamos.
        return None, 0.0