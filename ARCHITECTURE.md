# ARCHITECTURE.md — Zetzu Hunt V10.2
> Biblia tecnica del repositorio. Documento vivo: actualizar con cada version mayor.

---

## 1. Vision del Sistema

Zetzu Hunt es un motor de trading algoritmico cuantitativo para BTC/USDT.
Su arquitectura esta disenada alrededor de tres principios:

- **Fail-Fast sobre Fail-Silent.** Si falta un dato critico, el sistema lanza
  excepcion antes de ejecutar. Nunca opera con informacion corrupta.
- **Contratos, no diccionarios.** Todos los datos que cruzan fronteras de modulo
  viajan como modelos Pydantic (MarketContext, BarrierSet, TradeState).
- **Event-Driven por diseno.** Ninguna capa llama directamente a otra. Todo se
  comunica a traves del EventBus, lo que permite sustituir cualquier componente
  sin romper el resto.

---

## 2. Flujo Event-Driven (el viaje de una senal)

```
PostgreSQL
    |
    v
load_and_sync_data()          <- Backtester / Ingestor en vivo
    |  df_1m, df_15m, df_1h, df_4h, df_1d
    v
MTFDataEvent  -->  EventBus
                      |
                      v
              DecisionEngine.handle_mtf_data()
                      |
                      v
              StrategyManager.evaluate_all()
                 |
                 |-- 1. Extraccion O(1) de ultima vela (c1m, c15m, c1h)
                 |-- 2. Direction: LONG si close > EMA_200(1h)
                 |-- 3. get_full_market_ctx()  -> MarketContext (inmutable)
                 |-- 4. compute_barriers()     -> BarrierSet    (mutable)
                 |-- 5. UnicornOracle.evaluate(data)  -> Signal o None
                 |-- 6. AmbushOracle.evaluate(data)   -> Signal o None
                 |-- 7. ScoutOracle.evaluate(data)    -> Signal o None
                      |
                      v  (si Signal != None)
              SignalEvent  -->  EventBus
                      |
                      v
              _SignalCollector.last_signal   (en backtest)
              OMS.handle_signal()            (en produccion live)
```

**Nota sobre el FIX V10.2:** Pydantic v2 hace una copia del dict al construir
MTFDataEvent. Por eso el backtester NO lee `data_payload["barriers"]` sino que
reconstruye `barriers` directamente desde `Signal.sl_price / tp_price / entry_price`.

---

## 3. Estructura de Directorios

```
Unknown-bot/
|-- analysis/
|   |-- indicators/         # ATR, RSI, ADX, EMA, Z-Score, Vol-Ratio, VWAP
|   |-- liquidity/
|   |   |-- fvg.py          # Fair Value Gaps (BISI / SIBI)
|   |   |-- levels.py       # Order Blocks y niveles clave
|   |   +-- pools.py        # EQH/EQL y Liquidity Sweeps
|   |-- structure/
|   |   |-- breaks.py       # BOS / CHoCH
|   |   |-- fractals.py     # Swing Highs/Lows (scipy + numpy fallback)
|   |   +-- trend.py        # Regimen (BULLISH/BEARISH/RANGING) y zona P/D
|   |-- market_structure.py # Orquestador: get_full_market_ctx()
|   +-- volume_profile.py   # CVD (Cumulative Volume Delta)
|
|-- configs/
|   +-- btc_usdt_config.py  # TODOS los hiperparametros. Un solo archivo.
|
|-- core/
|   |-- decision_engine.py  # Suscriptor MTFDataEvent -> publica SignalEvent
|   |-- strategy_manager.py # Orquesta los 3 oraculos y computa ctx/barriers
|   |-- risk_manager.py     # compute_barriers(), evaluate_exit(), Kelly
|   |-- interfaces/
|   |   +-- base_oracle.py  # ABC: contrato que todos los oraculos deben cumplir
|   +-- oracles/
|       |-- scout.py        # Tier 1: alta frecuencia, menor conviccion
|       |-- ambush.py       # Tier 2: tendencia confirmada + OB touch
|       +-- unicorn.py      # Tier 3: CHoCH o SFP sobre EQL/EQH
|
|-- domain/
|   |-- models.py           # Contratos Pydantic: MarketContext, BarrierSet, TradeState
|   |-- trading.py          # Signal, Order, Position
|   +-- events.py           # MTFDataEvent, SignalEvent, OrderEvent
|
|-- engine/
|   +-- event_bus.py        # Pub/Sub sincrono. El sistema nervioso del bot.
|
|-- research/
|   |-- btc_backtester.py   # Motor de simulacion V10.2
|   |-- btc_forensics.py    # Analisis post-backtest con XGBoost
|   +-- blackbox.py         # Grabadora de ADN: captura 51 features por trade
|
+-- main.py                 # CLI: menu interactivo o argumentos directos
```

