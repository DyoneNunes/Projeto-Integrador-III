"""
Sentinela Ambiental - Treinamento do Modelo LightGBM
Roda OFFLINE: python src/train_model.py

Conecta ao PostgreSQL, extrai features dos dados históricos rotulados,
treina um classificador LightGBM e salva em models/sentinela_v1.txt
"""
import os
import sys
import numpy as np
import psycopg2
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION = os.getenv("DB_CONNECTION")
MODEL_OUTPUT = os.path.join(os.path.dirname(__file__), "..", "models", "sentinela_v1.txt")


def extract_training_data():
    """
    Extrai dados rotulados do PostgreSQL.
    Label: 1 = CRITICAL (fogo real), 0 = INFO/LOW (falso positivo ou ambiente)
    """
    conn = psycopg2.connect(DB_CONNECTION)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sr.latitude,
            sr.longitude,
            sr.frp,
            sr.temperature_k,
            sr.confidence,
            EXTRACT(HOUR FROM sr.reading_timestamp) AS hour,
            EXTRACT(MONTH FROM sr.reading_timestamp) AS month,
            CASE WHEN ah.severity = 'CRITICAL' THEN 1 ELSE 0 END AS label
        FROM sentinela_ambiental.sensor_readings sr
        JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
        WHERE sr.temperature_k IS NOT NULL
          AND sr.frp IS NOT NULL
        ORDER BY sr.reading_timestamp DESC
        LIMIT 50000
    """)

    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("[!] Nenhum dado de treinamento encontrado no banco.")
        sys.exit(1)

    data = np.array(rows, dtype=np.float64)
    X = data[:, :7]  # lat, lng, frp, temp_k, conf, hour, month
    y = data[:, 7]   # label

    # Adiciona feature de densidade de vizinhos (placeholder = 0)
    neighbors = np.zeros((X.shape[0], 1))
    X = np.hstack([X, neighbors])

    print(f"[+] Dataset: {X.shape[0]} amostras, {X.shape[1]} features")
    print(f"    Positivos (fogo): {int(y.sum())} ({y.mean()*100:.1f}%)")
    print(f"    Negativos: {int(len(y) - y.sum())} ({(1-y.mean())*100:.1f}%)")

    return X, y


def train():
    print("=" * 60)
    print("  SENTINELA AMBIENTAL - Treinamento LightGBM")
    print("=" * 60)

    X, y = extract_training_data()

    # Split treino/teste
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print(f"\n[*] Treino: {len(X_train)} | Teste: {len(X_test)}")

    # Dataset LightGBM
    feature_names = ['lat', 'lng', 'frp', 'temp_k', 'confidence', 'hour', 'month', 'neighbors']
    train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
    test_data = lgb.Dataset(X_test, label=y_test, feature_name=feature_names, reference=train_data)

    # Parâmetros
    params = {
        'objective': 'binary',
        'metric': 'binary_logloss',
        'num_leaves': 31,
        'max_depth': 6,
        'learning_rate': 0.1,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'verbose': -1,
        'seed': 42,
    }

    # Treina
    model = lgb.train(
        params,
        train_data,
        num_boost_round=200,
        valid_sets=[test_data],
    )

    # Avaliação
    y_proba = model.predict(X_test)
    y_pred = (y_proba >= 0.5).astype(int)

    print("\n" + "=" * 60)
    print("  RESULTADOS")
    print("=" * 60)
    print(classification_report(y_test, y_pred, target_names=['Falso/Ambiente', 'Fogo Real']))
    print(f"  AUC-ROC: {roc_auc_score(y_test, y_proba):.4f}")

    # Feature importance
    importances = model.feature_importance(importance_type='gain')
    total = importances.sum()
    norm_importances = importances / total if total > 0 else importances
    print("\n  Feature Importance:")
    for name, imp in sorted(zip(feature_names, norm_importances), key=lambda x: -x[1]):
        bar = '#' * int(imp * 40)
        print(f"    {name:12s} {imp:.4f} {bar}")

    # Salva modelo
    os.makedirs(os.path.dirname(MODEL_OUTPUT), exist_ok=True)
    model.save_model(MODEL_OUTPUT)
    print(f"\n[+] Modelo salvo em: {MODEL_OUTPUT}")
    print(f"    Tamanho: {os.path.getsize(MODEL_OUTPUT) / 1024:.1f} KB")


if __name__ == "__main__":
    train()
