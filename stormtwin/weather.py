"""Weather step: download last winter's (and this season's) observed weather into data/weather/.

The fleet API has no weather, so we pull Environment Canada historical climate data (free, no key)
for one station near both yards (Toronto Pearson, configured in settings["weather"]).

Pipeline
--------
    daily : one CSV per year  (timeframe=2) -> keep configured months -> data/weather/daily.json
    hourly: one CSV per month (timeframe=1)                          -> data/weather/hourly.json
    nights: for every Callout, summarise the hours around the callout -> data/weather/callout_nights.json
    raw CSVs are kept in data/weather/raw/ as evidence.

Notes
-----
* Hourly times are Local Standard Time (LST). Dec-Jan has no daylight saving, so LST == America/Toronto
  local time, which matches the township's local-time fields (Callout.calloutLocal).
* Empty cells become None. Nothing is interpolated here; that is a modelling decision for later.
"""

# =============================================================================
# Imports
# =============================================================================
import csv
import io
import json
import logging
import urllib.parse
from datetime import datetime, timedelta

from .load import LoadError, http_get_bytes, write_json_atomic

log = logging.getLogger("stormtwin.weather")

# =============================================================================
# Constants: CSV column -> our field name
# =============================================================================
DAILY_COLUMNS = {
    "Date/Time": "date",
    "Max Temp (°C)": "max_c",
    "Min Temp (°C)": "min_c",
    "Mean Temp (°C)": "mean_c",
    "Total Snow (cm)": "snow_cm",
    "Total Precip (mm)": "precip_mm",
    "Snow on Grnd (cm)": "snow_on_ground_cm",
    "Spd of Max Gust (km/h)": "max_gust_kmh",
}
HOURLY_COLUMNS = {
    "Date/Time (LST)": "datetime_local",
    "Temp (°C)": "temp_c",
    "Dew Point Temp (°C)": "dew_point_c",
    "Precip. Amount (mm)": "precip_mm",
    "Wind Spd (km/h)": "wind_kmh",
    "Visibility (km)": "visibility_km",
    "Wind Chill": "wind_chill",
    "Weather": "weather",
}
TEXT_FIELDS = {"date", "datetime_local", "weather"}

TIMEFRAME_HOURLY = 1
TIMEFRAME_DAILY = 2


# =============================================================================
# Download
# =============================================================================
def bulk_url(cfg, year, month, timeframe):
    """Environment Canada bulk-data URL for one station / period."""
    params = {"format": "csv", "stationID": cfg["station_id"], "Year": year, "Month": month, "Day": 1,
              "timeframe": timeframe, "submit": "Download Data"}
    return f"{cfg['base_url']}?{urllib.parse.urlencode(params)}"


def download_csv(url, settings, raw_file):
    """Fetch one CSV, save the raw copy, return parsed rows (list of dicts)."""
    body = http_get_bytes(url, {"Accept": "text/csv"}, settings)
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_bytes(body)
    text = body.decode("utf-8-sig")  # files start with a BOM
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise LoadError(f"Empty weather CSV from {url}")
    return rows


# =============================================================================
# Parsing
# =============================================================================
def normalise(rows, columns):
    """Rename columns, convert numbers, turn empty cells into None."""
    out = []
    for row in rows:
        rec = {}
        for src, dst in columns.items():
            value = (row.get(src) or "").strip()
            if dst in TEXT_FIELDS:
                rec[dst] = value or None
            else:
                rec[dst] = _to_float(value)
        out.append(rec)
    return out


def _to_float(value):
    try:
        return float(value) if value not in ("", "NA") else None
    except ValueError:
        return None


def _month_key(stamp):
    """'2025-12-03' or '2025-12-03 04:00' -> '2025-12'."""
    return stamp[:7] if stamp else None


