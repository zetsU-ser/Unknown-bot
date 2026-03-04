import logging
import time
from execution.oms import RealExecutor
from domain.trading import Signal
import configs.btc_usdt_config as config

# Forzamos los logs a la consola para ver qué hace el OMS
logging.basicConfig(level=logging.INFO, format='%(message)s')

def run_oms_stress_test():
    print(f"\n{'='*50}")
    print(" INICIANDO TEST DE ESTRÉS DEL OMS (TESTNET) ")
    print(f"{'='*50}\n")
    
    # 1. Inicializar el motor
    oms = RealExecutor()
    
    # Verificar balance
    balance = oms.get_usdt_balance()
    print(f"\n[*] Balance actual en Testnet: {balance} USDT")
    if balance <= 0:
        print("[!] ERROR: No tienes fondos en la Testnet. El test fallará.")
        return

    # 2. Fabricar una señal falsa (LONG en BTC)
    # Obtenemos el precio actual real para que el SL y TP sean válidos para el exchange
    ticker = oms.exchange.fetch_ticker(config.SYMBOL)
    current_price = ticker['last']
    
    dummy_signal = Signal(
        asset=config.SYMBOL,
        direction="LONG",
        entry_price=current_price,
        sl_price=current_price * 0.98,  # SL 2% abajo
        tp_price=current_price * 1.04,  # TP 4% arriba
        tier="AMBUSH",
        prob=85.0,
        timestamp=int(time.time() * 1000)
    )
    
    barriers = {
        'sl': dummy_signal.sl_price, 
        'tp': dummy_signal.tp_price
    }
    
    atr_simulado = current_price * 0.015 # ATR simulado del 1.5%

    print("\n[*] EMITIENDO SEÑAL DE PRUEBA...")
    print(f"Dirección: {dummy_signal.direction} | Precio Aprox: {current_price}")
    
    # 3. Ejecutar orden
    orden_abierta = oms.execute_signal(dummy_signal, barriers, atr_simulado)
    
    if not orden_abierta:
        print("\n[!] TEST FALLIDO: El OMS no pudo abrir la orden. Revisa los logs de arriba.")
        return
        
    print("\n[*] RESULTADO DE LA EJECUCIÓN ATÓMICA:")
    print(orden_abierta.model_dump_json(indent=2))
    
    # 4. Probar actualización de Breakeven
    print("\n[*] ESPERANDO 5 SEGUNDOS PARA SIMULAR MOVIMIENTO DEL MERCADO...")
    time.sleep(5)
    
    nuevo_sl = current_price * 1.01 # Movemos el SL a ganancias (Profit Lock)
    print(f"\n[*] SOLICITANDO CANCELACIÓN QUIRÚRGICA Y NUEVO SL EN: {nuevo_sl}")
    
    orden_actualizada = oms.update_breakeven(orden_abierta, nuevo_sl)
    
    if orden_actualizada:
        print("\n[*] RESULTADO DEL BREAKEVEN:")
        print(orden_actualizada.model_dump_json(indent=2))
        print("\n[✓] TEST EXITOSO. Verifica en la web de Binance Testnet que las órdenes están correctas.")
        print("NOTA: Recuerda cerrar manualmente la posición en la web de Testnet después del test.")
    else:
        print("\n[!] TEST FALLIDO EN BREAKEVEN.")

if __name__ == "__main__":
    run_oms_stress_test()