from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import polars as pl
import polars.selectors as cs

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PARQUET = BASE_DIR / "research" / "blackbox_export.parquet"
G, R, Y, C, B, RS = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"

def _build_target(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.when(pl.col("exit_reason") == "TP").then(1).otherwise(0).alias("target"))

def _numeric_features(df: pl.DataFrame, exclude: list[str]) -> pl.DataFrame:
    drop = [c for c in exclude if c in df.columns]
    return df.drop(drop).select(cs.numeric())

def _point_biserial_corr(feature: np.ndarray, target: np.ndarray) -> float:
    n, n1 = len(feature), target.sum()
    n0 = n - n1
    if n1 == 0 or n0 == 0: return 0.0
    m1, m0, std = feature[target == 1].mean(), feature[target == 0].mean(), feature.std(ddof=1)
    if std == 0: return 0.0
    return (m1 - m0) / std * np.sqrt(n1 * n0 / (n * n))

def run_analysis(parquet_path: Path = PARQUET) -> None:
    print(f"\n{C}{B}{'=' * 66}{RS}\n{C}{B}   MISION 2.1 -- RADIOGRAFIA DEL BLACKBOX{RS}\n{C}{B}{'=' * 66}{RS}\n")
    if not parquet_path.exists():
        print(f"{R}[!] No se encontro: {parquet_path}{RS}"); sys.exit(1)
    df = _build_target(pl.read_parquet(parquet_path))
    total, wins = len(df), df["target"].sum()
    wr = (wins / total) * 100
    print(f"{G}[+] Trades: {total:,} | WR Global: {wr:.1f}%{RS}")

    EXCLUDE = ["exit_reason", "pnl", "pnl_pct", "outcome", "bars_in_trade", "rr_realized", "trade_id", "entry_time", "exit_time", "timestamp", "tier", "direction", "target"]
    X_df, y = _numeric_features(df, EXCLUDE), df["target"].to_numpy().astype(int)
    corrs = sorted([(col, _point_biserial_corr(X_df[col].fill_nan(0).fill_null(0).to_numpy(), y)) for col in X_df.columns], key=lambda t: abs(t[1]), reverse=True)

    print(f"\n{B}--- TOP VARIABLES (Impacto en WIN) ---{RS}")
    for name, corr in corrs[:20]:
        col_c = G if corr > 0 else R
        print(f"  {name:<35} {col_c}{corr:+.4f}{RS}  {col_c}{'#' * int(abs(corr)*30)}{RS}")

if __name__ == "__main__":
    run_analysis()
