import os
from typing import Dict, List

import pandas as pd


_DATAFRAME_CACHE = None


def _get_dataset_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(
        base_dir,
        "data",
        "datasets",
        "nail_polish_datasets.csv",
    )


def _load_dataset() -> pd.DataFrame:
    global _DATAFRAME_CACHE
    if _DATAFRAME_CACHE is not None:
        return _DATAFRAME_CACHE
    csv_path = _get_dataset_path()
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset not found at: {csv_path}")
    df = pd.read_csv(csv_path)
    # Normalize column names for consistency
    df.columns = [c.strip() for c in df.columns]
    _DATAFRAME_CACHE = df
    return df


def recommend_polishes(user_input: Dict[str, str], top_n: int = 3) -> List[int]:
    """
    Return top product IDs that match the user's quiz preferences.

    This simple rule-based recommender filters the dataset by
    skin tone, finish type, dress/outfit color, and occasion.
    Then it picks the first top_n entries. The caller is expected
    to map colors/brands to actual Product rows if needed.
    """
    df = _load_dataset()

    skin = (user_input.get("skin_tone") or "").strip().lower()
    finish = (user_input.get("finish_type") or "").strip().lower()
    outfit = (user_input.get("outfit_color") or "").strip().lower()
    occasion = (user_input.get("occasion") or "").strip().lower()

    def norm(x: str) -> str:
        return (x or "").strip().lower()

    filtered = df[
        (df["skin_tone"].map(norm) == skin)
        & (df["finish_type"].map(norm) == finish)
        & (df["dress_color"].map(norm) == outfit)
        & (df["occasion"].map(norm) == occasion)
    ]

    if filtered.empty:
        # Soften filters progressively
        filtered = df[(df["skin_tone"].map(norm) == skin) & (df["finish_type"].map(norm) == finish)]
        if filtered.empty:
            filtered = df[(df["skin_tone"].map(norm) == skin)]
        if filtered.empty:
            filtered = df

    # For simplicity, assign synthetic IDs based on row index
    # In Flask app we map recommendations to Product table anyway
    top_rows = filtered.head(top_n)
    return list(top_rows.index.astype(int))


def recommend_color_brand_pairs(user_input: Dict[str, str], top_n: int = 3) -> List[Dict[str, str]]:
    """Return top_n color-brand pairs to aid UI rendering."""
    df = _load_dataset()

    ids = recommend_polishes(user_input, top_n=top_n)
    rows = df.iloc[ids]
    results: List[Dict[str, str]] = []
    for _, r in rows.iterrows():
        results.append(
            {
                "hex_color": str(r.get("recommended_hex_code", "#FF69B4")),
                "brand": str(r.get("brand_name", "Unknown")),
            }
        )
    return results





