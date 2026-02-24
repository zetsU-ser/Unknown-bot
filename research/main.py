# main.py — UNKNOWN-BOT V5.1 — LIVE ENGINE
# Foco: Sincronización Real-Time de 3 Capas (MTF) y Gestión de Estado Estricta
import time
import polars as pl
from data.ingestor import fetch_data, save_to_db
from analysis.indicators import add_indicators
from research.core.decision_engine import check_mtf_signals
from execution.simulated import wallet
from core.logger import bot_log

# ── COLORES DE CONSOLA ────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
BLUE   = "\033[94m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"

REASON_COLORS = {
    "SL": RED, "TP": GREEN, "TRAILING": GREEN,
    "BREAKEVEN": YELLOW, "RSI_EXIT": CYAN, "CHoCH": CYAN,
    "TIMEOUT": YELLOW, "TIMEOUT_TRAIL": YELLOW,
}

# ── ESTADO GLOBAL DEL TRADE ───────────────────────────────────────────────────
_barriers     = None
_breakeven_on = False

if __name__ == "__main__":
    bot_log.info("--- [UNKNOWN-BOT V5.1 — LIVE ENGINE] INICIADO ---")
    print(f"{BOLD}{CYAN}Arrancando Motor de 3 Temporalidades (1m, 15m, 1h)...{RESET}")

    while True:
        try:
            # 1. ── INGESTA DE DATOS ───────────────────────────────────────────
            # Nota: Asegúrate de que fetch_data() traiga suficiente historial 
            # (al menos 12,000 velas de 1m) para calcular la EMA 200 de 1h correctamente.
            df_raw = fetch_data()
            save_to_db(df_raw)

            # 2. ── CONSTRUCCIÓN DE CAPAS (RESAMPLING REAL-TIME) ───────────────
            # Capa 1: Sniper (1m)
            df_1m = add_indicators(df_raw)
            curr_price = df_1m["close"].tail(1).item()

            # Capa 2: Estructura (15m)
            df_15m = (
                df_1m.group_by_dynamic("timestamp", every="15m")
                .agg([pl.col("open").first(), pl.col("high").max(),
                      pl.col("low").min(),   pl.col("close").last(),
                      pl.col("volume").sum()])
            )
            df_15m = add_indicators(df_15m)

            # Capa 3: Dirección Macro (1h)
            df_1h = (
                df_1m.group_by_dynamic("timestamp", every="1h")
                .agg([pl.col("open").first(), pl.col("high").max(),
                      pl.col("low").min(),   pl.col("close").last(),
                      pl.col("volume").sum()])
            )
            df_1h = add_indicators(df_1h)

            # 3. ── ACTUALIZACIÓN DE ESTADO DEL TRADE ──────────────────────────
            if wallet.active_trade and _barriers:
                # Validar si cruzamos el umbral del 60% para activar el Breakeven Dinámico
                if not _breakeven_on and curr_price >= _barriers["be_trigger"]:
                    _breakeven_on = True
                    bot_log.info(f"🔒 BREAKEVEN ACTIVADO @ ${curr_price:,.2f}")

                # El tracking de max_price lo maneja la wallet internamente ahora en V5.1

            # 4. ── CEREBRO: TOMA DE DECISIONES ────────────────────────────────
            signal, reason, tentative_barriers = check_mtf_signals(
                df_1m        = df_1m,
                df_15m       = df_15m,
                df_1h        = df_1h,
                buy_price    = wallet.buy_price     if wallet.active_trade else None,
                max_p        = wallet.max_price     if wallet.active_trade else None,
                bars_in_t    = wallet.bars_in_trade if wallet.active_trade else 0,
                barriers     = _barriers            if wallet.active_trade else None,
                breakeven_on = _breakeven_on,
            )

            # 5. ── EJECUCIÓN ──────────────────────────────────────────────────
            # Si hay señal de compra válida, capturamos las barreras proyectadas ANTES de entrar
            if signal == "BUY" and not wallet.active_trade:
                _barriers     = tentative_barriers
                _breakeven_on = False

            cash, crypto = wallet.execute_trade(signal, curr_price, reason)

            # Limpiar estado si salimos del trade
            if signal == "SELL":
                _barriers     = None
                _breakeven_on = False

            # 6. ── DISPLAY EN CONSOLA ─────────────────────────────────────────
            total = cash + (crypto * curr_price)
            sig_c = GREEN if signal == "BUY" else RED if signal == "SELL" else DIM
            
            # Solo colorear "WAIT" si estamos debugeando filtros
            if signal == "WAIT" and reason and "FILTER" not in reason:
                rc = YELLOW
            else:
                rc = REASON_COLORS.get(reason, DIM)

            r_str = f" [{rc}{reason}{RESET}]" if reason else ""
            
            sl_str = ""
            if wallet.active_trade and _barriers:
                sl_str = f"| SL=${_barriers['sl']:,.0f} TP=${_barriers['tp']:,.0f} (RR: {_barriers['rr']:.2f})"

            print(
                f"{sig_c}[{signal}]{RESET}{r_str} "
                f"Price=${curr_price:,.2f} | "
                f"Portfolio=${total:,.2f} {sl_str}"
            )

            time.sleep(60)

        except KeyboardInterrupt:
            bot_log.warning("Bot detenido manualmente por el usuario.")
            print(f"\n{YELLOW}Motor V5.1 apagado de forma segura.{RESET}")
            break
        except Exception as e:
            bot_log.error(f"ERROR CRÍTICO EN LIVE ENGINE: {e}")
            print(f"{RED}Error detectado. Reintentando en 10s... ({e}){RESET}")
            time.sleep(10)