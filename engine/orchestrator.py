from __future__ import annotations

from engine.event_bus import EventBus
from core.state.state_manager import SQLiteStateManager
from execution.oms import OMS
from core.decision_engine import DecisionEngine
from execution.simulated import SimulatedExecutor

class ZetsuOrchestrator:
    """Contenedor de inyección de dependencias del sistema Event-Driven."""

    def __init__(self) -> None:
        self.bus = EventBus()
        self.state_manager = SQLiteStateManager()
        self.oms = OMS(self.bus)
        self.decision_engine = DecisionEngine(self.bus)
        self.executor = SimulatedExecutor(self.bus, self.state_manager)

    def get_bus(self) -> EventBus:
        return self.bus
