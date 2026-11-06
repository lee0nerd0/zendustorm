"""Replay step: turn the judges' maintenance input file into a prediction file, offline and deterministically.

Contract (REPLAY_FORMAT.md, maintenance persona)
-----------------------------------------------
    input : {"night", "callout_local", "weather", "trucks", "records_since_your_data_ends": {StatusData, FaultData, WorkOrder}}
    output: {"persona": "maintenance", "trucks": {"T-101": "ok" | "no_start" | "hydraulic", ...}}

Pipeline
--------
    raw   = read input JSON
    night = parse_input(raw)                  # tolerant of field-shape variations, fails loudly if unusable
    preds = predict(night, settings)          # one label per truck via the hidden rules
    write {"persona": "maintenance", "trucks": preds} with sorted keys (byte-identical re-runs)

Reproducibility rules
---------------------
* No network, no clock, no randomness. Same input + same committed data/ -> same bytes out.
* Every truck in the input gets exactly one valid label, even if a predictor misbehaves (falls back to "ok").
"""

# =============================================================================
# Imports
# =============================================================================
import json
import logging
from collections import Counter
from pathlib import Path

from .history import load_history, parse_local
from .night import night_conditions, weather_from_block, weather_from_history
from .rules import assess_fleet

log = logging.getLogger("stormtwin.replay")

# =============================================================================
# Constants
# =============================================================================
PERSONA = "maintenance"
LABELS = ("ok", "no_start", "hydraulic")
DEFAULT_LABEL = "ok"  # safest label: false alarms cost points
RECORD_TYPES = ("StatusData", "FaultData", "WorkOrder")


# =============================================================================
# Errors
# =============================================================================
class ReplayError(Exception):
    """The input file cannot be turned into a valid output."""


# =============================================================================
# Input parsing
# =============================================================================
def parse_input(raw, settings):
    """Normalise the replay input into a dict the predictors can rely on.

    Returns {"night", "callout_local", "weather", "trucks": [sorted names], "records": {type: [rows]}}.
    """
    if not isinstance(raw, dict):
        raise ReplayError("Input must be a JSON object")

    trucks = _truck_names(raw.get("trucks"))
    if not trucks:
        # The spec says every truck is listed; if not, fall back to the fleet roster so we still emit a full answer.
        trucks = _fleet_roster(settings)
        log.warning("Input has no usable 'trucks'; falling back to the %d trucks in data/raw/Vehicle.json", len(trucks))

    records_in = raw.get("records_since_your_data_ends") or {}
    records = {t: list(records_in.get(t) or []) for t in RECORD_TYPES}

    return {
        "night": raw.get("night"),
        "callout_local": raw.get("callout_local"),
        "weather": raw.get("weather") or {},
        "trucks": trucks,
        "records": records,
    }


def _truck_names(value):
    """Accept the truck list in any reasonable shape: ["T-101"], [{"name"|"truck"|"id"|"vehicleName": ...}], or {"T-101": {...}}."""
    if isinstance(value, dict):
        names = list(value.keys())
    elif isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                name = next((item[k] for k in ("name", "truck", "vehicleName", "id") if item.get(k)), None)
                if name:
                    names.append(name)
    else:
        names = []
    return sorted(set(names))


def _fleet_roster(settings):
    path = Path(settings["raw_path"]) / "Vehicle.json"
    try:
        return sorted(v["name"] for v in json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        raise ReplayError(f"No trucks in input and cannot read fleet roster at {path}: {exc}") from exc


# =============================================================================
# Prediction
# =============================================================================
def predict(night, settings):
    """Return {truck: label} by applying the hidden rules (stormtwin/rules.py) to this night.

    History (data/raw) is extended with the input's day-before records; committed weather is
    overridden by the input's weather block where both cover the same hours/days.
    """
    assessed = assess_night(night, settings)
    for truck, a in sorted(assessed.items()):
        if a["label"] != DEFAULT_LABEL:
            log.info("  %s -> %s: %s", truck, a["label"], "; ".join(a["reasons"]))
    return {truck: a["label"] for truck, a in assessed.items()}


def assess_night(night, settings):
    """Full per-truck assessment (label, reasons, features). Shared with the what-if command."""
    callout = _callout_time(night)
    hist = load_history(settings)
    hist.add_records(night["records"])
    weather = weather_from_history(settings).merged_with(weather_from_block(night["weather"]))
    cond = night_conditions(callout, weather, settings["night"])
    log.info("Night conditions at %s: low %s °C (%s), snow %s cm",
             callout, cond["night_low_c"], cond["low_source"], cond["snow_cm"])
    return assess_fleet(hist, night["trucks"], callout, cond, settings["rules"])


def _callout_time(night):
    """callout_local if present, else midnight of `night` (logged, since the window depends on it)."""
    if night.get("callout_local"):
        return parse_local(night["callout_local"])
    if night.get("night"):
        log.warning("No callout_local in input; assuming %sT00:00:00", night["night"])
        return parse_local(f"{str(night['night'])[:10]}T00:00:00")
    raise ReplayError("Input has neither callout_local nor night")


def sanitize(preds, trucks):
    """Guarantee exactly one valid label per input truck; repair anything else to the default."""
    clean = {}
    for truck in trucks:
        label = preds.get(truck, DEFAULT_LABEL)
        if label not in LABELS:
            log.warning("%s: invalid label %r, using %r", truck, label, DEFAULT_LABEL)
            label = DEFAULT_LABEL
        clean[truck] = label
    extra = sorted(set(preds) - set(trucks))
    if extra:
        log.warning("Dropping predictions for trucks not in the input: %s", ", ".join(extra))
    return clean


# =============================================================================
# Orchestration
# =============================================================================
def run_replay(input_path, output_path, settings):
    """Read input, predict, write output. Returns the output dict."""
    try:
        raw = json.loads(Path(input_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReplayError(f"Input file not found: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise ReplayError(f"Input file is not valid JSON: {input_path}: {exc}") from exc

    night = parse_input(raw, settings)
    log.info("Night %s, callout %s, %d trucks, new records: %s", night["night"], night["callout_local"],
             len(night["trucks"]), {t: len(r) for t, r in night["records"].items()})

    preds = sanitize(predict(night, settings), night["trucks"])
    out = {"persona": PERSONA, "trucks": preds}

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    log.info("Wrote %s: %s", output_path, dict(sorted(Counter(preds.values()).items())))
    return out