---

## 4. Los 3 Oraculos — Niveles de Conviccion

Cada oraculo es completamente independiente. Cambiar Scout no afecta a Ambush ni Unicorn.

| Oracle  | Prob Min | R:R Min | Be Threshold | Mult  | Habitat           |
|---------|----------|---------|--------------|-------|-------------------|
| Scout   | 45%      | 0.8     | 0.770        | 1.0x  | Cualquier regimen |
| Ambush  | 55%      | 1.0     | 0.698        | 1.25x | Solo tendencia    |
| Unicorn | 65%      | 1.2     | 0.950        | 3.0x  | Solo tendencia    |

**Unicorn** requiere CHoCH o SFP sobre EQL/EQH como precondicion obligatoria.
Sin ese trigger retorna `prob = 0.0` directamente.

La evaluacion es **Unicorn > Ambush > Scout** en orden de prioridad.
El primer oraculo que supera su umbral gana. No se acumulan senales.

---

## 5. Contratos Pydantic (Mision 1.1)

### MarketContext (inmutable)
Fotografia del mercado. Generada UNA vez por `get_full_market_ctx()`
y compartida entre los 3 oraculos sin recalcular.

```python
ctx.trend_15m            # "BULLISH" | "BEARISH" | "RANGING"
ctx.zone_15m             # "PREMIUM" | "DISCOUNT" | "EQUILIBRIUM"
ctx.sweep.sweep          # True si hubo Stop Hunt en la ultima vela 1m
ctx.sweep.direction      # "BULL" | "BEAR" | None
ctx.bos_choch.choch      # True si hay Change of Character en 1m
ctx.ob_touch.touching    # True si precio toca un Order Block
ctx.fvg_1m.bisi          # Lista de zonas Fair Value Gap bullish
ctx.eqh_eql.eql_swept    # True si se barrio una zona de Equal Lows
ctx.priors["LONG"]       # Probabilidad base segun tendencia (20/30/40)
```

### BarrierSet (mutable)
Niveles de riesgo. Creado por `compute_barriers()`, enriquecido
por `_apply_tier_to_barriers()` una vez que el oraculo elige el tier.

```python
b.sl             # Stop Loss price
b.tp             # Take Profit price
b.rr             # R:R calculado (reward / risk)
b.be_trigger     # Precio donde se activa el Break-Even
b.profit_lock_sl # SL de proteccion de ganancias
b.tier           # "SCOUT" | "AMBUSH" | "UNICORN"
b.mult           # Multiplicador de posicion por tier (1.0 / 1.25 / 3.0)
b.max_bars       # Duracion maxima del trade en velas 1m
```

### TradeState (mutable)
Reemplaza el dict `wallet`. Misma API con `.update({})`.

```python
wallet.active          # bool: hay trade abierto
wallet.buy_price       # float: precio de entrada
wallet.direction       # "LONG" | "SHORT"
wallet.barriers        # BarrierSet tipado (antes: dict)
wallet.be_on           # bool: break-even activado
wallet.bars_in_t       # int: velas desde la entrada
wallet.bayes_prob      # float: probabilidad de apertura
wallet.tier            # str: tier del trade activo
wallet.update({...})   # identico a dict.update()
```

---

## 6. Levantamiento del Entorno

### Requisitos
- Python >= 3.12
- PostgreSQL >= 14
- Poetry >= 2.0
- TA-Lib (libreria C, instalacion especial)

### Instalacion paso a paso

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd Unknown-bot

# 2. Instalar TA-Lib (debe ir ANTES de poetry install)
sudo apt-get install libta-lib-dev       # Ubuntu/Debian
# brew install ta-lib                    # macOS

# 3. Instalar dependencias Python
poetry install

# 4. Copiar y editar variables de entorno
cp .env.example .env
# Editar: DB_USER, DB_PASS, DB_HOST, DB_PORT, DISCORD_WEBHOOK

# 5. Crear la base de datos
psql -U postgres -f infra/setup_db.sql

