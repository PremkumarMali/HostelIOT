"""Layer 2: one Isolation Forest per demo, trained on NORMAL readings only.

Isolation Forest isolates points with random splits; unusual points are isolated in
fewer splits, so they get a higher anomaly score. It never sees a labelled fault, so
it can also catch fault types we did not think of.

  python ml/train_anomaly.py

Saves ml/models/anomaly_{room,water,cold}.joblib = {model, features, threshold}.
threshold = the 99.9th percentile of the scores of normal training readings,
i.e. about 1 normal reading in 1,000 scores above it (alerts also need 2 in a row).
With 30 devices x 1,440 readings a day, a looser threshold means too many alerts per day.
"""
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import IsolationForest

from features import FEATURES, build_features

ML = Path(__file__).resolve().parent
PERCENTILE = 99.9
MAX_ROWS = 150_000          # plenty for Isolation Forest; keeps training to seconds


def load(name, demo):
    df = pd.read_csv(ML / "data" / "synthetic" / f"{name}_{demo}.csv.gz")
    return df.sort_values(["device_id", "ts"]).reset_index(drop=True)


def anomaly_score(bundle, X):
    """Higher = more unusual (sklearn's score_samples is the opposite sign)."""
    return -bundle["model"].score_samples(X[bundle["features"]])


def train(demo):
    df = load("train", demo)
    X = build_features(df, demo)
    normal = X[(df["label"] == "normal") & ~df["recovery"]]
    sample = normal.sample(min(MAX_ROWS, len(normal)), random_state=0)
    model = IsolationForest(n_estimators=200, random_state=0, n_jobs=-1).fit(sample)
    bundle = {"model": model, "features": FEATURES[demo]}
    bundle["threshold"] = float(pd.Series(anomaly_score(bundle, normal)).quantile(PERCENTILE / 100))
    (ML / "models").mkdir(exist_ok=True)
    joblib.dump(bundle, ML / "models" / f"anomaly_{demo}.joblib")
    print(f"anomaly_{demo}: trained on {len(sample):,} normal rows, threshold {bundle['threshold']:.3f}")


if __name__ == "__main__":
    for demo in ("room", "water", "cold"):
        train(demo)
