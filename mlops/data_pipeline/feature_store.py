import polars as pl
import polars.selectors as cs
import numpy as np
from pathlib import Path

class FeatureStore:
    def __init__(self, parquet_path: str):
        self.filepath = Path(parquet_path)
        if not self.filepath.exists():
            raise FileNotFoundError(f"\033[91m[CRÍTICO] No se encontró el ADN en: {self.filepath}\033[0m")

    def prepare_data(self, test_size: float = 0.2):
        """
        Lee el Blackbox, extrae temporalidad, aplica la regla del Juez Supremo 
        y divide cronológicamente los tensores.
        """
        print(f"[*] Leyendo Blackbox (ADN) desde: {self.filepath.name}")
        df = pl.read_parquet(self.filepath)

        # ── 1. DEFINICIÓN DEL VECTOR Y (TARGET) ──
        if "exit_reason" not in df.columns:
            raise ValueError("Falta la columna 'exit_reason' en la Caja Negra.")
            
        df = df.with_columns(
            pl.when(pl.col("exit_reason") == "TP")
            .then(1)
            .otherwise(0)
            .alias("target")
        )

        # ── 2. INGENIERÍA DE CARACTERÍSTICAS (LA SOLUCIÓN PROFESIONAL) ──
        # Transformamos el texto de la fecha en ciclos matemáticos
        if "timestamp" in df.columns:
            try:
                # Convertimos el string a objeto Datetime
                df = df.with_columns(
                    pl.col("timestamp").str.to_datetime(strict=False).alias("dt_parsed")
                )
                # Extraemos Hora (0-23) y Día de la Semana (1-7)
                df = df.with_columns([
                    pl.col("dt_parsed").dt.hour().alias("hora_dia"),
                    pl.col("dt_parsed").dt.weekday().alias("dia_semana")
                ])
                # Destruimos el objeto datetime intermedio
                df = df.drop("dt_parsed")
                print("[*] Ingeniería de Features: Ciclos de tiempo extraídos (Hora y Día).")
            except Exception as e:
                print(f"\033[93m[*] Aviso: No se pudo procesar la temporalidad: {e}\033[0m")

        # ── 3. LIMPIEZA FINAL Y ESCUDO DE TITANIO ──
        # Agregamos a los 4 espías del futuro (outcome, pnl_pct, bars_in_trade, rr_realized)
        cols_to_drop = [
            "exit_reason", "pnl", "pnl_pct", "outcome", 
            "bars_in_trade", "rr_realized", "trade_id", 
            "entry_time", "exit_time", "timestamp", "tier"
        ]
        drop_cols = [c for c in cols_to_drop if c in df.columns]
        
        # Eliminamos la basura y separamos la X de la Y
        X_df = df.drop(drop_cols + ["target"])
        X_df = X_df.select(cs.numeric()) # Filtro absoluto: Solo pasan números
        y_df = df.select(["target"])

        # ── 4. SPLIT CRONOLÓGICO ──
        total_rows = len(df)
        train_idx = int(total_rows * (1 - test_size))

        X_train = X_df.head(train_idx).to_numpy()
        y_train = y_df.head(train_idx).to_numpy().ravel()
        
        X_test  = X_df.tail(total_rows - train_idx).to_numpy()
        y_test  = y_df.tail(total_rows - train_idx).to_numpy().ravel()

        print(f"[✓] Features numéricas listas: {len(X_df.columns)} variables por trade.")
        print(f"[✓] Set de Entrenamiento: {len(X_train)} trades históricos.")
        print(f"[✓] Set de Prueba (Unseen): {len(X_test)} trades futuros.")
        
        win_rate_train = (y_train.sum() / len(y_train)) * 100
        print(f"[!] Ratio de 'Unicornios puros' en Train: {win_rate_train:.1f}%")

        return X_train, X_test, y_train, y_test

if __name__ == "__main__":
    ruta_parquet = "research/blackbox_export.parquet"
    store = FeatureStore(ruta_parquet)
    X_tr, X_te, y_tr, y_te = store.prepare_data()