# 6. Descargar datos historicos (primera vez, tarda ~10 min)
poetry run python -m main download
```

### Instalar comando del sistema (opcional)

```bash
bash instalar_zetsu.sh
# Luego usar simplemente: zetsu
```

### Comandos disponibles

```bash
zetsu              # Menu interactivo
zetsu backtest     # Backtest directo sin menu
zetsu live         # Modo produccion (requiere API keys de Binance)
zetsu download     # Descargar datos historicos
```

---

## 7. Blackbox — Diccionario de las 51 Variables

La Blackbox captura el estado completo del mercado en el instante de cada
entrada. El parquet resultante es el dataset de entrenamiento para MLOps.

### Identidad
| Variable      | Tipo   | Descripcion                                   |
|---------------|--------|-----------------------------------------------|
| trade_id      | int    | ID secuencial del trade                       |
| timestamp     | str    | Timestamp ISO 8601 de la vela 1m de entrada   |
| direction     | str    | "LONG" o "SHORT"                              |

### Geometria del Trade
| Variable             | Tipo  | Descripcion                                          |
|----------------------|-------|------------------------------------------------------|
| entry_price          | float | Precio de entrada                                    |
| sl                   | float | Stop Loss price                                      |
| tp                   | float | Take Profit price                                    |
| rr_expected          | float | R:R esperado: (tp - entry) / (entry - sl)            |
| risk_pct             | float | Riesgo en % respecto al precio de entrada            |
| be_trigger           | float | Precio absoluto donde se activa Break-Even           |
| be_trigger_dist_pct  | float | Distancia % entre entry y be_trigger                 |

### Motor Bayesiano
| Variable      | Tipo  | Descripcion                                              |
|---------------|-------|----------------------------------------------------------|
| prob_bayesian | float | Probabilidad [0-100] calculada por el oraculo ganador    |
| tier_mult     | float | Multiplicador de posicion del tier (1.0 / 1.25 / 3.0)   |

### Capa 1m — SNIPER (micro estructura)
| Variable         | Tipo  | Descripcion                                              |
|------------------|-------|----------------------------------------------------------|
| rsi_1m           | float | RSI(14). Extremos <35 o >65 como senales de agotamiento  |
| atr_1m           | float | ATR(14). Volatilidad tick-a-tick                         |
| adx_1m           | float | ADX(14). >25 indica tendencia fuerte en micro            |
| z_score_1m       | float | Z-Score(50) del precio. Desviaciones de la media movil   |
| vol_ratio_1m     | float | Volumen actual / promedio(50). >2.0 = pico anomalo       |
| cvd_1m           | float | Cumulative Volume Delta. Positivo = presion compradora   |
| vwap_dist_1m_pct | float | (close - VWAP) / VWAP * 100. Distancia al VWAP diario    |
| sweep_detected   | int   | 1 si hubo Stop Hunt en la ultima vela 1m, 0 si no        |
| sweep_direction  | int   | 1=BULL (barrio lows), -1=BEAR (barrio highs), 0=ninguno  |

### Capa 15m — STRUCTURE (estructura de mercado)
| Variable          | Tipo  | Descripcion                                              |
|-------------------|-------|----------------------------------------------------------|
| rsi_15m           | float | RSI(14) en 15m                                           |
| atr_15m           | float | ATR(14) en 15m. Base del calculo de SL dinamico          |
| adx_15m           | float | ADX(14) en 15m. >20 suma puntos en Scout                 |
| cvd_15m           | float | CVD en 15m. < -55,000 bloquea LONGs                      |
| vwap_dist_15m_pct | float | Distancia % al VWAP del timeframe 15m                    |
| trend_15m         | int   | 1=BULLISH, -1=BEARISH, 0=RANGING (codificado para ML)    |
| zone_15m          | int   | 1=PREMIUM, -1=DISCOUNT, 0=EQUILIBRIUM                    |
| trend_15m_raw     | str   | Valor literal del regimen ("BULLISH", etc.)              |
| zone_15m_raw      | str   | Valor literal de la zona ("PREMIUM", etc.)               |
| vol_divergence    | str   | "BULL_DIV" / "BEAR_DIV" / "NEUTRAL"                      |
| vol_divergence_num| int   | 1=BULL_DIV, -1=BEAR_DIV, 0=NEUTRAL                       |

### Capa 1h — MACRO (tendencia macro)
| Variable        | Tipo  | Descripcion                                              |
|-----------------|-------|----------------------------------------------------------|
| rsi_1h          | float | RSI(14) en 1h                                            |
| adx_1h          | float | ADX(14) en 1h. >28 penaliza todos los oraculos           |
| ema_trend_1h    | float | EMA(200) en 1h. Separador LONG/SHORT global              |
| ema_dist_1h_pct | float | (close - EMA200) / EMA200. Rubber Band Effect            |

### Capa 4h — SWING (techo de cristal)
| Variable        | Tipo  | Descripcion                                              |
|-----------------|-------|----------------------------------------------------------|
| rsi_4h          | float | RSI(14) en 4h                                            |
| atr_4h          | float | ATR(14) en 4h                                            |
| adx_4h          | float | ADX(14) en 4h                                            |
| ema_trend_4h    | float | EMA(200) en 4h                                           |
| ema_dist_4h_pct | float | Distancia % al EMA200 en 4h                              |

### Capa 1d — MACRO ANCHOR (el jefe final)
| Variable        | Tipo  | Descripcion                                              |
|-----------------|-------|----------------------------------------------------------|
| rsi_1d          | float | RSI(14) en 1d                                            |
| atr_1d          | float | ATR(14) en 1d                                            |
| adx_1d          | float | ADX(14) en 1d                                            |
| ema_trend_1d    | float | EMA(200) en 1d. Ancla macro absoluta                     |
| ema_dist_1d_pct | float | Distancia % al EMA200 en 1d                              |

### Labels de Salida (target para ML)
| Variable      | Tipo  | Descripcion                                              |
|---------------|-------|----------------------------------------------------------|
| outcome       | int   | 1 = trade ganador, 0 = trade perdedor                    |
| pnl_pct       | float | PnL en % sin apalancamiento. Positivo = ganancia         |
| exit_reason   | str   | "TP" / "SL" / "TIMEOUT" / "PROFIT_LOCK"                  |
| bars_in_trade | int   | Duracion del trade en velas 1m                           |
| rr_realized   | float | R:R realizado al cierre. >0 = ganancia, <0 = perdida     |

---

## 8. Hiperparametros Clave

Todos en `configs/btc_usdt_config.py`. Un solo archivo como fuente de verdad.

```python
# Probabilidades minimas por tier
SCOUT_PROB_MIN   = 45.0
AMBUSH_PROB_MIN  = 55.0
UNICORN_PROB_MIN = 65.0

