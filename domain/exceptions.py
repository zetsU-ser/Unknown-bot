class MarketDataError(Exception):
    """Raised when there is a failure in market data ingestion or WebSocket feed."""
    pass

class RiskLimitExceededError(Exception):
    """Raised when risk limits (drawdown, margin, exposure) are exceeded."""
    pass

class ExecutionError(Exception):
    """Raised when broker rejects or fails to execute an order."""
    pass
