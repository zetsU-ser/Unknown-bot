"""
Setup de Infraestructura de Base de Datos - UNKNOWN-BOT V6.0
============================================================
Este script inicializa las tablas necesarias en PostgreSQL para almacenar
datos de alta frecuencia (OHLCV). Implementa índices B-Tree en las marcas 
de tiempo (timestamps) para garantizar que el motor de simulación (Backtester)
pueda hacer búsquedas de rango en milisegundos (O(log n)).
"""

import psycopg2
from urllib.parse import urlparse
import sys
import os

# Ajustamos el path para poder importar nuestra configuración agnóstica
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import configs.btc_usdt_config as config

# Estética de consola
GREEN, RED, CYAN, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[0m"

def get_db_connection():
    """Parsea la URL de la base de datos y retorna la conexión."""
    result = urlparse(config.DB_URL)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port
    
    return psycopg2.connect(
        database=database,
        user=username,
        password=password,
        host=hostname,
        port=port
    )

def setup_timeseries_table(symbol_table_name: str):
    """
    Crea la tabla OHLCV si no existe y le aplica optimizaciones quant.
    Es un proceso idempotente (se puede ejecutar múltiples veces sin romper nada).
    """
    print(f"{CYAN}Iniciando auditoría de DB para la tabla: {symbol_table_name}...{RESET}")
    
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {symbol_table_name} (
        timestamp BIGINT PRIMARY KEY,
        open DOUBLE PRECISION NOT NULL,
        high DOUBLE PRECISION NOT NULL,
        low DOUBLE PRECISION NOT NULL,
        close DOUBLE PRECISION NOT NULL,
        volume DOUBLE PRECISION NOT NULL
    );
    """

    # El índice B-Tree es el secreto para que np.searchsorted vuele en Python
    create_index_query = f"""
    CREATE INDEX IF NOT EXISTS idx_{symbol_table_name}_timestamp 
    ON {symbol_table_name} (timestamp ASC);
    """

    try:
        # Usamos context managers (with) para asegurar que la conexión se cierre sola
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                print(f"  [1/2] Verificando/Creando esquema OHLCV...")
                cur.execute(create_table_query)
                
                print(f"  [2/2] Aplicando Índice B-Tree de alta velocidad...")
                cur.execute(create_index_query)
                
            conn.commit()
            print(f"{GREEN}✓ Infraestructura para {symbol_table_name} optimizada y lista.{RESET}\n")

    except Exception as e:
        print(f"{RED}Error crítico al configurar la base de datos: {e}{RESET}")

if __name__ == "__main__":
    print(f"\n╔══════════════════════════════════════════════════╗")
    print(f"║ QUANT DATABASE SETUP ENGINE - UNKNOWN-BOT V6.0   ║")
    print(f"╚══════════════════════════════════════════════════╝\n")
    
    # Extraemos el nombre de la tabla desde el config (Ej: "BTC/USDT" -> "btc_usdt")
    table_name = config.SYMBOL.replace("/", "_").lower()
    setup_timeseries_table(table_name)
    
    # Si mañana operas ETH, solo cambias el config y corres este script de nuevo
    # setup_timeseries_table("eth_usdt")