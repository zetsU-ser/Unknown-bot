from infra.binance_client import BinanceClientFactory

def probar_conexion():
    print("\033[96m[*] Iniciando prueba de conexión estandarizada...\033[0m")
    try:
        exchange = BinanceClientFactory.create(testnet=True)
        balance = exchange.fetch_balance()
        
        # Leemos los USDT para confirmar acceso a la bóveda
        usdt = balance['total'].get('USDT', 0.0)
        
        print("\033[92m[✓] Conexión OK. Motor funcionando a la perfección.\033[0m")
        print(f"\033[93m[*] Bóveda Zetsu: ${usdt:,.2f} USDT\033[0m")
    except Exception as e:
        print(f"\033[91m[X] Error crítico en la conexión: {e}\033[0m")

if __name__ == "__main__":
    probar_conexion()