import os
import numpy as np
import xgboost as xgb
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix, precision_score
from mlops.data_pipeline.feature_store import FeatureStore

# ── CONFIGURACIÓN DE RUTAS ──
BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "mlops" / "models"
os.makedirs(MODEL_DIR, exist_ok=True)
PARQUET_PATH = BASE_DIR / "research" / "blackbox_export.parquet"

def train_juez_supremo():
    print("\n\033[96m[+] Iniciando el Gimnasio: Entrenamiento del Juez Supremo (XGBoost)\033[0m")
    
    # 1. Cargar el ADN
    store = FeatureStore(str(PARQUET_PATH))
    X_train, X_test, y_train, y_test = store.prepare_data(test_size=0.2)
    
    # 2. Calcular el Balance de Pesos (scale_pos_weight)
    ceros = np.sum(y_train == 0)
    unos  = np.sum(y_train == 1)
    peso_balance = ceros / unos
    print(f"[*] Desbalance detectado: Aplicando multiplicador de castigo a Unicornios: {peso_balance:.2f}x")
    
    # 3. Configurar la Bestia (XGBoost)
    modelo = xgb.XGBClassifier(
        n_estimators=100,          # Número de árboles de decisión
        max_depth=3,               # Árboles poco profundos (evita memorizar el pasado)
        learning_rate=0.05,        # Aprendizaje lento y seguro
        scale_pos_weight=peso_balance, # Obliga a la IA a prestar atención a los Win
        random_state=42,
        eval_metric="logloss"
    )
    
    # 4. Entrenar
    print("[*] Entrenando la Red de Árboles... (Fuerza Bruta Matemática)")
    modelo.fit(X_train, y_train)
    
    # 5. Evaluar con los datos del Futuro (Test Set Unseen)
    print("\n\033[93m[+] Evaluando al Juez con Múltiples Umbrales de Letalidad:\033[0m")
    
    # En lugar de predecir 1 o 0, le pedimos el % exacto de seguridad que tiene la IA
    probabilidades = modelo.predict_proba(X_test)[:, 1] 
    
    # Escaneamos desde el estándar 50% hasta el nivel de un francotirador 90%
    umbrales = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90]
    
    mejor_umbral = 0.50
    mejor_precision = 0.0
    
    for umbral in umbrales:
        # Si la IA está más segura que el umbral, dispara (1), si no, aborta (0)
        predicciones_umbral = (probabilidades >= umbral).astype(int)
        
        trades_aprobados = np.sum(predicciones_umbral)
        
        if trades_aprobados > 0:
            precision = precision_score(y_test, predicciones_umbral, zero_division=0)
            color = "\033[92m" if precision > 0.40 else "\033[91m"
            print(f"[*] Umbral {umbral*100:.0f}% -> {color}Precisión: {precision*100:.1f}%\033[0m | Trades Disparados: {trades_aprobados}")
            
            if precision > mejor_precision:
                mejor_precision = precision
                mejor_umbral = umbral
        else:
            print(f"[*] Umbral {umbral*100:.0f}% -> Precisión: N/A | Trades Disparados: 0 (Demasiado exigente)")

    print(f"\n\033[96m[!] El punto dulce estadístico está en exigirle un {mejor_umbral*100:.0f}% de seguridad a la IA.\033[0m")

    # 7. Guardar el Cerebro
    model_path = MODEL_DIR / "meta_labeler.json"
    modelo.save_model(model_path)
    print(f"\n\033[96m[✓] Cerebro compilado y guardado en producción: {model_path}\033[0m")

if __name__ == "__main__":
    train_juez_supremo()