"""Layer 3: trend forecast. "This fridge will leave its safe band in ~N minutes."

Fit a straight line through the last 8 readings; if the line is heading out of the
band, the time to reach the edge is (distance to edge) / slope. This warns BEFORE the
breach.

Normal operation also has rising stretches (compressor off, door opened), so we only warn when:
  - the unit is in the outer 20 % of its band (normal cycling stays inside 25-75 %),
  - temperature has risen at every one of the last 4 readings (a steady trend, not noise),
  - the door has been closed for the last 3 readings (a door bump is not a failure),
  - and the predicted breach is within 30 minutes.

  python ml/forecast.py      # quick self-check
"""
import numpy as np

from features import rolling_slope

WINDOW = 8          # readings (= minutes) used for the trend line
HORIZON_MIN = 30    # warn if the breach is predicted within this many minutes
EDGE = 0.80         # band position (0 = bottom, 1 = top) beyond which normal cycling never goes
RISING = 4          # readings in a row that must move toward the edge


def minutes_to_breach(temp, slope, safe_min, safe_max):
    """Minutes until the trend line leaves [safe_min, safe_max]; 0 if already out; None if not heading out."""
    if not safe_min <= temp <= safe_max:
        return 0.0
    if slope > 1e-6:
        return (safe_max - temp) / slope
    if slope < -1e-6:
        return (temp - safe_min) / -slope
    return None


def _should_warn(temps, doors, slope, safe_min, safe_max):
    temp = temps[-1]
    eta = minutes_to_breach(temp, slope, safe_min, safe_max)
    if eta is None or not 0 < eta <= HORIZON_MIN or any(doors[-3:]):
        return False, eta
    pos = (temp - safe_min) / (safe_max - safe_min)
    steps = np.diff(temps[-(RISING + 1):])
    heading_up = pos > EDGE and slope > 0 and (steps > 0).all()
    heading_down = pos < 1 - EDGE and slope < 0 and (steps < 0).all()
    return heading_up or heading_down, eta


def forecast(temps, doors, safe_min, safe_max):
    """For the live engine: last readings (oldest first) -> (warn, minutes_to_breach or None)."""
    if len(temps) < WINDOW:
        return False, None
    temps = np.asarray(temps, dtype=float)
    slope = rolling_slope(temps[-WINDOW:], WINDOW)[-1]
    warn, eta = _should_warn(temps, list(doors), slope, safe_min, safe_max)
    return warn, (None if eta is None else round(eta, 1))


def forecast_flags(df):
    """Same rule for every reading of one device's time-sorted cold-chain frame (for evaluation)."""
    temps = df["temp_c"].to_numpy(dtype=float)
    doors = df["door_open"].to_numpy(dtype=bool)
    slope = rolling_slope(temps, WINDOW)
    lo, hi = df["safe_min_c"].to_numpy(), df["safe_max_c"].to_numpy()
    flags = np.zeros(len(df), dtype=bool)
    for i in range(WINDOW - 1, len(df)):
        flags[i] = _should_warn(temps[: i + 1], doors[: i + 1], slope[i], lo[i], hi[i])[0]
    return flags


if __name__ == "__main__":
    closed = [False] * 8
    # walk-in chiller (0-5 °C) warming 0.1 °C/min, now at 4.1 °C -> breach in ~9 min
    warn, eta = forecast([3.4 + 0.1 * i for i in range(8)], closed, 0, 5)
    assert warn and 8 <= eta <= 10, (warn, eta)
    # normal cycling around the middle of the band: no warning
    assert not forecast([2.0 + 0.1 * i for i in range(8)], closed, 0, 5)[0]
    # same rise but the door was just opened: no warning
    assert not forecast([3.3 + 0.1 * i for i in range(8)], closed[:-1] + [True], 0, 5)[0]
    print(f"ok: rising walk-in -> warn, breach in {eta} min")
