from __future__ import annotations

from domain.events import OrderEvent, SignalEvent
from domain.trading import Order
from engine.event_bus import EventBus

class OMS:
    """Order Management System: convierte señales en órdenes (simulado por ahora)."""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.event_bus.subscribe(SignalEvent, self.handle_signal)

    def handle_signal(self, event: SignalEvent) -> None:
        signal = event.signal

        new_order = Order(
            asset=signal.asset,
            side=("BUY" if signal.direction == "LONG" else "SELL"),
            qty=0.0,
            order_type="MARKET",
            status="PENDING",
        )

        self.event_bus.publish(OrderEvent(order=new_order))
