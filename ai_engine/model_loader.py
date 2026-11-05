"""Load the trained models from ml/models and expose the shared ML code.

The ml/ scripts are run as plain scripts (flat imports such as `from features import ...`),
so we put ml/ on the import path here instead of turning it into a package.
If a model file is missing, that demo runs with rules + forecast only.
"""
import sys
from pathlib import Path

import joblib

ML_DIR = Path(__file__).resolve().parent.parent / "ml"
sys.path.insert(0, str(ML_DIR))

from features import build_features  # noqa: E402,F401  (re-exported for the detector)
from forecast import forecast  # noqa: E402,F401

DEMOS = ("room", "water", "cold")


def load_models(model_dir=ML_DIR / "models"):
    """{demo: {"anomaly": bundle, "classifier": bundle} or None}"""
    models = {}
    for demo in DEMOS:
        try:
            models[demo] = {
                "anomaly": joblib.load(model_dir / f"anomaly_{demo}.joblib"),
                "classifier": joblib.load(model_dir / f"classifier_{demo}.joblib"),
            }
        except FileNotFoundError:
            print(f"[ai] no trained models for '{demo}' in {model_dir}: rules + forecast only "
                  "(train with: cd ml; python train_anomaly.py; python train_fault_classifier.py)")
            models[demo] = None
    return models
