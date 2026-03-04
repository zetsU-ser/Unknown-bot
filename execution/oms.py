import logging
import math
import uuid
import time
from typing import Optional, Dict, Any, List
import ccxt
import configs.btc_usdt_config as config
from domain.trading import Signal, Order
from core.risk_manager import kelly_position_size

# ── ESTÉTICA PARA LOGS ───────────────────────────────────────────────────────
GREEN, RED, YELLOW, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"

class RealExecutor:
    """
    Motor de Ejecución (OMS). Blindado con atomicidad simulada, 
    idempotencia y una capa de Paper Trading nativa anti-deprecación de Binance.
    """

    def __init__(self) -> None:
        try:
            logging.info(f"{YELLOW}[OMS] Inicializando RealExecutor hacia Binance USD-M...{RESET}")
            
            self.is_paper = getattr(config, "LIVE_MODE", "False").lower() != "true"
            
            # Configuración base (sin llaves)
            exchange_config = {
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future'
                }
            }
            
            if self.is_paper:
                logging.info(f"{YELLOW}[OMS] MODO PAPER TRADING ACTIVADO.{RESET}")
                logging.warning(f"{YELLOW}[OMS] Binance cerró su Testnet. El OMS operará como observador público y simulará las órdenes.{RESET}")
            else:
                logging.warning(f"{RED}[OMS] MODO LIVE ACTIVADO. INYECTANDO LLAVES SECRETAS. RIESGO DE CAPITAL REAL.{RESET}")
                # SOLO inyectamos las llaves si estamos en vivo
                exchange_config['apiKey'] = config.BINANCE_API_KEY
                exchange_config['secret'] = config.BINANCE_API_SECRET

            # Instanciamos el exchange con la configuración dinámica
            self.exchange = ccxt.binanceusdm(exchange_config)
            self.symbol = config.SYMBOL
            
            # Cargar mercados reales (funciona de forma anónima)
            self.exchange.load_markets()
            self.market = self.exchange.market(self.symbol)
            logging.info(f"{GREEN}[OMS] Nervio motor conectado exitosamente (Lectura Activa).{RESET}")
        except Exception as e:
            logging.error(f"{RED}[OMS] Fallo crítico al inicializar el Exchange: {e}{RESET}")
            raise e

    def get_usdt_balance(self) -> float:
        if self.is_paper:
            return 10000.0  # Balance simulado de $10k para Paper Trading
        
        try:
            balance = self.exchange.fetch_balance()
            return float(balance['USDT']['free'])
        except Exception as e:
            logging.error(f"{RED}[OMS] Error obteniendo balance: {e}{RESET}")
            return 0.0

    def calculate_quantity(self, entry_price: float, atr: float, stop_loss: float) -> float:
        cash = self.get_usdt_balance()
        if cash <= 0:
            return 0.0

        peak_capital = getattr(config, "PEAK_CAPITAL", cash)
        risk_pct = kelly_position_size(cash, atr, entry_price, peak_capital)
        
        if risk_pct <= 0:
            return 0.0

        risk_usd = cash * risk_pct
        sl_distance_pct = abs(entry_price - stop_loss) / entry_price
        
        if sl_distance_pct == 0:
            return 0.0

        position_size_usd = risk_usd / sl_distance_pct
        raw_qty = position_size_usd / entry_price

        amount_precision = self.market['precision']['amount']
        if isinstance(amount_precision, int):
            decimals = amount_precision
        else:
            decimals = abs(int(math.log10(amount_precision)))
            
        factor = 10 ** decimals
        qty_rounded = math.floor(raw_qty * factor) / factor

        return float(qty_rounded)

    def execute_signal(self, signal: Signal, barriers: Dict[str, Any], atr: float) -> Optional[Order]:
        qty = self.calculate_quantity(signal.entry_price, atr, float(barriers['sl']))
        
        if qty <= 0:
            logging.error(f"{RED}[OMS] Cantidad final de contratos inválida. Ignorando señal.{RESET}")
            return None

        side = 'buy' if signal.direction == 'LONG' else 'sell'
        sl_side = 'sell' if side == 'buy' else 'buy'
        client_entry_id = f"zetsu_{signal.timestamp}_{uuid.uuid4().hex[:8]}"
        
        if self.is_paper:
            # ── SIMULACIÓN PAPER TRADING ──
            time.sleep(0.3) # Simular latencia de red
            logging.info(f"{YELLOW}[OMS-PAPER] Desplegando ataque: {side.upper()} {qty} {self.symbol}...{RESET}")
            logging.info(f"{GREEN}[OMS-PAPER] ✓ Infiltración y escudos confirmados (Simulados).{RESET}")
            return Order(
                id=f"sim_entry_{uuid.uuid4().hex[:8]}",
                symbol=self.symbol,
                direction=signal.direction,
                qty=qty,
                entry_price=signal.entry_price,
                status="OPEN",
                sl_id=f"sim_sl_{uuid.uuid4().hex[:8]}",
                tp_id=f"sim_tp_{uuid.uuid4().hex[:8]}"
            )

        # ── EJECUCIÓN REAL (LIVE MODE) ──
        try:
            logging.info(f"{YELLOW}[OMS] Desplegando ataque LIVE: {side.upper()} {qty} {self.symbol}...{RESET}")
            entry_order = self.exchange.create_order(
                symbol=self.symbol, type='market', side=side, amount=qty, params={'newClientOrderId': client_entry_id}
            )
            actual_entry_price = float(entry_order.get('average', signal.entry_price))
        except Exception as e:
            logging.error(f"{RED}[OMS] Fallo en la inserción de orden MKT: {e}{RESET}")
            return None

        try:
            sl_order = self.exchange.create_order(
                symbol=self.symbol, type='stop_market', side=sl_side, amount=qty, params={'stopPrice': float(barriers['sl']), 'reduceOnly': True}
            )
            tp_order = self.exchange.create_order(
                symbol=self.symbol, type='take_profit_market', side=sl_side, amount=qty, params={'stopPrice': float(barriers['tp']), 'reduceOnly': True}
            )
            logging.info(f"{GREEN}[OMS] ✓ Infiltración y escudos confirmados a {actual_entry_price}.{RESET}")
            return Order(
                id=str(entry_order['id']), symbol=self.symbol, direction=signal.direction, qty=qty,
                entry_price=actual_entry_price, status="OPEN", sl_id=str(sl_order['id']), tp_id=str(tp_order['id'])
            )
        except Exception as e:
            logging.error(f"{RED}[OMS] ERROR CRÍTICO AL PLANTAR ESCUDOS. INICIANDO PANIC CLOSE: {e}{RESET}")
            try:
                self.exchange.create_order(symbol=self.symbol, type='market', side=sl_side, amount=qty, params={'reduceOnly': True})
                logging.warning(f"{YELLOW}[OMS] Panic Close ejecutado. Posición liquidada.{RESET}")
            except Exception as panic_e:
                logging.error(f"{RED}[OMS] FATAL: PANIC CLOSE FALLÓ: {panic_e}{RESET}")
            return None

    def update_breakeven(self, order: Order, new_sl_price: float) -> Optional[Order]:
        if self.is_paper:
            # ── SIMULACIÓN PAPER TRADING ──
            time.sleep(0.2)
            logging.info(f"{YELLOW}[OMS-PAPER] Ajustando Breakeven...{RESET}")
            logging.info(f"[OMS-PAPER] SL anterior ({order.sl_id}) neutralizado exitosamente.")
            logging.info(f"{GREEN}[OMS-PAPER] ✓ Nuevo SL afianzado en {new_sl_price}.{RESET}")
            return order.model_copy(update={'sl_id': f"sim_sl_{uuid.uuid4().hex[:8]}"})

        # ── EJECUCIÓN REAL (LIVE MODE) ──
        try:
            logging.info(f"{YELLOW}[OMS] Ajustando Breakeven/Profit Lock LIVE...{RESET}")
            if order.sl_id:
                try:
                    self.exchange.cancel_order(order.sl_id, self.symbol)
                except ccxt.OrderNotFound:
                    logging.warning(f"[OMS] SL anterior ya no existe en el exchange.")

            sl_side = 'sell' if order.direction == 'LONG' else 'buy'
            new_sl = self.exchange.create_order(
                symbol=self.symbol, type='stop_market', side=sl_side, amount=order.qty, params={'stopPrice': new_sl_price, 'reduceOnly': True}
            )
            logging.info(f"{GREEN}[OMS] ✓ SL movido a {new_sl_price}.{RESET}")
            return order.model_copy(update={'sl_id': str(new_sl['id'])})
        except Exception as e:
            logging.error(f"{RED}[OMS] Error estructural al ejecutar Breakeven: {e}{RESET}")
            return None