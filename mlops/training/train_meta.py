import os
import pickle
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models, metrics, regularizers # type: ignore
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight
from mlops.data_pipeline.feature_store import FeatureStore

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "mlops" / "models"
os.makedirs(MODEL_DIR, exist_ok=True)

G, R, C, Y, B, RS = "\033[92m", "\033[91m", "\033[96m", "\033[93m", "\033[1m", "\033[0m"

def build_tri_neuronal_model(input_dim: int) -> models.Sequential:
    """Arquitectura Tri-Neuronal blindada contra sobreajuste."""
    model = models.Sequential([
        layers.Input(shape=(input_dim,)),
        layers.Dense(64, activation='relu', kernel_regularizer=regularizers.l2(0.005)),
        layers.Dropout(0.3),
        layers.Dense(32, activation='relu', kernel_regularizer=regularizers.l2(0.005)),
        layers.Dropout(0.2),
        layers.Dense(1, activation='sigmoid')
    ])
    
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=[metrics.Precision(name='precision'), metrics.AUC(name='auc')]
    )
    return model

def train_juez_supremo() -> None:
    print(f"\n{C}{B}MISION 2.3 -- ENTRENANDO RED NEURONAL (META-LABELER){RS}")
    
    store = FeatureStore(str(BASE_DIR / "research" / "blackbox_export.parquet"))
    
    # ⚠️ EL SPLIT DEBE SER CRONOLÓGICO, NO ALEATORIO.
    X_train, X_test, y_train, y_test = store.prepare_data(test_size=0.3)
    
    print(f"{Y}[*] Normalizando matriz de características (Z-Score Scaling)...{RS}")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # --- FIX AUDITORÍA: BALANCEO DE CLASES ---
    print(f"{Y}[*] Calculando pesos de desbalance de mercado...{RS}")
    classes = np.unique(y_train)
    weights = compute_class_weight('balanced', classes=classes, y=y_train)
    class_weights = dict(zip(classes, weights))
    print(f"    Pesos aplicados: {class_weights}")
    
    input_dim = X_train_scaled.shape[1]
    model = build_tri_neuronal_model(input_dim)
    
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor='val_loss', 
        patience=15, 
        restore_best_weights=True,
        verbose=1
    )
    
    print(f"{Y}[*] Entrenando Red Tri-Neuronal de {input_dim} features...{RS}")
    model.fit(
        X_train_scaled, y_train,
        validation_data=(X_test_scaled, y_test),
        epochs=150,
        batch_size=128,
        class_weight=class_weights,  # FIX APLICADO AQUÍ
        callbacks=[early_stopping],
        verbose=0
    )
    
    loss, precision, auc = model.evaluate(X_test_scaled, y_test, verbose=0)
    
    print(f"{G}[+] Red Entrenada. Precision OOS: {precision*100:.1f}% | AUC: {auc:.3f}{RS}")
    
    model.save(MODEL_DIR / "meta_labeler_nn.keras")
    with open(MODEL_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)
        
    print(f"{G}[+] Artefactos (.keras y .pkl) exportados a {MODEL_DIR}{RS}")

if __name__ == "__main__":
    train_juez_supremo()