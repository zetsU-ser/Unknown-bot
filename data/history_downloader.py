import ccxt
import polars as pl
import time

# Asegúrate de importar las variables correctas desde tu config
from configs.btc_usdt_config import DB_URL, SYMBOL, TF_SNIPER
# Si tienes un logger úsalo, si no, usaremos prints para ver el progreso
# from core.logger import bot_log 

def download_historical_data():
    # Inicializamos Binance activando el Rate Limit nativo para que no nos baneen
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    all_ohlcv = []
    
    # ── CAMBIO 1: FECHA DE INICIO EXACTA ──
    # Descargamos desde el 1 de Enero de 2025 (Más de un año entero de velas 1m)
    since = exchange.parse8601('2025-01-01T00:00:00Z')
    
    print(f"Iniciando descarga masiva de {SYMBOL} desde 2025...")

    while since < exchange.milliseconds():
        try:
            # Pedimos de a 1000 velas
            new_data = exchange.fetch_ohlcv(SYMBOL, TF_SNIPER, since=since, limit=1000)
            
            if not new_data:
                break
                
            all_ohlcv.extend(new_data)
            # Avanzamos el reloj al timestamp de la última vela + 1 milisegundo
            since = new_data[-1][0] + 1
            
            print(f"[*] Descargadas {len(all_ohlcv)} velas...", end="\r")
            time.sleep(0.1) # Respeto al servidor de Binance
            
        except Exception as e:
            # Si Binance nos corta la conexión, pausamos y reintentamos
            print(f"\n[!] Error de red: {e}. Reintentando en 5 segundos...")
            time.sleep(5)

    print("\n[*] Descarga completa. Procesando datos vectoriales en Polars...")
    df = pl.DataFrame(all_ohlcv, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    
    # Convertimos los milisegundos a fecha legible (TIMESTAMP)
    df = df.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
    
    # Nombre exacto de la tabla en PostgreSQL
    table_name = "btc_usdt" 
    
    print(f"[*] Inyectando motor en la Hipertabla de TimescaleDB...")
    # ── CAMBIO 2: APPEND EN LUGAR DE REPLACE ──
    # 'append' inyecta la data respetando la estructura particionada
    df.write_database(table_name=table_name, connection=DB_URL, if_table_exists="append")
    
    print(f"¡ÉXITO! {len(all_ohlcv)} velas de 1 minuto guardadas en la DB.")

if __name__ == "__main__":
    download_historical_data()