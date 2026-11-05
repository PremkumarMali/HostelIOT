"""Evaluate the AI layers on data they never trained on.

  python ml/evaluate.py            # synthetic test set + real-data checks (~1-2 min)

Part A - synthetic 7-day test set, per fault type and detection method:
  An ALERT = a run of flagged minutes on one device (gaps up to 10 min merged), like the
  alert manager will raise. A method flags a minute when:
    anomaly     Isolation Forest score above its threshold N readings in a row, N from
                config/alert_rules.yaml anomaly.min_consecutive (type-agnostic:
                precision counts an alert as correct if ANY fault is active on that device)
    classifier  Random Forest predicts a fault 2 readings in a row (the alert carries that type)
    forecast    trend line predicts a cold-chain breach within 30 min (cold units only)
    heartbeat   no reading for 3+ min (sensor_offline; from the gaps in the data)
  recall      = fault episodes caught while the fault was active / all episodes
  precision   = alerts that point at a real episode (same device; classifier: same type) / all alerts
  false alarms per day = alerts that match no episode / test days
  delay       = minutes from fault start to first flag (median over caught episodes)
  Alerts up to 30 min after a fault ends are not false alarms (the unit is still recovering).

Part B - real public data (ml/data/raw, see README):
  NAB machine temperature: Isolation Forest on a real failure series
  LBNL fan coil unit: Random Forest + Isolation Forest on real labelled HVAC faults
  UCI occupancy: is our simulated sensor noise realistic?

Writes ml/evaluation_report.md (also printed).
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import classification_report, f1_score

from features import FEATURES, build_features, rolling_slope
from forecast import forecast_flags
from train_anomaly import anomaly_score, load

ML = Path(__file__).resolve().parent
RAW = ML / "data" / "raw"
MERGE_GAP = 10          # flagged minutes closer than this belong to one alert
GRACE = 30              # minutes after a fault ends that are forgiven
CONSECUTIVE = 2         # Random Forest / forecast: same answer 2 readings in a row
# Isolation Forest alerts use the live engine's setting, so the report matches what the dashboard does
ANOMALY_CONSECUTIVE = yaml.safe_load((ML.parent / "config" / "alert_rules.yaml").read_text(encoding="utf-8"))[
    "anomaly"]["min_consecutive"]
SILENT_MIN = 3
TEST_DAYS = 7
report = []


def out(line=""):
    print(line)
    report.append(line)


# ---------------------------------------------------------------- Part A helpers
def minutes(ts):
    return (pd.to_datetime(ts.str.slice(0, 19)) - pd.Timestamp("2026-09-01")).dt.total_seconds() // 60


def consecutive(flags, device, n=CONSECUTIVE):
    """True where this and the previous n-1 readings of the same device are all flagged."""
    out = flags.copy()
    for k in range(1, n):
        out &= flags.groupby(device).shift(k, fill_value=False)
    return out


def alerts_from(df, flags, kind=None):
    """Turn per-minute flags into alerts: [(device, start_minute, type)]."""
    alerts = []
    sub = df[flags]
    for dev, g in sub.groupby("device_id"):
        last = None
        for m, k in zip(g["minute"], g[kind] if kind else [None] * len(g)):
            if last is None or m - last > MERGE_GAP:
                alerts.append((dev, m, k))
            last = m
    return alerts


def score(episodes, alerts, flagged_minutes, fault, typed):
    """Recall / delay for one fault type; precision for the alerts of that type (or all, if untyped)."""
    eps = episodes[episodes["fault"] == fault]
    delays = []
    for _, e in eps.iterrows():
        hits = [m for m in flagged_minutes.get(e["device_id"], []) if e["s"] <= m <= e["e"]]
        if hits:
            delays.append(min(hits) - e["s"])
    relevant = [a for a in alerts if not typed or a[2] == fault]

    def matches(a):
        ok = episodes[(episodes["device_id"] == a[0]) & (episodes["s"] <= a[1]) & (a[1] <= episodes["e"] + GRACE)]
        return len(ok) and (not typed or (ok["fault"] == a[2]).any())

    good = sum(bool(matches(a)) for a in relevant)
    recall = len(delays) / len(eps) if len(eps) else float("nan")
    precision = good / len(relevant) if relevant else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0
    return {"episodes": len(eps), "recall": recall, "precision": precision, "f1": f1,
            "false_alarms_per_day": (len(relevant) - good) / TEST_DAYS,
            "median_delay_min": float(np.median(delays)) if delays else float("nan")}


def table(rows):
    out("| Fault | Method | Episodes | Recall | Precision | F1 | False alarms/day | Median delay (min) |")
    out("|---|---|---|---|---|---|---|---|")
    for fault, method, r in rows:
        out(f"| {fault} | {method} | {r['episodes']} | {r['recall']:.2f} | {r['precision']:.2f} | {r['f1']:.2f} "
            f"| {r['false_alarms_per_day']:.1f} | {r['median_delay_min']:.0f} |")


FAULTS = {"room": ["hvac_stuck_on"], "water": ["leak"], "cold": ["compressor_failure", "door_left_open"]}


def part_a():
    out("## A. Synthetic test set (7 days, 30 devices, unseen seed)\n")
    ep = pd.read_csv(ML / "data" / "synthetic" / "test_episodes.csv")
    t0 = pd.Timestamp("2026-09-01")
    ep["s"] = (pd.to_datetime(ep["start"].str.slice(0, 19)) - t0).dt.total_seconds() // 60
    ep["e"] = (pd.to_datetime(ep["end"].str.slice(0, 19)) - t0).dt.total_seconds() // 60
    rows, results = [], {}

    for demo, faults in FAULTS.items():
        df = load("test", demo)
        df["minute"] = minutes(df["ts"])
        X = build_features(df, demo)
        episodes = ep[ep["demo"] == demo]

        an = joblib.load(ML / "models" / f"anomaly_{demo}.joblib")
        flag_an = consecutive(pd.Series(anomaly_score(an, X) > an["threshold"], index=df.index), df["device_id"],
                              ANOMALY_CONSECUTIVE)
        clf = joblib.load(ML / "models" / f"classifier_{demo}.joblib")
        df["pred"] = clf["model"].predict(X[clf["features"]])
        is_fault = df["pred"] != "normal"
        same = df["pred"] == df.groupby("device_id")["pred"].shift(1)
        flag_clf = is_fault & same

        methods = {"anomaly (IF)": (flag_an, None), "classifier (RF)": (flag_clf, "pred")}
        if demo == "cold":
            fc = np.concatenate([forecast_flags(g) for _, g in df.groupby("device_id", sort=False)])
            flag_fc = pd.Series(fc, index=np.concatenate([g.index for _, g in df.groupby("device_id", sort=False)]))
            methods["forecast (trend)"] = (consecutive(flag_fc.reindex(df.index), df["device_id"]), None)

        for name, (flags, kind) in methods.items():
            alerts = alerts_from(df, flags, kind)
            flagged = df[flags].groupby("device_id")["minute"].apply(list).to_dict()
            for fault in faults:
                if name.startswith("forecast") and fault != "compressor_failure":
                    continue                        # the forecast targets slow drifts, not door faults
                r = score(episodes, alerts, flagged, fault, typed=kind is not None)
                if name.startswith("forecast"):
                    # forecast is about warning BEFORE the breach: lead time vs first out-of-band reading
                    r["lead_min"] = forecast_lead(df, flags, episodes[episodes["fault"] == fault])
                rows.append((fault, name, r))
                results[f"{fault}/{name}"] = r

    rows.append(("sensor_offline", "heartbeat rule", offline_metrics(ep)))
    results["sensor_offline/heartbeat rule"] = rows[-1][2]
    table(rows)
    lead = results.get("compressor_failure/forecast (trend)", {}).get("lead_min")
    if lead is not None:
        out(f"\nForecast lead time: the trend warning came a median **{lead:.0f} min before** the walk-in / "
            "freezer actually left its safe band (compressor failures that breached).")
    return results


def forecast_lead(df, flags, eps):
    leads = []
    for _, e in eps.iterrows():
        d = df[(df["device_id"] == e["device_id"]) & (df["minute"] >= e["s"]) & (df["minute"] <= e["e"])]
        out_band = d[(d["temp_c"] > d["safe_max_c"]) | (d["temp_c"] < d["safe_min_c"])]
        warned = d[flags.loc[d.index]]
        if len(out_band) and len(warned):
            leads.append(out_band["minute"].iloc[0] - warned["minute"].iloc[0])
    return float(np.median(leads)) if leads else None


def offline_metrics(ep):
    """Heartbeat rule straight from the data: a gap of 3+ minutes in a device's readings."""
    gaps, alerts = {}, []
    for demo in ("room", "water", "cold"):
        df = load("test", demo)
        df["minute"] = minutes(df["ts"])
        for dev, g in df.groupby("device_id"):
            m = g["minute"].to_numpy()
            for a, b in zip(m[:-1], m[1:]):
                if b - a - 1 >= SILENT_MIN:
                    alerts.append((dev, a + SILENT_MIN + 1, "sensor_offline"))
    flagged = {}
    for dev, m, _ in alerts:
        flagged.setdefault(dev, []).append(m)
    return score(ep, alerts, flagged, "sensor_offline", typed=True)


