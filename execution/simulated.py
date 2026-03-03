from __future__ import annotations

from engine.event_bus import EventBus
from domain.events import OrderEvent
from core.interfaces.base_state import BaseStateManager

# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"

class SimulatedExecutor:
    """Ejecutor simulado: suscriptor de OrderEvent. Persiste órdenes en SQLite."""

    def __init__(self, event_bus: EventBus, state_manager: BaseStateManager) -> None:
        self.event_bus = event_bus
        self.state_manager = state_manager
        self.event_bus.subscribe(OrderEvent, self.handle_order)

    def handle_order(self, event: OrderEvent) -> None:
        try:
            fake_id = f"SIM-{int(event.timestamp.timestamp() * 1000)}"
            filled_order = event.order.model_copy(update={"order_id": fake_id, "status": "FILLED"})

            # Persistencia (SQLite)
            self.state_manager.save_active_order(filled_order)

            print(
                f"\n{GREEN}╔════════════════════════════════════════════════════════╗{RESET}\n"
                f"{GREEN}║    ⚔️  ZETSU SIM EXECUTOR — ORDEN EJECUTADA (FILLED)     ║{RESET}\n"
                f"{GREEN}╠════════════════════════════════════════════════════════╣{RESET}\n"
                f"{CYAN}  order_id:{RESET} {filled_order.order_id}\n"
                f"{CYAN}  asset:   {RESET} {filled_order.asset}\n"
                f"{CYAN}  side:    {RESET} {filled_order.side}\n"
                f"{CYAN}  type:    {RESET} {filled_order.order_type}\n"
                f"{CYAN}  qty:     {RESET} {filled_order.qty}\n"
                f"{CYAN}  status:  {RESET} {filled_order.status}\n"
                f"{YELLOW}  SQLite:{RESET} guardada en StateManager (memoria inmortal)\n"
                f"{GREEN}╚════════════════════════════════════════════════════════╝{RESET}\n"
            )

        except Exception as e:
            print(f"{RED}[!] SimulatedExecutor error: {e}{RESET}")
