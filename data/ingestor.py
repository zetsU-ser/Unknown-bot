import json
import websocket
import datetime
import polars as pl
import requests
import sys
import io
from typing import Optional

# ── IMPORTACIONES LIMPIAS ────────────────────────────────────────────────────
import configs.btc_usdt_config as config
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features

from engine.event_bus import EventBus
from engine.orchestrator import ZetsuOrchestrator
from domain.events import MTFDataEvent, SignalEvent, OrderEvent
from domain.trading import Signal

# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET, MAGENTA = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m", "\033[95m"

# ── BUS / ORQUESTADOR (INYECCIÓN) ───────────────────────────────────────────
_orchestrator: Optional[ZetsuOrchestrator] = None
_bus: Optional[EventBus] = None

# Referencia al payload en evaluación (para leer barriers dentro de handlers)
_current_eval_data: Optional[dict] = None

# ── ESTADO GLOBAL DEL TABLERO TÁCTICO ────────────────────────────────────────
class DashboardState:
    start_time = datetime.datetime.now()
    candles_analyzed = 0
    trades_executed = 0
    current_price = 0.0
    last_close = 0.0
    last_reason = "Sincronizando con la Matrix..."
    is_first_render = True

state = DashboardState()

def render_dashboard():
    """Dibuja y actualiza el tablero táctico en la misma posición de la consola"""
    uptime = datetime.datetime.now() - state.start_time
    uptime_str = str(uptime).split('.')[0]
    reason_str = (state.last_reason[:42] + "...") if len(state.last_reason) > 45 else state.last_reason

    lines = [
        f"{CYAN}╔════════════════════════════════════════════════════════╗{RESET}",
        f"  🟢 {GREEN}ZETSU HUNT LIVE DASHBOARD{RESET}",
        f"{CYAN}╠════════════════════════════════════════════════════════╣{RESET}",
        f"  ⏱️  Tiempo Operando : {YELLOW}{uptime_str}{RESET}",
        f"  🕯️  Velas Analizadas: {CYAN}{state.candles_analyzed}{RESET}",
        f"  🎯 Trades Forjados  : {MAGENTA}{state.trades_executed}{RESET}",
        f"  💵 Precio Actual    : {GREEN}${state.current_price:,.2f}{RESET}",
        f"  📉 Último Cierre    : {YELLOW}${state.last_close:,.2f}{RESET}",
        f"  🧠 Estado IA        : {reason_str}",
        f"{CYAN}╚════════════════════════════════════════════════════════╝{RESET}"
    ]

    if state.is_first_render:
        sys.stdout.write("\n" * len(lines))
        state.is_first_render = False

    sys.stdout.write(f"\r\033[{len(lines)}A")
    for line in lines:
        sys.stdout.write(f"\033[K{line}\n")
    sys.stdout.flush()

# ── HANDLERS EVENT-DRIVEN PARA DASHBOARD ─────────────────────────────────────
def _handle_signal_event(event: SignalEvent) -> None:
    """Alerta táctica cuando DecisionEngine publica una señal."""
    global _current_eval_data
    sig = event.signal
    barriers = None
    rr = 0.0

    if isinstance(_current_eval_data, dict):
        barriers = _current_eval_data.get("barriers")
        if isinstance(barriers, dict):
            rr = float(barriers.get("rr", 0.0))
            barriers["tier"] = sig.tier

    state.last_reason = f"ENTRY: {sig.tier} ({sig.prob:.1f}%)"
    state.is_first_render = True

    print(f"\n{MAGENTA}╔════════════════════════════════════════════════════════╗")
    print(f"║ 🎯 ¡ALERTA DE FRANCOTIRADOR ZETSU! SEÑAL DETECTADA 🎯  ║")
    print(f"╚════════════════════════════════════════════════════════╝{RESET}")
    print(f"  🚀 DIRECCIÓN : {GREEN if sig.direction == 'LONG' else RED}{sig.direction}{RESET}")
    print(f"  ⚔️  TIER      : {CYAN}{sig.tier}{RESET} (Prob: {sig.prob:.1f}%)")
    if rr:
        print(f"  ⚖️  RATIO R:R : {YELLOW}{rr:.2f}{RESET}")
    print(f"  💥 ENTRY/SL/TP: {YELLOW}{sig.entry_price:,.2f}{RESET} / {RED}{sig.sl_price:,.2f}{RESET} / {GREEN}{sig.tp_price:,.2f}{RESET}")

