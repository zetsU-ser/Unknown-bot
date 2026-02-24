# execution/simulated.py — UNKNOWN-BOT V5.1
# Foco: Ejecución quirúrgica y tracking estricto de PnL / MFE (Maximum Favorable Excursion)
from core.config import INITIAL_CASH
from core.logger import bot_log

class PaperWallet:
    def __init__(self):
        # Estado inicial limpio
        self.cash          = INITIAL_CASH
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
        """
        V5.1 Focus: Simula la transacción y mantiene el estado del trade.
        La actualización del 'max_price' es vital para el Breakeven Dinámico.
        """

        # ── COMPRAR (Entrada) ─────────────────────────────────────────
        if signal == "BUY" and not self.active_trade:
            # All-in simulado del capital asignado por Kelly (que se maneja en main)
            self.crypto        = self.cash / current_price
            self.buy_price     = current_price
            self.max_price     = current_price
            self.bars_in_trade = 0
            self.cash          = 0.0
            self.active_trade  = True
            
            bot_log.warning(
                f"💸 COMPRA SIMULADA: {self.crypto:.6f} BTC @ ${current_price:,.2f} | Razón: {reason}"
            )

        # ── VENDER (Salida) ───────────────────────────────────────────
        elif signal == "SELL" and self.active_trade:
            self.cash = self.crypto * current_price
            pnl_pct   = (current_price / self.buy_price - 1) * 100
            
            reason_str = f" | Razón: {reason}" if reason else ""
            bot_log.warning(
                f"💰 VENTA SIMULADA: ${self.cash:,.2f} | PnL: {pnl_pct:+.3f}%{reason_str}"
            )
            
            # Reset riguroso del estado para evitar datos fantasma en el siguiente trade
            self.crypto        = 0.0
            self.active_trade  = False
            self.buy_price     = 0.0
            self.max_price     = 0.0
            self.bars_in_trade = 0

        # ── MANTENIMIENTO (Trade Activo) ──────────────────────────────
        elif self.active_trade:
            self.bars_in_trade += 1
            # El MFE (Max Price) se actualiza tick a tick para el Trailing y el Breakeven
            if current_price > self.max_price:
                self.max_price = current_price

        return self.cash, self.crypto


# Instancia única de la billetera para ser consumida globalmente por main.py
wallet = PaperWallet()