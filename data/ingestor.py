#~IMPORTS
import ccxt
import polars as pl
from core.config import DB_URL,CANDLE_LIMIT,TIMEFRAME,TRADING_SYMBOL


#~EXTRACCION DE DATOS
def fetch_data():
    try:
        exchange = ccxt.binance()

        #~Extraccion y Escritura de los datos
        raw_data = exchange.fetch_ohlcv(TRADING_SYMBOL, timeframe=TIMEFRAME, limit=CANDLE_LIMIT)
        df = pl.DataFrame(
            raw_data,
            schema=["timestamp", "open", "high", "low", "close", "volume"], 
            orient="row"
        )

        #~Retorno y Escritura legible del tiempo
        return df.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
    except Exception as e:
            print(f"[!] Error en fetch_data: {e}")
            return None

#~GUARDADO DE DATOS
def save_to_db(df):
    if df is None: return

    table_name = TRADING_SYMBOL.replace("/", "_").lower()
    #~Escritura de datos en la DB
    df.write_database(
        table_name = table_name,
        connection = DB_URL,
        if_table_exists = "replace"
    )
    print(f"[*] Datos de {TRADING_SYMBOL} guardados en la tabla '{table_name}'")