# ---------------------------------------------------------------- Part B: real data
def nab():
    path = RAW / "nab" / "machine_temperature_system_failure.csv"
    if not path.exists():
        out("NAB data missing: run `python ml/download_datasets.py`.")
        return {}
    df = pd.read_csv(path, parse_dates=["timestamp"])
    windows = json.loads((RAW / "nab" / "combined_windows.json").read_text())[
        "realKnownCause/machine_temperature_system_failure.csv"]
    v = df["value"]
    X = pd.DataFrame({
        "value": v,
        "mean_12": v.rolling(12, min_periods=1).mean(),
        "std_12": v.rolling(12, min_periods=2).std(),
        "z_288": (v - v.rolling(288, min_periods=12).mean()) / v.rolling(288, min_periods=12).std(),
        "slope_8": rolling_slope(v.to_numpy()),
    }).fillna(0)
    probation = int(len(df) * 0.15)                    # NAB convention: first 15 % = learning period
    model = IsolationForest(n_estimators=200, random_state=0).fit(X.iloc[:probation])
    s = -model.score_samples(X)
    flags = pd.Series(s > np.quantile(s[:probation], 0.995))
    flags = flags & flags.shift(1, fill_value=False)
    flags.iloc[:probation] = False
    in_window = pd.Series(False, index=df.index)
    caught = []
    for start, end in windows:
        w = (df["timestamp"] >= pd.Timestamp(start)) & (df["timestamp"] <= pd.Timestamp(end))
        in_window |= w
        caught.append(bool((flags & w).any()))
    false_runs = (flags & ~in_window) & ~(flags & ~in_window).shift(1, fill_value=False)
    days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[probation]).total_seconds() / 86400
    r = {"windows": len(windows), "caught": sum(caught), "false_alarms_per_day": false_runs.sum() / days}
    out(f"- **NAB machine temperature** (real industrial sensor, 5-min readings, {len(df):,} rows, 4 labelled "
        f"failure windows): Isolation Forest trained only on the first 15 % caught **{r['caught']}/{r['windows']}** "
        f"windows, with {r['false_alarms_per_day']:.2f} false alarms/day outside them.")
    return r


