import json
import websocket
import datetime
import polars as pl
import requests
import sys
import io

# ── IMPORTACIONES LIMPIAS ────────────────────────────────────────────────────
import configs.btc_usdt_config as config
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from core.decision_engine import check_mtf_signals
from execution.simulated import ZetsuExecutor

# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET, MAGENTA = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m", "\033[95m"

# ── INICIALIZACIÓN DEL BRAZO EJECUTOR ────────────────────────────────────────
executor = ZetsuExecutor(use_testnet=True)

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


def evaluate_live_market():
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

        signal, reason, barriers, prob, direction = check_mtf_signals(
            slice_1m, slice_15m, slice_1h, slice_4h, slice_1d, trade_state=None
        )

        sys.stdout = sys.__stdout__
        state.last_reason = reason
        state.candles_analyzed += 1

        if signal == "ENTRY":
            state.trades_executed += 1
            tier = barriers.get("tier", "UNKNOWN")
            rr = barriers.get("rr", 0)
            
            print(f"\n{MAGENTA}╔════════════════════════════════════════════════════════╗")
            print(f"║ 🎯 ¡ALERTA DE FRANCOTIRADOR ZETSU! SEÑAL DETECTADA 🎯  ║")
            print(f"╚════════════════════════════════════════════════════════╝{RESET}")
            print(f"  🚀 DIRECCIÓN : {GREEN if direction == 'LONG' else RED}{direction}{RESET}")
            print(f"  ⚔️  TIER      : {CYAN}{tier}{RESET} (Prob: {prob:.1f}%)")
            print(f"  ⚖️  RATIO R:R : {YELLOW}{rr:.2f}{RESET}")
            
            entry_price = float(slice_1m["close"][-1])
            executor.execute_signal(
                direction=direction,
                entry_price=entry_price,
                sl_price=barriers['sl'],
                tp_price=barriers['tp'],
                tier=tier,
                prob=prob
            )
            state.is_first_render = True

    except Exception as e:
        sys.stdout = sys.__stdout__
        state.is_first_render = True
        print(f"\n{RED}[!] Error crítico en el análisis en vivo: {e}{RESET}")


def on_message(ws, message):
    data = json.loads(message)
    kline = data['k']
    is_closed = kline['x']
    state.current_price = float(kline['c'])

    if is_closed:
        state.last_close = state.current_price
        timestamp_ms = data['E']
        open_p  = float(kline['o'])
        high_p  = float(kline['h'])
        low_p   = float(kline['l'])
        close_p = float(kline['c'])
        volume  = float(kline['v'])

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

    print(f"{YELLOW}[⚙️] Forzando trade de simulación para verificar ejecución y Discord...{RESET}")
    try:
        df_test = pl.read_database_uri("SELECT close FROM btc_usdt ORDER BY timestamp DESC LIMIT 1", uri=config.DB_URL)
        test_price = float(df_test["close"][0]) if len(df_test) > 0 else 65000.0
        
        executor.execute_signal(
            direction="LONG",
            entry_price=test_price,
            sl_price=test_price * 0.98,
            tp_price=test_price * 1.05,
            tier="SIMULACRO_INICIAL",
            prob=99.9
        )
        print(f"{CYAN}[*] Simulacro completado. Iniciando Tablero Táctico...{RESET}\n")
    except Exception as e:
        print(f"{RED}[!] Error en el simulacro de inicio: {e}{RESET}")

# ── MÓDULO DE CURACIÓN TEMPORAL (GAP FILLER) ─────────────────────────────────
def sync_historical_gaps():
    print(f"\n{CYAN}[*] Iniciando Protocolo de Sincronización Temporal (Gap Filler)...{RESET}")
    try:
        query = "SELECT timestamp FROM btc_usdt ORDER BY timestamp DESC LIMIT 1"
        df_last = pl.read_database_uri(query, uri=config.DB_URL)

        if len(df_last) == 0:
            print(f"{YELLOW}[!] Base de datos vacía. Arrancando con memoria limpia.{RESET}")
            return

        # Obtenemos el timestamp en milisegundos de la última vela en PostgreSQL
        last_ts_ms = int(df_last["timestamp"][0].timestamp() * 1000)
        current_ts_ms = int(datetime.datetime.now().timestamp() * 1000)

        # Si pasaron menos de 2 minutos (120,000 ms), no hay nada que rellenar
        if current_ts_ms - last_ts_ms < 120_000:
            print(f"{GREEN}[✓] Memoria intacta. Sin ceguera temporal.{RESET}")
            return

        print(f"{YELLOW}[!] Ceguera temporal detectada. Descargando velas faltantes...{RESET}")
        
        symbol = config.SYMBOL.replace("/", "").upper()
        start_time = last_ts_ms + 60000 # Sumamos 1 minuto para no duplicar la última vela
        total_filled = 0
        
        # Bucle robusto por si estuviste desconectado días enteros
        while True:
            #url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={config.TF_SNIPER}&startTime={start_time}&limit=1000"
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={config.TF_SNIPER}&startTime={start_time}&limit=1000"
            response = requests.get(url)
            data = response.json()
            
            # Si la API falla o devuelve lista vacía, rompemos el bucle
            if not data or isinstance(data, dict): 
                break
                
            records = []
            for k in data:
                records.append({
                    "timestamp": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
                
            df_gap = pl.DataFrame(records)
            df_gap = df_gap.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
            df_gap.write_database(table_name="btc_usdt", connection=config.DB_URL, if_table_exists="append")
            
            fetched_count = len(df_gap)
            total_filled += fetched_count
            
            # Actualizamos el puntero de tiempo para la siguiente petición (si son más de 1000 velas)
            start_time = int(data[-1][0]) + 60000
            
            if fetched_count < 1000:
                break # Ya atrapamos el presente

        if total_filled > 0:
            print(f"{GREEN}[✓] Brecha temporal curada: {total_filled} velas inyectadas en la Matrix.{RESET}")
        else:
            print(f"{GREEN}[✓] Sincronización verificada.{RESET}")

    except Exception as e:
        print(f"{RED}[!] Error crítico en Gap Filler: {e}{RESET}")


def start_ingestor():
    # EJECUTAMOS EL CURADOR TEMPORAL ANTES DE ABRIR LOS OJOS
    sync_historical_gaps()
    
    symbol = config.SYMBOL.replace("/", "").lower()
    #socket = f"wss://stream.binance.com:9443/ws/{symbol}@kline_{config.TF_SNIPER}"
    socket = f"wss://fstream.binance.com/ws/{symbol}@kline_{config.TF_SNIPER}"
    ws = websocket.WebSocketApp(socket, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    start_ingestor()