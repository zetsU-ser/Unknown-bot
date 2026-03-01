import json
import websocket
import datetime
import polars as pl
import sys
import os
import requests

# Aseguramos que Python encuentre tus módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configs.btc_usdt_config as config
from analysis.indicators import add_indicators
from analysis.volume_profile import enrich_with_volume_features
from core.decision_engine import check_mtf_signals
from execution.simulated import ZetsuExecutor
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_DISCORD = os.getenv("DISCORD_WEBHOOK")


# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET, MAGENTA = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m", "\033[95m"

# ── INICIALIZACIÓN DEL BRAZO EJECUTOR ────────────────────────────────────────
executor = ZetsuExecutor(use_testnet=True)


def evaluate_live_market():
    try:
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

        if signal == "ENTRY":
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
                tier=tier
            )
        else:
            print(f"{YELLOW}  ➔ [IA] Posición denegada. Razón: {reason}{RESET}")

    except Exception as e:
        print(f"{RED}[!] Error crítico en el análisis en vivo: {e}{RESET}")


def on_message(ws, message):
    data = json.loads(message)
    kline = data['k']
    is_closed = kline['x']

    if is_closed:
        timestamp_ms = data['E']
        open_p  = float(kline['o'])
        high_p  = float(kline['h'])
        low_p   = float(kline['l'])
        close_p = float(kline['c'])
        volume  = float(kline['v'])

        timestamp_str = datetime.datetime.fromtimestamp(timestamp_ms / 1000).strftime('%H:%M:%S')
        print(f"\n{GREEN}[✓] VELA 1M CERRADA {timestamp_str} | Precio: ${close_p:,.2f} | Vol: {volume:.2f} BTC{RESET}")

        df_new = pl.DataFrame({
            "timestamp": [timestamp_ms],
            "open": [open_p], "high": [high_p], "low": [low_p], "close": [close_p], "volume": [volume]
        })
        df_new = df_new.with_columns(pl.from_epoch("timestamp", time_unit="ms"))

        try:
            df_new.write_database(table_name="btc_usdt", connection=config.DB_URL, if_table_exists="append")
            print(f"{CYAN}  ➔ [DB] Memoria actualizada. Escaneando Matrix...{RESET}")
            evaluate_live_market()
            
        except Exception as e:
            print(f"{RED}[!] Error crítico inyectando a la base de datos: {e}{RESET}")

    else:
        close_price = float(kline['c'])
        print(f"\r{YELLOW}[⚡] LIVE | BTC/USDT: ${close_price:,.2f}{RESET}", end="")

def on_error(ws, error):
    print(f"\n{RED}[!] Error en el Nervio Óptico: {error}{RESET}")

def on_close(ws, close_status_code, close_msg):
    print(f"\n{RED}[!] Conexión perdida. Reconectando...{RESET}")

def on_open(ws):
    print(f"{CYAN}╔{'═'*56}╗")
    print(f"║{'INGESTOR V10.2 — CAZADOR AUTÓNOMO EN LÍNEA':^56}║")
    print(f"╚{'═'*56}╝{RESET}\n")

    # ── EL GRITO DE ENCENDIDO A DISCORD ──
    try:
        msg = {"content": "🟢 **ZETSU HUNT EN LÍNEA**\nEl Nervio Óptico está conectado a la Matrix. Cazando..."}
        requests.post(WEBHOOK_DISCORD, json=msg)
        print(f"{GREEN}[✓] Ping de inicio enviado al Discord exitosamente.{RESET}")
    except Exception as e:
        print(f"{RED}[!] Error enviando el ping a Discord: {e}{RESET}")

def start_ingestor():
    symbol = config.SYMBOL.replace("/", "").lower()
    socket = f"wss://stream.binance.com:9443/ws/{symbol}@kline_{config.TF_SNIPER}"
    ws = websocket.WebSocketApp(socket, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    start_ingestor()