def _handle_order_event(event: OrderEvent) -> None:
    """Contabiliza órdenes emitidas por OMS (PENDING)."""
    state.trades_executed += 1

def _ensure_bus(event_bus: Optional[EventBus] = None) -> EventBus:
    """Inicializa bus/orquestador y suscripciones del ingestor."""
    global _orchestrator, _bus
    if event_bus is not None:
        _bus = event_bus
    else:
        if _orchestrator is None:
            _orchestrator = ZetsuOrchestrator()
        _bus = _orchestrator.get_bus()
    _bus.subscribe(SignalEvent, _handle_signal_event)
    _bus.subscribe(OrderEvent, _handle_order_event)
    return _bus

def evaluate_live_market():
    global _current_eval_data, _bus
    try:
        suppress_text = io.StringIO()
        sys.stdout = suppress_text

        df_1m = pl.read_database_uri("SELECT * FROM btc_usdt ORDER BY timestamp ASC", uri=config.DB_URL)
        df_1m = df_1m.unique(subset=["timestamp"], keep="last").sort("timestamp")
        df_1m = add_indicators(df_1m)

        df_15m = df_1m.group_by_dynamic("timestamp", every="15m").agg([
            pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
            pl.col("close").last(), pl.col("volume").sum()
        ])
        df_15m = add_indicators(df_15m)

        df_1h = df_1m.group_by_dynamic("timestamp", every="1h").agg([
            pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
            pl.col("close").last(), pl.col("volume").sum()
        ])
        df_1h = add_indicators(df_1h)

        df_4h = df_1m.group_by_dynamic("timestamp", every="4h").agg([
            pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
            pl.col("close").last(), pl.col("volume").sum()
        ])
        df_4h = add_indicators(df_4h)

        df_1d = df_1m.group_by_dynamic("timestamp", every="1d").agg([
            pl.col("open").first(), pl.col("high").max(), pl.col("low").min(),
            pl.col("close").last(), pl.col("volume").sum()
        ])
        df_1d = add_indicators(df_1d)

        df_1m  = enrich_with_volume_features(df_1m)
        df_15m = enrich_with_volume_features(df_15m)
        df_1h  = enrich_with_volume_features(df_1h)
        df_4h  = enrich_with_volume_features(df_4h)
        df_1d  = enrich_with_volume_features(df_1d)

        slice_1m  = df_1m.tail(150)
        slice_15m = df_15m.tail(120)
        slice_1h  = df_1h.tail(49)
        slice_4h  = df_4h.tail(25)
        slice_1d  = df_1d.tail(15)

        sys.stdout = sys.__stdout__
        if _bus is None:
            _bus = _ensure_bus()

        data_payload = {
            "1m": slice_1m, "15m": slice_15m, "1h": slice_1h,
            "4h": slice_4h, "1d": slice_1d, "trade_state": None
        }

        _current_eval_data = data_payload
        _bus.publish(MTFDataEvent(data=data_payload))
        _current_eval_data = None

        state.last_reason = "NO_TRADE"
        state.candles_analyzed += 1

    except Exception as e:
        sys.stdout = sys.__stdout__
        state.is_first_render = True
        _current_eval_data = None
        print(f"\n{RED}[!] Error crítico en el análisis en vivo: {e}{RESET}")

def on_message(ws, message):
    data = json.loads(message)
    kline = data['k']
    is_closed = kline['x']
    state.current_price = float(kline['c'])

    if is_closed:
        state.last_close = state.current_price
        timestamp_ms = data['E']
        open_p, high_p, low_p, close_p, volume = float(kline['o']), float(kline['h']), float(kline['l']), float(kline['c']), float(kline['v'])

        df_new = pl.DataFrame({
            "timestamp": [timestamp_ms],
            "open": [open_p], "high": [high_p], "low": [low_p], "close": [close_p], "volume": [volume]
        })
        df_new = df_new.with_columns(pl.from_epoch("timestamp", time_unit="ms"))

        try:
            suppress_text = io.StringIO()
            sys.stdout = suppress_text
            df_new.write_database(table_name="btc_usdt", connection=config.DB_URL, if_table_exists="append")
            sys.stdout = sys.__stdout__
            evaluate_live_market()
        except Exception as e:
            sys.stdout = sys.__stdout__
            state.is_first_render = True
            print(f"\n{RED}[!] Error crítico inyectando a la base de datos: {e}{RESET}")
    render_dashboard()

