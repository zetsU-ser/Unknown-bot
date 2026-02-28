import os
import sys
import optuna
import statistics

# Aseguramos que Python encuentre nuestras carpetas
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import configs.btc_usdt_config as config
from research.btc_backtester import load_and_sync_data, run_simulation

# ── ESTÉTICA ──
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"

def objective(trial, d1, d15, d1h, d4h, d1d):
    """
    La Función de Aptitud (Fitness Function).
    Aquí Optuna muta los parámetros de config.py, corre una simulación
    rápida y devuelve una métrica de éxito (Ej: Sharpe Ratio o Capital Final).
    """
    
    # ── 1. MUTACIÓN GENÉTICA (El motor de Optuna modificando las reglas) ──
    # Dejamos que la IA busque el SL perfecto entre 1.0 y 2.5 ATRs
    config.ATR_SL_MULT = trial.suggest_float("ATR_SL_MULT", 1.0, 2.5)
    
    # Buscamos la exigencia mínima perfecta para entrar a un trade
    config.SCOUT_PROB_MIN = trial.suggest_float("SCOUT_PROB_MIN", 65.0, 80.0)
    config.AMBUSH_PROB_MIN = trial.suggest_float("AMBUSH_PROB_MIN", 80.0, 88.0)
    config.UNICORN_PROB_MIN = trial.suggest_float("UNICORN_PROB_MIN", 88.0, 95.0)
    
    # Buscamos el punto exacto para proteger capital (Break-Even)
    config.SCOUT_BE_THRESHOLD = trial.suggest_float("SCOUT_BE_THRESHOLD", 0.5, 0.9)
    config.AMBUSH_BE_THRESHOLD = trial.suggest_float("AMBUSH_BE_THRESHOLD", 0.5, 0.9)

    # ── 2. LA PELEA (Ejecutar simulación con los genes mutados) ──
    # Le pasamos los DataFrames que ya están en RAM para que sea instantáneo
    trades, final_cap, _ = run_simulation(d1, d15, d1h, d4h, d1d)
    
    # ── 3. LA FUNCIÓN DE CASTIGO / RECOMPENSA (Loss Function) ──
    if not trades or len(trades) < 10:
        # Castigo letal: Si la mutación hace que el bot no opere, la matamos
        raise optuna.exceptions.TrialPruned()

    wins = [t for t in trades if t["pnl"] > 0]
    wr = len(wins) / len(trades) * 100
    pnls = [t["pnl"] for t in trades]
    
    # Calculamos el Sharpe Ratio (Rentabilidad ajustada al riesgo)
    stdev = statistics.stdev(pnls) if len(pnls) > 1 else 1.0
    if stdev == 0: stdev = 1.0
    sharpe = statistics.mean(pnls) / stdev

    # Recompensa combinada: Queremos ganar dinero, pero con un buen Sharpe
    # Si la IA quema dinero (final_cap < inicial), el score es negativo
    score = (final_cap - config.INITIAL_CASH) * sharpe

    return score

def run_mutant_lab():
    print(f"\n{CYAN}[*] Iniciando el Laboratorio Mutante (Optuna)...{RESET}")
    print(f"[*] Descargando la Matrix de Datos a la RAM una sola vez. Paciencia...")
    
    # Cargamos el mercado real (pesado, toma segundos)
    d1, d15, d1h, d4h, d1d = load_and_sync_data()
    
    print(f"\n{YELLOW}[!] Datos en RAM. Soltando a los clones a pelear a la velocidad de la luz...{RESET}")
    
    # Creamos el ecosistema de Optuna obligándolo a MAXIMIZAR el score
    study = optuna.create_study(direction="maximize")
    
    # Ocultamos los prints ruidosos del backtester original silenciando el stdout temporalmente
    import sys, io
    original_stdout = sys.stdout
    
    try:
        sys.stdout = io.StringIO() # Silenciador
        # Lanzamos 100 generaciones de clones
        study.optimize(lambda trial: objective(trial, d1, d15, d1h, d4h, d1d), n_trials=100)
    finally:
        sys.stdout = original_stdout # Devolvemos la voz a la consola

    # ── 4. EL SUPERVIVIENTE (La configuración perfecta) ──
    print(f"\n\033[92m[✓] ¡Evolución Completada! 100 Generaciones simuladas.\033[0m")
    print(f"\n{CYAN}╔{'═'*56}╗")
    print(f"║{'EL ADN PERFECTO (Mejores Hiperparámetros)':^56}║")
    print(f"╚{'═'*56}╝{RESET}")
    
    best_params = study.best_params
    for key, value in best_params.items():
        print(f"  ➔ {key:<20}: \033[93m{value:.3f}\033[0m")
        
    print(f"\n{YELLOW}[!] Copia estos valores y pégalos en tu archivo configs/btc_usdt_config.py{RESET}\n")

if __name__ == "__main__":
    run_mutant_lab()