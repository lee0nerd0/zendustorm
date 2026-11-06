"""Night conditions: the weather numbers the rules need for one callout.

    night_low_c : coldest hourly temperature from `window_start_hour` the evening before the callout
                  morning to `window_end_hour` that morning (fit on history: 18:00 -> 08:00).
    snow_cm     : snowfall on the callout date (daily total).

Weather can come from two places with different shapes:
  * our committed Environment Canada files (data/weather/hourly.json, daily.json), and
  * the `weather` block of the judges' replay input, whose exact shape is not published.
So the parser accepts row-wise lists ([{"time": ..., "temp": ...}]) and column-wise blocks
({"time": [...], "temperature_2m": [...]}) with a range of common key names.
"""

# =============================================================================
# Imports
# =============================================================================
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .history import parse_local

log = logging.getLogger("stormtwin.night")

# =============================================================================
# Constants: accepted key names (first match wins)
# =============================================================================
TIME_KEYS = ("datetime_local", "time", "datetime", "dateTime", "timestamp", "local", "date")
TEMP_KEYS = ("temp_c", "temperature_c", "temperature", "temp", "temperature_2m", "air_temp_c")
DAY_KEYS = ("date", "day", "time")
DAY_MIN_KEYS = ("min_c", "temp_min_c", "min_temp_c", "temperature_min", "tmin", "temperature_2m_min", "low_c")
SNOW_KEYS = ("snow_cm", "snowfall_cm", "total_snow_cm", "snowfall", "snow", "snowfall_sum", "new_snow_cm")


# =============================================================================
# Normalising weather blocks
# =============================================================================
class Weather:
    """Hourly temps keyed by 'YYYY-MM-DD HH' and daily records keyed by 'YYYY-MM-DD'."""

    def __init__(self, hourly_rows=(), daily_rows=()):
        self.hourly = {}
        for r in hourly_rows:
            t, temp = _first(r, TIME_KEYS), _num(_first(r, TEMP_KEYS))
            if t and temp is not None:
                self.hourly[_hour_key(t)] = temp
        self.daily = {}
        for r in daily_rows:
            d = _first(r, DAY_KEYS)
            if d:
                self.daily[str(d)[:10]] = {"min_c": _num(_first(r, DAY_MIN_KEYS)), "snow_cm": _num(_first(r, SNOW_KEYS))}

    def merged_with(self, other):
        """Return a copy where `other` (e.g. replay input) overrides self (e.g. history)."""
        w = Weather()
        w.hourly = {**self.hourly, **other.hourly}
        w.daily = {**self.daily, **other.daily}
        return w


def weather_from_block(block):
    """Build Weather from a replay input's `weather` block ({"hourly": ..., "daily": ...})."""
    block = block or {}
    return Weather(_rows(block.get("hourly")), _rows(block.get("daily")))


def weather_from_history(settings):
    """Build Weather from the committed Environment Canada files."""
    wdir = Path(settings["data_path"]) / settings["weather"]["dir"]
    try:
        hourly = json.loads((wdir / "hourly.json").read_text(encoding="utf-8"))
        daily = json.loads((wdir / "daily.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.warning("No committed weather in %s; run `python -m stormtwin weather`", wdir)
        return Weather()
    return Weather(hourly, daily)


def _rows(value):
    """Row-wise list -> as is; column-wise dict of equal-length lists -> list of dicts; dict keyed by time -> rows."""
    if isinstance(value, list):
        return [r for r in value if isinstance(r, dict)]
    if isinstance(value, dict):
        lists = {k: v for k, v in value.items() if isinstance(v, list)}
        if lists:
            n = min(len(v) for v in lists.values())
            return [{k: v[i] for k, v in lists.items()} for i in range(n)]
        if all(isinstance(v, dict) for v in value.values()):  # {"2026-01-15T00:00": {...}}
            return [{"time": k, **v} for k, v in value.items()]
    return []


def _first(row, keys):
    for k in keys:
        if row.get(k) not in (None, ""):
            return row[k]
    return None


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _hour_key(stamp):
    """Accept '2026-01-15 03:00', '2026-01-15T03:00', '2026-01-15T03:00:00' -> '2026-01-15 03'."""
    s = str(stamp).replace("T", " ")
    return s[:13]


# =============================================================================
# Night conditions
# =============================================================================
def morning_of(callout):
    """The morning the trucks must start: same day for a callout before noon, else the next day."""
    return callout.date() if callout.hour < 12 else callout.date() + timedelta(days=1)


def night_conditions(callout_local, weather, cfg):
    """Return {"night_low_c", "snow_cm", "low_source"} for one callout (strings or datetimes accepted)."""
    callout = parse_local(callout_local) if isinstance(callout_local, str) else callout_local
    morning = datetime.combine(morning_of(callout), datetime.min.time())
    start = morning - timedelta(hours=24 - int(cfg["night_window_start_hour"]))
    end = morning + timedelta(hours=int(cfg["night_window_end_hour"]))

    temps, t = [], start
    while t < end:
        v = weather.hourly.get(t.strftime("%Y-%m-%d %H"))
        if v is not None:
            temps.append(v)
        t += timedelta(hours=1)

    day = weather.daily.get(morning.strftime("%Y-%m-%d"), {})
    if len(temps) >= int(cfg["min_hours_for_hourly_low"]):
        low, source = min(temps), f"hourly ({len(temps)} h)"
    elif day.get("min_c") is not None:
        low, source = day["min_c"], "daily min (hourly missing)"
    else:
        low, source = None, "missing"

    snow = weather.daily.get(callout.strftime("%Y-%m-%d"), {}).get("snow_cm")
    return {"night_low_c": low, "snow_cm": snow, "low_source": source}