LBNL_COLS = ["Datetime", "FCU_CTRL", "RM_TEMP", "RMCLGSPT", "FCU_CVLV", "FCU_DAT", "FCU_SPD", "FCU_OAT",
             "FCU_DA_CFM", "FCU_RAT", "FCU_MAT"]
LBNL_FILES = {
    "fault_free": "FCU_FaultFree.csv",
    "cooling_valve_stuck_open": "FCU_VLVStuck_Cooling_100.csv",   # real-world twin of our "AC stuck on"
    "cooling_valve_leak": "FCU_VLVLeak_Cooling_50.csv",
    "filter_restriction": "FCU_FilterRestriction_50%.csv",
    "coil_fouling": "FCU_Fouling_Cooling_Airside_Severe.csv",
    "room_sensor_bias": "FCU_SensorBias_RMTemp_+2C.csv",
}


def lbnl():
    base = RAW / "lbnl_fcu"
    found = {k: next(base.rglob(f), None) for k, f in LBNL_FILES.items()} if base.exists() else {}
    if not found or None in found.values():
        out("- **LBNL FCU** data missing: run `python ml/download_datasets.py --lbnl`.")
        return {}
    frames = []
    for label, path in found.items():
        d = pd.read_csv(path, usecols=LBNL_COLS).iloc[::5]            # every 5th minute is plenty
        d["label"] = label
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df["t"] = pd.to_datetime(df["Datetime"], format="%m/%d/%Y %H:%M")
    df = df[df["FCU_CTRL"] > 0]                     # keep minutes when the unit is actually running
    feats = [c for c in LBNL_COLS if c not in ("Datetime",)] + ["dat_minus_rat", "rm_minus_spt"]
    df["dat_minus_rat"] = df["FCU_DAT"] - df["FCU_RAT"]
    df["rm_minus_spt"] = df["RM_TEMP"] - df["RMCLGSPT"]
    train, test = df[df["t"].dt.month <= 9], df[df["t"].dt.month >= 10]   # time split: Jan-Sep / Oct-Dec

    rf = RandomForestClassifier(n_estimators=200, max_depth=14, min_samples_leaf=3, n_jobs=-1,
                                class_weight="balanced", random_state=0).fit(train[feats], train["label"])
    pred = rf.predict(test[feats])
    macro = f1_score(test["label"], pred, average="macro")
    per = classification_report(test["label"], pred, output_dict=True, zero_division=0)

    normal = train[train["label"] == "fault_free"][feats]
    iso = IsolationForest(n_estimators=200, random_state=0, n_jobs=-1).fit(normal.sample(min(60000, len(normal)), random_state=0))
    thr = np.quantile(-iso.score_samples(normal), 0.995)
    rate = {k: float((-iso.score_samples(g[feats]) > thr).mean()) for k, g in test.groupby("label")}

    out(f"- **LBNL fan coil unit** (real labelled HVAC fault data, 6 classes, trained Jan-Sep, tested Oct-Dec, "
        f"{len(test):,} test rows): Random Forest macro F1 **{macro:.2f}**.")
    out("\n  | LBNL class | RF F1 | Isolation Forest flag rate |")
    out("  |---|---|---|")
    for k in LBNL_FILES:
        out(f"  | {k} | {per[k]['f1-score']:.2f} | {rate[k]:.1%} |")
    return {"macro_f1": macro, "per_class_f1": {k: per[k]["f1-score"] for k in LBNL_FILES}, "if_flag_rate": rate}


