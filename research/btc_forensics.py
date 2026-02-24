"""
Laboratorio Forense Modular - UNKNOWN-BOT V7.0
================================================
Analiza la eficiencia de los Tiers usando Momentos Estadísticos (Curtosis, Skewness).
Genera sugerencias cuantitativas automáticas para reajustar variables en config.py y el Oráculo.
"""

import numpy as np
import statistics
from research.btc_backtester import load_and_sync_data, run_simulation
import configs.btc_usdt_config as config

# Estética de Terminal
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"
BOLD, DIM = "\033[1m", "\033[2m"

def calculate_moments(pnl_array):
    """Calcula Asimetría (Skewness) y Curtosis de los retornos."""
    if len(pnl_array) < 4: return 0.0, 0.0
    mean = np.mean(pnl_array)
    std = np.std(pnl_array)
    if std == 0: return 0.0, 0.0
    
    skew = np.mean(((pnl_array - mean) / std) ** 3)
    # Curtosis de Fisher (Normal = 0.0)
    kurtosis = np.mean(((pnl_array - mean) / std) ** 4) - 3.0
    return skew, kurtosis

def analyze_tier(tier_name, trades_subset, expected_prob):
    """Analiza la rentabilidad y la distribución estadística del Tier."""
    if len(trades_subset) < 5:
        return f"  {tier_name:10} | Datos insuficientes para modelado estadístico.", None

    pnls = np.array([t["pnl"] for t in trades_subset])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    
    wr = (len(wins) / len(pnls)) * 100
    avg_w = np.mean(wins) if len(wins) > 0 else 0
    avg_l = np.mean(losses) if len(losses) > 0 else 0
    
    ev = ((wr/100) * avg_w) + (((100-wr)/100) * avg_l)
    net_pnl = np.sum(pnls)
    
    skew, kurtosis = calculate_moments(pnls)
    
    color = GREEN if ev > 0 else RED
    wr_color = YELLOW if wr >= 50 else RED
    
    # Formato de la tabla
    row = (f"  {tier_name:10} | {len(pnls):<5} | {wr_color}{wr:>5.1f}%{RESET} | "
           f"{avg_w:>6.3f}% / {avg_l:>6.3f}% | {color}{ev:>6.3f}%{RESET} | "
           f"Skew: {skew:>5.2f} | Kurt: {kurtosis:>5.2f}")
    
    return row, {"wr": wr, "ev": ev, "kurt": kurtosis, "count": len(pnls)}

def generate_quant_suggestions(metrics):
    """Motor de Inferencia: Sugiere cambios a variables globales basado en la Curtosis y el EV."""
    print(f"\n{BOLD}{CYAN}🧠 MOTOR DE INFERENCIA BAYESIANA (SUGERENCIAS DE REAJUSTE){RESET}")
    print(f"{DIM}─────────────────────────────────────────────────────────────────{RESET}")
    
    # 1. Análisis de Asfixia de Unicornios
    if "🦄 UNICORN" not in metrics or metrics["🦄 UNICORN"]["count"] == 0:
        print(f"{YELLOW}[!] ASFIXIA DE UNICORNIOS DETECTADA (0 Trades){RESET}")
        print("  ➔ Causa: Las matemáticas del Oráculo son demasiado estrictas. La confluencia nunca llega a 75.0%.")
        print("  ➔ Sugerencia (decision_engine.py):")
        print("     1. Sube self.W_SWEEP a 30.0 (Premia más fuerte la manipulación).")
        print("     2. O reduce el multiplicador de penalización de self.W_ADX_HIGH a -5.0.")
    
    # 2. Análisis del Motor Principal (Ambush)
    if "⚔️  AMBUSH" in metrics:
        ambush = metrics["⚔️  AMBUSH"]
        print(f"\n{YELLOW}[*] ANÁLISIS DE EFICIENCIA AMBUSH{RESET}")
        
        if ambush["ev"] < 0:
            print(f"  {RED}➔ Hemorragia de EV: El motor principal está perdiendo dinero.{RESET}")
            print("  ➔ Sugerencia (config.py): Incrementa RR_MIN_REQUIRED de 1.1 a 1.5 para forzar asimetría matemática.")
        else:
            print(f"  {GREEN}➔ EV Positivo: El motor es matemáticamente estable.{RESET}")
            
        if ambush["kurt"] < 0:
            print(f"  {RED}➔ Curtosis Negativa ({ambush['kurt']:.2f}): Operando Ruido (Platicúrtica).{RESET}")
            print("  ➔ Causa: El bot está entrando en rangos sin volumen direccional real.")
            print("  ➔ Sugerencia (decision_engine.py): Aumenta la penalización self.W_NOISE a -25.0.")
        elif ambush["kurt"] > 1.5:
            print(f"  {GREEN}➔ Curtosis Positiva Extrema ({ambush['kurt']:.2f}): Fat Tails detectadas.{RESET}")
            print("  ➔ Confirmación: Smart Money Concepts está funcionando. Las ganancias vienen de explosiones de FVG.")
            print("  ➔ Sugerencia: Incrementa KELLY_FRACTION en config.py para ser más agresivo.")
            
    # 3. Análisis de Ruido (Scouts)
    if "🍃 SCOUT" in metrics and metrics["🍃 SCOUT"]["count"] > 0:
        print(f"\n{YELLOW}[!] ADVERTENCIA DE RUIDO (SCOUTS ACTIVOS){RESET}")
        print("  ➔ El nivel de disparo bajó. Tienes operaciones de baja probabilidad sangrando el EV.")
        print("  ➔ Sugerencia: En check_mtf_signals, sube el límite 'if prob >= 65.0' a 68.0.")
    
    print(f"{DIM}─────────────────────────────────────────────────────────────────{RESET}\n")

def run_bayesian_autopsy():
    print(f"\n{CYAN}Iniciando Autopsia Forense Modular V7.0...{RESET}")
    d1, d15, d1h = load_and_sync_data()
    trades, final_cap = run_simulation(d1, d15, d1h)
    
    if not trades:
        return print(f"{RED}No hay trades para analizar.{RESET}")

    scouts   = [t for t in trades if t.get("mult", 1.0) == 1.0]
    ambushes = [t for t in trades if t.get("mult", 1.0) == 1.5]
    unicorns = [t for t in trades if t.get("mult", 1.0) == 3.0]

    print(f"\n{BOLD}{CYAN}╔{'═'*105}╗")
    print(f"║{'LABORATORIO FORENSE MODULAR — DISTRIBUCIÓN ESTADÍSTICA Y CURTOSIS':^105}║")
    print(f"╚{'═'*105}╝{RESET}\n")
    
    metrics = {}
    row_s, m_s = analyze_tier("🍃 SCOUT", scouts, 60.0)
    row_a, m_a = analyze_tier("⚔️  AMBUSH", ambushes, 65.0)
    row_u, m_u = analyze_tier("🦄 UNICORN", unicorns, 75.0)
    
    print(row_s)
    print(row_a)
    print(row_u)
    
    if m_s: metrics["🍃 SCOUT"] = m_s
    if m_a: metrics["⚔️  AMBUSH"] = m_a
    if m_u: metrics["🦄 UNICORN"] = m_u
    
    # Llamamos al motor de inferencia con los datos calculados
    generate_quant_suggestions(metrics)

if __name__ == "__main__":
    run_bayesian_autopsy()