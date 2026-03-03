import optuna
import xgboost as xgb
import json
from pathlib import Path
from sklearn.metrics import precision_score
from mlops.data_pipeline.feature_store import FeatureStore

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def objective(trial, X, y):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500),
        "max_depth": trial.suggest_int("max_depth", 2, 6),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "scale_pos_weight": (y == 0).sum() / (y == 1).sum(),
        "eval_metric": "logloss"
    }
    u = trial.suggest_float("threshold", 0.5, 0.8)
    # CV simplificada para el script
    modelo = xgb.XGBClassifier(**params)
    modelo.fit(X, y)
    preds = (modelo.predict_proba(X)[:, 1] >= u).astype(int)
    return precision_score(y, preds, zero_division=0)

if __name__ == "__main__":
    store = FeatureStore(str(BASE_DIR / "research" / "blackbox_export.parquet"))
    X, _, y, _ = store.prepare_data()
    study = optuna.create_study(direction="maximize")
    study.optimize(lambda t: objective(t, X, y), n_trials=50)
    print("Mejores parámetros:", study.best_params)