# =============================================================================
# Callout-night summaries
# =============================================================================
def summarise_callouts(callouts, hourly, daily, cfg):
    """For each callout, summarise the weather in the hours before and after it.

    Fields (all from hourly obs unless noted):
      min_temp_before_c    coldest hour in the `hours_before` window (overnight cold soak before trucks start)
      min_temp_window_c    coldest hour in [callout - hours_before, callout + hours_after]
      max_wind_window_kmh  strongest hourly wind in that window
      precip_window_mm     summed hourly precipitation in that window
      hours_with_data      how many hourly rows had a temperature (data-quality check)
      daily_snow_cm        Total Snow on the callout date (daily obs)
    """
    by_time = {h["datetime_local"]: h for h in hourly if h["datetime_local"]}
    by_date = {d["date"]: d for d in daily}
    before, after = int(cfg["hours_before_callout"]), int(cfg["hours_after_callout"])

    out = []
    for c in sorted(callouts, key=lambda c: c["calloutLocal"]):
        t0 = datetime.strptime(c["calloutLocal"], "%Y-%m-%dT%H:%M:%S")
        hours_before = _hours(by_time, t0 - timedelta(hours=before), t0)
        hours_all = _hours(by_time, t0 - timedelta(hours=before), t0 + timedelta(hours=after))
        out.append({
            "calloutId": c["id"],
            "calloutLocal": c["calloutLocal"],
            "min_temp_before_c": _min(hours_before, "temp_c"),
            "min_temp_window_c": _min(hours_all, "temp_c"),
            "max_wind_window_kmh": _max(hours_all, "wind_kmh"),
            "precip_window_mm": round(sum(h["precip_mm"] or 0 for h in hours_all), 1),
            "hours_with_data": sum(1 for h in hours_all if h["temp_c"] is not None),
            "daily_snow_cm": (by_date.get(c["calloutLocal"][:10]) or {}).get("snow_cm"),
        })
    return out


def _hours(by_time, start, end):
    """Hourly rows with start <= t < end."""
    rows, t = [], start.replace(minute=0, second=0)
    while t < end:
        row = by_time.get(t.strftime("%Y-%m-%d %H:%M"))
        if row:
            rows.append(row)
        t += timedelta(hours=1)
    return rows


def _min(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return min(vals) if vals else None


def _max(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return max(vals) if vals else None


# =============================================================================
# Orchestration
# =============================================================================
def run_weather(settings):
    """Download daily + hourly weather, write normalised JSON and callout-night summaries."""
    cfg = settings["weather"]
    months = sorted(cfg["months"])  # "YYYY-MM"
    out_dir = settings["data_path"] / cfg["dir"]
    raw_dir = out_dir / "raw"
    log.info("Weather: station %s (%s), months %s", cfg["station_name"], cfg["climate_id"], ", ".join(months))

    # --- 1. Daily: one request per year, then keep only configured months ----
    daily = []
    for year in sorted({m[:4] for m in months}):
        rows = download_csv(bulk_url(cfg, year, 1, TIMEFRAME_DAILY), settings, raw_dir / f"daily_{year}.csv")
        daily += [d for d in normalise(rows, DAILY_COLUMNS) if _month_key(d["date"]) in months]

    # --- 2. Hourly: one request per month ------------------------------------
    hourly = []
    for month in months:
        year, mon = month.split("-")
        rows = download_csv(bulk_url(cfg, year, int(mon), TIMEFRAME_HOURLY), settings, raw_dir / f"hourly_{month}.csv")
        hourly += normalise(rows, HOURLY_COLUMNS)

    # --- 3. Callout-night summaries (needs data/raw/Callout.json from `load`) --
    callouts_path = settings["raw_path"] / "Callout.json"
    try:
        callouts = json.loads(callouts_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LoadError(f"{callouts_path} missing: run `python -m stormtwin load` first") from exc
    nights = summarise_callouts(callouts, hourly, daily, cfg)

    # --- 4. Write --------------------------------------------------------------
    write_json_atomic(out_dir / "daily.json", daily)
    write_json_atomic(out_dir / "hourly.json", hourly)
    write_json_atomic(out_dir / "callout_nights.json", nights)

    missing = [n["calloutId"] for n in nights if n["hours_with_data"] == 0]
    if missing:
        log.warning("No hourly weather for callouts: %s", ", ".join(missing))
    log.info("Wrote %d daily, %d hourly rows and %d callout nights to %s", len(daily), len(hourly), len(nights), out_dir)
    for n in nights:
        log.info("  %s  low before %5s °C  window low %5s °C  snow %s cm",
                 n["calloutLocal"], n["min_temp_before_c"], n["min_temp_window_c"], n["daily_snow_cm"])
    return nights
