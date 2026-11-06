"""Evidence: re-derive the hidden rules' numbers from history and backtest them. Fully offline.

    python -m stormtwin evidence      -> prints tables, writes data/derived/evidence.json

Two checks
----------
1. no_start, per truck-day. Most no-starts happened on ordinary mornings (~05:10), not on callout nights,
   so every truck x winter morning is a test case (event = ROAD_CALL/NO_START opened that day).
2. Backtest per callout: run the full classifier on each of the 11 callouts and compare with what happened
   (ROAD_CALL NO_START / HYDRAULIC_FAILURE on that date).

Caveat printed with the results: the thresholds were chosen on this same history, so this is in-sample
accuracy. The margins (closest ok vs closest failure) show how much room each threshold has.
"""

# =============================================================================
# Imports
# =============================================================================
import logging
from collections import Counter
from datetime import datetime, timedelta

from .history import load_history, load_raw, parse_local
from .load import write_json_atomic
from .night import night_conditions, weather_from_history
from .rules import assess_fleet, classify, truck_features

log = logging.getLogger("stormtwin.evidence")


# =============================================================================
# Ground truth from the shop's road calls
# =============================================================================
def actual_events(raw):
    """{(truck, 'YYYY-MM-DD'): 'no_start' | 'hydraulic'} from ROAD_CALL work orders."""
    reason_map = {"NO_START": "no_start", "HYDRAULIC_FAILURE": "hydraulic"}
    events = {}
    for w in raw["WorkOrder"]:
        label = reason_map.get(w.get("reason")) if w.get("type") == "ROAD_CALL" else None
        if label:
            events[(w["vehicleName"], w["openedLocal"][:10])] = label
    return events


# =============================================================================
# Check 1: no_start on every truck-morning
# =============================================================================
def check_no_start_daily(hist, weather, settings, events):
    rules, ncfg = settings["rules"], settings["night"]
    start_hour = int(settings["evidence"]["daily_start_hour"])
    months = tuple(settings["evidence"]["months"])
    counts = Counter()
    margins = {"fail_max_voltage": None, "fail_max_low": None, "ok_cold_min_voltage": None, "ok_lowvolt_min_low": None}
    rows = []

    days = sorted(d for d in weather.daily if d[:7] in months)
    for day in days:
        morning = datetime.strptime(day, "%Y-%m-%d").replace(hour=start_hour)
        cond = night_conditions(morning, weather, ncfg)
        if cond["night_low_c"] is None:
            continue
        for truck in hist.trucks:
            f = truck_features(hist, truck, morning, cond)
            if f["voltage_v"] is None or (morning - parse_local(f["voltage_at"])) > timedelta(hours=36):
                continue  # no fresh evening reading: not a valid test case
            pred = classify(f, rules)[0] == "no_start"
            actual = events.get((truck, day)) == "no_start"
            counts[("TP" if pred else "FN") if actual else ("FP" if pred else "TN")] += 1
            _update_margins(margins, f, actual, rules)
            if pred or actual:
                rows.append({"truck": truck, "morning": day, "voltage_v": f["voltage_v"],
                             "night_low_c": f["night_low_c"], "predicted": pred, "actual": actual})
    return {"counts": dict(counts), "margins": margins, "flagged_or_failed": rows}


def _update_margins(m, f, actual, rules):
    """Track the closest cases on each side of both thresholds."""
    ns = rules["no_start"]
    v, low = f["voltage_v"], f["night_low_c"]
    if actual:
        m["fail_max_voltage"] = max(v, m["fail_max_voltage"] or v)
        m["fail_max_low"] = max(low, m["fail_max_low"] if m["fail_max_low"] is not None else low)
    else:
        if low <= ns["night_low_max_c"]:
            m["ok_cold_min_voltage"] = min(v, m["ok_cold_min_voltage"] or v)
        if v < ns["max_voltage_v"]:
            m["ok_lowvolt_min_low"] = min(low, m["ok_lowvolt_min_low"] if m["ok_lowvolt_min_low"] is not None else low)


