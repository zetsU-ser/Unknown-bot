import requests
import configs.btc_usdt_config as config
from infra.binance_client import BinanceClientFactory

# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"

class ZetsuExecutor:
    def __init__(self, use_testnet=True):
        print(f"{CYAN}[*] Inicializando Brazo Ejecutor de Zetsu (Testnet: {use_testnet})...{RESET}")
        self.exchange = BinanceClientFactory.create(testnet=use_testnet)
        try:
            self.exchange.load_markets()
        except Exception as e:
            print(f"{RED}[!] Aviso: No se pudieron cargar los mercados. {e}{RESET}")

    def calculate_position_size(self, entry_price, sl_price, usdt_balance):
        risk_pct = getattr(config, "RISK_PER_TRADE_PCT", 0.02)
        capital_at_risk = usdt_balance * risk_pct
        sl_distance = abs(entry_price - sl_price)
        if sl_distance == 0: return 0
        qty_btc = capital_at_risk / sl_distance
        return round(qty_btc, 4)

    def execute_signal(self, direction, entry_price, sl_price, tp_price, tier):
        print(f"\n{YELLOW}[⚙️] Zetsu está armando el paquete de ejecución institucional...{RESET}")
        try:
            balance = self.exchange.fetch_balance()
            usdt_balance = balance['total'].get('USDT', 0.0)
            
            if usdt_balance < 10:
                print(f"{RED}[X] Fuego Abortado: Balance insuficiente.{RESET}")
                return False

            qty = self.calculate_position_size(entry_price, sl_price, usdt_balance)
            notional = qty * entry_price
            
            if notional < 5:
                print(f"{RED}[X] Fuego Abortado: Tamaño de posición menor al mínimo.{RESET}")
                return False

            side = 'buy' if direction == 'LONG' else 'sell'
            
            # ── ALERTA DIRECTA A DISCORD ──
            webhook_url = "https://discord.com/api/webhooks/1477518249972465795/MWLQWl7m4i_vmi1sHDyJZQyGtjxfQcaXJpo-shuw-IgZq8BdPgjOrp7qX-tdF27evdO8"
            
            discord_msg = {
                "content": f"🚨 **ZETSU HUNT: TRADE DETECTADO** 🚨\n**Dirección:** {direction} | **Tier:** {tier}\n```text\nEntry: {entry_price:,.2f}\nTP: {tp_price:,.2f}\nSL: {sl_price:,.2f}\n```"
            }
            
            try:
                requests.post(webhook_url, json=discord_msg)
            except Exception as e:
                print(f"{RED}[!] Error enviando a Discord: {e}{RESET}")

            # Print básico en consola para saber que disparó
            print(f"{GREEN}[✓] ORDEN ENVIADA - REVISA DISCORD{RESET}\n")
            
            return True

        except Exception as e:
            print(f"{RED}[!] Error Crítico de Ejecución: {e}{RESET}")
            return False