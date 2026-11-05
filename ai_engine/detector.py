"""Runs all detection layers once per simulated minute and returns Findings.

  Layer 1  rules        config/alert_rules.yaml (critical alarms, offline heartbeat)
  Layer 2  ML           Random Forest names the fault; Isolation Forest is the safety net
                        for patterns nobody labelled (raised only if the RF sees nothing)
  Layer 3  forecast     cold units: "will leave the safe band in ~N min"

`detect()` is pure computation on copies of the recent readings, so the backend runs
it in a worker thread; the AlertManager then turns findings into alerts.
"""
import pandas as pd

from ai_engine.model_loader import build_features, forecast
from ai_engine.rules import make_finding, offline_finding, run_rules

DEMO = {"thermostat": "room", "water": "water", "cold_chain": "cold"}
MIN_HISTORY = 10          # readings needed before the ML layers have meaningful rolling features
CLASSIFIER_MIN_PROB = 0.5
ANOMALY_ACTION = "Inspect the device and its area: the AI saw a pattern that does not occur in normal operation."


class Detector:
    def __init__(self, rules_cfg, devices_cfg, models):
        self.rules = rules_cfg["rules"]
        self.anomaly_consecutive = rules_cfg["anomaly"]["min_consecutive"]
        self.anomaly_demos = set(rules_cfg["anomaly"]["alert_demos"])
        self.models = models
        self.action = {r["fault_type"]: r["action"] for r in self.rules.values()}

        # display names and normal flows, by device_id
        self.names, self.normal = {}, {}
        for floor, rooms in devices_cfg["rooms"]["floors"].items():
            for r in rooms:
                self.names[f"thermo-{r}"] = f"Room {r}"
        for z in devices_cfg["water_zones"]:
            self.names[z["device_id"]] = z["name"]
            self.normal[z["device_id"]] = z["normal_flow_lpm"]
        for u in devices_cfg["cold_units"]:
            self.names[u["device_id"]] = u["name"]

        # state carried between minutes ("2 readings in a row")
        self.prev_label = {}      # device_id -> classifier label last minute
        self.anomaly_run = {}     # device_id -> consecutive anomalous minutes

    def detect(self, histories, silent):
        """histories: device_id -> recent readings (oldest first); silent: device_id -> minutes without data.
        Returns (findings, breach_eta) where breach_eta: device_id -> minutes until a predicted breach."""
        findings, eta = [], {}
        for did, minutes in silent.items():
            findings.append(offline_finding(did, self.names.get(did, did), minutes, self.rules))

        by_demo = {"room": {}, "water": {}, "cold": {}}
        for did, h in histories.items():
            if h and did not in silent:
                by_demo[DEMO[h[-1]["type"]]][did] = h

        for demo, devices in by_demo.items():
            for did, h in devices.items():
                findings += run_rules(h, self.names.get(did, did), self.rules, self.normal.get(did))
            if self.models.get(demo):
                findings += self._ml(demo, devices)
            if demo == "cold":
                findings += self._forecast(devices, eta)
        return findings, eta

    # ---------- Layer 2 ----------
    def _ml(self, demo, devices):
        ready = {d: h for d, h in devices.items() if len(h) >= MIN_HISTORY}
        if not ready:
            return []
        df = pd.DataFrame([p for h in ready.values() for p in h])
        X = build_features(df, demo)
        last = df.groupby("device_id", sort=False).tail(1).index      # newest reading of each device
        an, clf = self.models[demo]["anomaly"], self.models[demo]["classifier"]
        scores = -an["model"].score_samples(X.loc[last, an["features"]])
        probs = clf["model"].predict_proba(X.loc[last, clf["features"]])

        found = []
        for i, idx in enumerate(last):
            did = df.at[idx, "device_id"]
            p, name = ready[did][-1], self.names.get(did, did)

            # Random Forest: the same fault 2 minutes in a row -> name it
            k = probs[i].argmax()
            label = clf["classes"][k] if probs[i][k] >= CLASSIFIER_MIN_PROB else "normal"
            if label != "normal" and self.prev_label.get(did) == label:
                found.append(make_finding(p, name, label, "classifier", "warning", probs[i][k], self.action[label],
                                          f"Random Forest: {label.replace('_', ' ')} ({probs[i][k]:.0%})",
                                          self.normal.get(did)))
            self.prev_label[did] = label

            # Isolation Forest: unusual for N minutes and the RF has no name for it -> "unusual readings"
            run = self.anomaly_run.get(did, 0) + 1 if scores[i] > an["threshold"] else 0
            self.anomaly_run[did] = run
            if run >= self.anomaly_consecutive and label == "normal" and demo in self.anomaly_demos:
                confidence = min(0.95, 0.5 + 5 * (scores[i] - an["threshold"]))   # just over threshold = 0.5
                found.append(make_finding(p, name, "anomaly", "anomaly", "warning", confidence, ANOMALY_ACTION,
                                          f"Isolation Forest score {scores[i]:.2f} (normal below {an['threshold']:.2f})",
                                          self.normal.get(did)))
        return found

    # ---------- Layer 3 ----------
    def _forecast(self, devices, eta):
        found = []
        for did, h in devices.items():
            p = h[-1]
            warn, minutes = forecast([x["temp_c"] for x in h], [x["door_open"] for x in h],
                                     p["safe_min_c"], p["safe_max_c"])
            if warn:
                eta[did] = minutes
                name = self.names.get(did, did)
                found.append(make_finding(p, name, "compressor_failure", "forecast", "warning", 0.8,
                                          self.action["compressor_failure"],
                                          f"Trend predicts leaving the safe band in ~{minutes:.0f} min",
                                          title=f"Breach predicted: {name}"))
        return found
