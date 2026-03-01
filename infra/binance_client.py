import os
import ccxt
from dotenv import load_dotenv

# Inyectamos seguridad: obligamos a Python a leer el archivo .env
load_dotenv()

class BinanceClientFactory:
    @staticmethod
    def create(testnet: bool = True):
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")

        if not api_key or not api_secret:
            raise ValueError("[!] Faltan BINANCE_API_KEY o BINANCE_API_SECRET en el archivo .env")

        exchange = ccxt.binance({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        })

        if testnet:
            exchange.set_sandbox_mode(True)

        return exchange