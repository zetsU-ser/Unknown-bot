import logging
from typing import Callable, Dict, List, Type
from domain.events import Event

class EventBus:
    """
    Sistema Pub/Sub (Sistema Nervioso) para enrutar eventos de forma síncrona/segura
    entre los componentes aislados de la arquitectura Zetsu.
    """
    def __init__(self) -> None:
        self.subscribers: Dict[Type[Event], List[Callable]] = {}

    def subscribe(self, event_type: Type[Event], handler: Callable) -> None:
        """Registra una función receptora para un evento específico."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
        logging.debug(f"[EventBus] {handler.__name__} suscrito a {event_type.__name__}")

    def publish(self, event: Event) -> None:
        """Propaga el evento a todos los órganos suscritos."""
        event_type = type(event)
        if event_type in self.subscribers:
            for handler in self.subscribers[event_type]:
                try:
                    handler(event)
                except Exception as e:
                    logging.error(f"[EventBus] Error crítico en el handler {handler.__name__} procesando {event_type.__name__}: {e}")