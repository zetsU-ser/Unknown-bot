import logging
import sys
from typing import Dict, Any

from engine.event_bus import EventBus
from execution.oms import RealExecutor
from core.decision_engine import DecisionEngine
from infra.discord_notifier import DiscordNotifier
from domain.events import MTFDataEvent, SignalEvent, OrderEvent
import configs.btc_usdt_config as config

# ── ESTÉTICA PARA LOGS ───────────────────────────────────────────────────────
GREEN, RED, YELLOW, RESET, CYAN = "\033[92m", "\033[91m", "\033[93m", "\033[0m", "\033[96m"

class ZetsuOrchestrator:
    """
    El Cerebro Central. Instancia el EventBus, conecta los órganos vitales (Ingestor, OMS, DecisionEngine)
    y gestiona el ciclo de vida de la aplicación y su apagado seguro.
    """
    def __init__(self) -> None:
        logging.info(f"{CYAN}[ORCHESTRATOR] Ensamblando el Sistema Nervioso Central...{RESET}")
        
        # 1. Bus de Eventos y Telemetría
        self.bus = EventBus()
        self.telemetry = DiscordNotifier()
        
        # 2. Órganos de Ejecución
        self.executor = RealExecutor()
        
        # 3. Motor de Decisión Lógica / ML
        try:
            self.decision_engine = DecisionEngine(event_bus=self.bus)
        except Exception as e:
            logging.error(f"{RED}[ORCHESTRATOR] Fallo al arrancar el Motor de Decisiones: {e}{RESET}")
            raise e

        # 4. Mapeo de Suscripciones
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        self.bus.subscribe(SignalEvent, self._handle_signal)
        self.bus.subscribe(OrderEvent, self._handle_order_event)
        logging.info(f"{GREEN}[ORCHESTRATOR] ✓ Suscripciones neuronales mapeadas exitosamente.{RESET}")

    def get_bus(self) -> EventBus:
        return self.bus

    def _handle_signal(self, event: SignalEvent) -> None:
        """Intercepta la señal, prepara las variables y ordena al OMS disparar."""
        signal = event.signal
        logging.info(f"{YELLOW}[ORCHESTRATOR] Recibida orden táctica ({signal.direction}). Transmitiendo al OMS...{RESET}")
        
        barriers = {
            'sl': signal.sl_price,
            'tp': signal.tp_price
        }
        
        # FIX DE AUDITORÍA: Ingeniería inversa del ATR usando la configuración real del sistema
        sl_distance = abs(signal.entry_price - signal.sl_price)
        atr_inferido = sl_distance / config.ATR_SL_MULT if config.ATR_SL_MULT else sl_distance
        
        try:
            order = self.executor.execute_signal(signal=signal, barriers=barriers, atr=atr_inferido)
            if order:
                self.bus.publish(OrderEvent(order=order))
        except Exception as e:
            error_msg = f"Fallo al ejecutar señal en OMS: {e}"
            logging.error(f"{RED}[ORCHESTRATOR] {error_msg}{RESET}")
            self.telemetry.send_alert(error_msg)

    def _handle_order_event(self, event: OrderEvent) -> None:
        if event.order.status == "OPEN":
            self.telemetry.send_trade_open(event.order)

    def start(self) -> None:
        """Arranca el Ingestor y comienza la caza."""
        self.telemetry.send_startup()
        logging.info(f"{GREEN}[ORCHESTRATOR] Inyectando adrenalina. Despertando Ingestor de Mercado...{RESET}")
        
        from data.ingestor import start_ingestor
        
        try:
            start_ingestor(event_bus=self.bus)
        except KeyboardInterrupt:
            self.shutdown("Intervención del Usuario (KeyboardInterrupt)")
        except Exception as e:
            error_msg = f"Colapso masivo en el Ingestor: {e}"
            logging.error(f"{RED}[ORCHESTRATOR] {error_msg}{RESET}")
            self.telemetry.send_alert(error_msg)
            self.shutdown("Fallo Crítico del Ingestor")

    def shutdown(self, reason: str = "Desconocida") -> None:
        """Apagado elegante. Cancela rutinas y cierra la conexión del bot."""
        logging.warning(f"\n{RED}[ORCHESTRATOR] Secuencia de Apagado Iniciada. Motivo: {reason}{RESET}")
        self.telemetry.send_alert(f"Iniciando Graceful Shutdown. Motivo: {reason}")
        
        try:
            logging.info(f"{YELLOW}[ORCHESTRATOR] Cerrando subprocesos y puertos de red...{RESET}")
        except Exception as e:
            logging.error(f"{RED}[ORCHESTRATOR] Error durante el proceso de limpieza: {e}{RESET}")
        
        logging.info(f"{CYAN}[ORCHESTRATOR] Sistema Zetsu desconectado de la Matrix de forma segura.{RESET}")
        sys.exit(0)