import logging
import json
import urllib.request
from typing import Optional
import configs.btc_usdt_config as config
from domain.trading import Order

class DiscordNotifier:
    """
    Módulo de Telemetría Nativo para notificaciones vía Webhook de Discord.
    No requiere librerías externas.
    """
    def __init__(self) -> None:
        self.webhook_url: Optional[str] = getattr(config, "WEBHOOK_DISCORD", None)

    def _send_payload(self, message: str) -> None:
        if not self.webhook_url:
            return
        try:
            payload = json.dumps({"content": message}).encode('utf-8')
            req = urllib.request.Request(
                self.webhook_url, 
                data=payload, 
                headers={'Content-Type': 'application/json', 'User-Agent': 'ZetsuBot/10.2'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                pass
        except Exception as e:
            logging.error(f"[TELEMETRÍA] Error de red al contactar con Discord: {e}")

    def send_startup(self) -> None:
        msg = "🟢 **Cazador Zetsu V10.2 Iniciado**\nEl Nervio Motor y el Orquestador están en línea. Comenzando a bombear datos de la Matrix..."
        self._send_payload(msg)

    def send_trade_open(self, order: Order) -> None:
        side = "🟢 LONG" if order.direction == "LONG" else "🔴 SHORT"
        msg = (f"🎯 **ALERTA DE FRANCOTIRADOR ZETSU: TRADE DESPLEGADO**\n"
               f"**Asset:** {order.symbol}\n"
               f"**Dirección:** {side}\n"
               f"**Precio de Entrada:** {order.entry_price}\n"
               f"**Tamaño (Qty):** {order.qty}\n"
               f"**Estado:** {order.status}\n"
               f"**SL ID:** {order.sl_id} | **TP ID:** {order.tp_id}")
        self._send_payload(msg)

    def send_alert(self, message: str) -> None:
        msg = f"⚠️ **ALERTA CRÍTICA DEL SISTEMA**\n{message}"
        self._send_payload(msg)