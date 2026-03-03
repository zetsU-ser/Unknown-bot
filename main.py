import sys
import subprocess

GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"


def print_banner():
    print(f"\n{CYAN}╔{'═'*56}╗")
    print(f"║{'ZETSU HUNT V10.2 — COMANDANCIA CENTRAL':^56}║")
    print(f"╚{'═'*56}╝{RESET}\n")


def run_live():
    print(f"{GREEN}[*] Inicializando Sistema en MODO PRODUCCIÓN (LIVE)...{RESET}")
    try:
        from engine.orchestrator import ZetsuOrchestrator
        from data.ingestor import start_ingestor
        orchestrator = ZetsuOrchestrator()
        start_ingestor(event_bus=orchestrator.get_bus())
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Cacería abortada por el usuario.{RESET}")


def run_backtest():
    print(f"{YELLOW}[*] Inicializando Motor de Simulación Cuantitativa...{RESET}", flush=True)
    try:
        from research.btc_backtester import load_and_sync_data, run_simulation, print_fancy_report
        d1, d15, d1h, d4h, d1d = load_and_sync_data()
        results, cap, bb = run_simulation(d1, d15, d1h, d4h, d1d)
        print_fancy_report(results, cap, bb)
    except KeyboardInterrupt:
        import traceback
        print("\n")
        traceback.print_exc()
        print(f"\n{RED}[!] Simulación cancelada a la mitad.{RESET}")


def run_download():
    print(f"{CYAN}[*] Inicializando Extractor de Datos Históricos...{RESET}")
    try:
        import data.history_downloader
        data.history_downloader.run()
    except Exception as e:
        print(f"\n{RED}[!] Error en descarga: {e}{RESET}")


def interactive_menu():
    while True:
        print_banner()
        print(f"  {CYAN}[1]{RESET} Iniciar Cazador en Vivo")
        print(f"  {CYAN}[2]{RESET} Ejecutar Backtest")
        print(f"  {CYAN}[3]{RESET} Descargar Datos Historicos")
        print(f"  {CYAN}[4]{RESET} ML: Escanear Features (feature_analysis)")
        print(f"  {CYAN}[5]{RESET} ML: Entrenar Juez Supremo (train_meta)")
        print(f"  {CYAN}[6]{RESET} ML: Optimizar Hiperparametros (optuna_lab)")
        print(f"  {CYAN}[7]{RESET} Salir")
        try:
            choice = input(f"{YELLOW}Zetsu> {RESET}").strip()
            if   choice == "1": run_live()
            elif choice == "2": run_backtest()
            elif choice == "3": run_download()
            elif choice == "4":
                subprocess.run([sys.executable, "mlops/analysis/feature_analysis.py"])
            elif choice == "5":
                subprocess.run([sys.executable, "mlops/training/train_meta.py"])
            elif choice == "6":
                trials = input(f"{YELLOW}  Trials [50]: {RESET}").strip() or "50"
                model  = input(f"{YELLOW}  Modelo (xgb/rf/both) [xgb]: {RESET}").strip() or "xgb"
                subprocess.run([
                    sys.executable, "mlops/optimization/optuna_lab.py",
                    "--trials", trials,
                    "--model",  model,
                ])
            elif choice == "7": sys.exit(0)
        except KeyboardInterrupt:
            sys.exit(0)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Zetsu Hunt V10.2 - Comandancia Central",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser(
        "live",
        help="Iniciar el cazador en modo PRODUCCION (live trading)",
    )
    subparsers.add_parser(
        "backtest",
        help="Ejecutar simulacion cuantitativa sobre datos historicos",
    )
    subparsers.add_parser(
        "download",
        help="Descargar datos historicos OHLCV desde el exchange",
    )
    subparsers.add_parser(
        "ml-scan",
        help="Analizar correlacion de las 51 variables del Blackbox",
    )
    subparsers.add_parser(
        "ml-train",
        help="Entrenar el Juez Supremo XGBoost con el Blackbox",
    )

    p_opt = subparsers.add_parser(
        "ml-optimize",
        help="Buscar hiperparametros optimos con Optuna",
    )
    p_opt.add_argument(
        "--trials",
        type=int,
        default=50,
        help="Numero de trials de Optuna (default: 50)",
    )
    p_opt.add_argument(
        "--model",
        type=str,
        default="xgb",
        choices=["xgb", "rf", "both"],
        help="Tipo de modelo: xgb | rf | both (default: xgb)",
    )

    args = parser.parse_args()

    if args.command == "live":
        run_live()

    elif args.command == "backtest":
        run_backtest()

    elif args.command == "download":
        run_download()

    elif args.command == "ml-scan":
        subprocess.run(
            [sys.executable, "mlops/analysis/feature_analysis.py"],
            check=False,
        )

    elif args.command == "ml-train":
        subprocess.run(
            [sys.executable, "mlops/training/train_meta.py"],
            check=False,
        )

    elif args.command == "ml-optimize":
        subprocess.run(
            [
                sys.executable, "mlops/optimization/optuna_lab.py",
                "--trials", str(args.trials),
                "--model",  args.model,
            ],
            check=False,
        )

    else:
        interactive_menu()


if __name__ == "__main__":
    main()