# execution/simulated.py — V10.2
"""
PaperWallet legacy — usado por main.py viejo y compatibilidad backward.
V10.2: eliminada dependencia de core.logger (que no existe).
      Usa logging estándar de Python.
"""
import logging
import configs.btc_usdt_config as config

log = logging.getLogger("simulated")


class PaperWallet:
    def __init__(self):
        self.cash          = config.INITIAL_CASH
        self.crypto        = 0.0
        self.active_trade  = False
        self.buy_price     = 0.0
        self.max_price     = 0.0
        self.bars_in_trade = 0

    def execute_trade(
        self,
        signal: str,
        current_price: float,
        reason: str | None = None,
    ) -> tuple[float, float]:

        if signal == "BUY" and not self.active_trade:
            self.crypto        = self.cash / current_price
            self.buy_price     = current_price
            self.max_price     = current_price
            self.bars_in_trade = 0
            self.cash          = 0.0
            self.active_trade  = True
            log.warning(f"COMPRA SIMULADA: {self.crypto:.6f} BTC @ ${current_price:.2f}")

        elif signal == "SELL" and self.active_trade:
            self.cash          = self.crypto * current_price
            pnl_pct            = (current_price / self.buy_price - 1) * 100
            reason_str         = f" | Razón: {reason}" if reason else ""
            log.warning(f"VENTA SIMULADA: ${self.cash:.2f} | PnL: {pnl_pct:+.2f}%{reason_str}")
            self.crypto        = 0.0
            self.active_trade  = False
            self.buy_price     = 0.0
            self.max_price     = 0.0
            self.bars_in_trade = 0

        elif self.active_trade:
            self.bars_in_trade += 1
            if current_price > self.max_price:
                self.max_price = current_price

        return self.cash, self.crypto


wallet = PaperWallet()