# =============================================================================
# Check 2: backtest every historical callout
# =============================================================================
def backtest_callouts(hist, weather, raw, settings, events):
    results, totals = [], Counter()
    for c in sorted(raw["Callout"], key=lambda c: c["calloutLocal"]):
        callout = parse_local(c["calloutLocal"])
        trucks = sorted({d["vehicleName"] for d in raw["DispatchAssignment"] if d["calloutId"] == c["id"]}
                        | {t for (t, d), _ in events.items() if d == c["date"]})
        cond = night_conditions(callout, weather, settings["night"])
        assessed = assess_fleet(hist, trucks, callout, cond, settings["rules"])
        night = Counter()
        mistakes = []
        for truck, a in assessed.items():
            actual = events.get((truck, c["date"]), "ok")
            hit = a["label"] == actual
            night["correct" if hit else "wrong"] += 1
            totals[(actual, a["label"])] += 1
            if not hit:
                mistakes.append({"truck": truck, "predicted": a["label"], "actual": actual, "reasons": a["reasons"]})
        results.append({"callout": c["calloutLocal"], "night_low_c": cond["night_low_c"], "snow_cm": cond["snow_cm"],
                        "trucks": len(trucks), **night,
                        "flagged": {t: a["label"] for t, a in assessed.items() if a["label"] != "ok"},
                        "mistakes": mistakes})
    confusion = {f"{actual}->{pred}": n for (actual, pred), n in sorted(totals.items())}
    return {"nights": results, "confusion_actual_to_predicted": confusion}


# =============================================================================
# Hydraulic margins (per callout truck)
# =============================================================================
def hydraulic_margins(hist, weather, raw, settings, events):
    """Closest ok vs closest failure on PTO-since-service, split by heavy / light snow nights."""
    hy = settings["rules"]["hydraulic"]
    fail_min, ok_heavy_max, ok_light_max = None, None, None
    for c in raw["Callout"]:
        callout = parse_local(c["calloutLocal"])
        cond = night_conditions(callout, weather, settings["night"])
        heavy = (cond["snow_cm"] or 0) >= hy["min_snow_cm"]
        for truck in {d["vehicleName"] for d in raw["DispatchAssignment"] if d["calloutId"] == c["id"]}:
            pto, _ = hist.pto_since_hyd_service(truck, callout)
            if pto is None:
                continue
            if events.get((truck, c["date"])) == "hydraulic":
                fail_min = pto if fail_min is None else min(fail_min, pto)
            elif heavy:
                ok_heavy_max = pto if ok_heavy_max is None else max(ok_heavy_max, pto)
            else:
                ok_light_max = pto if ok_light_max is None else max(ok_light_max, pto)
    return {"fail_min_pto_h": fail_min, "ok_heavy_snow_max_pto_h": ok_heavy_max, "ok_light_snow_max_pto_h": ok_light_max}


# =============================================================================
# Orchestration
# =============================================================================
def run_evidence(settings):
    raw = load_raw(settings)
    hist = load_history(settings, raw)
    weather = weather_from_history(settings)
    events = actual_events(raw)

    report = {
        "rules": settings["rules"],
        "in_sample_warning": "Thresholds were chosen on this history; this is in-sample accuracy.",
        "events_on_record": dict(Counter(events.values())),
        "no_start_daily": check_no_start_daily(hist, weather, settings, events),
        "hydraulic_margins": hydraulic_margins(hist, weather, raw, settings, events),
        "callout_backtest": backtest_callouts(hist, weather, raw, settings, events),
    }
    out = settings["data_path"] / settings["evidence"]["out_dir"] / "evidence.json"
    write_json_atomic(out, report)
    _print(report)
    log.info("Wrote %s", out)
    return report


def _print(r):
    ns = r["no_start_daily"]
    print(f"\nEvents on record: {r['events_on_record']}")
    print(f"\nRule 1 no_start, every truck-morning: {ns['counts']}")
    print(f"  margins: {ns['margins']}")
    print(f"\nRule 2 hydraulic margins (PTO h since service): {r['hydraulic_margins']}")
    print("\nCallout backtest:")
    for n in r["callout_backtest"]["nights"]:
        print(f"  {n['callout']}  low {n['night_low_c']!s:>6}  snow {n['snow_cm']!s:>5}  "
              f"correct {n.get('correct', 0):>2}/{n['trucks']}  flagged {n['flagged']}")
        for m in n["mistakes"]:
            print(f"      MISS {m['truck']}: predicted {m['predicted']}, actual {m['actual']}")
    print(f"  confusion (actual->predicted): {r['callout_backtest']['confusion_actual_to_predicted']}")
    print(f"\n{r['in_sample_warning']}\n")
