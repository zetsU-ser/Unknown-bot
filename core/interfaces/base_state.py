from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from domain.trading import Order

class BaseStateManager(ABC):

    @abstractmethod
    def save_active_order(self, order: Order) -> None:
        ...

    @abstractmethod
    def load_active_orders(self) -> List[Order]:
        ...

    @abstractmethod
    def remove_order(self, order_id: str) -> None:
        ...
