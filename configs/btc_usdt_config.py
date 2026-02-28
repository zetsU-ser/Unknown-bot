import os

# ── RUTAS Y LOGGING ──────────────────────────────────────────────────────────
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot_activity.log")

# ── INFRAESTRUCTURA DE DATOS ──────────────────────────────────────────────────
DB_USER = "admin"
DB_PASS = "unknown_vault"
DB_NAME = "market_high_freq"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_URL  = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ── MARCO DE TRABAJO ──────────────────────────────────────────────────────────
SYMBOL         = "BTC/USDT"
EXCHANGE_ID    = "binance"
TF_SNIPER      = "1m"
TF_STRUCTURE   = "15m"
TF_MACRO       = "1h"
CANDLE_LIMIT   = 600   # Barras 1m cargadas en el loop en vivo

# ── INDICADORES TÉCNICOS ─────────────────────────────────────────────────────
EMA_FAST        = 9
EMA_SLOW        = 21
EMA_TREND       = 200
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ZSCORE_LOOKBACK = 50

# ── ESTRUCTURA DE MERCADO (Bloque 1) ──────────────────────────────────────────
SWING_LOOKBACK     = 5
STRUCTURE_LOOKBACK = 20

# ── GATILLOS DE ENTRADA ──────────────────────────────────────────────────────
RSI_OVERSOLD        = 35
RSI_TREND_MIN       = 45
ENTRY_SCORE_MIN     = 2
TRADE_COOLDOWN_BARS = 20

# ── FILTROS DE CALIDAD ────────────────────────────────────────────────────────
ATR_NOISE_MAX   = 0.45
ADX_MIN_TREND   = 15
ADX_STRONG      = 25

# ── TRIPLE BARRIER ────────────────────────────────────────────────────────────
USE_STRUCTURE_LEVELS = True
ATR_SL_MULT          = 1.90   # V10.7: recover avg_win; 1.55→1.75 compromiso
ATR_TP_MULT          = 0.65

# ══════════════════════════════════════════════════════════════════════════════
# ── TIER SYSTEM V10.2 (Tier = f(probabilidad)) ───────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
SCOUT_RR_MIN    = 1.50
SCOUT_RR_MAX    = 1.75
AMBUSH_RR_MIN   = 1.76
AMBUSH_RR_MAX   = 2.49
UNICORN_RR_MIN  = 2.50
UNICORN_RR_MAX  = 5.00
RR_MIN_REQUIRED = SCOUT_RR_MIN

SCOUT_PROB_MIN  = 66.75
AMBUSH_PROB_MIN = 81.75
UNICORN_PROB_MIN= 89.95

SCOUT_MULT   = 1.0
AMBUSH_MULT  = 1.25
UNICORN_MULT = 3.0

SCOUT_BE_THRESHOLD  = 0.77
AMBUSH_BE_THRESHOLD  = 0.75
UNICORN_BE_THRESHOLD = 0.95

SCOUT_PROFIT_LOCK   = 0.00
AMBUSH_PROFIT_LOCK  = 0.00
UNICORN_PROFIT_LOCK = 0.00

SCOUT_MAX_BARS   = 240
AMBUSH_MAX_BARS  = 360
UNICORN_MAX_BARS = 720

BE_DYNAMIC_THRESHOLD = AMBUSH_BE_THRESHOLD
PROFIT_LOCK_FRACTION = AMBUSH_PROFIT_LOCK
MAX_TRADE_BARS       = AMBUSH_MAX_BARS

# ── GESTIÓN DE RIESGO ─────────────────────────────────────────────────────────
INITIAL_CASH       = 10000.0
RISK_PER_TRADE_PCT = 0.02
LEVERAGE           = 20        # Apalancamiento institucional (20x)
KELLY_FRACTION     = 0.30
MAX_DRAWDOWN_HALT  = 0.12
DRAWDOWN_REDUCE_1  = 0.04
DRAWDOWN_REDUCE_2  = 0.08

STOP_LOSS_PCT = 0.02   # legacy

# ── V10.9: PARÁMETROS DE SEÑALES SMC (calibrados por Módulo 8) ───────────────
# CVD_1m: umbral institucional micro
CVD_1M_CONTRA_THRESHOLD  = -15_000  # LONG + cvd_1m < -15k → presión vendedora

# CVD_15m: umbral flujo institucional macro (NUEVA SEÑAL V10.9)
# WIN=-48,305 vs LOSS=-60,527 → umbral -55,000
CVD_15M_LONG_BLOCK     = -55_000   # LONG bloqueado si presión macro muy negativa
CVD_15M_SHORT_SUPPORT  = -40_000   # SHORT sin soporte si CVD_15m > -40k

# EMA_dist_1h: Rubber Band Effect (Bloque 3) (NUEVA SEÑAL V10.9)
# WIN=-0.444% vs LOSS=-0.672% → umbral -0.55%
EMA_DIST_1H_EXTEND_PCT = -0.0055   # precio muy lejos bajo la EMA 1h → penalizar

# ATR_15m: umbral de ruido de mercado (V10.7)
ATR_15M_NOISE_MAX      = 270       # ATR_15m > 270 → mercado volátil

# Vol ratio spike (V10.7)
VOL_RATIO_SPIKE_MAX    = 2.0       # vol_ratio > 2.0 → momentum agotado

# ── V10.9: PARÁMETROS EXCLUSIVOS UNICORN ─────────────────────────────────────
# Unicorn ahora tiene precondiciones OBLIGATORIAS propias (CHoCH / EQH/EQL swept)
# Cambios aquí NO afectan Scout ni Ambush.
UNICORN_CVD15M_BLOCK   = -60_000   # Bloqueo si CVD_15m extremo negativo (LONG)
UNICORN_CVD15M_ALIGNED = -48_000   # CVD_15m "alineado" si > este umbral (LONG)
UNICORN_RSI_EXTREME    = 30        # RSI < 30 para LONG = oversold extremo Unicorn
UNICORN_OB_TOLERANCE   = 0.003     # 0.3% de tolerancia para OB proximity

# ── V10.9: PARÁMETROS SMC (market_structure.py) ──────────────────────────────
FVG_LOOKBACK_1M        = 30        # Barras para detectar FVG en 1m
FVG_LOOKBACK_15M       = 50        # Barras para detectar FVG en 15m
OB_LOOKBACK            = 100       # Barras para buscar Order Blocks
EQH_EQL_LOOKBACK       = 80        # Barras para Equal Highs/Lows
EQH_EQL_TOLERANCE_PCT  = 0.002     # 0.2% tolerancia para EQH/EQL
BOS_CHOCH_LOOKBACK     = 40        # Barras para BOS/CHoCH en 1m