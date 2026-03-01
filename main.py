import argparse
import sys

# ── ESTÉTICA ─────────────────────────────────────────────────────────────────
GREEN, RED, CYAN, YELLOW, RESET = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[0m"

def print_banner():
    print(f"\n{CYAN}╔{'═'*56}╗")
    print(f"║{'ZETSU HUNT V10.2 — COMANDANCIA CENTRAL':^56}║")
    print(f"╚{'═'*56}╝{RESET}\n")

def run_live():
    print(f"{GREEN}[*] Inicializando Sistema en MODO PRODUCCIÓN (LIVE)...{RESET}")
    print(f"{YELLOW}[i] Tip: Presiona Ctrl+C en cualquier momento para detener la cacería y volver al menú.{RESET}")
    try:
        from data.ingestor import start_ingestor
        start_ingestor()
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Cacería abortada por el usuario. Desconectando de la Matrix...{RESET}")

def run_backtest():
    print(f"{YELLOW}[*] Inicializando Motor de Simulación Cuantitativa...{RESET}")
    try:
        from research.btc_backtester import load_and_sync_data, run_simulation, print_fancy_report
        d1, d15, d1h, d4h, d1d = load_and_sync_data()
        results, cap, bb = run_simulation(d1, d15, d1h, d4h, d1d)
        print_fancy_report(results, cap, bb)
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Simulación cancelada a la mitad.{RESET}")

def run_download():
    print(f"{CYAN}[*] Inicializando Extractor de Datos Históricos...{RESET}")
    try:
        import data.history_downloader
        # data.history_downloader.run()
        print(f"{YELLOW}[!] Módulo de descarga invocado.{RESET}")
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Descarga de datos cancelada.{RESET}")

def interactive_menu():
    while True:
        print_banner()
        print(f"  {CYAN}[1]{RESET} 🟢 Iniciar Cazador en Vivo (Producción)")
        print(f"  {CYAN}[2]{RESET} 📊 Ejecutar Backtest (Simulación)")
        print(f"  {CYAN}[3]{RESET} 💾 Descargar Datos Históricos")
        print(f"  {CYAN}[4]{RESET} ❌ Salir del Sistema")
        print("")
        
        try:
            choice = input(f"{YELLOW}Zetsu> {RESET}").strip()

            if choice == "1":
                run_live()
                input(f"\n{CYAN}Presiona ENTER para volver al menú principal...{RESET}")
            elif choice == "2":
                run_backtest()
                input(f"\n{CYAN}Presiona ENTER para volver al menú principal...{RESET}")
            elif choice == "3":
                run_download()
                input(f"\n{CYAN}Presiona ENTER para volver al menú principal...{RESET}")
            elif choice == "4":
                print(f"\n{RED}[!] Apagando sistemas. Hasta la vista.{RESET}")
                sys.exit(0)
            else:
                print(f"\n{RED}[!] Opción inválida. Concéntrate, mi sangre.{RESET}")
                
        except KeyboardInterrupt:
            # Si el usuario presiona Ctrl+C estando en el menú principal esperando orden
            print(f"\n{RED}[!] Apagado forzado. Hasta la vista.{RESET}")
            sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Zetsu Hunt - Motor Quant Institucional")
    parser.add_argument(
        "mode",
        nargs="?", 
        choices=["live", "backtest", "download"],
        help="Elige el modo de ejecución o déjalo vacío para el menú interactivo"
    )
    
    args = parser.parse_args()
    
    # Modo Directo (Si pasas un argumento desde consola)
    if args.mode == "live":
        print_banner()
        run_live()
    elif args.mode == "backtest":
        print_banner()
        run_backtest()
    elif args.mode == "download":
        print_banner()
        run_download()
    # Modo Interactivo (Si solo escribes el comando zetsu)
    else:
        interactive_menu()

if __name__ == "__main__":
    main()