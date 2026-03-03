from __future__ import annotations

class MarketDataError(Exception):
    """Fallos en WebSockets, datos faltantes o corruptos."""

class RiskLimitExceededError(Exception):
    """Cuando drawdown, margen u otro límite de riesgo es excedido."""

class ExecutionError(Exception):
    """Rechazos del broker/exchange o fallos de ejecución."""