def uci():
    path = RAW / "uci_occupancy" / "datatraining.txt"
    if not path.exists():
        out("- UCI data missing: run `python ml/download_datasets.py`.")
        return {}
    real = pd.read_csv(path)                         # first column is a row id
    real_noise = real["Temperature"].diff().std()    # spread of minute-to-minute changes
    sim = load("test", "room")
    sim["step"] = sim.groupby("device_id")["temp_c"].diff()                 # diff BEFORE filtering rows
    sim["prev_hvac"] = sim.groupby("device_id")["hvac_on"].shift(1, fill_value=True)
    sim_noise = sim[(sim["label"] == "normal") & ~sim["hvac_on"] & ~sim["prev_hvac"].astype(bool)]["step"].std()
    ratio = sim_noise / real_noise
    verdict = ("within 2x of the real sensors, so the simulated rooms are realistic enough"
               if 0.5 <= ratio <= 2 else "NOT comparable: recalibrate simulator/room_sensor.py")
    out(f"- **UCI occupancy** (real office room sensors, 1-min readings): the minute-to-minute temperature change "
        f"has a spread (std) of {real_noise:.3f} °C in the real data vs {sim_noise:.3f} °C in our simulator "
        f"(AC off): {verdict}.")
    return {"real_median_step_c": float(real_noise), "sim_median_step_c": float(sim_noise)}


def main():
    out("# Evaluation report\n")
    out("Generated by `python ml/evaluate.py`. All numbers are on data the models did not train on.\n")
    results = {"synthetic": part_a()}
    out("\n## B. Real public datasets\n")
    results["nab"] = nab()
    results["lbnl"] = lbnl()
    results["uci"] = uci()
    (ML / "evaluation_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (ML / "models" / "evaluation.json").write_text(json.dumps(results, indent=2, default=float), encoding="utf-8")
    print("\nSaved ml/evaluation_report.md and ml/models/evaluation.json")


if __name__ == "__main__":
    main()
