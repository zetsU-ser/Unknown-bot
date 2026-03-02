from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.trading import Order, Position

class BaseBroker(ABC):

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def fetch_position(self, asset: str) -> Optional[Position]:
        ...

    @abstractmethod
    def fetch_balance(self) -> float:
        ...
