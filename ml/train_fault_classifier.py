"""Fault classifier: one Random Forest per demo, trained on labelled synthetic faults.

The anomaly model says "something is wrong"; the classifier names WHAT:
  room  -> normal | hvac_stuck_on
  water -> normal | leak
  cold  -> normal | compressor_failure | door_left_open
(sensor_offline has no readings to classify; the heartbeat rule in Phase 7 catches it.)

  python ml/train_fault_classifier.py

Saves ml/models/classifier_{demo}.joblib = {model, features, classes} and prints a
per-reading report on the separate 7-day test set.
"""
from pathlib import Path

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

from features import FEATURES, build_features
from train_anomaly import load

ML = Path(__file__).resolve().parent

# First minutes of a fault that look exactly like normal operation, so they are not used
# for training (they would teach the model to flag normal behaviour):
#   door: a 1-2 min door opening is normal; hvac: setback only starts after 10 vacant minutes;
#   compressor: the unit is still inside its normal cycle for the first minutes.
ONSET_MIN = {"door_left_open": 3, "hvac_stuck_on": 12, "compressor_failure": 8, "leak": 0}


def train(demo):
    df = load("train", demo)
    onset = df["fault_min"] < df["label"].map(ONSET_MIN).fillna(0)
    keep = ~df["recovery"] & ~((df["label"] != "normal") & onset)   # recovery minutes are neither normal nor fault
    X, y = build_features(df, demo)[keep], df["label"][keep]
    model = RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=3,
                                   class_weight="balanced", n_jobs=-1, random_state=0).fit(X, y)
    joblib.dump({"model": model, "features": FEATURES[demo], "classes": list(model.classes_)},
                ML / "models" / f"classifier_{demo}.joblib")

    test = load("test", demo)
    keep = ~test["recovery"]
    pred = model.predict(build_features(test, demo)[keep])
    print(f"\n=== classifier_{demo} (test set, per reading) ===")
    print(classification_report(test["label"][keep], pred, digits=3, zero_division=0))
    top = sorted(zip(model.feature_importances_, FEATURES[demo]), reverse=True)[:4]
    print("most useful features:", ", ".join(f"{n} {v:.2f}" for v, n in top))


if __name__ == "__main__":
    for demo in ("room", "water", "cold"):
        train(demo)
