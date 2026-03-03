import json
import os
import xgboost as xgb
from pathlib import Path
from sklearn.metrics import classification_report, precision_score
from mlops.data_pipeline.feature_store import FeatureStore

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "mlops" / "models"
os.makedirs(MODEL_DIR, exist_ok=True)
G, R, C, Y, B, RS = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[1m", "\033[0m"

def train_juez_supremo():
    print(f"\n{C}{B}MISION 2.2 -- ENTRENANDO JUEZ SUPREMO{RS}")
    store = FeatureStore(str(BASE_DIR / "research" / "blackbox_export.parquet"))
    X_train, X_test, y_train, y_test = store.prepare_data()
    spw = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
    modelo = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.03, scale_pos_weight=spw, eval_metric="logloss")
    modelo.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    
    probs = modelo.predict_proba(X_test)[:, 1]
    best_u, best_p = 0.5, 0.0
    for u in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]:
        p = precision_score(y_test, (probs >= u).astype(int), zero_division=0)
        if p > best_p: best_p, best_u = p, u

    print(f"{G}[+] Modelo entrenado. Mejor Precision: {best_p*100:.1f}% al umbral {best_u*100:.0f}%{RS}")
    modelo.save_model(MODEL_DIR / "meta_labeler.json")
    (MODEL_DIR / "meta_labeler_config.json").write_text(json.dumps({"threshold": best_u, "feature_names": store.get_feature_names()}, indent=2))

if __name__ == "__main__":
    train_juez_supremo()
