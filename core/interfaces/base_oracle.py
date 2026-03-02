from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from domain.trading import Signal

class BaseOracle(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def tier(self) -> str:
        ...

    @abstractmethod
    def evaluate(self, data: Any) -> Optional[Signal]:
        ...
