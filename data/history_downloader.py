import ccxt
import polars as pl
import time
from core.config import DB_URL, TRADING_SYMBOL, TIMEFRAME
from core.logger import bot_log

def download_month_data():
    exchange = ccxt.binance()
    all_ohlcv = []
    
    # Calculamos el timestamp de hace 30 días en milisegundos
    since = exchange.milliseconds() - (200000 * 60 * 1000)
    
    bot_log.info(f"Iniciando descarga masiva de {TRADING_SYMBOL}...")

    while since < exchange.milliseconds():
        # Bajamos de a 1000 velas (límite de Binance)
        symbol = TRADING_SYMBOL.replace("/", "") # CCXT usa BTCUSDT para histórico a veces
        new_data = exchange.fetch_ohlcv(TRADING_SYMBOL, TIMEFRAME, since=since, limit=1000)
        
        if not new_data:
            break
            
        all_ohlcv.extend(new_data)
        # El nuevo 'since' es el timestamp de la última vela recibida + 1ms
        since = new_data[-1][0] + 1
        
        print(f"[*] Descargadas {len(all_ohlcv)} velas...", end="\r")
        time.sleep(0.1) # Respetar rate limit

    # Convertir a DataFrame y guardar
    df = pl.DataFrame(all_ohlcv, schema=["timestamp", "open", "high", "low", "close", "volume"], orient="row")
    df = df.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
    
    table_name = TRADING_SYMBOL.replace("/", "_").lower()
    df.write_database(table_name=table_name, connection=DB_URL, if_table_exists="replace")
    
    bot_log.info(f"¡ÉXITO! {len(all_ohlcv)} velas guardadas en la DB.")

if __name__ == "__main__":
    download_month_data()