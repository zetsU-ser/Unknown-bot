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

# ── MARCO DE TRABAJO (AGNOSTICO) ─────────────────────────────────────────────
SYMBOL         = "BTC/USDT"
TF_SNIPER      = "1m"
TF_STRUCTURE   = "15m"
TF_MACRO       = "1h"

# ── PARÁMETROS TÉCNICOS ──────────────────────────────────────────────────────
EMA_TREND       = 200
RSI_PERIOD      = 14
ATR_PERIOD      = 14
ZSCORE_LOOKBACK = 50
SWING_LOOKBACK  = 5

# ── GATILLOS DE ENTRADA ──────────────────────────────────────────────────────
RR_MIN_REQUIRED     = 1.5 
RSI_OVERSOLD        = 35
RSI_TREND_MIN       = 45
ENTRY_SCORE_MIN     = 2
TRADE_COOLDOWN_BARS = 20

# ── FILTROS DE CALIDAD (V5.5 AUDITED) ────────────────────────────────────────
ATR_NOISE_MAX   = 0.45  # Relación de volatilidad 1m/15m
ADX_MIN_TREND   = 15    # Filtro de mercado lateral
ADX_STRONG      = 25

# ── TRIPLE BARRIER (LA MATEMÁTICA DEL SET) ───────────────────────────────────
USE_STRUCTURE_LEVELS = True
ATR_SL_MULT          = 1.05  # Amplitud del Stop Loss
ATR_TP_MULT          = 0.65  # Target mínimo

# ── GESTIÓN DE SALIDAS DINÁMICAS ─────────────────────────────────────────────
BE_DYNAMIC_THRESHOLD = 0.80  # Activación de defensa al 65% del recorrido
PROFIT_LOCK_FRACTION = 0.25  # Asegurar 50% de la ganancia flotante
MAX_TRADE_BARS       = 360   # Timeout (6 horas)

# ── GESTIÓN DE RIESGO (MONEY MANAGEMENT) ─────────────────────────────────────
INITIAL_CASH       = 10000.0
RISK_PER_TRADE_PCT = 0.01
KELLY_FRACTION     = 0.50 #anteriormente 40
MAX_DRAWDOWN_HALT  = 0.12

DRAWDOWN_REDUCE_1  = 0.04   # Reduce posición al 75% si la cuenta cae 4%
DRAWDOWN_REDUCE_2  = 0.08   # Reduce posición a la mitad si la cuenta cae 8%