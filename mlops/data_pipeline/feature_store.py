from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import polars as pl
import polars.selectors as cs

_LABELS_TO_DROP = ["exit_reason", "pnl", "pnl_pct", "outcome", "bars_in_trade", "rr_realized", "trade_id", "entry_time", "exit_time", "timestamp", "tier"]

class FeatureStore:
    def __init__(self, parquet_path: str) -> None:
        self.filepath = Path(parquet_path)
        if not self.filepath.exists(): raise FileNotFoundError(f"ADN no encontrado en: {self.filepath}")
        self._feature_names: Optional[list[str]] = None

    def get_feature_names(self) -> list[str]: return self._feature_names or []

    def prepare_data(self, test_size: float = 0.2) -> tuple:
        df = pl.read_parquet(self.filepath)
        df = df.with_columns(pl.when(pl.col("exit_reason") == "TP").then(1).otherwise(0).alias("target"))
        if "timestamp" in df.columns:
            try:
                df = df.with_columns(pl.col("timestamp").str.to_datetime(strict=False).alias("_dt"))
                df = df.with_columns([pl.col("_dt").dt.hour().alias("hora_dia"), pl.col("_dt").dt.weekday().alias("dia_semana")]).drop("_dt")
            except: pass
        drop_cols = [c for c in _LABELS_TO_DROP if c in df.columns]
        X_df = df.drop(drop_cols + ["target"]).select(cs.numeric()).fill_nan(0).fill_null(0)
        self._feature_names = X_df.columns
        train_idx = int(len(df) * (1 - test_size))
        return X_df.head(train_idx).to_numpy(), X_df.tail(len(df)-train_idx).to_numpy(), df["target"].head(train_idx).to_numpy(), df["target"].tail(len(df)-train_idx).to_numpy()