def on_error(ws, error):
    state.is_first_render = True
    print(f"\n{RED}[!] Error en el Nervio Óptico: {error}{RESET}")

def on_close(ws, close_status_code, close_msg):
    state.is_first_render = True
    print(f"\n{RED}[!] Conexión perdida. Reconectando...{RESET}")

def on_open(ws):
    print(f"{CYAN}╔{'═'*56}╗")
    print(f"║{'INGESTOR V10.2 — CAZADOR AUTÓNOMO EN LÍNEA':^56}║")
    print(f"╚{'═'*56}╝{RESET}\n")

    try:
        msg = {"content": "🟢 **ZETSU HUNT EN LÍNEA**\nEl Nervio Óptico está conectado a la Matrix. Cazando..."}
        if config.WEBHOOK_DISCORD:
            requests.post(config.WEBHOOK_DISCORD, json=msg)
    except Exception as e:
        print(f"{RED}[!] Error enviando el ping a Discord: {e}{RESET}")

    print(f"{YELLOW}[⚙️] Forzando trade de simulación para verificar OMS/Executor/SQLite...{RESET}")
    try:
        _ensure_bus()
        now_ms = int(datetime.datetime.utcnow().timestamp() * 1000)
        test_price = 65000.0
        sig = Signal(
            asset=config.SYMBOL, direction="LONG", entry_price=test_price,
            sl_price=test_price * 0.98, tp_price=test_price * 1.05,
            tier="SIMULACRO_INICIAL", prob=99.9, timestamp=now_ms
        )
        _bus.publish(SignalEvent(signal=sig))
        print(f"{CYAN}[*] Simulacro completado. Iniciando Tablero Táctico...{RESET}\n")
    except Exception as e:
        print(f"{RED}[!] Error en el simulacro de inicio: {e}{RESET}")

def sync_historical_gaps():
    print(f"\n{CYAN}[*] Iniciando Protocolo de Sincronización Temporal (Gap Filler)...{RESET}")
    try:
        query = "SELECT timestamp FROM btc_usdt ORDER BY timestamp DESC LIMIT 1"
        df_last = pl.read_database_uri(query, uri=config.DB_URL)
        if len(df_last) == 0:
            print(f"{YELLOW}[!] Base de datos vacía. Arrancando con memoria limpia.{RESET}")
            return

        last_ts_ms = int(df_last["timestamp"][0].timestamp() * 1000)
        current_ts_ms = int(datetime.datetime.now().timestamp() * 1000)
        if current_ts_ms - last_ts_ms < 120_000:
            print(f"{GREEN}[✓] Memoria intacta. Sin ceguera temporal.{RESET}")
            return

        print(f"{YELLOW}[!] Ceguera temporal detectada. Descargando velas faltantes...{RESET}")
        symbol = config.SYMBOL.replace("/", "").upper()
        start_time, total_filled = last_ts_ms + 60000, 0

        while True:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={config.TF_SNIPER}&startTime={start_time}&limit=1000"
            data = requests.get(url).json()
            if not data or isinstance(data, dict): break
            records = [{"timestamp": k[0], "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])} for k in data]
            df_gap = pl.DataFrame(records).with_columns(pl.from_epoch("timestamp", time_unit="ms"))
            df_gap.write_database(table_name="btc_usdt", connection=config.DB_URL, if_table_exists="append")
            total_filled += len(df_gap)
            start_time = int(data[-1][0]) + 60000
            if len(df_gap) < 1000: break
        print(f"{GREEN}[✓] Brecha temporal curada: {total_filled} velas inyectadas.{RESET}")
    except Exception as e:
        print(f"{RED}[!] Error crítico en Gap Filler: {e}{RESET}")

def start_ingestor(event_bus: Optional[EventBus] = None):
    _ensure_bus(event_bus)
    sync_historical_gaps()
    symbol = config.SYMBOL.replace("/", "").lower()
    socket = f"wss://fstream.binance.com/ws/{symbol}@kline_{config.TF_SNIPER}"
    ws = websocket.WebSocketApp(socket, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    start_ingestor()