# Riesgo por trade
ATR_SL_MULT         = 1.871   # Multiplicador ATR para SL dinamico
RR_MIN_REQUIRED     = 0.8     # R:R minimo global
RISK_PER_TRADE_PCT  = 0.02    # 2% del capital como base Kelly
KELLY_FRACTION      = 0.30    # Kelly fraccional
LEVERAGE            = 20      # Apalancamiento simulado
MAX_DRAWDOWN_HALT   = 0.12    # Detiene trading si DD > 12%

# Filtros de flujo institucional
CVD_15M_LONG_BLOCK      = -55_000   # Bloquea LONGs si CVD 15m < umbral
CVD_1M_CONTRA_THRESHOLD = -15_000   # Penaliza si CVD 1m es contrario
EMA_DIST_1H_EXTEND_PCT  = -0.0055   # Penaliza si precio muy lejos de EMA200
ATR_15M_MAX_PCT         = 0.0035    # ATR / precio > 0.35% = mercado ruidoso
```

---

## 9. Como agregar un nuevo Oraculo

```python
# 1. Crear core/oracles/sniper.py
from core.interfaces.base_oracle import BaseOracle
from domain.trading import Signal
from domain.models import MarketContext, BarrierSet
from typing import Optional
import configs.btc_usdt_config as config

class SniperOracle(BaseOracle):
    @property
    def name(self) -> str: return "sniper"

    @property
    def tier(self) -> str: return "SNIPER"

    def probability(self, c1m, c15m, c1h, direction, ctx: MarketContext) -> float:
        # Acceso tipado: ctx.sweep.sweep, ctx.bos_choch.choch, etc.
        return 0.0

    def evaluate(self, data: dict) -> Optional[Signal]:
        barriers: BarrierSet = data.get("barriers")
        if not barriers or barriers.rr < 1.5:
            return None
        c1m, c15m, c1h = self._extract_candles(data)
        prob = self.probability(c1m, c15m, c1h, data["direction"], data["ctx"])
        if prob < 70.0:
            return None
        # Construir y retornar Signal...

# 2. Registrar en StrategyManager.__init__()
self.oracles = [SniperOracle(), UnicornOracle(), AmbushOracle(), ScoutOracle()]
# No requiere ningun otro cambio. EventBus, backtester y risk_manager
# funcionan automaticamente con el nuevo oraculo.
```

---

## 10. Glosario SMC

| Termino  | Significado                                                           |
|----------|-----------------------------------------------------------------------|
| BOS      | Break of Structure. Confirmacion de continuacion de tendencia         |
| CHoCH    | Change of Character. Senal de posible reversion. Trigger de Unicorn   |
| OB       | Order Block. Zona donde institucionales colocaron ordenes grandes     |
| FVG      | Fair Value Gap (BISI/SIBI). Desequilibrio de precio sin relleno       |
| EQH/EQL  | Equal Highs / Equal Lows. Trampas de liquidez para retail             |
| SFP      | Swing Failure Pattern. Sweep falso de un nivel de liquidez            |
| Premium  | Zona por encima del 50% Fibonacci del rango. Zona de distribucion     |
| Discount | Zona por debajo del 50% Fibonacci del rango. Zona de acumulacion      |
| CVD      | Cumulative Volume Delta. Presion neta compradora vs vendedora         |
| VWAP     | Volume Weighted Average Price. Precio promedio ponderado por volumen  |
