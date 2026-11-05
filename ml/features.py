"""Feature engineering shared by training, evaluation and the live AI engine (Phase 7).

Input: readings of ONE demo (any number of devices), sorted by time per device.
Output: one row of numeric features per reading, computed only from that device's
past readings (rolling windows), so the same code works live on the last ~60 readings.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CONFIG = Path(__file__).resolve().parent.parent / "config" / "devices.yaml"
with open(CONFIG, encoding="utf-8") as f:
    NORMAL_FLOW = {z["id"]: z["normal_flow_lpm"] for z in yaml.safe_load(f)["water_zones"]}

FEATURES = {
    "room": ["temp_c", "temp_minus_setpoint", "hvac_on", "occupied", "vacant_min", "hvac_on_30",
             "empty_cooling_30", "below_setpoint_run", "temp_slope_8", "hour_sin", "hour_cos"],
    "water": ["flow_ratio", "ratio_mean_10", "ratio_min_10", "ratio_std_10", "ratio_z_60", "leak_wet",
              "hour_sin", "hour_cos"],
    "cold": ["band_pos", "temp_slope_8", "temp_std_10", "door_open", "door_open_10", "door_run",
             "above_cycle_run"],
}


def rolling_slope(values, window=8):
    """Least-squares slope (units per minute) over the last `window` readings.

    For x = 0..w-1 the slope is a fixed weighted sum of the y values, so we can
    compute it for every row at once with a convolution. NaN for the first rows.
    """
    y = np.asarray(values, dtype=float)
    x = np.arange(window) - (window - 1) / 2
    w = x / (x ** 2).sum()
    out = np.full(len(y), np.nan)
    if len(y) >= window:
        out[window - 1:] = np.convolve(y, w[::-1], mode="valid")
    return out


def run_length(flags):
    """How many readings in a row (up to and including this one) the flag has been true."""
    flags = np.asarray(flags, dtype=bool)
    out = np.zeros(len(flags))
    run = 0
    for i, f in enumerate(flags):
        run = run + 1 if f else 0
        out[i] = run
    return out


def _hour(df, out):
    ts = pd.to_datetime(df["ts"].str.slice(0, 19))        # hotel-local time, offset dropped
    hour = ts.dt.hour + ts.dt.minute / 60
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)


def _room(d):
    out = pd.DataFrame(index=d.index)
    out["temp_c"] = d["temp_c"]
    out["temp_minus_setpoint"] = d["temp_c"] - d["setpoint_c"]
    out["hvac_on"] = d["hvac_on"].astype(int)
    out["occupied"] = d["occupied"].astype(int)
    out["vacant_min"] = d["vacant_min"].clip(upper=240)
    out["hvac_on_30"] = out["hvac_on"].rolling(30, min_periods=1).mean()
    out["empty_cooling_30"] = ((1 - out["occupied"]) * out["hvac_on"]).rolling(30, min_periods=1).mean()
    # A working thermostat switches cooling off 0.5 °C below setpoint; still cooling below that = stuck
    below = d["hvac_on"].astype(bool) & (out["temp_minus_setpoint"] < -0.6)
    out["below_setpoint_run"] = np.minimum(run_length(below), 60)
    out["temp_slope_8"] = rolling_slope(d["temp_c"])
    _hour(d, out)
    return out


def _water(d):
    out = pd.DataFrame(index=d.index)
    ratio = d["flow_lpm"] / d["zone"].map(NORMAL_FLOW)
    out["flow_ratio"] = ratio
    out["ratio_mean_10"] = ratio.rolling(10, min_periods=1).mean()
    out["ratio_min_10"] = ratio.rolling(10, min_periods=1).min()     # a leak lifts the floor of the flow
    out["ratio_std_10"] = ratio.rolling(10, min_periods=2).std()
    mean60, std60 = ratio.rolling(60, min_periods=10).mean(), ratio.rolling(60, min_periods=10).std()
    out["ratio_z_60"] = (ratio - mean60) / std60.replace(0, np.nan)
    out["leak_wet"] = d["leak_wet"].astype(int)
    _hour(d, out)
    return out


def _cold(d):
    out = pd.DataFrame(index=d.index)
    width = d["safe_max_c"] - d["safe_min_c"]
    out["band_pos"] = (d["temp_c"] - d["safe_min_c"]) / width      # 0 = bottom of safe band, 1 = top
    out["temp_slope_8"] = rolling_slope(d["temp_c"])
    out["temp_std_10"] = d["temp_c"].rolling(10, min_periods=2).std()
    out["door_open"] = d["door_open"].astype(int)
    out["door_open_10"] = out["door_open"].rolling(10, min_periods=1).mean()
    out["door_run"] = np.minimum(run_length(d["door_open"]), 60)
    # normal compressor cycling keeps the unit in the middle 40 % of the band
    out["above_cycle_run"] = np.minimum(run_length(out["band_pos"] > 0.72), 60)
    return out


BUILDERS = {"room": _room, "water": _water, "cold": _cold}


def build_features(df, demo):
    """Feature frame (same index as df) for one demo; NaNs from warm-up windows filled with 0."""
    parts = [BUILDERS[demo](d) for _, d in df.groupby("device_id", sort=False)]
    feats = pd.concat(parts).reindex(df.index)
    return feats[FEATURES[demo]].fillna(0.0)
