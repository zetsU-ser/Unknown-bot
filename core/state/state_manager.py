from __future__ import annotations

import json
import sqlite3
from typing import List

from core.interfaces.base_state import BaseStateManager
from domain.trading import Order

class SQLiteStateManager(BaseStateManager):
    """State Manager persistente usando SQLite (stdlib)."""

    def __init__(self, db_path: str = "zetsu_state.db") -> None:
        self.db_path = db_path
        try:
            self.conn = sqlite3.connect(self.db_path)
            self._ensure_schema()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to initialize SQLiteStateManager: {e}") from e

    def _ensure_schema(self) -> None:
        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS active_orders (
                    order_id TEXT PRIMARY KEY,
                    asset TEXT,
                    order_data TEXT
                )
                """
            )
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to ensure schema: {e}") from e

    def save_active_order(self, order: Order) -> None:
        if not order.id:
            raise ValueError("Order.id is required to persist an active order.")

        try:
            # Al volcar el modelo, los nuevos campos sl_id y tp_id se guardarán automáticamente
            order_json = order.model_dump_json()
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO active_orders (order_id, asset, order_data)
                VALUES (?, ?, ?)
                """,
                (order.id, order.symbol, order_json),
            )
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to save active order {order.id}: {e}") from e

    def load_active_orders(self) -> List[Order]:
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT order_data FROM active_orders")
            rows = cur.fetchall()

            orders: List[Order] = []
            for (order_data,) in rows:
                # order_data es JSON string de Pydantic
                orders.append(Order.model_validate_json(order_data))
            return orders
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to load active orders: {e}") from e

    def remove_order(self, order_id: str) -> None:
        try:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM active_orders WHERE order_id = ?", (order_id,))
            self.conn.commit()
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to remove order {order_id}: {e}") from e