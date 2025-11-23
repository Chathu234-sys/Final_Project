import os
import pickle
from typing import Dict, List

import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MODEL_DIR = os.path.join(_BASE_DIR, "data", "trained_models", "NailPolish_Model")

def _load_pickle(name):
    path = os.path.join(_MODEL_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing model file: {path}")
    with open(path, "rb") as f:
        return pickle.load(f)

# Load pretrained assets
_preprocessor = _load_pickle("preprocessor_v3.pkl")
_scaler = _load_pickle("scaler_v3.pkl")
_kmeans = _load_pickle("Kmeans_v3.pkl")         # only if using clustering
_label_encoder = _load_pickle("label_encoder_v3.pkl")

_model = load_model(os.path.join(_MODEL_DIR, "nail_polish_model_v3.h5"))

def _load_dataset() -> pd.DataFrame:
    csv_path = os.path.join(
        _BASE_DIR, "data", "datasets", "nail_polish_datasets.csv"
    )
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset not found at {csv_path}")

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    return df

def recommend_polishes(user_input: Dict[str, str], top_n: int = 3) -> List[int]:
    """
    Generate recommendations using the trained ML model.
    """

    df = _load_dataset()
    input_df = pd.DataFrame([user_input])
    X = _preprocessor.transform(input_df)
    X_scaled = _scaler.transform(X)
    pred_class = _model.predict(X_scaled)
    pred_label = np.argmax(pred_class, axis=1)[0]
    decoded_label = _label_encoder.inverse_transform([pred_label])[0]
    results = df[df["ml_label"] == decoded_label]

    if results.empty:
       
        results = df.head(top_n)

    return list(results.index[:top_n])

def recommend_color_brand_pairs(user_input: Dict[str, str], top_n: int = 3):
    ids = recommend_polishes(user_input, top_n)

    final = []
    for idx in ids:
        row = df.iloc[idx]
        final.append({
            "hex_color": str(row.get("recommended_hex_code","#FF69B4")),
            "brand": str(row.get("brand_name", "Unknown")),
            "shade_name": str(row.get("shade_name", "N/A"))
        })

    return final


